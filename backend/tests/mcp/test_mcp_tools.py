async def test_read_memory_system_views(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="Agent identity",
        priority=1,
        title="agent",
        disclosure="When booting",
    )
    await graph_service.create_memory(
        parent_path="",
        content="User identity",
        priority=1,
        title="my_user",
        disclosure="When booting",
    )

    boot = await mcp_module.read_memory("system://boot")
    index_view = await mcp_module.read_memory("system://index/core")
    recent = await mcp_module.read_memory("system://recent/5")
    index_error = await mcp_module.read_memory("system://index")

    assert "core://agent" in boot
    assert "core://my_user" in boot
    assert "system://index/<domain>" in boot
    assert "core://agent" in index_view
    assert "core://my_user" in recent
    assert "requires a domain" in index_error


async def test_diagnostic_view_points_duplicate_aliases_to_delete_memory(mcp_module):
    await mcp_module.create_memory(
        "core://",
        "Folder memory",
        priority=1,
        title="folder",
        disclosure="When testing diagnostics",
    )
    await mcp_module.add_alias(
        "core://folder_copy",
        "core://folder",
        priority=2,
        disclosure="When testing duplicate aliases",
    )

    diagnostic = await mcp_module.read_memory("system://diagnostic/core")

    assert "### 3.2 Duplicate Aliases under Same Parent" in diagnostic
    assert "Use `delete_memory` on the redundant alias URI to remove the extra path." in diagnostic
    assert "`delete_path`" not in diagnostic
    assert "core://folder" in diagnostic
    assert "core://folder_copy" in diagnostic


def test_read_memory_tool_description_discourages_duplicate_reads(mcp_module):
    description = mcp_module.read_memory.__doc__ or ""
    assert "同一会话中某 URI 已成功读取后" in description
    assert "不要重复读取" in description
    assert "正文已更新" in description
    assert "禁止遍历整个 domain" in description
    assert "最多读取 3 条直接相关正文" in description


async def test_memory_index_is_navigation_not_read_all_checklist(mcp_module):
    index = await mcp_module.read_memory("system://index/core")
    assert "导航地图，不是待读清单" in index
    assert "禁止遍历整个 domain" in index
    assert "最多读取 3 条" in index


def test_search_memory_tool_description_discourages_first_pass_expansion(mcp_module):
    description = mcp_module.search_memory.__doc__ or ""
    assert "首轮保持 include_partial=false" in description
    assert "include_snippets=false" in description
    assert "用户明确要求原文片段" in description
    assert "read_memory(uri)" in description
    assert "2-5 个有区分度的关键词/短语" in description
    assert "不要直接提交完整问题长句" in description
    assert "token_budget=0" in description
    assert "保留默认摘要预算" in description
    assert "不要全局默认 0" in description


async def test_search_memory_omits_partial_fallback_summaries_by_default(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="alpha beta gamma",
        priority=2,
        title="partial_summary_probe",
    )
    memory = await graph_service.get_memory_by_path("partial_summary_probe", "core")
    await mcp_module.update_memory_summary(
        memory["id"], "PARTIAL_SUMMARY_SENTINEL should only appear when explicitly requested."
    )

    query = "alpha beta gamma delta epsilon"
    default_result = await mcp_module.search_memory(query)
    assert "No matching memories found" in default_result
    assert "PARTIAL_SUMMARY_SENTINEL" not in default_result

    explicit_result = await mcp_module.search_memory(query, include_partial=True)
    assert "Match: PARTIAL" in explicit_result
    assert "PARTIAL_SUMMARY_SENTINEL" in explicit_result


