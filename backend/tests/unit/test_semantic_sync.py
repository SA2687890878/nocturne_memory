import sqlite3

import pytest

from backend import semantic_sync
from backend.vector_index import VectorIndex


def make_source(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE nodes (uuid TEXT PRIMARY KEY, lifecycle_status TEXT);
        CREATE TABLE memories (id INTEGER PRIMARY KEY, node_uuid TEXT, deprecated INTEGER, content TEXT, summary_content TEXT);
        CREATE TABLE search_documents (memory_id INTEGER, uri TEXT, namespace TEXT, domain TEXT, path TEXT, summary_content TEXT, search_terms TEXT, content TEXT, node_uuid TEXT);
    """)
    con.execute("INSERT INTO nodes VALUES ('n1','active')")
    con.execute("INSERT INTO memories VALUES (1,'n1',0,'body one','summary one')")
    con.execute("INSERT INTO search_documents VALUES (1,'core://one','personal','core','one','summary one','keyword','body one','n1')")
    con.commit(); con.close()


@pytest.mark.asyncio
async def test_configured_semantic_sync_is_incremental_and_uses_sidecar(monkeypatch, tmp_path):
    source = tmp_path / "work-memory.db"
    make_source(source)
    settings = {"database_url": f"sqlite+aiosqlite:///{source.as_posix()}",
                "embedding": {"model": "test-model", "document_input_type": "passage"}}
    monkeypatch.setattr(semantic_sync.config, "get", lambda key: settings[key])
    calls = []
    async def fake_embed(texts, *, input_type):
        calls.append((list(texts), input_type))
        return [[1.0] + [0.0] * (semantic_sync.DIMENSIONS - 1) for _ in texts]
    monkeypatch.setattr(semantic_sync, "embed_texts", fake_embed)

    first = await semantic_sync.sync_configured_vector_index()
    assert first["upserted"] == 1 and first["index_health"]["vector_count"] == 1
    second = await semantic_sync.sync_configured_vector_index()
    assert second["upserted"] == 0 and second["unchanged"] == 1
    assert len(calls) == 1
    target = tmp_path / "work-memory-vectors.db"
    with VectorIndex(target, dimensions=semantic_sync.DIMENSIONS, model_name="test-model",
                     document_format_version=semantic_sync.DOCUMENT_FORMAT_VERSION, read_only=True) as index:
        assert index.health_check()["metadata_count"] == 1
        assert list(index.list_documents()) == ["core://one"]


@pytest.mark.asyncio
async def test_vector_sync_updates_and_deletes_stale_documents(tmp_path):
    from backend.vector_index_sync import sync_vector_index

    target = tmp_path / "vectors.db"
    dims = 8
    def doc(uri, text, memory_id):
        return {"uri": uri, "text": text, "memory_id": memory_id,
                "namespace": "personal", "domain": "core", "path": uri,
                "lifecycle_status": "active"}

    calls = []
    async def embed(texts):
        calls.extend(texts)
        return [[float(i + 1)] + [0.0] * (dims - 1) for i, _ in enumerate(texts)]

    with VectorIndex(target, dimensions=dims, model_name="test-model") as index:
        first = await sync_vector_index(index, [doc("core://one", "body one", 1)], embed)
        assert first["upserted"] == 1 and first["deleted"] == 0

        changed = await sync_vector_index(index, [
            doc("core://one", "body one revised", 1),
            doc("core://two", "body two", 2),
        ], embed)
        assert changed["upserted"] == 2 and changed["deleted"] == 0
        assert changed["integrity_ok"] is True
        assert set(index.list_documents()) == {"core://one", "core://two"}

        removed = await sync_vector_index(index, [doc("core://two", "body two", 2)], embed)
        assert removed["upserted"] == 0 and removed["deleted"] == 1
        assert removed["unchanged"] == 1
        assert list(index.list_documents()) == ["core://two"]
        assert index.health_check()["metadata_count"] == index.health_check()["vector_count"] == 1

    assert calls == ["body one", "body one revised", "body two"]


@pytest.mark.asyncio
async def test_vector_sync_embedding_failure_preserves_previous_index(tmp_path):
    from backend.vector_index_sync import sync_vector_index

    target = tmp_path / "vectors.db"
    dims = 8
    old = {"uri": "core://stable", "text": "old body", "memory_id": 1,
           "namespace": "personal", "domain": "core", "path": "stable",
           "lifecycle_status": "active"}
    with VectorIndex(target, dimensions=dims, model_name="test-model") as index:
        async def good_embed(texts):
            return [[1.0] + [0.0] * (dims - 1) for _ in texts]
        await sync_vector_index(index, [old], good_embed)
        before = index.list_documents()

        async def failing_embed(texts):
            raise RuntimeError("simulated embedding outage")

        revised = dict(old, text="new body")
        with pytest.raises(RuntimeError, match="simulated embedding outage"):
            await sync_vector_index(index, [revised], failing_embed)

        after = index.list_documents()
        assert after == before
        assert index.health_check()["metadata_count"] == index.health_check()["vector_count"] == 1
