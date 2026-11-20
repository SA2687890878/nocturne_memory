"""Verify read-only live stdio/semantic delivery with one query embedding.

Uses the configured work database in mode=ro, skips migrations, disables the
embedded UI, and never opens a listening port. Run with the configured MCP
Python interpreter. This checks the service, not a desktop agent's decisions.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    import config
    from sqlalchemy.engine import make_url
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="Relevant task query; sent to the configured embedding provider once")
    parser.add_argument("--expected-uri", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp/memory-runtime-verification.json")
    args = parser.parse_args()
    url = make_url(config.get("database_url"))
    if url.get_backend_name() != "sqlite":
        raise ValueError("This local read-only runtime check requires SQLite.")
    source = Path(url.database).resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    runtime = ROOT / ".tmp/runtime-verification"
    runtime.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ, "NOCTURNE_NO_UI": "1", "SKIP_DB_INIT": "true", "NAMESPACE": "",
        "NOCTURNE_DB_URL": f"sqlite+aiosqlite:///{source.as_uri()}?mode=ro&uri=true",
        "TEMP": str(runtime), "TMP": str(runtime), "TMPDIR": str(runtime),
    }
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "backend/mcp_server.py")],
                                   env=env, cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=45)) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("semantic_search_memory", {
                "query": args.query, "limit": 5, "token_budget": 1200,
            })
            text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
            uris = re.findall(r"^\d+\. (\S+)", text, re.MULTILINE)
            target_rank = next((rank for rank, uri in enumerate(uris, 1) if uri == args.expected_uri), None)
            assert not result.isError and "Semantic candidates for:" in text, "Live semantic tool did not return candidates"
            assert target_rank is not None, "Expected URI absent from semantic Top5"
            assert "Summary [VALID]" in text and "Body not expanded." in text, "Summary-first response missing"
            report = {
                "created_at": datetime.now().astimezone().isoformat(), "interpreter": sys.executable,
                "transport": "stdio", "source_access": "actual configured work DB, SQLite mode=ro; initialization skipped",
                "embedded_ui_disabled": True, "tool_count": len(tools.tools),
                "query_embedding_requests": 1, "expected_uri": args.expected_uri,
                "target_rank": target_rank, "candidate_uris": uris,
                "valid_summaries": text.count("Summary [VALID]"), "body_expanded": False,
                "response_chars": len(text), "provider_llm_token_usage": "not measured",
                "scope": "Actual service and embedding API; no claim about desktop agent dispatch behavior",
            }
    report["source_sha256_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert report["source_sha256_unchanged"], "Work database changed during read-only runtime check; inspect concurrent writers"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