async def test_mcp_tool_flow_covers_crud_alias_triggers_and_search(mcp_module, graph_service):
    created = await mcp_module.create_memory(
        "core://",
        "Important Salem memory",
        priority=2,
        title="salem_note",
        disclosure="When testing MCP tools",
    )
    updated = await mcp_module.update_memory(
        "core://salem_note",
        append="\nGraphService handles aliases.",
    )
    triggers = await mcp_module.manage_triggers(
        "core://salem_note",
        add=["Salem"],
    )
    search = await mcp_module.search_memory("GraphService")
    alias = await mcp_module.add_alias(
        "project://salem_alias",
        "core://salem_note",
        priority=3,
        disclosure="When mirroring note",
    )
    deleted = await mcp_module.delete_memory("project://salem_alias")

    current = await graph_service.get_memory_by_path("salem_note", "core")
    removed_alias = await graph_service.get_memory_by_path("salem_alias", "project")

    assert "Success: Memory created" in created
    assert "Success: Memory at 'core://salem_note' updated" == updated
    assert "Added: Salem" in triggers
    assert "core://salem_note" in search
    assert "Success: Alias 'project://salem_alias'" in alias
    assert "Success: Memory 'project://salem_alias' deleted." in deleted
    assert current["content"].endswith("GraphService handles aliases.")
    assert removed_alias is None


# =============================================================================
# Unit tests for normalize_with_positions
# =============================================================================

from text_patch import normalize_with_positions, try_normalized_patch


class TestNormalizeWithPositions:
    def test_straight_quotes_unchanged(self):
        text = 'She said "hello" to him.'
        norm, pos_map = normalize_with_positions(text)
        assert norm == text
        assert len(pos_map) == len(norm)
        assert all(pos_map[i] == i for i in range(len(norm)))

    def test_curly_quotes_normalized(self):
        text = "She said \u201chello\u201d to him."
        norm, pos_map = normalize_with_positions(text)
        assert norm == 'She said "hello" to him.'
        assert pos_map[0] == 0  # 'S'
        assert pos_map[9] == 9  # curly open quote maps to original pos 9

    def test_dash_variants(self):
        text = "range\u2014end"
        norm, _ = normalize_with_positions(text)
        assert norm == "range-end"

    def test_trailing_whitespace_stripped(self):
        text = "hello   \nworld"
        norm, pos_map = normalize_with_positions(text)
        assert norm == "hello\nworld"
        assert pos_map[5] == 8  # '\n' at original position 8

    def test_consecutive_spaces_collapsed(self):
        text = "hello    world"
        norm, pos_map = normalize_with_positions(text)
        assert norm == "hello world"
        assert pos_map[5] == 5  # first space kept
        assert pos_map[6] == 9  # 'w' at original position 9

    def test_leading_spaces_preserved(self):
        text = "    - item"
        norm, pos_map = normalize_with_positions(text)
        assert norm == "    - item"
        assert len(pos_map) == len(norm)
        assert pos_map[0] == 0
        assert pos_map[3] == 3
        assert pos_map[4] == 4  # '-'

    def test_mixed_leading_and_inline_spaces(self):
        text = "    hello    world"
        norm, pos_map = normalize_with_positions(text)
        assert norm == "    hello world"
        assert len(norm) == 15
        assert pos_map[9] == 9  # space after hello
        assert pos_map[10] == 13 # 'w'

    def test_empty_string(self):
        norm, pos_map = normalize_with_positions("")
        assert norm == ""
        assert pos_map == []

    def test_multiline_with_mixed_issues(self):
        text = "line1   \n  \u201chello\u201d   \nend"
        norm, pos_map = normalize_with_positions(text)
        assert norm == 'line1\n  "hello"\nend'
        assert len(pos_map) == len(norm)

    def test_crlf_normalized_to_lf(self):
        text = "line1\r\nline2\r\nline3"
        norm, pos_map = normalize_with_positions(text)
        assert norm == "line1\nline2\nline3"
        assert len(pos_map) == len(norm)
        assert pos_map[5] == 6  # '\n' maps to the original '\n' which is at index 6
        assert pos_map[6] == 7  # 'l' in line2

    def test_backtick_is_not_normalized(self):
        text = "Run `update` command."
        norm, pos_map = normalize_with_positions(text)
        assert norm == "Run `update` command."


# =============================================================================
# Unit tests for try_normalized_patch
# =============================================================================


