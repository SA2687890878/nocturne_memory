async def test_search_indexer_refreshes_on_content_and_alias_changes(graph_service, search_indexer):
    await graph_service.create_memory(
        parent_path="",
        content="GraphService owns alias refreshes",
        priority=2,
        title="search_note",
        disclosure="When testing search refresh",
    )

    initial_results = await search_indexer.search("GraphService")

    await graph_service.update_memory("search_note", content="MemoryBrowser owns rendered search")
    await graph_service.add_path(
        new_path="mirrored_search_note",
        target_path="search_note",
        new_domain="project",
        target_domain="core",
        priority=4,
        disclosure="When mirroring search note",
    )

    updated_results = await search_indexer.search("MemoryBrowser")
    alias_results = await search_indexer.search("mirrored_search_note", domain="project")

    assert initial_results[0]["uri"] == "core://search_note"
    assert updated_results[0]["uri"] == "core://search_note"
    assert alias_results[0]["uri"] == "project://mirrored_search_note"

async def test_memory_summary_is_searchable_and_version_scoped(graph_service, search_indexer):
    created = await graph_service.create_memory(
        parent_path="",
        content="The body contains implementation details and baseline context.",
        priority=2,
        title="summary_version_note",
        disclosure="When testing summary versioning",
    )
    memory_id = created["rows_after"]["memories"][0]["id"]

    summary_write = await graph_service.update_memory_summary(
        memory_id, "This is rare_summary_phrase about the project purpose."
    )
    assert summary_write["summary_status"] == "VALID"
    assert summary_write["summary_updated_at"] is not None

    await search_indexer.rebuild_all_search_documents()
    summary_results = await search_indexer.search("rare_summary_phrase")
    assert summary_results[0]["memory_id"] == memory_id
    assert summary_results[0]["summary_status"] == "VALID"
    assert "rare_summary_phrase" in summary_results[0]["summary"]
    assert "implementation details" in summary_results[0]["snippet"]

    updated = await graph_service.update_memory(
        "summary_version_note",
        content="The revised body contains a different set of details.",
    )
    new_memory_id = updated["new_memory_id"]

    active_results = await search_indexer.search("revised body")
    assert active_results[0]["memory_id"] == new_memory_id
    assert active_results[0]["summary_status"] == "MISSING"
    assert await search_indexer.search("rare_summary_phrase") == []
    await graph_service.update_memory_summary(memory_id, "Historical_only_summary_phrase")
    assert await search_indexer.search("Historical_only_summary_phrase") == []

    from db.models import Memory
    from db import get_db_manager

    async with get_db_manager().session() as session:
        old_memory = await session.get(Memory, memory_id)
        assert old_memory.deprecated is True
        assert old_memory.summary_content == "Historical_only_summary_phrase"


async def test_search_retains_matching_alias_entries_without_duplicate_content(
    graph_service, search_indexer
):
    await graph_service.create_memory(
        parent_path="",
        content="Alias summary lookup body.",
        priority=2,
        title="summary_alias_source",
        disclosure="When looking up the source alias",
    )
    await graph_service.add_path(
        new_path="summary_alias_target",
        target_path="summary_alias_source",
        new_domain="project",
        priority=4,
        disclosure="When looking up the alternate alias",
    )

    results = await search_indexer.search("Alias summary lookup")
    assert len(results) == 1
    assert results[0]["uri"] == "core://summary_alias_source"
    assert len(results[0]["aliases"]) == 1
    # Both paths reuse the same Edge in the current graph model, so metadata is shared.
    alias = results[0]["aliases"][0]
    assert alias["uri"] == "project://summary_alias_target"
    assert alias["priority"] == results[0]["priority"]
    assert alias["disclosure"] == results[0]["disclosure"]


async def test_search_reads_only_bounded_body_snippet_from_search_index(
    graph_service, search_indexer
):
    from sqlalchemy import event
    from db import get_db_manager

    body = ("ordinary implementation background text " * 1200) + " rare_tail_search_marker " + (" trailing details " * 1200)
    await graph_service.create_memory(
        parent_path="",
        content=body,
        priority=2,
        title="bounded_search_payload",
        disclosure="When validating bounded search payload",
    )

    statements = []
    engine = get_db_manager().engine.sync_engine

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "FROM search_documents AS sd" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        results = await search_indexer.search("rare_tail_search_marker")
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert len(results) == 1
    assert "rare_tail_search_marker" in results[0]["snippet"]
    assert len(results[0]["snippet"]) < 500
    assert statements
    # Search may use the indexed body for FTS matching and bounded snippet extraction,
    # but must not select the complete SearchDocument.content column into Python.
    assert all("                        sd.content,\n" not in statement for statement in statements)
    assert all("AS snippet" in statement for statement in statements)


