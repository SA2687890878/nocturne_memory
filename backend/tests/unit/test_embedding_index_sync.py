import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "experiments" / "nvidia_embedding_incremental_sync.py"
SPEC = importlib.util.spec_from_file_location("nvidia_embedding_incremental_sync", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_document_text_uses_real_line_breaks():
    row = {
        "uri": "memory://a", "path": "a/b", "domain": "work",
        "namespace": "default", "summary_content": "summary",
        "search_terms": "terms", "content": "body", "lifecycle_status": "active",
    }
    text = module.build_document_text(row)
    assert "\n" in text
    assert "\\n" not in text


def test_validate_documents_rejects_duplicate_uri():
    docs = [
        {"uri": "memory://same", "content_hash": "a"},
        {"uri": "memory://same", "content_hash": "b"},
    ]
    with pytest.raises(ValueError, match="duplicate source URI"):
        module.validate_documents(docs)


def test_validate_documents_rejects_empty_uri():
    with pytest.raises(ValueError, match="empty URI"):
        module.validate_documents([{"uri": " ", "content_hash": "a"}])


def test_validate_vectors_checks_count_and_dimensions():
    with pytest.raises(ValueError, match="count mismatch"):
        module.validate_vectors([[0.0] * 3], 2, expected_dimensions=3)
    with pytest.raises(ValueError, match="dimensions mismatch"):
        module.validate_vectors([[0.0] * 2], 1, expected_dimensions=3)


def test_validate_vectors_rejects_non_finite_values():
    with pytest.raises(ValueError, match="non-finite"):
        module.validate_vectors([[0.0, float("nan")]], 1, expected_dimensions=2)


@pytest.mark.asyncio
async def test_sync_api_failure_keeps_previous_index_intact(tmp_path, monkeypatch):
    import asyncio
    import sqlite3

    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    cache = tmp_path / "cache.db"
    con = sqlite3.connect(source)
    con.executescript("""
        CREATE TABLE nodes(uuid TEXT PRIMARY KEY, lifecycle_status TEXT NOT NULL);
        CREATE TABLE memories(id INTEGER PRIMARY KEY, deprecated INTEGER);
        CREATE TABLE search_documents(
            memory_id INTEGER, node_uuid TEXT, uri TEXT, namespace TEXT, domain TEXT,
            path TEXT, summary_content TEXT, search_terms TEXT, content TEXT
        );
        INSERT INTO nodes VALUES('node-1', 'active');
        INSERT INTO memories VALUES(1, 0);
        INSERT INTO search_documents VALUES(1, 'node-1', 'memory://one', 'default', 'work', 'a', 's', 'k', 'body-v1');
    """)
    con.commit()
    con.close()

    monkeypatch.setattr(module, "SOURCE_DB", source)
    monkeypatch.setattr(module, "TARGET_DB", target)
    monkeypatch.setattr(module, "CACHE_DB", cache)

    async def valid_vectors(texts):
        return [[0.25] * module.EXPECTED_DIMENSIONS for _ in texts]

    monkeypatch.setattr(module, "generate_vectors", valid_vectors)
    first = await module.sync()
    assert first["integrity_ok"] is True
    assert first["source_document_count"] == 1

    con = sqlite3.connect(source)
    con.execute("UPDATE search_documents SET content='body-v2' WHERE uri='memory://one'")
    con.commit()
    con.close()

    async def failed_vectors(texts):
        raise RuntimeError("simulated embedding outage")

    monkeypatch.setattr(module, "generate_vectors", failed_vectors)
    with pytest.raises(RuntimeError, match="simulated embedding outage"):
        await module.sync()

    con = sqlite3.connect(target)
    stored_hash = con.execute("SELECT content_hash FROM memory_meta WHERE uri='memory://one'").fetchone()[0]
    meta_count = con.execute("SELECT COUNT(*) FROM memory_meta").fetchone()[0]
    con.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(con)
    vector_count = con.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
    con.close()
    assert stored_hash != module.load_docs()[0]["content_hash"]
    assert meta_count == vector_count == 1


@pytest.mark.asyncio
async def test_sync_handles_uri_rename_and_obsolete_transition(tmp_path, monkeypatch):
    import sqlite3

    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    cache = tmp_path / "cache.db"
    con = sqlite3.connect(source)
    con.executescript("""
        CREATE TABLE nodes(uuid TEXT PRIMARY KEY, lifecycle_status TEXT NOT NULL);
        CREATE TABLE memories(id INTEGER PRIMARY KEY, deprecated INTEGER);
        CREATE TABLE search_documents(
            memory_id INTEGER, node_uuid TEXT, uri TEXT, namespace TEXT, domain TEXT,
            path TEXT, summary_content TEXT, search_terms TEXT, content TEXT
        );
        INSERT INTO nodes VALUES('node-1', 'active');
        INSERT INTO memories VALUES(1, 0);
        INSERT INTO search_documents VALUES(1, 'node-1', 'memory://old', 'default', 'work', 'a', 's', 'k', 'body');
    """)
    con.commit()
    con.close()

    monkeypatch.setattr(module, "SOURCE_DB", source)
    monkeypatch.setattr(module, "TARGET_DB", target)
    monkeypatch.setattr(module, "CACHE_DB", cache)

    async def vectors(texts):
        return [[0.5] * module.EXPECTED_DIMENSIONS for _ in texts]

    monkeypatch.setattr(module, "generate_vectors", vectors)
    await module.sync()

    con = sqlite3.connect(source)
    con.execute("UPDATE search_documents SET uri='memory://new' WHERE uri='memory://old'")
    con.commit()
    con.close()
    renamed = await module.sync()
    assert renamed["inserted_or_updated"] == 1
    assert renamed["deleted_stale"] == 1

    con = sqlite3.connect(source)
    con.execute("UPDATE nodes SET lifecycle_status='obsolete' WHERE uuid='node-1'")
    con.commit()
    con.close()
    obsolete = await module.sync()
    assert obsolete["source_document_count"] == 0
    assert obsolete["deleted_stale"] == 1
    assert obsolete["metadata_count"] == 0
    assert obsolete["vector_count"] == 0


@pytest.mark.asyncio
async def test_sync_excludes_deprecated_memories(tmp_path, monkeypatch):
    import sqlite3

    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    con = sqlite3.connect(source)
    con.executescript("""
        CREATE TABLE nodes(uuid TEXT PRIMARY KEY, lifecycle_status TEXT NOT NULL);
        CREATE TABLE memories(id INTEGER PRIMARY KEY, deprecated INTEGER);
        CREATE TABLE search_documents(
            memory_id INTEGER, node_uuid TEXT, uri TEXT, namespace TEXT, domain TEXT,
            path TEXT, summary_content TEXT, search_terms TEXT, content TEXT
        );
        INSERT INTO nodes VALUES('node-1', 'active');
        INSERT INTO memories VALUES(1, 1);
        INSERT INTO search_documents VALUES(1, 'node-1', 'memory://deprecated', 'default', 'work', 'a', 's', 'k', 'body');
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(module, "SOURCE_DB", source)
    monkeypatch.setattr(module, "TARGET_DB", target)
    async def no_vectors(texts):
        assert texts == []
        return []
    monkeypatch.setattr(module, "generate_vectors", no_vectors)
    result = await module.sync()
    assert result["source_document_count"] == 0
    assert result["metadata_count"] == result["vector_count"] == 0
