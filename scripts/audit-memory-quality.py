#!/usr/bin/env python3
"""只读检查 Nocturne 个人记忆库质量，不修改数据库。"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

def resolve_database(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    url = config["database_url"]
    if not url.startswith(("sqlite+aiosqlite:///", "sqlite:///")):
        raise SystemExit("当前只读质量审计脚本仅支持 SQLite 数据库")
    prefix = "sqlite+aiosqlite:///" if url.startswith("sqlite+aiosqlite:///") else "sqlite:///"
    return Path(url[len(prefix):])

def grams(value: str) -> set[str]:
    value = re.sub(r"\s+", "", (value or "").casefold())
    if len(value) < 3:
        return {value} if value else set()
    return {value[i:i+3] for i in range(len(value)-2)}

def main() -> int:
    parser = argparse.ArgumentParser(description="只读审计 Nocturne 记忆质量")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.json")
    parser.add_argument("--db", type=Path, help="可选：覆盖 config.json 中的 SQLite 路径")
    args = parser.parse_args()
    db_path = args.db or resolve_database(args.config)
    if not db_path.is_file():
        raise SystemExit(f"数据库不存在：{db_path}")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        scalar = lambda sql: conn.execute(sql).fetchone()[0]
        counts = {name: scalar(f"SELECT COUNT(*) FROM {table}") for name, table in
                  (("memories","memories"),("nodes","nodes"),("paths","paths"),("search_documents","search_documents"))}
        lifecycle = {row["lifecycle_status"]: row["n"] for row in
                     conn.execute("SELECT lifecycle_status, COUNT(*) n FROM nodes GROUP BY lifecycle_status")}
        latest = list(conn.execute("""
            SELECT m.id,m.node_uuid,m.content,m.summary_content,m.deprecated,m.migrated_to,n.lifecycle_status
            FROM memories m
            JOIN (SELECT node_uuid,MAX(id) id FROM memories GROUP BY node_uuid) x ON x.id=m.id
            JOIN nodes n ON n.uuid=m.node_uuid
        """))
        current = [r for r in latest if not r["deprecated"] and r["migrated_to"] is None]
        missing_summary = [r["id"] for r in current if not (r["summary_content"] or "").strip()]
        hashes: dict[str,list[int]] = defaultdict(list)
        for row in current:
            normalized = re.sub(r"\s+"," ",row["content"] or "").strip().casefold()
            if len(normalized) >= 40:
                hashes[hashlib.sha256(normalized.encode("utf-8")).hexdigest()].append(row["id"])
        exact_duplicates = [ids for ids in hashes.values() if len(ids)>1]
        docs = list(conn.execute("""
            SELECT d.uri,d.memory_id,d.summary_content
            FROM search_documents d JOIN memories m ON m.id=d.memory_id
            WHERE m.deprecated=0 AND m.migrated_to IS NULL
              AND m.id=(SELECT MAX(m2.id) FROM memories m2 WHERE m2.node_uuid=m.node_uuid)
            ORDER BY d.uri
        """))
        unique_docs = {}
        for d in docs:
            unique_docs.setdefault(d["memory_id"],d)
        unique = list(unique_docs.values())
        near_duplicates = []
        for i,left in enumerate(unique):
            a=left["summary_content"] or ""
            if len(a.strip())<20: continue
            ga=grams(a)
            for right in unique[i+1:]:
                b=right["summary_content"] or ""
                if len(b.strip())<20: continue
                gb=grams(b); union=ga|gb
                jaccard=len(ga&gb)/len(union) if union else 0.0
                sequence=SequenceMatcher(None,a,b,autojunk=False).ratio()
                if sequence>=0.72 or (sequence>=0.50 and jaccard>=0.28):
                    near_duplicates.append({
                        "left_uri":left["uri"],"left_memory_id":left["memory_id"],
                        "right_uri":right["uri"],"right_memory_id":right["memory_id"],
                        "summary_sequence_ratio":round(sequence,4),
                        "summary_trigram_jaccard":round(jaccard,4),"review_required":True})
        near_duplicates.sort(key=lambda x:(x["summary_sequence_ratio"],x["summary_trigram_jaccard"]),reverse=True)
        summary_mismatch=[r[0] for r in conn.execute("""
            SELECT d.uri FROM search_documents d JOIN memories m ON m.id=d.memory_id
            WHERE COALESCE(d.summary_content,'')<>COALESCE(m.summary_content,'')
        """)]
        missing_disclosure=scalar("SELECT COUNT(*) FROM search_documents WHERE disclosure IS NULL OR trim(disclosure)=''")
        orphan_docs=scalar("SELECT COUNT(*) FROM search_documents d LEFT JOIN memories m ON m.id=d.memory_id WHERE m.id IS NULL")
        pathless=[{"node_uuid":r[0],"lifecycle_status":r[1]} for r in conn.execute("""
            SELECT n.uuid,n.lifecycle_status FROM nodes n LEFT JOIN paths p ON p.node_uuid=n.uuid WHERE p.node_uuid IS NULL
        """)]
        unspecified=[]
        for r in conn.execute("""
            SELECT n.uuid,m.id,m.summary_content,group_concat(d.uri,' | ') uris
            FROM nodes n
            LEFT JOIN (SELECT m1.* FROM memories m1 JOIN (SELECT node_uuid,MAX(id) id FROM memories GROUP BY node_uuid) x ON x.id=m1.id) m ON m.node_uuid=n.uuid
            LEFT JOIN search_documents d ON d.node_uuid=n.uuid
            WHERE COALESCE(n.lifecycle_status,'unspecified')='unspecified'
            GROUP BY n.uuid,m.id,m.summary_content ORDER BY m.id
        """):
            unspecified.append({"node_uuid":r["uuid"],"memory_id":r["id"],"uris":r["uris"],"summary":r["summary_content"]})
        report={
            "database":str(db_path),"read_only":True,"counts":counts,"current_memory_versions":len(current),
            "lifecycle":lifecycle,"missing_current_summaries":missing_summary,
            "exact_duplicate_memory_id_groups":exact_duplicates,"near_duplicate_candidates":near_duplicates,
            "near_duplicate_method":"摘要字符三元组 Jaccard + SequenceMatcher；只生成候选，不自动合并；同一 Memory ID 的 URI 别名先去重",
            "search_document_summary_mismatches":summary_mismatch,"missing_disclosure_count":missing_disclosure,
            "orphan_search_document_count":orphan_docs,"pathless_nodes":pathless,
            "unspecified_lifecycle_records":unspecified,
            "notes":["历史 deprecated 版本不纳入当前摘要缺失判断。","相同 Memory ID 的多个 URI 是别名入口，不计为重复记忆。",
                     "unspecified 生命周期状态只报告，不自动判定过期。","脚本只读，不执行更新、合并或删除。"]}
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    finally:
        conn.close()

if __name__=="__main__":
    raise SystemExit(main())
