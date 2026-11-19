"""Safe diagnostics for the configured local memory database."""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from urllib.parse import unquote

import config


def diagnose_memory_database() -> dict[str, object]:
    url = str(config.get("database_url") or "")
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return {"database_type": "non-sqlite", "database_readable": False,
                "database_writable": False, "write_probe": "unsupported_database_type"}
    path = Path(unquote(url[len(prefix):]))
    result: dict[str, object] = {
        "database_type": "sqlite", "database_file_exists": path.is_file(),
        "database_readable": False, "database_writable": False,
        "write_probe": "not_run",
    }
    if not path.is_file():
        result["write_probe"] = "database_file_missing"
        return result
    try:
        read_con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            read_con.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        finally:
            read_con.close()
        result["database_readable"] = True
    except Exception as exc:
        result["read_error"] = type(exc).__name__
        result["write_probe"] = "read_failed"
        return result

    probe_name = "__nocturne_write_probe_" + uuid.uuid4().hex
    con = None
    try:
        con = sqlite3.connect(path, timeout=5, isolation_level=None)
        con.execute("BEGIN IMMEDIATE")
        con.execute(f'CREATE TABLE "{probe_name}" (id INTEGER PRIMARY KEY)')
        con.execute("ROLLBACK")
        leftover = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (probe_name,)
        ).fetchone()
        if leftover:
            raise RuntimeError("write probe rollback left a temporary schema object")
        result["database_writable"] = True
        result["write_probe"] = "passed_and_rolled_back"
    except Exception as exc:
        if con is not None:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
        result["database_writable"] = False
        result["write_probe"] = "failed"
        result["write_error"] = type(exc).__name__
    finally:
        if con is not None:
            con.close()
    return result
