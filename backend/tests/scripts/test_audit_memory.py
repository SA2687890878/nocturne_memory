"""Isolated regression tests; no application config or live database is read."""
import importlib.util
import json
import sqlite3
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "audit_memory", Path(__file__).resolve().parents[2] / "scripts/audit_memory.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class KeywordQualityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE paths(namespace TEXT, node_uuid TEXT, path TEXT);
            CREATE TABLE memories(node_uuid TEXT, content TEXT, deprecated INT);
            CREATE TABLE glossary_keywords(namespace TEXT, keyword TEXT, node_uuid TEXT);
        """)
        self.addCleanup(self.db.close)

    def add_node(self, node, body, namespace="", deprecated=0):
        self.db.execute("INSERT INTO paths VALUES(?,?,?)", (namespace, node, node))
        self.db.execute("INSERT INTO memories VALUES(?,?,?)", (node, body, deprecated))

    def bind(self, word, node, namespace=""):
        self.db.execute("INSERT INTO glossary_keywords VALUES(?,?,?)", (namespace, word, node))

    def test_zero_hits_and_case_sensitive_runtime_matching(self):
        self.add_node("a", "GraphService")
        self.bind("graphservice", "a")
        self.bind("missing", "a")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_zero_hit"],
                         [{"keyword": "graphservice"}, {"keyword": "missing"}])

    def test_frequency_boundary_is_five_percent(self):
        for i in range(20):
            self.add_node(str(i), "GraphService" if i == 0 else "other")
        self.bind("GraphService", "0")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_high_frequency"],
                         [{"keyword": "GraphService", "hits": 1, "corpus_nodes": 20}])
        self.add_node("20", "other")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_high_frequency"], [])

    def test_aliases_do_not_dilute_frequency(self):
        self.add_node("a", "状态")
        for i in range(30):
            self.db.execute("INSERT INTO paths VALUES(?,?,?)", ("", "a", str(i)))
        self.bind("状态", "a")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_high_frequency"],
                         [{"keyword": "状态", "hits": 1, "corpus_nodes": 1}])

    def test_old_revisions_and_other_namespaces_do_not_count(self):
        self.add_node("a", "current")
        self.db.execute("INSERT INTO memories VALUES(?,?,?)", ("a", "old", 1))
        self.add_node("b", "outside", "private")
        self.bind("old", "a")
        self.bind("outside", "a")
        self.bind("private-keyword", "b", "private")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_zero_hit"],
                         [{"keyword": "old"}, {"keyword": "outside"}])

    def test_bindings_are_counted_by_node_not_row(self):
        self.add_node("a", "entity")
        for node in ["a", "a", "b"]:
            self.bind("entity", node)
        self.assertEqual(audit.keyword_quality(self.db)["glossary_overbound"], [])
        self.bind("entity", "c")
        self.assertEqual(audit.keyword_quality(self.db)["glossary_overbound"],
                         [{"keyword": "entity", "nodes": 3}])

    def test_low_frequency_generic_is_still_reported(self):
        for i in range(21):
            self.add_node(str(i), "中文" if i == 0 else "other")
        self.bind("中文", "0")
        result = audit.keyword_quality(self.db)
        self.assertEqual(result["glossary_high_frequency"], [])
        self.assertEqual(result["glossary_generic"], [{"keyword": "中文"}])

    def test_empty_corpus(self):
        self.assertEqual(audit.keyword_quality(self.db),
                         {"glossary_zero_hit": [], "glossary_high_frequency": [],
                          "glossary_overbound": [], "glossary_generic": []})

    def test_untriggered_is_advisory_but_real_issues_fail(self):
        report = {"db": "unused", "total_paths": 10, "untriggered_leaves": ["a"],
                  "edges_without_disclosure": 0, "glossary_zero_hit": []}
        self.assertEqual(audit.issue_count(report), 0)
        report["glossary_zero_hit"] = [{"keyword": "missing"}]
        self.assertEqual(audit.issue_count(report), 1)
        report["edges_without_disclosure"] = 2
        self.assertEqual(audit.issue_count(report), 3)


SCHEMA_SQL = """
    CREATE TABLE nodes(uuid TEXT PRIMARY KEY,
                       lifecycle_status TEXT NOT NULL DEFAULT 'unspecified');
    CREATE TABLE paths(namespace TEXT NOT NULL DEFAULT '', domain TEXT, path TEXT,
                       edge_id INTEGER, node_uuid TEXT);
    CREATE TABLE memories(id INTEGER PRIMARY KEY, node_uuid TEXT, content TEXT,
                          deprecated INT DEFAULT 0);
    CREATE TABLE edges(id INTEGER PRIMARY KEY, parent_uuid TEXT, child_uuid TEXT,
                       priority INTEGER, disclosure TEXT);
    CREATE TABLE search_documents(namespace TEXT, domain TEXT, path TEXT, node_uuid TEXT,
                                  memory_id INTEGER, uri TEXT, content TEXT,
                                  disclosure TEXT, priority INTEGER, search_terms TEXT,
                                  updated_at TEXT);
    CREATE TABLE search_documents_fts(namespace, domain, path, node_uuid, uri,
                                      content, disclosure, search_terms);
