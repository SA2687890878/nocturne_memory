"""Isolated lifecycle recall/status tests.

Uses a temporary SQLite database and a temporary config.json only.
No live database, server, or credentials are touched.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.pop("TEST_DATABASE_URL", None)
os.environ.pop("NOCTURNE_DB_URL", None)

import config


class LifecycleRecallTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls._db_path = root / "test.db"
        cls._db_url = f"sqlite+aiosqlite:///{cls._db_path.as_posix()}"
        cfg_path = root / "config.json"
        cfg_path.write_text(json.dumps({
            "database_url": cls._db_url,
            "valid_domains": ["core", "writer"],
            "boot_uris": {"": []},
            "bloat_min_bytes": 2400,
        }), encoding="utf-8")
        cls._old_config_path = config.CONFIG_PATH
        config.CONFIG_PATH = cfg_path
        config._invalidate()

    @classmethod
    def tearDownClass(cls):
        config.CONFIG_PATH = cls._old_config_path
        config._invalidate()
        cls._tmp.cleanup()

    async def asyncSetUp(self):
        from db import (
            close_db, get_db_manager, get_glossary_service,
            get_graph_service, get_search_indexer, set_runtime_database_url,
        )
        from db.namespace import set_namespace

        await close_db()
        for suffix in ("", "-wal", "-shm"):
            Path(str(self._db_path) + suffix).unlink(missing_ok=True)
        set_runtime_database_url(self._db_url)
        manager = get_db_manager()
        await manager.init_db()
        self.db = manager
        self.graph = get_graph_service()
        self.search = get_search_indexer()
        self.glossary = get_glossary_service()
        set_namespace("")

    async def asyncTearDown(self):
        from db import close_db, set_runtime_database_url

        await close_db()
        set_runtime_database_url(None)

    async def make(self, title, content, status="unspecified", namespace="",
                   domain="core"):
        return await self.graph.create_memory(
            "", content, priority=2, title=title, domain=domain,
            namespace=namespace, lifecycle_status=status)

    async def test_v31_synthetic_recall_and_summary_token_efficiency(self):
        """Measure summary-based recall on 15 synthetic tasks, never live user data."""
        import json
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[3]
        dataset = json.loads(
            (project_root / "docs/project/v3.1-recall-evaluation.json").read_text(
                encoding="utf-8"
            )
        )
        cases = dataset["cases"]
        self.assertEqual(len(cases), 15)

        # Build the entire corpus before querying. The earlier sequential version
        # queried one document at a time and overstated retrieval quality.
        total_body_chars = sum(len(case["body_detail"]) for case in cases)
        total_summary_chars = sum(len(case["summary"]) for case in cases)
        for case in cases:
            created = await self.graph.create_memory(
                parent_path="",
                content=case["body_detail"],
                priority=2,
                title=case["title"],
                lifecycle_status="active",
            )
            await self.graph.update_memory_summary(created["id"], case["summary"])

        hits_at_10 = 0
        reciprocal_rank_sum = 0.0
        precision_at_10_sum = 0.0
        task_results = []
        for case in cases:
            results = await self.search.search(case["query"], limit=10)
            returned = [item["uri"] for item in results]
            if case["expected_uri"] not in returned:
                results = await self.search.search(
                    case["query"], limit=10, include_partial=True
                )
                returned = [item["uri"] for item in results]
            hit = case["expected_uri"] in returned
            if hit:
                hits_at_10 += 1
                rank = returned.index(case["expected_uri"]) + 1
                reciprocal_rank_sum += 1.0 / rank
                precision_at_10_sum += 1.0 / 10
            task_results.append({"task": case["id"], "hit": hit, "rank": rank if hit else None})

        recall_at_10 = hits_at_10 / len(cases)
        mean_reciprocal_rank = reciprocal_rank_sum / len(cases)
        precision_at_10 = precision_at_10_sum / len(cases)

        # Harder keyword queries deliberately avoid the exact title/URI slug.
        # They test whether useful summary/body terms can retrieve the target
        # when the query is phrased as a task rather than a memory identifier.
        hard_queries = [
            ("SQLite 数据库迁移 schema_migrations 隔离测试库", "core://sqlite_migration_guard"),
            ("Boot 上下文只加载摘要 不展开全文", "core://boot_summary_delivery"),
            ("同一 Node 多个入口 Edge 元数据", "core://alias_path_entry"),
            ("completed 仍然可用 obsolete 默认过滤", "core://obsolete_lifecycle_filter"),
            ("URI 明确指定时获取完整正文", "core://explicit_uri_read"),
        ]
        hard_hits = 0
        hard_results = []
        for query, expected_uri in hard_queries:
            results = await self.search.search(query, limit=10)
            returned = [item["uri"] for item in results]
            if expected_uri not in returned:
                results = await self.search.search(
                    query, limit=10, include_partial=True
                )
                returned = [item["uri"] for item in results]
            hit = expected_uri in returned
            hard_hits += int(hit)
            hard_results.append((query, expected_uri, returned.index(expected_uri) + 1 if hit else None))
        hard_recall_at_10 = hard_hits / len(hard_queries)
        # Character-based estimate compares stored summaries with bodies; it is
        # not a measurement of actual MCP payload or model-token consumption.
        estimated_body_tokens = (total_body_chars + 3) // 4
        estimated_summary_tokens = (total_summary_chars + 3) // 4
        reduction = 1 - estimated_summary_tokens / max(estimated_body_tokens, 1)

        self.assertGreaterEqual(recall_at_10, 0.90)
        self.assertGreaterEqual(hard_recall_at_10, 0.60)
        self.assertGreaterEqual(reduction, 0.70)
        print(
            "\nV3.1 synthetic corpus benchmark: "
            f"tasks={len(cases)}, Recall@10={recall_at_10:.1%}, "
            f"MRR={mean_reciprocal_rank:.3f}, P@10={precision_at_10:.3f}, "
            f"body_tokens_proxy={estimated_body_tokens}, "
            f"summary_tokens_proxy={estimated_summary_tokens}, "
            f"summary/body_proxy_reduction={reduction:.1%}, "
            f"hard_queries={len(hard_queries)}, hard_Recall@10={hard_recall_at_10:.1%}, "
            f"hard_ranks={hard_results}, "
            f"misses={[item['task'] for item in task_results if not item['hit']]}"
        )

    async def test_auxiliary_search_terms_paraphrase_diagnostic(self):
        """Measure lexical recall after isolated FTS term injection; no live data."""
        import json
        project_root = Path(__file__).resolve().parents[3]
        dataset = json.loads((project_root / "docs/project/v3.1-recall-evaluation.json").read_text(encoding="utf-8"))
        nodes_by_uri = {}
        for case in dataset["cases"]:
            created = await self.graph.create_memory(
                parent_path="", content=case["body_detail"], priority=2,
                title=case["title"], lifecycle_status="active",
            )
            nodes_by_uri[case["expected_uri"]] = created["node_uuid"]
            await self.graph.update_memory_summary(created["id"], case["summary"])

        paraphrases = [
            ("如何避免迁移脚本重复执行", "core://sqlite_migration_guard"),
            ("检索摘要内容需要同步全文索引", "core://summary_fts_keyword"),
            ("只在需要时展开完整记忆", "core://on_demand_expansion"),
            ("启动时不要读取完整正文", "core://boot_summary_delivery"),
            ("为 AI 上下文控制输入长度", "core://token_budget_estimate"),
            ("不同入口对应不同关系属性", "core://alias_path_entry"),
            ("已完成的历史经验仍可检索", "core://obsolete_lifecycle_filter"),
            ("正文修改后摘要也要重新生成", "core://memory_version_summary"),
            ("相同内容避免重复保存", "core://duplicate_memory_check"),
            ("关联内容不要递归加载", "core://related_memory_disclosure"),
        ]
        # Diagnostic only: inject phrases directly into the derived
        # SearchDocument/FTS index. Do not touch GlossaryKeyword, whose separate
        # purpose is trigger-based cross-memory links during read_memory.
        from sqlalchemy import select, text
        from db.models import SearchDocument

        baseline = {}
        for query, expected_uri in paraphrases:
            baseline[query] = await self.search.search(query, limit=10)

        for query, expected_uri in paraphrases:
            node_uuid = nodes_by_uri[expected_uri]
            async with self.db.session() as session:
                document = (
                    await session.execute(
                        select(SearchDocument).where(
                            SearchDocument.node_uuid == node_uuid,
                            SearchDocument.namespace == "",
                        )
                    )
                ).scalar_one()
                document.search_terms = " ".join(
                    part for part in (document.search_terms, query) if part
                )
                await session.flush()
                await session.execute(
                    text(
                        "UPDATE search_documents_fts SET search_terms = :terms "
                        "WHERE namespace = :namespace AND domain = :domain AND path = :path"
                    ),
                    {
                        "terms": document.search_terms,
                        "namespace": document.namespace,
                        "domain": document.domain,
                        "path": document.path,
                    },
                )

        strict_hits = partial_hits = 0
        baseline_hits = sum(
            expected_uri in [item["uri"] for item in baseline[query]]
            for query, expected_uri in paraphrases
        )
        details = []
        for query, expected_uri in paraphrases:
            strict = await self.search.search(query, limit=10)
            expanded = await self.search.search(query, limit=10, include_partial=True)
            strict_uris = [item["uri"] for item in strict]
            expanded_uris = [item["uri"] for item in expanded]
            strict_hit = expected_uri in strict_uris
            partial_hit = expected_uri in expanded_uris
            strict_hits += int(strict_hit)
            partial_hits += int(partial_hit)
            details.append({
                "query": query, "expected": expected_uri,
                "strict_rank": strict_uris.index(expected_uri) + 1 if strict_hit else None,
                "expanded_rank": expanded_uris.index(expected_uri) + 1 if partial_hit else None,
                "recovered_by_partial": partial_hit and not strict_hit,
            })
        print({
            "paraphrase_tasks": len(paraphrases),
            "baseline_recall_at_10": baseline_hits / len(paraphrases),
            "auxiliary_index_recall_at_10": strict_hits / len(paraphrases),
            "with_partial_recall_at_10": partial_hits / len(paraphrases),
            "recovered_by_partial": sum(x["recovered_by_partial"] for x in details),
            "details": details,
        })

    async def test_boot_budget_is_summary_only_not_total_output_budget(self):
        """Boot must not read bodies; summary budget does not cap fixed metadata."""
        from unittest.mock import AsyncMock, patch
        import system_views

        original_get = config.get
        body_marker = "BODY_ONLY_SECRET_MARKER " + ("full body detail " * 120)
        summary = "SUMMARY_MARKER " + ("compact summary detail " * 30)
        created = await self.make("boot_budget_probe", body_marker, "active")
        await self.graph.update_memory_summary(created["id"], summary)

        with patch.object(
            config, "get",
            side_effect=lambda key: 12 if key == "boot_summary_token_budget" else original_get(key),
        ), patch.object(
            system_views, "fetch_and_format_memory", new_callable=AsyncMock
        ) as full_reader:
            boot = await system_views.generate_boot_memory_view(
                ["core://boot_budget_probe"]
            )
            full_reader.assert_not_awaited()

        self.assertIn("Summary budget: 12 estimated tokens", boot)
        self.assertIn("Summary [TRUNCATED]", boot)
        self.assertNotIn("BODY_ONLY_SECRET_MARKER", boot)
        self.assertIn('read_memory("core://boot_budget_probe")', boot)

        # The configured limit applies to summary payload only. Headers, URI,
        # disclosure and recent metadata remain outside that summary budget.
        summary_budget_line = next(
            line for line in boot.splitlines() if line.startswith("# Summary budget:")
        )
        self.assertIn("used: 12", summary_budget_line)
        self.assertGreater(len(boot.encode("utf-8")), 12 * 3)

        # Explicit URI reading remains the intentional full-body expansion path.
        from system_views import fetch_and_format_memory
        full = await fetch_and_format_memory("core://boot_budget_probe")
        self.assertIn("BODY_ONLY_SECRET_MARKER", full)

    async def test_recent_memories_query_does_not_select_full_memory_body(self):
        from sqlalchemy import event

        await self.make(
            "recent_metadata_only",
            "RECENT_BODY_MUST_NOT_BE_SELECTED " + ("large body detail " * 200),
            "active",
        )
        statements = []
        engine = self.db.engine.sync_engine

        def capture_sql(conn, cursor, statement, parameters, context, executemany):
            normalized = statement.lower()
            if normalized.lstrip().startswith("select") and "paths" in normalized and "memories" in normalized:
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture_sql)
        try:
            recent = await self.graph.get_recent_memories(limit=5, namespace="")
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)

        self.assertTrue(any("recent_metadata_only" in item["uri"] for item in recent))
        self.assertTrue(statements, "Expected get_recent_memories to execute a query")
        normalized_sql = " ".join(statements).lower()
        self.assertNotIn("memories.content", normalized_sql)
        self.assertNotIn("select memories.*", normalized_sql)

    async def test_boot_missing_summary_does_not_expand_body(self):
        from unittest.mock import AsyncMock, patch
        import system_views

        body_marker = "MISSING_SUMMARY_BODY_MARKER " + ("long detail " * 80)
        await self.make("boot_missing_summary", body_marker, "active")
        with patch.object(
            system_views, "fetch_and_format_memory", new_callable=AsyncMock
        ) as full_reader:
            boot = await system_views.generate_boot_memory_view(
                ["core://boot_missing_summary"]
            )
            full_reader.assert_not_awaited()

        self.assertIn("Summary [MISSING]", boot)
        self.assertNotIn("MISSING_SUMMARY_BODY_MARKER", boot)

    async def test_optional_partial_lane_never_displaces_strict_results(self):
        strict = await self.make("strict_target", "alpha beta strict evidence", "active")
        partial = await self.make("partial_target", "alpha only partial evidence", "active")

        default = await self.search.search("alpha beta", limit=10)
        self.assertEqual([item["uri"] for item in default], ["core://strict_target"])
        self.assertNotIn("match_type", default[0])

        expanded = await self.search.search("alpha beta", limit=10, include_partial=True)
        by_uri = {item["uri"]: item for item in expanded}
        self.assertIn("core://strict_target", by_uri)
        self.assertIn("core://partial_target", by_uri)
        self.assertEqual(by_uri["core://strict_target"]["match_type"], "strict")
        self.assertEqual(by_uri["core://partial_target"]["match_type"], "partial")
        self.assertEqual(by_uri["core://partial_target"]["matched_terms"], ["alpha"])
        self.assertEqual(by_uri["core://partial_target"]["match_coverage"], 0.5)

    async def test_partial_match_fallback_precision_experiment(self):
        """Compare strict AND with OR on partial relevant hits and hard negatives."""
        from sqlalchemy import text

        query = "postgres migration isolation guard"
        target = await self.make(
            "architecture_notes",
            "PostgreSQL migration checklist and schema compatibility notes",
            "active",
        )
        target_uuid = target["node_uuid"]

        # Hard negatives contain every query term but discuss unrelated incidents.
        for index in range(12):
            await self.make(
                f"incident_{index:02d}",
                f"Postgres migration isolation guard incident {index}: "
                "unrelated deployment log, retry timeout and service alert",
                "active",
            )
        for index in range(15):
            await self.make(
                f"unrelated_{index:02d}",
                f"Routine application maintenance note number {index}",
                "active",
            )

        async with self.search._session() as session:
            async def ranked(operator):
                match_query = self.search._to_sqlite_match_query(query, operator=operator)
                result = await session.execute(text("""
                    SELECT sd.node_uuid, sd.uri,
                           bm25(search_documents_fts, 0.0, 0.0, 2.5, 0.0,
                                2.0, 2.5, 1.0, 1.0, 0.75) AS score
                    FROM search_documents AS sd
                    JOIN nodes AS n ON n.uuid = sd.node_uuid
                    JOIN search_documents_fts
                      ON search_documents_fts.namespace = sd.namespace
                     AND search_documents_fts.domain = sd.domain
                     AND search_documents_fts.path = sd.path
                    WHERE search_documents_fts MATCH :match_query
                      AND sd.namespace = ''
                      AND n.lifecycle_status != 'obsolete'
                    ORDER BY score ASC, sd.priority ASC, length(sd.path) ASC
                    LIMIT 50
                """), {"match_query": match_query})
                return result.mappings().all()

            strict_rows = await ranked("AND")
            relaxed_rows = await ranked("OR")

        strict_ids = [row["node_uuid"] for row in strict_rows]
        relaxed_ids = [row["node_uuid"] for row in relaxed_rows]
        delivered = await self.search.search(query, limit=10)
        delivered_ids = {item["memory_id"] for item in delivered}
        strict_recall = 1.0 if target_uuid in strict_ids else 0.0
        relaxed_recall = 1.0 if target_uuid in relaxed_ids else 0.0
        strict_precision = sum(node == target_uuid for node in strict_ids) / max(len(strict_ids), 1)
        relaxed_precision = sum(node == target_uuid for node in relaxed_ids) / max(len(relaxed_ids), 1)

        # Diagnostic only: OR recovers partial matches but admits lexical noise.
        self.assertEqual(strict_recall, 0.0)
        self.assertEqual(relaxed_recall, 1.0)
        self.assertNotIn(target["id"], delivered_ids)
        self.assertLess(relaxed_precision, 0.2)
        print({
            "strict_candidates": len(strict_rows),
            "strict_recall_at_50": strict_recall,
            "strict_precision_at_50": strict_precision,
            "or_candidates": len(relaxed_rows),
            "or_recall_at_50": relaxed_recall,
            "or_precision_at_50": relaxed_precision,
            "target_or_rank": relaxed_ids.index(target_uuid) + 1,
            "actual_search_limit_10_target_returned": target["id"] in delivered_ids,
        })

    async def test_search_excludes_obsolete_before_limit(self):
        await self.make("a", "alpha " * 40, "obsolete")
        await self.make("zz_active", "alpha once", "active")

        default = await self.search.search("alpha", limit=1)
        self.assertEqual([item["uri"] for item in default], ["core://zz_active"])

        both = await self.search.search("alpha", limit=10, include_obsolete=True)
        self.assertEqual({item["uri"] for item in both},
                         {"core://a", "core://zz_active"})

    async def test_search_keeps_namespace_isolation(self):
        await self.make("inside", "gamma hit", "active")
        await self.make("outside", "gamma hit", "active", namespace="private")

        found = await self.search.search("gamma")
        self.assertEqual([item["uri"] for item in found], ["core://inside"])

    async def test_glossary_auto_links_skip_obsolete_but_listing_keeps_status(self):
        active = await self.make("live_target", "target", "active")
        obsolete = await self.make("dead_target", "old target", "obsolete")
        await self.glossary.add_glossary_keyword("liveword", active["node_uuid"])
        await self.glossary.add_glossary_keyword("deadword", obsolete["node_uuid"])

        links = await self.glossary.find_glossary_in_content(
            "liveword and deadword", namespace="")
        self.assertIn("liveword", links)
        self.assertEqual(links["liveword"], [
            {"node_uuid": active["node_uuid"], "uri": "core://live_target"}])
        self.assertNotIn("deadword", links)

        listing = await self.glossary.get_all_glossary(namespace="")
        statuses = {
            node["uri"]: node["lifecycle_status"]
            for entry in listing for node in entry["nodes"]
        }
        self.assertEqual(statuses["core://dead_target"], "obsolete")
        self.assertEqual(statuses["core://live_target"], "active")

    async def test_explicit_views_show_status_and_keep_loaded_count_honest(self):
        from system_views import (
            fetch_and_format_memory, generate_boot_memory_view,
            generate_glossary_index_view, generate_memory_index_view,
        )

        obsolete = await self.make("old", "old body", "obsolete")
        await self.make("new", "new body", "active")
        await self.glossary.add_glossary_keyword("oldword", obsolete["node_uuid"])

        text = await fetch_and_format_memory("core://old")
        self.assertIn("Lifecycle: obsolete", text)
        self.assertIn("Lifecycle Warning", text)

        boot = await generate_boot_memory_view(["core://old"])
        self.assertIn("# Loaded: 1/1 memories", boot)
        self.assertIn("Lifecycle: obsolete", boot)
        await asyncio.sleep(0.05)

        index = await generate_memory_index_view("core")
        self.assertIn("core://old", index)
        self.assertIn("[lifecycle: obsolete]", index)

        glossary_view = await generate_glossary_index_view()
        self.assertIn("core://old", glossary_view)
        self.assertIn("[lifecycle: obsolete]", glossary_view)


if __name__ == "__main__":
    unittest.main(verbosity=2)