class TestTryNormalizedPatch:
    def test_curly_to_straight_quote_patch(self):
        content = "She said \u201chello\u201d to him."
        result = try_normalized_patch(
            content, 'She said "hello"', 'She said "goodbye"'
        )
        assert result is not None
        assert '"goodbye"' in result
        assert "to him." in result

    def test_dash_variant_patch(self):
        content = "range: 10\u201420"
        result = try_normalized_patch(
            content, "range: 10-20", "range: 10-30"
        )
        assert result is not None
        assert "10-30" in result

    def test_trailing_whitespace_patch(self):
        content = "hello   \nworld"
        result = try_normalized_patch(
            content, "hello\nworld", "goodbye\nworld"
        )
        assert result is not None
        assert result.startswith("goodbye\n")

    def test_space_collapse_patch(self):
        content = "A    B    C"
        result = try_normalized_patch(
            content, "A B", "X Y"
        )
        assert result is not None
        assert result.startswith("X Y")
        assert result.endswith("C")

    def test_no_match_returns_none(self):
        result = try_normalized_patch(
            "hello world", "completely different", "replacement"
        )
        assert result is None

    def test_ambiguous_match_returns_none(self):
        content = 'He said "yes". She said "yes".'
        result = try_normalized_patch(
            content, '"yes"', '"no"'
        )
        assert result is None

    def test_exact_match_still_needed_when_no_normalization_diff(self):
        content = "hello world"
        result = try_normalized_patch(
            content, "helo world", "replacement"
        )
        assert result is None


# =============================================================================
# Integration: update_memory with normalized fallback
# =============================================================================


async def test_update_memory_falls_back_to_normalized_patch(
    mcp_module, graph_service
):
    original_content = "Nocturne said \u201cI will not kneel.\u201d That is final."
    await graph_service.create_memory(
        parent_path="",
        content=original_content,
        priority=1,
        title="norm_test",
    )

    result = await mcp_module.update_memory(
        "core://norm_test",
        old_string='Nocturne said "I will not kneel."',
        new_string='Nocturne said "I refuse to kneel."',
    )
    assert "Error" in result


async def test_update_memory_exact_match_takes_priority(
    mcp_module, graph_service
):
    """Exact match must be used when available, not normalized."""
    await graph_service.create_memory(
        parent_path="",
        content="Hello World",
        priority=1,
        title="exact_test",
    )
    result = await mcp_module.update_memory(
        "core://exact_test",
        old_string="Hello",
        new_string="Goodbye",
    )
    assert "Success: Memory at 'core://exact_test' updated" in result
    memory = await graph_service.get_memory_by_path("exact_test", "core")
    assert memory["content"] == "Goodbye World"


async def test_update_memory_normalized_ambiguous_returns_error(
    mcp_module, graph_service
):
    content = "He said \u201cyes\u201d. She said \u201cyes\u201d."
    await graph_service.create_memory(
        parent_path="",
        content=content,
        priority=1,
        title="ambig_test",
    )
    result = await mcp_module.update_memory(
        "core://ambig_test",
        old_string='\u201cyes\u201d',
        new_string='"no"',
    )
    assert "Error" in result
    assert "ambiguous" in result.lower()


async def test_create_memory_preserves_all_content_verbatim(
    mcp_module, graph_service
):
    """create_memory never normalizes — whatever you pass is stored as-is."""
    for title_suffix, content in [
        ("backslash", r"Windows path: C:\tmp\test and regex token: foo\\nbar"),
        ("escaped_multiline", "# Title\\n\\n- alpha\\n- beta"),
        ("single_token", r"Use \n to represent a newline in regex examples."),
        ("code_literal", 'payload = "line1\\n\\nline2"'),
        ("regex", "^(?:[A-Z]\\n)+$"),
        ("plain_prose", "line one\\nline two"),
    ]:
        result = await mcp_module.create_memory(
            "core://",
            content,
            priority=1,
            title=f"verbatim_{title_suffix}",
            disclosure="When verifying verbatim storage",
        )
        assert "Success" in result, f"Failed for {title_suffix}"
        assert "SYSTEM NOTICE" not in result, f"Unexpected normalization for {title_suffix}"
        memory = await graph_service.get_memory_by_path(f"verbatim_{title_suffix}", "core")
        assert memory["content"] == content, f"Content mismatch for {title_suffix}"