"""

DOC_COLUMNS = ("namespace, domain, path, node_uuid, memory_id, uri, content, "
               "disclosure, priority, search_terms")
DOC_VALUES = (":namespace, :domain, :path, :node_uuid, :memory_id, :uri, :content, "
              ":disclosure, :priority, :search_terms")
FTS_COLUMNS = "namespace, domain, path, node_uuid, uri, content, disclosure, search_terms"
FTS_VALUES = (":namespace, :domain, :path, :node_uuid, :uri, :content, "
              ":disclosure, :search_terms")


class GuardTestBase(unittest.TestCase):
    """Full in-memory schema mirroring the columns the guards rely on."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(SCHEMA_SQL)
        self.addCleanup(self.db.close)

    def add_live(self, path, body="body text", priority=2, disclosure="when needed",
                 node=None, domain="core", namespace="", lifecycle_status="unspecified"):
        node = node or "node-" + path
        self.db.execute("insert or ignore into nodes(uuid) values (?)", (node,))
        if lifecycle_status != "unspecified":
            self.db.execute("update nodes set lifecycle_status=? where uuid=?",
                            (lifecycle_status, node))
        edge = self.db.execute(
            "insert into edges(priority, disclosure) values (?,?)",
            (priority, disclosure)).lastrowid
        self.db.execute(
            "insert into paths(namespace, domain, path, edge_id, node_uuid) "
            "values (?,?,?,?,?)", (namespace, domain, path, edge, node))
        memory_id = self.db.execute(
            "insert into memories(node_uuid, content, deprecated) values (?,?,0)",
            (node, body)).lastrowid
        return {"namespace": namespace, "domain": domain, "path": path,
                "node_uuid": node, "memory_id": memory_id, "content": body,
                "priority": priority, "disclosure": disclosure,
                "uri": domain + "://" + path, "search_terms": "terms " + path}

    def write_document(self, row, **overrides):
        values = {**row, **overrides}
        self.db.execute(
            "insert into search_documents(%s) values (%s)" % (DOC_COLUMNS, DOC_VALUES),
            values)

    def write_fts(self, row, **overrides):
        values = {**row, **overrides}
        self.db.execute(
            "insert into search_documents_fts(%s) values (%s)" % (FTS_COLUMNS, FTS_VALUES),
            values)


class PriorityBudgetTests(GuardTestBase):
    def test_limit_equalities_are_allowed(self):
        for i in range(5):
            self.add_live("p0-%d" % i, priority=0)
        for i in range(15):
            self.add_live("p1-%d" % i, priority=1)
        self.assertEqual(audit.priority_budget(self.db), [])

    def test_over_budget_reports_path_counts(self):
        for i in range(6):
            self.add_live("p0-%d" % i, priority=0)
        for i in range(16):
            self.add_live("p1-%d" % i, priority=1)
        self.assertEqual(audit.priority_budget(self.db), [
            {"priority": 0, "paths": 6, "limit": 5},
            {"priority": 1, "paths": 16, "limit": 15},
        ])

    def test_alias_paths_count_once_each_not_once_per_node(self):
        for i in range(16):
            self.add_live("alias-%d" % i, priority=1, node="shared-node")
        self.assertEqual(audit.priority_budget(self.db),
                         [{"priority": 1, "paths": 16, "limit": 15}])

    def test_other_namespaces_do_not_consume_budget(self):
        for i in range(6):
            self.add_live("p0-%d" % i, priority=0, namespace="private")
        self.assertEqual(audit.priority_budget(self.db), [])

    def test_priorities_without_limit_are_ignored(self):
        for i in range(40):
            self.add_live("p2-%d" % i, priority=2)
        self.assertEqual(audit.priority_budget(self.db), [])


