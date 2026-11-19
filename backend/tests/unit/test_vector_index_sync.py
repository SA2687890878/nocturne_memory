import pytest

from backend.vector_index import VectorIndex
from backend.vector_index_sync import sync_vector_index

DIMS = 8

def doc(uri, text, **extra):
    return {"memory_id": 1, "uri": uri, "text": text, "namespace": "n", "domain": "d",
            "path": "/p", "lifecycle_status": "active", **extra}

@pytest.mark.asyncio
async def test_sync_incremental_add_update_delete_and_noop(tmp_path):
    calls = []
    async def embed(texts):
        calls.append(list(texts))
        return [[1.0] + [0.0] * 7 for _ in texts]
    with VectorIndex(tmp_path / "sync.db", dimensions=DIMS, model_name="m") as index:
        first = await sync_vector_index(index, [doc("u1", "one"), doc("u2", "two")], embed)
        assert first["upserted"] == 2
        second = await sync_vector_index(index, [doc("u1", "one"), doc("u2", "changed"), doc("u3", "three")], embed)
        assert second["upserted"] == 2 and second["deleted"] == 0
        third = await sync_vector_index(index, [doc("u1", "one"), doc("u3", "three")], embed)
        assert third["deleted"] == 1 and third["upserted"] == 0
        noop = await sync_vector_index(index, [doc("u1", "one"), doc("u3", "three")], embed)
        assert noop["unchanged"] == 2
        assert len(calls) == 2
        assert set(index.list_documents()) == {"u1", "u3"}

@pytest.mark.asyncio
async def test_sync_embedding_failure_preserves_old_index(tmp_path):
    async def good(texts): return [[1.0] + [0.0] * 7 for _ in texts]
    async def bad(texts): raise RuntimeError("API unavailable")
    with VectorIndex(tmp_path / "failure.db", dimensions=DIMS, model_name="m") as index:
        await sync_vector_index(index, [doc("old", "old")], good)
        before = index.list_documents()
        with pytest.raises(RuntimeError, match="API unavailable"):
            await sync_vector_index(index, [doc("new", "new")], bad)
        assert index.list_documents() == before

@pytest.mark.asyncio
async def test_sync_metadata_change_triggers_reembedding(tmp_path):
    calls = []
    async def embed(texts):
        calls.append(texts)
        return [[1.0] + [0.0] * 7 for _ in texts]
    with VectorIndex(tmp_path / "meta.db", dimensions=DIMS, model_name="m") as index:
        await sync_vector_index(index, [doc("u", "same", lifecycle_status="active")], embed)
        result = await sync_vector_index(index, [doc("u", "same", lifecycle_status="completed")], embed)
        assert result["upserted"] == 1
        assert len(calls) == 2
        assert index.list_documents()["u"]["lifecycle_status"] == "completed"