async def test_update_memory_preserves_literal_backslash_sequences(
    mcp_module, graph_service
):
    original_content = r"Store C:\tmp\test and regex foo\\nbar literally."
    await graph_service.create_memory(
        parent_path="",
        content=original_content,
        priority=1,
        title="literal_backslash_update",
    )

    result = await mcp_module.update_memory(
        "core://literal_backslash_update",
        old_string=r"C:\tmp\test",
        new_string=r"D:\logs\test",
    )

    assert "Success: Memory at 'core://literal_backslash_update' updated" in result
    memory = await graph_service.get_memory_by_path("literal_backslash_update", "core")
    assert memory["content"] == r"Store D:\logs\test and regex foo\\nbar literally."


async def test_update_memory_normalizes_escaped_newlines_on_patch_fallback(
    mcp_module, graph_service
):
    """When stored content has real newlines but old_string has literal \\n,
    exact match fails, then the newline-normalization fallback kicks in."""
    await graph_service.create_memory(
        parent_path="",
        content="# Title\n\n- alpha\n- beta",
        priority=1,
        title="escaped_multiline_update",
    )

    result = await mcp_module.update_memory(
        "core://escaped_multiline_update",
        old_string="# Title\\n\\n- alpha\\n- beta",
        new_string="# Title\n\n- gamma\n- delta",
    )

    assert "Success: Memory at 'core://escaped_multiline_update' updated" in result
    memory = await graph_service.get_memory_by_path("escaped_multiline_update", "core")
    assert memory["content"] == "# Title\n\n- gamma\n- delta"


async def test_update_memory_exact_match_wins_over_normalization(
    mcp_module, graph_service
):
    """When stored content literally contains \\n sequences, exact match
    succeeds and no normalization occurs."""
    literal_content = 'payload = "line1\\n\\nline2"'
    await graph_service.create_memory(
        parent_path="",
        content=literal_content,
        priority=1,
        title="literal_exact_match",
    )

    result = await mcp_module.update_memory(
        "core://literal_exact_match",
        old_string='payload = "line1\\n\\nline2"',
        new_string='payload = "line1\\n\\nline2\\nline3"',
    )

    assert "Success" in result
    assert "SYSTEM NOTICE" not in result
    memory = await graph_service.get_memory_by_path("literal_exact_match", "core")
    assert memory["content"] == 'payload = "line1\\n\\nline2\\nline3"'


async def test_update_memory_append_preserves_content_verbatim(
    mcp_module, graph_service
):
    """Append mode never normalizes — whatever you pass is appended as-is."""
    await graph_service.create_memory(
        parent_path="",
        content="Base content",
        priority=1,
        title="append_verbatim",
    )

    result = await mcp_module.update_memory(
        "core://append_verbatim",
        append="\\n\\nCode: foo\\n\\nbar",
    )

    assert "Success" in result
    assert "SYSTEM NOTICE" not in result
    memory = await graph_service.get_memory_by_path("append_verbatim", "core")
    assert memory["content"] == "Base content\\n\\nCode: foo\\n\\nbar"


# =============================================================================
# Block patch mode (old_start + old_end + new_string)
# =============================================================================


async def test_update_memory_block_replaces_section(mcp_module, graph_service):
    """Block mode replaces the uniquely matched block."""
    await graph_service.create_memory(
        parent_path="",
        content="## History\nOld stuff\nMore old stuff\n\n## Future\nPlans here",
        priority=1,
        title="block_basic",
    )

    result = await mcp_module.update_memory(
        "core://block_basic",
        old_string="## History\n...\n\n## Future",
        new_string="## History\nRewritten content\n\n## Future",
    )

    assert "Success" in result
    memory = await graph_service.get_memory_by_path("block_basic", "core")
    assert memory["content"] == "## History\nRewritten content\n\n## Future\nPlans here"


async def test_update_memory_block_delete_section(mcp_module, graph_service):
    """Block mode with empty new_string deletes the matched block."""
    await graph_service.create_memory(
        parent_path="",
        content="Keep this\n## Remove\nGarbage\n## End",
        priority=1,
        title="block_delete",
    )

    result = await mcp_module.update_memory(
        "core://block_delete",
        old_string="\n## Remove\n...\n## End",
        new_string="",
    )

    assert "Success" in result
    memory = await graph_service.get_memory_by_path("block_delete", "core")
    assert memory["content"] == "Keep this"


