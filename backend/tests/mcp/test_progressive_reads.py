"""Disclosure boundaries must hold at the database and response layers."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event


async def _seed(graph_service, *, summary=True):
    created = await graph_service.create_memory(
        parent_path="", title="progressive_probe", priority=2,
        content="SECRET_LINE_ONE\n证据第二行\nTHIRD_LINE\nLAST_PRIVATE_LINE\n",
        disclosure="Only when checking progressive disclosure",
    )
    memory_id = created["rows_after"]["memories"][0]["id"]
    if summary:
        await graph_service.update_memory_summary(memory_id, "用于验证摘要分层的简明结论。")
    return memory_id


async def test_summary_read_never_queries_body_or_related_nodes(
    mcp_module, graph_service, monkeypatch,
):
    from db import get_db_manager

    memory_id = await _seed(graph_service)
    full_read = AsyncMock(side_effect=AssertionError("must not query full body"))
    children = AsyncMock(side_effect=AssertionError("must not query children"))
    monkeypatch.setattr(graph_service, "get_memory_by_path", full_read)
    monkeypatch.setattr(graph_service, "get_children", children)
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement.lower())

    engine = get_db_manager().engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        output = await mcp_module.read_memory("core://progressive_probe", detail="summary")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert f"Memory ID: {memory_id}" in output
    assert "Summary [VALID]" in output
    assert "摘要分层" in output
    assert "SECRET_LINE_ONE" not in output
    assert statements
    assert all("memories.content" not in sql for sql in statements)
    full_read.assert_not_awaited()
    children.assert_not_awaited()


async def test_missing_summary_does_not_fall_back_to_body(mcp_module, graph_service):
    await _seed(graph_service, summary=False)
    output = await mcp_module.read_memory("core://progressive_probe", detail="summary")
    assert "Summary [MISSING]" in output
    assert "SECRET_LINE_ONE" not in output


@pytest.mark.parametrize("budget", [0, 2])
async def test_summary_read_obeys_budget(mcp_module, graph_service, monkeypatch, budget):
    import config
    from system_views import _estimate_context_tokens

    await _seed(graph_service)
    original = config.get
    monkeypatch.setattr(config, "get", lambda key: budget if key == "search_summary_token_budget" else original(key))
    output = await mcp_module.read_memory("core://progressive_probe", detail="summary")
    assert "Summary [OMITTED]" in output if budget == 0 else "Summary [TRUNCATED]" in output
    if budget:
        text = output.split("Summary [TRUNCATED]: ", 1)[1].split("...", 1)[0]
        assert _estimate_context_tokens(text) <= budget
    assert "SECRET_LINE_ONE" not in output


async def test_line_range_returns_only_selected_body_and_no_relations(
    mcp_module, graph_service, monkeypatch,
):
    memory_id = await _seed(graph_service)
    children = AsyncMock(side_effect=AssertionError("range read must not expand children"))
    monkeypatch.setattr(graph_service, "get_children", children)
    output = await mcp_module.read_memory("core://progressive_probe", start_line=2, end_line=3)
    assert f"Memory ID: {memory_id}" in output
    assert "Content lines: 2-3/4" in output
    assert "2: 证据第二行\n3: THIRD_LINE" in output
    assert "SECRET_LINE_ONE" not in output
    assert "LAST_PRIVATE_LINE" not in output
    assert "start_line=4, end_line=4" in output
    children.assert_not_awaited()


async def test_range_end_is_clamped_and_full_read_remains_verbatim(mcp_module, graph_service):
    await _seed(graph_service)
    tail = await mcp_module.read_memory("core://progressive_probe", start_line=4, end_line=999)
    assert "Content lines: 4-4/4" in tail
    assert "Continue only if needed" not in tail
    full = await mcp_module.read_memory("core://progressive_probe")
    assert "SECRET_LINE_ONE\n证据第二行\nTHIRD_LINE\nLAST_PRIVATE_LINE\n" in full
    assert "Partial body read" not in full


@pytest.mark.parametrize("options", [
    {"detail": "unknown"}, {"start_line": 0}, {"start_line": True},
    {"start_line": 1.5}, {"start_line": 3, "end_line": 2},
    {"detail": "summary", "end_line": 2}, {"end_line": -1},
])
async def test_invalid_disclosure_options_fail_before_body_access(mcp_module, graph_service, monkeypatch, options):
    full_read = AsyncMock(side_effect=AssertionError("invalid request must not load body"))
    monkeypatch.setattr(graph_service, "get_memory_by_path", full_read)
    assert (await mcp_module.read_memory("core://progressive_probe", **options)).startswith("Error:")
    full_read.assert_not_awaited()


async def test_out_of_range_and_missing_uri_are_explicit_errors(mcp_module, graph_service):
    await _seed(graph_service)
    assert "exceeds total lines (4)" in await mcp_module.read_memory("core://progressive_probe", start_line=5)
    assert (await mcp_module.read_memory("core://does_not_exist", detail="summary")).startswith("Error:")
    assert (await mcp_module.read_memory("system://boot", detail="summary")).startswith("Error:")
    assert (await mcp_module.read_memory("system://random/core", end_line=2)).startswith("Error:")


async def test_summary_and_range_follow_current_version_and_namespace(mcp_module, graph_service):
    from db.namespace import _namespace, set_namespace

    old_id = await _seed(graph_service)
    token = set_namespace("another_namespace")
    try:
        assert (await mcp_module.read_memory("core://progressive_probe", detail="summary")).startswith("Error:")
        assert (await mcp_module.read_memory("core://progressive_probe", end_line=1)).startswith("Error:")
    finally:
        _namespace.reset(token)
    updated = await graph_service.update_memory("progressive_probe", content="NEW_VERSION_ONLY")
    summary = await mcp_module.read_memory("core://progressive_probe", detail="summary")
    assert "Summary [MISSING]" in summary
    assert f"Memory ID: {updated['new_memory_id']}" in summary
    assert updated["new_memory_id"] != old_id
    line = await mcp_module.read_memory("core://progressive_probe", end_line=1)
    assert "NEW_VERSION_ONLY" in line
    assert "SECRET_LINE_ONE" not in line


async def test_mcp_default_search_skips_sql_snippet_extraction(mcp_module, graph_service):
    from db import get_db_manager

    await _seed(graph_service)
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        if "FROM search_documents AS sd" in statement:
            statements.append(statement)

    engine = get_db_manager().engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        output = await mcp_module.search_memory("SECRET_LINE_ONE")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert "core://progressive_probe" in output
    assert "Body snippet:" not in output
    assert statements
    assert all("snippet(" not in sql and "substr(sd.content" not in sql for sql in statements)


@pytest.mark.parametrize("include_partial", [False, True])
async def test_snippet_opt_out_keeps_candidates_ranking_and_partial_evidence(
    graph_service, search_indexer, include_partial,
):
    await _seed(graph_service)
    await graph_service.create_memory(parent_path="", title="other_probe", priority=3, content="SECRET_LINE_ONE other text")
    for query in ("SECRET_LINE_ONE", "SECRET_LINE_ONE nonexistentkeyword"):
        baseline = await search_indexer.search(query, include_partial=include_partial)
        compact = await search_indexer.search(query, include_partial=include_partial, include_snippets=False)
        assert compact == [{**row, "snippet": ""} for row in baseline]