class DerivedDocumentTests(GuardTestBase):
    def test_matching_document_is_clean(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.assertEqual(audit.derived_document_issues(self.db), {
            "search_documents_missing": [], "search_documents_extra": [],
            "search_documents_duplicate": [], "search_documents_drift": []})

    def test_same_row_count_with_one_missing_and_one_extra(self):
        first = self.add_live("a")
        self.add_live("b")
        self.write_document(first)
        self.write_document(first, path="ghost")
        issues = audit.derived_document_issues(self.db)
        self.assertEqual(issues["search_documents_missing"],
                         [{"uri": "core://b", "namespace": ""}])
        self.assertEqual(issues["search_documents_extra"],
                         [{"uri": "core://ghost", "namespace": ""}])
        self.assertEqual(issues["search_documents_duplicate"], [])

    def test_duplicate_document_rows(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.write_document(expected)
        self.assertEqual(
            audit.derived_document_issues(self.db)["search_documents_duplicate"],
            [{"uri": "core://a", "rows": 2}])

    def test_field_drift_is_reported_per_field(self):
        expected = self.add_live("a", body="new body", priority=1, disclosure="new why")
        self.write_document(expected, content="stale body", priority=2,
                            disclosure="old why", memory_id=999, node_uuid="other-node")
        fields = [item["field"] for item in
                  audit.derived_document_issues(self.db)["search_documents_drift"]]
        self.assertEqual(sorted(fields),
                         ["content", "disclosure", "memory_id", "node_uuid", "priority"])

    def test_uri_drift_is_reported(self):
        expected = self.add_live("a")
        self.write_document(expected, uri="writer://a")
        self.assertEqual(audit.derived_document_issues(self.db)["search_documents_drift"],
                         [{"uri": "core://a", "field": "uri"}])

    def test_drift_report_never_echoes_field_values(self):
        expected = self.add_live("a", body="SENSITIVE-CONTENT",
                                 disclosure="SENSITIVE-DISCLOSURE")
        expected["search_terms"] = "SENSITIVE-TERMS"
        self.write_document(expected, content="LEAKED-CONTENT",
                            disclosure="LEAKED-DISCLOSURE",
                            search_terms="LEAKED-TERMS")
        self.write_fts(expected, content="LEAKED-CONTENT-FTS",
                       disclosure="LEAKED-DISCLOSURE-FTS",
                       search_terms="LEAKED-TERMS-FTS")
        report = {}
        report.update(audit.derived_document_issues(self.db))
        report.update(audit.search_fts_issues(self.db))
        payload = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("SENSITIVE", payload)
        self.assertNotIn("LEAKED", payload)
        self.assertEqual(
            sorted(item["field"] for item in report["search_documents_drift"]),
            ["content", "disclosure"])
        self.assertEqual(
            sorted(item["field"] for item in report["search_fts_drift"]),
            ["content", "disclosure", "search_terms"])
        entries = report["search_documents_drift"] + report["search_fts_drift"]
        self.assertTrue(all(set(item) == {"uri", "field"} for item in entries))

    def test_null_and_empty_disclosure_are_equivalent(self):
        expected = self.add_live("a", disclosure=None)
        self.write_document(expected, disclosure="")
        self.assertEqual(
            audit.derived_document_issues(self.db)["search_documents_drift"], [])
        self.write_document(expected, disclosure=None)
        self.assertEqual(
            audit.derived_document_issues(self.db)["search_documents_drift"], [])

    def test_other_namespace_rows_match_their_own_namespace(self):
        public = self.add_live("a")
        private = self.add_live("a", namespace="private", node="node-private")
        self.write_document(public)
        self.write_document(private)
        self.assertEqual(audit.derived_document_issues(self.db), {
            "search_documents_missing": [], "search_documents_extra": [],
            "search_documents_duplicate": [], "search_documents_drift": []})

    def test_namespace_is_part_of_the_document_key(self):
        private = self.add_live("a", namespace="private")
        self.write_document(private, namespace="")
        issues = audit.derived_document_issues(self.db)
        self.assertEqual(issues["search_documents_missing"],
                         [{"uri": "core://a", "namespace": "private"}])
        self.assertEqual(issues["search_documents_extra"],
                         [{"uri": "core://a", "namespace": ""}])

    def test_deprecated_memory_is_not_expected(self):
        expected = self.add_live("a")
        self.db.execute("update memories set deprecated=1 where id=?", (expected["memory_id"],))
        self.write_document(expected)
        self.assertEqual(audit.derived_document_issues(self.db)["search_documents_extra"],
                         [{"uri": "core://a", "namespace": ""}])


class SearchFtsTests(GuardTestBase):
    def test_matching_fts_is_clean(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.write_fts(expected)
        self.assertEqual(audit.search_fts_issues(self.db), {
            "search_fts_missing": [], "search_fts_extra": [],
            "search_fts_duplicate": [], "search_fts_drift": []})

    def test_missing_and_extra_fts_rows(self):
        first = self.add_live("a")
        second = self.add_live("b")
        self.write_document(first)
        self.write_document(second)
        self.write_fts(first)
        self.write_fts(first, path="ghost")
        issues = audit.search_fts_issues(self.db)
        self.assertEqual(issues["search_fts_missing"],
                         [{"uri": "core://b", "namespace": ""}])
        self.assertEqual(issues["search_fts_extra"],
                         [{"uri": "core://ghost", "namespace": ""}])

    def test_duplicate_fts_rows(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.write_fts(expected)
        self.write_fts(expected)
        self.assertEqual(audit.search_fts_issues(self.db)["search_fts_duplicate"],
                         [{"uri": "core://a", "rows": 2}])

    def test_all_cached_fields_drift(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.write_fts(expected, node_uuid="other", uri="writer://a", content="stale",
                       search_terms="old terms")
        fields = sorted(item["field"] for item in
                        audit.search_fts_issues(self.db)["search_fts_drift"])
        self.assertEqual(fields, ["content", "node_uuid", "search_terms", "uri"])

    def test_disclosure_normalised_before_comparison(self):
        expected = self.add_live("a", disclosure=None)
        self.write_document(expected, disclosure=None)
        self.write_fts(expected, disclosure="")
        self.assertEqual(audit.search_fts_issues(self.db)["search_fts_drift"], [])

    def test_key_includes_namespace_not_only_uri(self):
        expected = self.add_live("a")
        self.write_document(expected)
        self.write_fts(expected, namespace="private")
        issues = audit.search_fts_issues(self.db)
        self.assertEqual(issues["search_fts_missing"],
                         [{"uri": "core://a", "namespace": ""}])
        self.assertEqual(issues["search_fts_extra"],
                         [{"uri": "core://a", "namespace": "private"}])


class StatusAuditTests(GuardTestBase):
    def statuses(self, boot=frozenset()):
        return audit.status_issues(self.db, boot)

    def test_field_not_body_controls_missing_status(self):
        self.add_live("header", body="状态: 在用")
        self.add_live("clear", body="plain body", lifecycle_status="active")
        result = self.statuses()
        self.assertEqual(result["entries_without_status"], ["header"])
        self.assertEqual(result["template_status_residue"], [
            {"path": "header", "body_status": "在用", "field_status": "unspecified"}])

    def test_leaf_boot_and_namespace_exemptions_are_preserved(self):
        self.add_live("leaf")
        self.add_live("container")
        self.db.execute("insert into edges(parent_uuid, child_uuid) values (?,?)",
                        ("node-container", "child"))
        self.add_live("booted")
        self.add_live("private", namespace="private")
        self.assertEqual(self.statuses(boot={"booted"})["entries_without_status"],
                         ["leaf"])

    def test_body_and_field_conflict_is_advisory(self):
        self.add_live("a", body="状态: 在用", lifecycle_status="obsolete")
        result = self.statuses()
        self.assertEqual(result["status_field_conflicts"], [
            {"path": "a", "body_status": "在用", "field_status": "obsolete"}])
        self.assertEqual(len(result["template_status_residue"]), 1)

    def test_consistent_legacy_header_is_residue_not_conflict(self):
        self.add_live("a", body="状态: 已过时", lifecycle_status="obsolete")
        result = self.statuses()
        self.assertEqual(result["status_field_conflicts"], [])
        self.assertEqual(result["template_status_residue"], [
            {"path": "a", "body_status": "已过时", "field_status": "obsolete"}])

    def test_fenced_or_ambiguous_status_lines_are_not_headers(self):
        self.add_live("fenced", body="```\n状态: 在用\n```\n")
        self.add_live("draft", body="状态: 草稿")
        result = self.statuses()
        self.assertEqual(result["template_status_residue"], [])
        self.assertEqual(result["status_field_conflicts"], [])

    def test_obsolete_boot_reference_requires_explicit_config(self):
        self.add_live("booted", lifecycle_status="obsolete")
        self.add_live("other", lifecycle_status="obsolete")
        self.assertEqual(self.statuses({"booted"})["obsolete_boot_references"],
                         [{"path": "booted"}])
        self.assertEqual(self.statuses({"missing"})["obsolete_boot_references"], [])

    def test_status_advisories_do_not_fail_the_audit(self):
        report = {"db": "unused", "total_paths": 0,
                  "entries_without_status": ["a"],
                  "template_status_residue": [{"path": "a"}],
                  "status_field_conflicts": [{"path": "a"}],
                  "obsolete_boot_references": [{"path": "a"}]}
        self.assertEqual(audit.issue_count(report), 0)
        report["edges_without_disclosure"] = 1
        self.assertEqual(audit.issue_count(report), 1)


class SchemaGuardTests(unittest.TestCase):
    def test_missing_schema_raises(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        with self.assertRaises(RuntimeError) as caught:
            audit.require_schema(con)
        self.assertIn("missing table", str(caught.exception))

    def test_missing_column_raises(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.executescript(SCHEMA_SQL)
        con.execute("alter table search_documents drop column priority")
        with self.assertRaises(RuntimeError) as caught:
            audit.require_schema(con)
        self.assertIn("priority", str(caught.exception))

    def test_missing_lifecycle_status_raises(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.executescript(SCHEMA_SQL)
        con.execute("alter table nodes drop column lifecycle_status")
        with self.assertRaises(RuntimeError) as caught:
            audit.require_schema(con)
        self.assertIn("lifecycle_status", str(caught.exception))

    def test_full_schema_passes(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.executescript(SCHEMA_SQL)
        self.assertIsNone(audit.require_schema(con))

    def test_empty_but_valid_schema_is_healthy(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.executescript(SCHEMA_SQL)
        self.assertEqual(audit.priority_budget(con), [])
        self.assertEqual(audit.derived_document_issues(con), {
            "search_documents_missing": [], "search_documents_extra": [],
            "search_documents_duplicate": [], "search_documents_drift": []})
        self.assertEqual(audit.search_fts_issues(con), {
            "search_fts_missing": [], "search_fts_extra": [],
            "search_fts_duplicate": [], "search_fts_drift": []})

    def test_new_issue_keys_make_the_audit_fail(self):
        report = {"db": "unused", "total_paths": 0, "untriggered_leaves": ["leaf"],
                  "priority_over_budget": [], "search_documents_missing": [],
                  "search_documents_extra": [], "search_documents_duplicate": [],
                  "search_documents_drift": [], "search_fts_missing": [],
                  "search_fts_extra": [], "search_fts_duplicate": [],
                  "search_fts_drift": []}
        self.assertEqual(audit.issue_count(report), 0)
        report["priority_over_budget"] = [{"priority": 1, "paths": 16, "limit": 15}]
        self.assertEqual(audit.issue_count(report), 1)
        report["search_fts_drift"] = [{"uri": "core://a", "field": "content"}]
        self.assertEqual(audit.issue_count(report), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