async def test_update_memory_block_no_match_returns_error(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="Nothing matches here",
        priority=1,
        title="block_nomatch",
    )

    result = await mcp_module.update_memory(
        "core://block_nomatch",
        old_string="## NONEXISTENT...## END",
        new_string="replacement",
    )

    assert "Error" in result
    assert "Could not find any match" in result


async def test_update_memory_block_multiple_matches_returns_error(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="## Section\nContent A\n## End\n\n## Section\nContent B\n## End",
        priority=1,
        title="block_multi",
    )

    result = await mcp_module.update_memory(
        "core://block_multi",
        old_string="## Section\n...\n## End",
        new_string="replacement",
    )

    assert "Error" in result
    assert "Ambiguous update" in result
    assert "Match 1" in result
    assert "Match 2" in result


async def test_update_memory_block_missing_end_returns_error(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="Some content",
        priority=1,
        title="block_missing_end",
    )

    result = await mcp_module.update_memory(
        "core://block_missing_end",
        old_string="Some...missing",
        new_string="replacement",
    )

    assert "Error" in result


async def test_update_memory_block_without_new_string_returns_error(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="Some content",
        priority=1,
        title="block_no_new",
    )

    result = await mcp_module.update_memory(
        "core://block_no_new",
        old_string="Some...content",
    )

    assert "Error" in result
    assert "new_string" in result




async def test_update_memory_block_identical_result_returns_error(mcp_module, graph_service):
    """Block that matches text identical to new_string should fail."""
    await graph_service.create_memory(
        parent_path="",
        content="Hello world",
        priority=1,
        title="block_noop",
    )

    result = await mcp_module.update_memory(
        "core://block_noop",
        old_string="Hello...world",
        new_string="Hello world",
    )

    assert "Error" in result
    assert "identical" in result


async def test_diagnostic_view_respects_config_bloat_min_bytes(mcp_module, monkeypatch):
    import config
    monkeypatch.setattr(config, "get", lambda key: 50 if key == "bloat_min_bytes" else config.DEFAULTS.get(key))

    await mcp_module.create_memory(
        "core://",
        "A" * 60,
        priority=1,
        title="bloated_node_test",
        disclosure="Testing bloat diagnostic config",
    )

    diagnostic = await mcp_module.read_memory("system://diagnostic/core")
    assert "## 4. Bloated Memories" in diagnostic
    assert "core://bloated_node_test" in diagnostic

async def test_update_memory_summary_tool_and_search_output(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="",
        content="The body contains detailed implementation notes.",
        priority=1,
        title="mcp_summary_note",
        disclosure="When testing the summary MCP tool",
    )
    from db import get_search_indexer

    result = (await get_search_indexer().search("mcp_summary_note"))[0]
    saved = await mcp_module.update_memory_summary(
        result["memory_id"], "MCP summary unique phrase for context delivery."
    )
    search_output = await mcp_module.search_memory("MCP summary unique phrase", include_snippets=True)

    assert "Success: summary" in saved
    assert "Summary [VALID]" in search_output
    assert "MCP summary unique phrase" in search_output
    assert "Body snippet:" in search_output
    assert "read_memory(\"core://mcp_summary_note\")" in search_output

async def test_boot_delivers_only_summary_and_preserves_explicit_full_read(
    mcp_module, graph_service
):
    summarized = await graph_service.create_memory(
        parent_path="",
        content="PRIVATE_BODY_SENTINEL full details must not appear in boot output.",
        priority=1,
        title="boot_summary_ready",
        disclosure="When testing summary-first boot",
    )
    missing = await graph_service.create_memory(
        parent_path="",
        content="MISSING_SUMMARY_BODY_SENTINEL also stays out of boot output.",
        priority=2,
        title="boot_summary_missing",
        disclosure="When testing missing summary behavior",
    )
    await graph_service.update_memory_summary(
        summarized["rows_after"]["memories"][0]["id"],
        "Boot summary contains only the essential project context.",
    )

    from system_views import generate_boot_memory_view

    boot = await generate_boot_memory_view([
        "core://boot_summary_ready",
        "core://boot_summary_missing",
    ])
    assert "Summary [VALID]" in boot
    assert "essential project context" in boot
    assert "Summary [MISSING]" in boot
    assert "PRIVATE_BODY_SENTINEL" not in boot
    assert "MISSING_SUMMARY_BODY_SENTINEL" not in boot

    full_read = await mcp_module.read_memory("core://boot_summary_ready")
    assert "PRIVATE_BODY_SENTINEL" in full_read

