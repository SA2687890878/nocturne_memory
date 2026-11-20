"""Semantic candidates must be current, isolated, body-free and budgeted."""
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event

from backend import semantic_search
from backend.vector_index import VectorIndex

DIMS = semantic_search.EXPECTED_DIMENSIONS


@pytest.fixture
def semantic_env(monkeypatch, tmp_path, graph_service):
    path = tmp_path / "checked-vectors.db"
    monkeypatch.setattr(semantic_search, "vector_index_path", lambda: path)
    original = semantic_search.config.get
    monkeypatch.setattr(semantic_search.config, "get", lambda key: {
        "api_key": "isolated-test-only", "model": "test-model",
    } if key == "embedding" else original(key))
    embed = AsyncMock(return_value=[[0.0] * DIMS])
    monkeypatch.setattr(semantic_search, "embed_texts", embed)
    return path, embed


async def seed(graph, title, *, namespace="", lifecycle="active"):
    created = await graph.create_memory(
        "", f"PRIVATE_BODY_{title}", priority=2, title=title,
        namespace=namespace, lifecycle_status=lifecycle,
    )
    memory_id = created["rows_after"]["memories"][0]["id"]
    await graph.update_memory_summary(memory_id, f"Current summary for {title}")
    return {"memory_id": memory_id, "uri": f"core://{title}", "content_hash": "test-hash",
            "namespace": namespace, "domain": "core", "path": title, "lifecycle_status": "active"}


def build(path, documents):
    with VectorIndex(path, dimensions=DIMS, model_name="test-model",
                     document_format_version=semantic_search.DOCUMENT_FORMAT_VERSION) as index:
        index.upsert_many([{**doc, "vector": [float(rank)] + [0.0] * (DIMS - 1)}
                           for rank, doc in enumerate(documents)])


@pytest.mark.parametrize("change", ["body", "path", "obsolete"])
async def test_semantic_filters_updated_deleted_and_obsolete_candidates(
    semantic_env, graph_service, change,
):
    path, embed = semantic_env
    stale = await seed(graph_service, "old_candidate", lifecycle="obsolete" if change == "obsolete" else "active")
    good = await seed(graph_service, "current_candidate")
    build(path, [stale, good])
    if change == "body":
        await graph_service.update_memory("old_candidate", content="Replaced body in a new version")
    elif change == "path":
        await graph_service.remove_path("old_candidate")
    result = await semantic_search.search_semantic_memories("historical question", limit=1)
    assert [item["uri"] for item in result] == [good["uri"]]
    assert result[0]["summary"] == "Current summary for current_candidate"
    embed.assert_awaited_once()


async def test_semantic_refills_after_many_stale_hits_without_reembedding(semantic_env, graph_service):
    path, embed = semantic_env
    good = await seed(graph_service, "good_after_stale")
    stale = [{**good, "uri": f"core://removed_{rank}", "path": f"removed_{rank}"} for rank in range(13)]
    build(path, [*stale, good])
    result = await semantic_search.search_semantic_memories("historical question", limit=1)
    assert [item["uri"] for item in result] == [good["uri"]]
    embed.assert_awaited_once()


async def test_semantic_aliases_do_not_consume_candidate_slots(semantic_env, graph_service):
    path, _embed = semantic_env
    first = await seed(graph_service, "alias_source")
    second = await seed(graph_service, "independent_candidate")
    await graph_service.add_path("alias_copy", "alias_source")
    alias = {**first, "uri": "core://alias_copy", "path": "alias_copy"}
    build(path, [first, alias, second])
    result = await semantic_search.search_semantic_memories("historical question", limit=2)
    assert [item["uri"] for item in result] == [first["uri"], second["uri"]]
    assert result[0]["aliases"] == ["core://alias_copy"]


async def test_semantic_defaults_to_active_namespace_and_rejects_cached_leak(semantic_env, graph_service):
    from db.namespace import _namespace, set_namespace

    path, _embed = semantic_env
    other = await seed(graph_service, "only_other_namespace", namespace="other")
    shared = await seed(graph_service, "personal_candidate", namespace="personal")
    # Even falsified vector metadata must not bypass current path isolation.
    build(path, [{**other, "namespace": "personal"}, shared])
    token = set_namespace("personal")
    try:
        result = await semantic_search.search_semantic_memories("historical question", limit=5)
    finally:
        _namespace.reset(token)
    assert [item["uri"] for item in result] == [shared["uri"]]


async def test_semantic_reads_latest_summary_without_selecting_body(semantic_env, graph_service):
    from db import get_db_manager

    path, _embed = semantic_env
    doc = await seed(graph_service, "summary_refresh")
    build(path, [doc])
    await graph_service.update_memory_summary(doc["memory_id"], "Freshly corrected summary")
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement.lower())

    engine = get_db_manager().engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = await semantic_search.search_semantic_memories("historical question")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result[0]["summary"] == "Freshly corrected summary"
    assert statements and all("memories.content" not in sql for sql in statements)
    assert "PRIVATE_BODY" not in str(result)


async def test_empty_index_does_not_spend_embedding_request(semantic_env):
    path, embed = semantic_env
    build(path, [])
    assert await semantic_search.search_semantic_memories("historical question") == []
    embed.assert_not_awaited()


@pytest.mark.parametrize("read_only_uri", [False, True])
def test_semantic_sidecar_uses_active_database_override(tmp_path, read_only_uri):
    from db import get_runtime_database_url, set_runtime_database_url

    original = get_runtime_database_url()
    try:
        source = tmp_path / "isolated.db"
        url = (f"sqlite+aiosqlite:///{source.as_uri()}?mode=ro&uri=true" if read_only_uri
               else f"sqlite+aiosqlite:///{source.as_posix()}")
        set_runtime_database_url(url)
        assert semantic_search.vector_index_path() == tmp_path / "work-memory-vectors.db"
    finally:
        set_runtime_database_url(original)


@pytest.mark.parametrize("budget", [0, 3, 1200])
async def test_semantic_mcp_delivers_budgeted_summary_without_body(mcp_module, monkeypatch, budget):
    results = [{"uri": "core://verified", "memory_id": 1, "distance": 0.123,
                "domain": "core", "lifecycle_status": "active", "summary": "摘要测试的完整结论。" * 10}]
    mock_search = AsyncMock(return_value=results)
    monkeypatch.setattr(mcp_module, "search_semantic_memories", mock_search)
    output = await mcp_module.semantic_search_memory("historical question", token_budget=budget)
    status = "OMITTED" if budget == 0 else "TRUNCATED" if budget == 3 else "VALID"
    assert f"Summary [{status}]" in output
    assert "Memory ID: 1" in output
    assert "Body not expanded" in output
    assert "not verified relevance" in output


async def test_semantic_invalid_budget_fails_before_paid_query(mcp_module, monkeypatch):
    mock_search = AsyncMock(side_effect=AssertionError("must not spend an API request"))
    monkeypatch.setattr(mcp_module, "search_semantic_memories", mock_search)
    assert (await mcp_module.semantic_search_memory("query", token_budget=-1)).startswith("Error:")
    mock_search.assert_not_awaited()