async def test_boot_summary_query_does_not_select_memory_body(graph_service):
    from sqlalchemy import event
    from db import get_db_manager
    from system_views import generate_boot_memory_view

    await graph_service.create_memory(
        parent_path="",
        content="BOOT_BODY_MUST_NOT_BE_SELECTED " + ("large body " * 3000),
        priority=2,
        title="boot_projection_check",
        disclosure="Only load this memory summary during boot",
    )

    statements = []
    engine = get_db_manager().engine.sync_engine

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        if "from paths" in normalized and "join memories" in normalized:
            statements.append(normalized)

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        boot = await generate_boot_memory_view(["core://boot_projection_check"])
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert "# Loaded: 1/1 memories" in boot
    assert "BOOT_BODY_MUST_NOT_BE_SELECTED" not in boot
    assert statements
    assert all("memories.content" not in statement for statement in statements)



async def test_search_uses_curated_phrase_alias_only_after_original_strict_miss(
    graph_service, search_indexer
):
    await graph_service.create_memory(
        parent_path="",
        content="任务恢复时读取 task contract 和 product_path，继续上次开发工作。",
        priority=2,
        title="task_recovery_contract",
    )
    await graph_service.create_memory(
        parent_path="",
        content="用户日常开发技术栈与语言偏好。",
        priority=2,
        title="user_technical_stack",
    )
    await graph_service.create_memory(
        parent_path="",
        content="上次开发任务的普通讨论记录。",
        priority=2,
        title="handoff_query_noise",
    )

    recovered = await search_indexer.search("上次开发任务怎么找回来", limit=10, include_partial=True)
    assert recovered
    assert recovered[0]["uri"] == "core://task_recovery_contract"
    assert recovered[0]["match_type"] == "strict"
    assert "core://handoff_query_noise" not in [item["uri"] for item in recovered]

    paraphrase = await search_indexer.search("恢复之前开发进度需要先看什么", limit=10)
    assert paraphrase[0]["uri"] == "core://task_recovery_contract"

    # A genuine strict match of the original wording must outrank aliases.
    await graph_service.create_memory(
        parent_path="",
        content="上次开发任务怎么找回来：这是原始表达的精确匹配。",
        priority=2,
        title="exact_original_wording",
    )
    exact = await search_indexer.search("上次开发任务怎么找回来", limit=10)
    assert exact[0]["uri"] == "core://exact_original_wording"

    await graph_service.create_memory(
        parent_path="",
        content="交接前保留修改文件、测试命令和未解决问题。",
        priority=2,
        title="handoff_compaction",
    )
    handoff = await search_indexer.search("交接给下一个会话要留下什么", limit=10)
    assert handoff
    assert handoff[0]["uri"] == "core://handoff_compaction"
    handoff_paraphrase = await search_indexer.search("切换会话前应该交代哪些信息", limit=10)
    assert handoff_paraphrase[0]["uri"] == "core://handoff_compaction"

    await graph_service.create_memory(
        parent_path="",
        content="为本次用例设计桩时，响应或期望耗尽要明确失败，并断言真实调用次数、顺序与入参。",
        priority=2,
        title="test_design",
    )
    test_paraphrase = await search_indexer.search("自动化测试用例应该怎么设计", limit=10)
    assert test_paraphrase[0]["uri"] == "core://test_design"

    # Phrase alternatives cover wording differences without global token rewriting.
    phrase_cases = [
        ("task_resume", "现行任务真源是在办 active.json 与历史 index.json；推进或恢复任务时先核对 task_id。", "把之前那个开发任务接着做，第一步去哪里找"),
        ("mock_exhaustion", "为本次用例设计桩时，响应或期望耗尽要明确失败，并断言真实调用次数。", "Mock 返回值不够了测试应当怎么报错"),
        ("collaboration_preferences", "回复简洁精准，每组列表不超过五项，最相关的放前面。", "回答尽量短一点，列清楚重点"),
        ("memory_governance", "季度复审不等于自动删除；只定向处理不再适用、重复或过于具体的条目。", "Nocturne 里哪些记忆不应该自动清理"),
        ("config_verification", "配置变更用同源方式单独解析，不能以 build/test 通过代替配置正确。", "配置调整后怎样证明新配置确实加载了"),
    ]
    for title, content, query in phrase_cases:
        await graph_service.create_memory(
            parent_path="", content=content, priority=2, title=title
        )
        results = await search_indexer.search(query, limit=10)
        assert any(item["uri"] == f"core://{title}" for item in results)

    # A query without a curated phrase alias keeps its original ranking path.
    technical = await search_indexer.search(
        "我常用哪些开发技术", limit=10, include_partial=True
    )
    assert technical[0]["uri"] == "core://user_technical_stack"