async def test_boot_respects_configured_summary_token_budget(
    mcp_module, graph_service, monkeypatch
):
    created = await graph_service.create_memory(
        parent_path="",
        content="This body is not part of the boot payload.",
        priority=1,
        title="boot_budget_note",
        disclosure="When testing boot token budget",
    )
    await graph_service.update_memory_summary(
        created["rows_after"]["memories"][0]["id"],
        "A deliberately long summary that must be shortened by the configured context budget.",
    )

    import config
    from system_views import generate_boot_memory_view

    original_get = config.get
    monkeypatch.setattr(
        config,
        "get",
        lambda key: 5 if key == "boot_summary_token_budget" else original_get(key),
    )
    boot = await generate_boot_memory_view(["core://boot_budget_note"])

    assert "Summary [TRUNCATED]" in boot
    assert "Summary budget: 5 estimated tokens" in boot
    assert "This body is not part of the boot payload" not in boot

async def test_boot_recent_index_is_compact_but_recent_view_keeps_disclosure(
    graph_service,
):
    from system_views import generate_recent_memories_view

    disclosure = "ONLY_RECENT_DISCLOSURE_TRIGGER_FOR_TEST"
    await graph_service.create_memory(
        parent_path="",
        content="Recent disclosure retention test",
        priority=2,
        title="recent_disclosure_retention",
        disclosure=disclosure,
    )

    compact = await generate_recent_memories_view(limit=5, include_disclosure=False)
    detailed = await generate_recent_memories_view(limit=5)

    assert "core://recent_disclosure_retention" in compact
    assert disclosure not in compact
    assert "core://recent_disclosure_retention" in detailed
    assert disclosure in detailed



async def test_read_memory_survives_access_tracking_failure(mcp_module, graph_service, monkeypatch):
    await graph_service.create_memory(
        parent_path="",
        content="Memory body remains available even if access analytics fail.",
        priority=2,
        title="read_without_access_log",
        disclosure="When validating read resilience",
    )

    async def fail_access_log(*args, **kwargs):
        raise RuntimeError("simulated access-log failure")

    monkeypatch.setattr(graph_service, "log_access", fail_access_log)
    content = await mcp_module.read_memory("core://read_without_access_log")

    assert "MEMORY: core://read_without_access_log" in content
    assert "Memory body remains available" in content


async def test_search_memory_omits_body_snippets_by_default(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="", content="A compact summary-first retrieval fixture.",
        priority=1, title="summary_first_search_fixture",
    )
    result = await mcp_module.search_memory("summary-first retrieval fixture")
    assert "core://summary_first_search_fixture" in result
    assert "Body snippet:" not in result
    assert "Summary budget:" in result


async def test_search_memory_can_include_snippets_on_demand(mcp_module, graph_service):
    await graph_service.create_memory(
        parent_path="", content="An opt-in snippet retrieval fixture.",
        priority=1, title="snippet_opt_in_fixture",
    )
    result = await mcp_module.search_memory("snippet retrieval fixture", include_snippets=True)
    assert "Body snippet:" in result


async def test_search_memory_respects_summary_token_budget(mcp_module, graph_service):
    created = await graph_service.create_memory(
        parent_path="", content="Budget fixture content that can be retrieved by its unique marker.",
        priority=1, title="budget_fixture",
    )
    await graph_service.update_memory_summary(
        created["memory"]["id"] if "memory" in created else created["id"],
        "This is a deliberately long summary used to verify the search token budget."
    )
    result = await mcp_module.search_memory("unique marker", token_budget=3)
    assert "Summary [TRUNCATED]" in result or "Summary [OMITTED]" in result
    assert "Body snippet:" not in result
