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
