"""记忆系统体检（只读）。

用法：python backend/scripts/audit_memory.py [--stale-days 90] [--json]

检查项对应 docs/project/memory-system-guide.md 的 §5.2（分层）、§5.5（定向审计）：
  crowded   父节点子数 > 10 —— URI 层级没有表达出主题关系
  orphan    无入边且非根 —— 删路径留下的死节点
  nodisc    边缺 disclosure —— 无法按触发条件召回
  nostatus  字段 lifecycle_status 为 unspecified —— 只提示待标注，不阻断
  residue   正文仍有旧 "状态:" 专用头部 —— 只提示，不自动改写正文
  conflict  正文旧状态与 lifecycle_status 不一致 —— 字段是唯一真源，只提示
  bootold   显式 Boot 配置指向 obsolete 节点 —— 只提示，不静默改写配置
  bloat     正文 > bloat_min_bytes —— 单条挤占检索预算
  untrigger 叶子节点没有触发词 —— 仅提示，不要求为凑覆盖率绑定泛词
  glossary  零命中、正文命中率 >=5%、绑定节点 >2 —— 定向审查词表质量
  priority  空 namespace 路径口径的 priority 0/1 超额 —— 检索预算被抢占
  search    派生文档缺失/额外/重复/字段漂移 —— 按 live path、memory、edge 逐字段核对
  fts       全文缓存缺失/额外/重复/字段漂移 —— 按 namespace+domain+path 与派生文档核对

缺表/缺列一律抛错，不得静默返回 health。
  stale     超过 N 天未访问 —— 候选归档（新库会全为 0，需运行一段时间才有意义）

只读，不修改任何数据。
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
ROOT_UUID = "00000000-0000-0000-0000-000000000000"


ADVISORY_CHECKS = frozenset({
    "untriggered_leaves",
    "entries_without_status",
    "template_status_residue",
    "status_field_conflicts",
    "obsolete_boot_references",
})
# Legacy body headers are advisory only; lifecycle_status remains the sole truth.
LEGACY_STATUS_HEADERS = {"在用": "active", "已交付": "completed", "已过时": "obsolete"}
STATUS_HEADER_RE = re.compile(r"^状态\s*[:：]\s*(在用|已交付|已过时)\s*$")
# Local policy: these terms produced unrelated glossary links in the migration audit.
GENERIC_KEYWORDS = frozenset(
    "状态 文件 配置 条目 code 任务 test config server profile .cs data 结论 条件 "
    "中心 契约 术语 节点 系统 方案 中文 probe audit 语义 真源 源码 架构 链路 批量".split()
)


PRIORITY_LIMITS = {0: 5, 1: 15}

# Columns each check depends on; a partial schema must fail loudly, not read as healthy.
SCHEMA = {
    "nodes": ("uuid", "lifecycle_status"),
    "paths": ("namespace", "domain", "path", "node_uuid", "edge_id"),
    "memories": ("id", "node_uuid", "content", "deprecated"),
    "edges": ("id", "priority", "disclosure"),
    "search_documents": ("namespace", "domain", "path", "node_uuid", "memory_id",
                         "uri", "content", "disclosure", "priority", "search_terms"),
    "search_documents_fts": ("namespace", "domain", "path", "node_uuid", "uri",
                             "content", "disclosure", "search_terms"),
}


def require_schema(con: sqlite3.Connection) -> None:
    """Raise instead of silently reporting health when a table/column is absent."""
    for table, columns in SCHEMA.items():
        info = con.execute("pragma table_info(%s)" % table).fetchall()
        if not info:
            raise RuntimeError("audit_memory: missing table %r" % table)
        present = {row[1] for row in info}
        missing = [c for c in columns if c not in present]
        if missing:
            raise RuntimeError(
                "audit_memory: table %r missing columns %s" % (table, ", ".join(missing)))


def _norm(value) -> str:
    """NULL and empty disclosures render identically in the live views."""
    return "" if value is None else str(value)



def priority_budget(con: sqlite3.Connection) -> list:
    """Count empty-namespace path rows, not nodes: an alias path still consumes a slot."""
    rows = con.execute(
        """select e.priority, count(*) from paths p
           join edges e on e.id = p.edge_id
           where p.namespace = '' group by e.priority"""
    ).fetchall()
    issues = []
    for priority, paths in sorted(rows, key=lambda r: (r[0] is None, r[0])):
        limit = PRIORITY_LIMITS.get(priority)
        if limit is not None and paths > limit:
            issues.append({"priority": priority, "paths": paths, "limit": limit})
    return issues


def _expected_documents(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        """select p.namespace, p.domain, p.path, p.node_uuid, m.id, m.content,
                  e.priority, e.disclosure
           from paths p
           join memories m on m.node_uuid = p.node_uuid and m.deprecated = 0
           join edges e on e.id = p.edge_id"""
    ).fetchall()
    expected = {}
    for namespace, domain, path, node, memory_id, content, priority, disclosure in rows:
        expected[(namespace, domain, path)] = {
            "node_uuid": node,
            "memory_id": memory_id,
            "content": content,
            "priority": priority,
            "disclosure": _norm(disclosure),
        }
    return expected


def _document_rows(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        """select namespace, domain, path, node_uuid, memory_id, uri, content,
                  disclosure, priority, search_terms
           from search_documents"""
    ).fetchall()
    keyed = {}
    for row in rows:
        keyed.setdefault((row[0], row[1], row[2]), []).append(row)
    return keyed


def derived_document_issues(con: sqlite3.Connection) -> dict:
    """Every live path must have exactly one derived doc matching its node/memory/edge."""
    require_schema(con)
    expected = _expected_documents(con)
    documented = _document_rows(con)
    missing, extra, duplicate, drift = [], [], [], []
    for key, want in sorted(expected.items()):
        namespace, domain, path = key
        uri = "%s://%s" % (domain, path)
        rows = documented.get(key, [])
        if not rows:
            missing.append({"uri": uri, "namespace": namespace})
            continue
        if len(rows) > 1:
            duplicate.append({"uri": uri, "rows": len(rows)})
        for row in rows:
            actual = {"node_uuid": row[3], "memory_id": row[4], "content": row[6],
                      "disclosure": _norm(row[7]), "priority": row[8]}
            for field, wanted in want.items():
                if actual[field] != wanted:
                    drift.append({"uri": uri, "field": field})
            if row[5] != uri:
                drift.append({"uri": uri, "field": "uri"})
    for key in sorted(documented):
        if key not in expected:
            extra.append({"uri": "%s://%s" % (key[1], key[2]), "namespace": key[0]})
    return {"search_documents_missing": missing, "search_documents_extra": extra,
            "search_documents_duplicate": duplicate, "search_documents_drift": drift}


def _fts_rows(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        """select namespace, domain, path, node_uuid, uri, content, disclosure, search_terms
           from search_documents_fts"""
    ).fetchall()
    keyed = {}
    for row in rows:
        keyed.setdefault((row[0], row[1], row[2]), []).append(row)
    return keyed


def search_fts_issues(con: sqlite3.Connection) -> dict:
    """FTS cache must mirror search_documents row for row, keyed by namespace/domain/path."""
    require_schema(con)
    documented = {key: rows[0] for key, rows in _document_rows(con).items()}
    indexed = _fts_rows(con)
    missing, extra, duplicate, drift = [], [], [], []
    for key, doc in sorted(documented.items()):
        namespace, domain, path = key
        uri = "%s://%s" % (domain, path)
        rows = indexed.get(key, [])
        if not rows:
            missing.append({"uri": uri, "namespace": namespace})
            continue
        if len(rows) > 1:
            duplicate.append({"uri": uri, "rows": len(rows)})
        want = {"node_uuid": doc[3], "uri": doc[5], "content": doc[6],
                "disclosure": _norm(doc[7]), "search_terms": doc[9]}
        for row in rows:
            actual = {"node_uuid": row[3], "uri": row[4], "content": row[5],
                      "disclosure": _norm(row[6]), "search_terms": row[7]}
            for field, expected_value in want.items():
                if actual[field] != expected_value:
                    drift.append({"uri": uri, "field": field})
    for key in sorted(indexed):
        if key not in documented:
            extra.append({"uri": "%s://%s" % (key[1], key[2]), "namespace": key[0]})
    return {"search_fts_missing": missing, "search_fts_extra": extra,
            "search_fts_duplicate": duplicate, "search_fts_drift": drift}




def keyword_quality(con: sqlite3.Connection) -> dict:
    """Match the runtime's case-sensitive substring rules, once per live node.

    Thresholds are this installation's review policy, not Nocturne invariants.
    Aliases and deprecated revisions must not inflate the corpus denominator.
    """
    bodies = dict(con.execute(
        """select distinct m.node_uuid, m.content from memories m
           join paths p on p.node_uuid=m.node_uuid
           where p.namespace='' and m.deprecated=0"""
    ))
    words = {}
    for keyword, node in con.execute(
        "select keyword, node_uuid from glossary_keywords where namespace=''"
    ):
        words.setdefault(keyword, set()).add(node)
    issues = {"glossary_zero_hit": [], "glossary_high_frequency": [],
              "glossary_overbound": [], "glossary_generic": []}
    for keyword, nodes in sorted(words.items()):
        hits = sum(keyword in body for body in bodies.values())
        if keyword in GENERIC_KEYWORDS:
            issues["glossary_generic"].append({"keyword": keyword})
        if hits == 0:
            issues["glossary_zero_hit"].append({"keyword": keyword})
        if bodies and hits / len(bodies) >= 0.05:
            issues["glossary_high_frequency"].append(
                {"keyword": keyword, "hits": hits, "corpus_nodes": len(bodies)})
        if len(nodes) > 2:
            issues["glossary_overbound"].append(
                {"keyword": keyword, "nodes": len(nodes)})
    return issues


def _legacy_body_status(content: str):
    """Return the legacy 状态 value only for a dedicated leading header line.

    Fenced code is skipped: a quoted command or sample is not a template header.
    """
    fenced = False
    for line in (content or "").splitlines()[:5]:
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = STATUS_HEADER_RE.match(stripped)
        if match:
            return match.group(1)
    return None


def status_issues(con: sqlite3.Connection, boot=frozenset()) -> dict:
    """Read lifecycle_status as the sole truth; body headers are advisory only.

    Scope matches the former nostatus check: namespace '', live revised
    memories, leaf paths except Boot entries. Residue and conflicts scan every
    live node in that default namespace, including containers and Boot entries.
    """
    rows = con.execute(
        """select p.path, p.node_uuid, m.content, n.lifecycle_status
           from paths p
           join memories m on m.node_uuid = p.node_uuid and m.deprecated = 0
           join nodes n on n.uuid = p.node_uuid
           where p.namespace = ''
           order by p.path"""
    ).fetchall()
    parents = {row[0] for row in con.execute("select parent_uuid from edges")}
    entries_without_status = []
    residue = []
    conflicts = []
    for path, node_uuid, content, field_status in rows:
        if (node_uuid not in parents and path not in boot
                and field_status == "unspecified"):
            entries_without_status.append(path)
        body_status = _legacy_body_status(content)
        if body_status is None:
            continue
        residue.append({"path": path, "body_status": body_status,
                        "field_status": field_status})
        mapped = LEGACY_STATUS_HEADERS[body_status]
        if field_status != "unspecified" and field_status != mapped:
            conflicts.append({"path": path, "body_status": body_status,
                              "field_status": field_status})
    obsolete_boot = [
        {"path": path}
        for path, in con.execute(
            """select p.path from paths p
               join nodes n on n.uuid = p.node_uuid
               where p.namespace = '' and n.lifecycle_status = 'obsolete'
               order by p.path"""
        )
        if path in boot
    ]
    return {
        "entries_without_status": entries_without_status,
        "template_status_residue": residue,
        "status_field_conflicts": conflicts,
        "obsolete_boot_references": obsolete_boot,
    }


def dead_rule_links(con: sqlite3.Connection) -> list:
    """Markdown links to local files must resolve; a rename must not cut the index silently."""
    missing, seen = [], set()
    for path, content in con.execute(
        """select distinct p.path, m.content from memories m
           join paths p on p.node_uuid = m.node_uuid
           where p.namespace = '' and m.deprecated = 0"""
    ):
        text = re.sub(r"```.*?```|`[^`\n]*`", "", content or "", flags=re.S)
        for bracketed, bare in re.findall(r"\]\(<([^>\n]+)>|\]\(([^)\s#]+)", text):
            target = unquote((bracketed or bare).split("#", 1)[0])
            if not re.match(r"[A-Za-z]:", target):
                continue
            if (path, target) not in seen and not Path(target).exists():
                seen.add((path, target))
                missing.append({"path": path, "target": target})
    return missing


def issue_count(report: dict) -> int:
    return sum(len(value) if isinstance(value, list) else value
               for key, value in report.items()
               if key not in {"db", "total_paths"} and key not in ADVISORY_CHECKS)


def db_path() -> str:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    url = cfg["database_url"]
    if not url.startswith("sqlite"):
        raise SystemExit("audit_memory: 仅支持 sqlite 数据库（当前 %s）" % url)
    return url.split("///", 1)[1]


def boot_paths() -> set:
    """L0 节点靠 boot 常驻，不需要触发词。"""
    con = sqlite3.connect("file:" + db_path() + "?mode=ro", uri=True)
    row = con.execute("select boot_uris from presets where is_active=1 limit 1").fetchone()
    con.close()
    if not row or not row[0]:
        return set()
    out = set()
    for uris in json.loads(row[0]).values():
        for uri in uris:
            out.add(uri.split("://", 1)[-1])
    return out


def bloat_limit() -> int:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return int(cfg.get("bloat_min_bytes") or 2400)


def audit(stale_days: int = 90) -> dict:
    con = sqlite3.connect("file:" + db_path() + "?mode=ro", uri=True)
    require_schema(con)
    q = lambda sql, *a: con.execute(sql, a).fetchall()
    one = lambda sql, *a: con.execute(sql, a).fetchone()[0]

    total_paths = one("select count(*) from paths where namespace=''")
    crowded = q(
        """select p.path, count(*) n from edges e
           join paths p on p.node_uuid=e.parent_uuid and p.namespace=''
           group by e.parent_uuid having n > 10 order by n desc"""
    )
    crowded = [{"path": r[0], "children": r[1]} for r in crowded]

    orphans = q(
        """select uuid from nodes
           where uuid != ? and uuid not in (select child_uuid from edges)""",
        ROOT_UUID,
    )

    nodisc = one("select count(*) from edges where disclosure is null or trim(disclosure)=''")

    boot = boot_paths()

    limit = bloat_limit()
    bloat = q(
        """select p.path, length(m.content) n from paths p
           join memories m on m.node_uuid=p.node_uuid and m.deprecated=0
           where p.namespace='' and n > ? order by n desc""",
        limit,
    )
    bloat = [{"path": r[0], "bytes": r[1]} for r in bloat]

    untrigger = [
        r[0]
        for r in q(
            """select p.path from paths p
               where p.namespace=''
                 and p.node_uuid not in (select node_uuid from glossary_keywords where namespace='')
                 and p.node_uuid not in (select parent_uuid from edges)"""
        )
        if r[0] not in boot
    ]

    cutoff = (datetime.now() - timedelta(days=stale_days)).strftime("%Y-%m-%d %H:%M:%S")
    stale = q(
        """select p.path, n.last_accessed_at from paths p
           join nodes n on n.uuid=p.node_uuid
           where p.namespace='' and p.node_uuid not in (select parent_uuid from edges)
             and coalesce(n.last_accessed_at, n.created_at) < ?""",
        cutoff,
    )
    stale = [{"path": r[0], "last_accessed": r[1]} for r in stale]

    report = {
        "db": db_path(),
        "total_paths": total_paths,
        "crowded": crowded,
        "orphan_nodes": [r[0] for r in orphans],
        "edges_without_disclosure": nodisc,
        "dead_rule_links": dead_rule_links(con),
        "bloat_over_%d" % limit: bloat,
        "untriggered_leaves": untrigger,
        "stale_over_%d_days" % stale_days: stale,
    }
    report.update(status_issues(con, boot))
    report.update(keyword_quality(con))
    report["priority_over_budget"] = priority_budget(con)
    report.update(derived_document_issues(con))
    report.update(search_fts_issues(con))
    con.close()
    return report


def main() -> int:
    args = sys.argv[1:]
    stale_days = 90
    if "--stale-days" in args:
        stale_days = int(args[args.index("--stale-days") + 1])
    report = audit(stale_days)

    if "--json" in args:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("记忆系统体检 · %s" % report["db"])
        print("总路径数: %d" % report["total_paths"])
        for key, val in report.items():
            if key in ("db", "total_paths"):
                continue
            if isinstance(val, list):
                bad = len(val)
                detail = "" if not bad else "  ← " + ", ".join(
                    (v.get("path") or v.get("keyword") or v.get("uri") or str(v) if isinstance(v, dict) else str(v)) for v in val[:3]
                )
                label = key + (" (提示)" if key in ADVISORY_CHECKS else "")
                print("  %-28s %d%s" % (label, bad, detail))
            else:
                print("  %-28s %d" % (key, val))

    bad = issue_count(report)
    print("结果: %s" % ("health" if bad == 0 else "%d 项待处理" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
