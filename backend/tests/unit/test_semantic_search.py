import pytest

from backend import semantic_search
from backend.vector_index import VectorIndex

DIMS = semantic_search.EXPECTED_DIMENSIONS


def test_vector_index_path_is_next_to_configured_sqlite_database(monkeypatch, tmp_path):
    source = tmp_path / "work-memory.db"
    monkeypatch.setattr(semantic_search.config, "get", lambda key: {
        "database_url": f"sqlite+aiosqlite:///{source.as_posix()}"
    }[key])
    assert semantic_search.vector_index_path() == tmp_path / "work-memory-vectors.db"


def test_vector_index_path_rejects_non_sqlite_database(monkeypatch):
    monkeypatch.setattr(semantic_search.config, "get", lambda key: "postgresql://localhost/memory")
    with pytest.raises(RuntimeError, match="requires a SQLite"):
        semantic_search.vector_index_path()


@pytest.mark.asyncio
async def test_semantic_search_returns_explicit_nearest_candidates(monkeypatch, tmp_path, graph_service):
    created = await graph_service.create_memory("", "Current candidate body", priority=2, title="candidate", namespace="personal")
    memory_id = created["rows_after"]["memories"][0]["id"]
    db = tmp_path / "work-memory-vectors.db"
    monkeypatch.setattr(semantic_search.config, "get", lambda key: {
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'work-memory.db').as_posix()}",
        "embedding": {"api_key": "test-key", "model": "test-model", "query_input_type": "query"},
    }[key])
    with VectorIndex(db, dimensions=DIMS, model_name="test-model",
                     document_format_version=semantic_search.DOCUMENT_FORMAT_VERSION) as index:
        index.upsert_many([{"memory_id": memory_id, "uri": "core://candidate", "content_hash": "hash",
                            "namespace": "personal", "domain": "core", "path": "candidate",
                            "lifecycle_status": "active", "vector": [1.0] + [0.0] * (DIMS - 1)}])
    async def fake_embed(texts, *, input_type):
        assert texts == ["a natural language question"]
        assert input_type == "query"
        return [[1.0] + [0.0] * (DIMS - 1)]
    monkeypatch.setattr(semantic_search, "embed_texts", fake_embed)
    result = await semantic_search.search_semantic_memories("a natural language question", limit=5, namespace="personal")
    assert len(result) == 1
    assert result[0]["uri"] == "core://candidate"


@pytest.mark.asyncio
async def test_semantic_search_does_not_create_missing_index(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_search.config, "get", lambda key: {
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'work-memory.db').as_posix()}",
        "embedding": {"api_key": "test-key", "model": "test-model"},
    }[key])
    with pytest.raises(RuntimeError, match="not initialized"):
        await semantic_search.search_semantic_memories("question")
    assert not (tmp_path / "work-memory-vectors.db").exists()


@pytest.mark.asyncio
async def test_semantic_search_validates_limit(monkeypatch):
    with pytest.raises(ValueError, match="between 1 and 50"):
        await semantic_search.search_semantic_memories("question", limit=100)