async def test_search_filters_low_coverage_partial_fallbacks(graph_service, search_indexer):
    await graph_service.create_memory(
        parent_path="",
        content="alpha beta gamma",
        priority=2,
        title="partial_match_relevant",
    )
    await graph_service.create_memory(
        parent_path="",
        content="alpha",
        priority=2,
        title="partial_match_noise",
    )
    for index in range(5):
        await graph_service.create_memory(
            parent_path="",
            content=f"alpha beta gamma candidate {index}",
            priority=2,
            title=f"partial_match_candidate_{index}",
        )

    results = await search_indexer.search(
        "alpha beta gamma delta epsilon", limit=10, include_partial=True
    )
    uris = [item["uri"] for item in results]

    assert "core://partial_match_relevant" in uris
    assert "core://partial_match_noise" not in uris
    assert len(uris) <= 3

    # The first pass must not leak PARTIAL candidates. They are an explicit
    # second-stage disclosure only.
    default_results = await search_indexer.search(
        "alpha beta gamma delta epsilon", limit=10
    )
    assert default_results == []


async def test_curated_phrase_aliases_recover_natural_language_paraphrases(
    graph_service, search_indexer
):
    cases = [
        (
            "上下文很长的时候，怎么减少一次性塞进模型的内容？",
            "输出 超过 5KB",
            "paraphrase_context_output",
        ),
        (
            "程序运行异常时，应该按什么顺序定位真正原因？",
            "故障 排查",
            "paraphrase_debugging",
        ),
        (
            "开发新需求时，怎样优先沿用项目现有实现而不是重新造轮子？",
            "复用",
            "paraphrase_development",
        ),
        (
            "业务描述不清楚时，怎样判断先追问还是按默认假设继续？",
            "阻塞 澄清 问题",
            "paraphrase_requirements",
        ),
        (
            "接手之前没做完的开发工作，应该从哪里恢复进度？",
            "恢复任务 进度",
            "paraphrase_task_handoff",
        ),
        (
            "Codex 接入 Copilot 转发服务后，API 请求格式有哪些适配点？",
            "Codex Copilot Responses 协议",
            "paraphrase_codex_bridge",
        ),
    ]

    for _query, indexed_terms, title in cases:
        await graph_service.create_memory(
            parent_path="",
            content=f"Search benchmark fixture: {indexed_terms}",
            priority=2,
            title=title,
            disclosure="Only for curated phrase-alias regression coverage",
        )

    expected = {
        "上下文很长的时候，怎么减少一次性塞进模型的内容？": "core://paraphrase_context_output",
        "程序运行异常时，应该按什么顺序定位真正原因？": "core://paraphrase_debugging",
        "开发新需求时，怎样优先沿用项目现有实现而不是重新造轮子？": "core://paraphrase_development",
        "业务描述不清楚时，怎样判断先追问还是按默认假设继续？": "core://paraphrase_requirements",
        "接手之前没做完的开发工作，应该从哪里恢复进度？": "core://paraphrase_task_handoff",
        "Codex 接入 Copilot 转发服务后，API 请求格式有哪些适配点？": "core://paraphrase_codex_bridge",
    }
    for query, uri in expected.items():
        results = await search_indexer.search(query, limit=10)
        assert results, query
        assert results[0]["uri"] == uri, (query, [item["uri"] for item in results])


async def test_phrase_alias_candidates_are_appended_after_existing_strict_hits(
    graph_service, search_indexer
):
    await graph_service.create_memory(
        parent_path="",
        content="业务描述不清楚 时 怎样 判断 先追问 还是 按 默认 假设 继续",
        priority=2,
        title="strict_but_generic_requirement_match",
    )
    await graph_service.create_memory(
        parent_path="",
        content="阻塞 澄清 问题",
        priority=2,
        title="curated_requirement_target",
    )

    results = await search_indexer.search(
        "业务描述不清楚时，怎样判断先追问还是按默认假设继续？",
        limit=10,
    )
    uris = [item["uri"] for item in results]
    assert "core://strict_but_generic_requirement_match" in uris
    assert "core://curated_requirement_target" in uris
    assert uris.index("core://strict_but_generic_requirement_match") < uris.index(
        "core://curated_requirement_target"
    )
