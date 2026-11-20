"""Reproduce retrieval/disclosure checks on a read-only snapshot of the work DB.

The source is accessed read-only and never migrated. Windows fallback copies
only while writers are excluded and no WAL exists. Stdio validation uses only
the temporary copy, with the embedded UI disabled. No embedding calls.
Run from the repo root: .venv/Scripts/python.exe scripts/evaluate-progressive-disclosure.py
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def snapshot_source(source, snapshot):
    """Prefer SQLite backup; handle a WAL-mode DB whose directory is read-only."""
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            with closing(sqlite3.connect(snapshot)) as destination:
                origin.backup(destination)
        return "SQLite mode=ro backup; no source initialization/migration"
    except sqlite3.OperationalError as exc:
        if os.name != "nt" or "unable to open database file" not in str(exc):
            raise

    # A WAL-mode file may need new -wal/-shm files even for mode=ro. Do not
    # change directory permissions or use immutable=1 on an unlocked live DB.
    # FILE_SHARE_READ refuses both existing and new writers while copying.
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel.CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    handle = create_file(str(source), 0x80000000, 0x1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close_handle = kernel.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(handle)
        raise
    with os.fdopen(fd, "rb") as locked:
        wal = Path(str(source) + "-wal")
        if wal.exists():
            raise RuntimeError("WAL sidecar exists; a raw source copy is unsafe. Use a readable SQLite backup instead.")
        with snapshot.open("wb") as destination:
            shutil.copyfileobj(locked, destination)
    return "Windows read-only handle excluding writers, no WAL sidecar, locked copy; no source writes/migration"


def target_rank(rows, target):
    return next((rank for rank, row in enumerate(rows, 1)
                 if target in [row["uri"], *(alias["uri"] for alias in row["aliases"])]), None)


async def evaluate(snapshot):
    import db
    from system_views import (
        _estimate_context_tokens, fetch_and_format_memory, fetch_and_format_summary,
    )

    db.set_runtime_database_url(f"sqlite+aiosqlite:///{snapshot.as_uri()}?mode=ro&uri=true")
    search = db.get_search_indexer()
    cases = read_json(ROOT / "docs/project/keyword-retrieval-contrast-2026-11-19.json")["cases"]
    negatives = read_json(ROOT / "docs/project/lexical-negative-query-eval-2026-11-19.json")["results"]
    comparisons, reads, negative_results = [], [], []
    try:
        for case in cases:
            for field in ("keyword_query", "natural_query"):
                for partial in (False, True):
                    baseline = await search.search(case[field], include_partial=partial)
                    compact = await search.search(case[field], include_partial=partial, include_snippets=False)
                    same = compact == [{**row, "snippet": ""} for row in baseline]
                    if not same:
                        raise AssertionError(f"Candidate/ranking drift: {case['case_id']} {field} partial={partial}")
                    comparisons.append({
                        "case_id": case["case_id"], "query_kind": field,
                        "include_partial": partial, "identical_except_snippet": same,
                        "target_rank": target_rank(compact, case["target_uri"]),
                        "candidates": [row["uri"] for row in compact],
                    })
        for case in negatives:
            baseline = await search.search(case["query"])
            compact = await search.search(case["query"], include_snippets=False)
            if compact != [{**row, "snippet": ""} for row in baseline]:
                raise AssertionError(f"Negative-query candidate drift: {case['id']}")
            negative_results.append({"id": case["id"], "candidate_count": len(compact)})

        for uri in dict.fromkeys(case["target_uri"] for case in cases):
            full = await fetch_and_format_memory(uri, track_access=False)
            summary = await fetch_and_format_summary(uri)
            excerpt = await fetch_and_format_memory(uri, track_access=False, start_line=1, end_line=3)
            reads.append({
                "uri": uri,
                "full_chars": len(full), "summary_chars": len(summary), "first_three_lines_chars": len(excerpt),
                "full_estimated_tokens": _estimate_context_tokens(full),
                "summary_estimated_tokens": _estimate_context_tokens(summary),
                "first_three_lines_estimated_tokens": _estimate_context_tokens(excerpt),
                "summary_valid": "Summary [VALID]" in summary,
            })
    finally:
        await db.close_db()
        db.set_runtime_database_url(None)

    totals = {field: sum(row[field] for row in reads) for field in (
        "full_chars", "summary_chars", "first_three_lines_chars", "full_estimated_tokens",
        "summary_estimated_tokens", "first_three_lines_estimated_tokens",
    )}
    totals["summary_estimated_token_reduction_pct"] = round(
        100 * (1 - totals["summary_estimated_tokens"] / max(1, totals["full_estimated_tokens"])), 2,
    )
    return {
        "candidate_comparisons": len(comparisons), "candidate_comparisons_identical": len(comparisons),
        "keyword_strict_target_hits": sum(row["target_rank"] is not None for row in comparisons
                                          if row["query_kind"] == "keyword_query" and not row["include_partial"]),
        "keyword_cases": len(cases), "negative_queries": len(negative_results),
        "negative_strict_zero_candidates": sum(row["candidate_count"] == 0 for row in negative_results),
        "read_comparison_uris": len(reads), "response_size_totals": totals,
        "retrieval_cases": comparisons, "negative_cases": negative_results, "read_cases": reads,
    }


async def verify_stdio(snapshot):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        **os.environ, "NOCTURNE_NO_UI": "1", "SKIP_DB_INIT": "true", "NAMESPACE": "",
        "NOCTURNE_DB_URL": f"sqlite+aiosqlite:///{snapshot.as_posix()}",
        "TEMP": str(snapshot.parent), "TMP": str(snapshot.parent), "TMPDIR": str(snapshot.parent),
    }
    uri = read_json(ROOT / "docs/project/keyword-retrieval-contrast-2026-11-19.json")["cases"][0]["target_uri"]
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "backend/mcp_server.py")], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next(item for item in tools.tools if item.name == "read_memory")
            fields = set(tool.inputSchema["properties"])
            assert {"uri", "detail", "start_line", "end_line"} <= fields
            semantic_tool = next(item for item in tools.tools if item.name == "semantic_search_memory")
            assert "token_budget" in semantic_tool.inputSchema["properties"]
            invalid_budget = await session.call_tool("semantic_search_memory", {"query": "protocol validation only", "token_budget": -1})
            invalid_text = "\n".join(part.text for part in invalid_budget.content if hasattr(part, "text"))
            assert "Error: token_budget must be between 0 and 20000." in invalid_text
            summary_result = await session.call_tool("read_memory", {"uri": uri, "detail": "summary"})
            excerpt_result = await session.call_tool("read_memory", {"uri": uri, "start_line": 1, "end_line": 2})
            summary = "\n".join(part.text for part in summary_result.content if hasattr(part, "text"))
            excerpt = "\n".join(part.text for part in excerpt_result.content if hasattr(part, "text"))
            assert not summary_result.isError and not excerpt_result.isError
            assert "Summary [VALID]" in summary and "Body and related memories were not expanded." in summary
            assert "Content lines: 1-" in excerpt and "Partial body read" in excerpt
            return {
                "transport": "stdio", "database": "temporary snapshot only", "tool_count": len(tools.tools),
                "read_memory_fields": sorted(fields), "summary_read_ok": True, "line_range_read_ok": True,
                "embedded_ui_disabled": True,
                "semantic_budget_validation_ok": True,
            }


def audit_semantic_snapshot(snapshot, source_index):
    """Compare full sync hashes locally; no model, query embedding or writes."""
    import config
    from semantic_sync import load_source_documents, DIMENSIONS, DOCUMENT_FORMAT_VERSION
    from vector_index import VectorIndex
    from vector_index_sync import validate_source_documents

    if not source_index.is_file():
        return {"status": "unavailable", "reason": "semantic sidecar does not exist"}
    before = hashlib.sha256(source_index.read_bytes()).hexdigest()
    target = snapshot.parent / "work-memory-vectors.db"
    access = snapshot_source(source_index, target)
    _path, documents = load_source_documents(f"sqlite+aiosqlite:///{snapshot.as_posix()}")
    current = validate_source_documents(documents)
    model = str((config.get("embedding") or {}).get("model") or "nvidia/nemotron-3-embed-1b")
    with VectorIndex(target, dimensions=DIMENSIONS, model_name=model,
                     document_format_version=DOCUMENT_FORMAT_VERSION, read_only=True) as index:
        existing = index.list_documents()
        health = index.health_check()
    shared = set(current) & set(existing)
    result = {
        "source_access": access, "source_documents": len(current), "index_documents": len(existing),
        "missing": sorted(set(current) - set(existing)), "stale_paths": sorted(set(existing) - set(current)),
        "hash_mismatches": sorted(uri for uri in shared if current[uri]["content_hash"] != existing[uri]["content_hash"]),
        "version_mismatches": sorted(uri for uri in shared if current[uri]["memory_id"] != existing[uri]["memory_id"]),
        "metadata_mismatches": sorted(uri for uri in shared if any(current[uri].get(key, "") != existing[uri].get(key, "")
                                                                for key in ("namespace", "domain", "path", "lifecycle_status"))),
        "integrity_ok": health["ok"], "embedding_requests": 0,
        "source_sha256_unchanged_after_validation": hashlib.sha256(source_index.read_bytes()).hexdigest() == before,
    }
    result["status"] = "pass" if health["ok"] and not any(result[key] for key in (
        "missing", "stale_paths", "hash_mismatches", "version_mismatches", "metadata_mismatches",
    )) else "needs_sync"
    return result


async def main():
    from sqlalchemy.engine import make_url
    import config
    from db.namespace import _namespace, set_namespace

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp/progressive-disclosure-evaluation.json")
    parser.add_argument("--semantic-audit", action="store_true", help="Audit sidecar hashes on a read-only copy; no embedding API")
    args = parser.parse_args()
    url = make_url(config.get("database_url"))
    if url.get_backend_name() != "sqlite":
        raise ValueError("This read-only evaluation currently supports configured SQLite databases only.")
    source = Path(url.database).resolve()
    if not source.is_file():
        raise FileNotFoundError("Configured SQLite database does not exist.")
    temp_root = ROOT / ".tmp"
    temp_root.mkdir(exist_ok=True)
    token = set_namespace("")
    try:
        with tempfile.TemporaryDirectory(prefix="progressive-eval-", dir=temp_root) as directory:
            snapshot = Path(directory) / "snapshot.db"
            source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
            source_access = snapshot_source(source, snapshot)
            with closing(sqlite3.connect(snapshot)) as check:
                if check.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise RuntimeError("Temporary snapshot integrity check failed.")
            report = {
                "created_at": datetime.now().astimezone().isoformat(),
                "source_access": source_access,
                "snapshot_sha256_before_protocol": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "token_method": "ceil(UTF-8 bytes / 3), complete response text; not provider token usage",
                "limitations": [
                    "Existing 18-case manually compressed queries; no new blind recall claim.",
                    "Response-size comparison only; summaries/excerpts may not be sufficient evidence for every task.",
                    "Read-only SQL projection/namespace/version boundaries are covered by isolated regression tests.",
                    "Stdio on a temporary snapshot does not establish that an existing desktop client reloaded its tools.",
                ],
                "evaluation": await evaluate(snapshot),
                "protocol": await verify_stdio(snapshot),
            }
            report["source_sha256_unchanged_after_validation"] = (
                hashlib.sha256(source.read_bytes()).hexdigest()
                == source_hash_before
            )
            if args.semantic_audit:
                report["semantic_index_audit"] = audit_semantic_snapshot(snapshot, source.with_name("work-memory-vectors.db"))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"output": str(args.output.resolve()), **{
                key: value for key, value in report["evaluation"].items()
                if key not in {"retrieval_cases", "negative_cases", "read_cases"}
            }, "protocol": report["protocol"], "semantic_index_audit": report.get("semantic_index_audit")}, ensure_ascii=False, indent=2))
    finally:
        _namespace.reset(token)


if __name__ == "__main__":
    asyncio.run(main())
