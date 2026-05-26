"""
System API — Database switching support.

Allows listing all .db files in the configured database directories and
switching the active database at runtime without restarting the server.

Configuration (in .env):
  DB_DIRS=C:/path/one,D:/path/two   # comma-separated list of directories
  DATABASE_DIR=C:/path              # legacy single-directory fallback
"""

import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import switch_database, get_current_database_url

router = APIRouter(prefix="/system", tags=["system"])


def _get_db_dirs() -> list[Path]:
    """Return the list of directories to scan for .db files.

    Reads DB_DIRS (comma-separated paths) first.  Falls back to the
    legacy DATABASE_DIR single-directory variable if DB_DIRS is absent.
    """
    dirs_raw = os.getenv("DB_DIRS", "").strip()
    if dirs_raw:
        return [Path(p.strip()) for p in dirs_raw.split(",") if p.strip()]
    legacy = os.getenv("DATABASE_DIR", "").strip()
    if legacy:
        return [Path(legacy)]
    return []


class SwitchRequest(BaseModel):
    db_path: str  # absolute path to the .db file, e.g. "D:/novels/book.db"


@router.get("/databases")
async def list_databases():
    """List all .db files across all configured directories with metadata."""
    db_dirs = _get_db_dirs()
    missing = [str(d) for d in db_dirs if not d.exists()]
    if missing:
        raise HTTPException(500, f"Database director{'y' if len(missing) == 1 else 'ies'} not found: {', '.join(missing)}")
    if not db_dirs:
        raise HTTPException(500, "No database directories configured. Set DB_DIRS in .env")

    current_url = get_current_database_url()
    current_path = ""
    if current_url:
        # extract file path from sqlite URL
        # sqlite+aiosqlite:///E:/path/to/file.db
        after_triple = current_url.split("///", 1)[-1] if "///" in current_url else ""
        current_path = str(Path(after_triple).resolve()) if after_triple else ""

    dbs = []
    seen: set[Path] = set()
    for db_dir in db_dirs:
        for f in sorted(db_dir.glob("*.db")):
            resolved = f.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            # Get basic stats via sync sqlite (lightweight, just row counts)
            stats = {"memories": 0, "nodes": 0, "edges": 0}
            try:
                conn = sqlite3.connect(str(f))
                for table in stats:
                    try:
                        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                        stats[table] = count
                    except Exception:
                        pass
                conn.close()
            except Exception:
                pass

            abs_path = str(f.resolve())
            size_kb = round(f.stat().st_size / 1024, 1)
            dbs.append({
                "name": f.name,
                "path": abs_path,
                "dir": str(f.parent.resolve()),
                "size_kb": size_kb,
                "size_mb": round(size_kb / 1024, 2),
                "is_current": abs_path == current_path,
                **stats,
            })

    return {
        "current_db": current_path,
        "databases": dbs,
    }


@router.post("/switch-database")
async def switch_db(req: SwitchRequest):
    """Switch the active database to the specified .db file (full path)."""
    target = Path(req.db_path)
    if not req.db_path.endswith(".db"):
        raise HTTPException(400, "Only .db files are supported")
    if not target.exists():
        raise HTTPException(404, f"Database file not found: {req.db_path}")

    # Ensure the requested file lives inside one of the configured directories
    db_dirs = _get_db_dirs()
    resolved = target.resolve()
    if db_dirs and not any(resolved.is_relative_to(d.resolve()) for d in db_dirs if d.exists()):
        raise HTTPException(403, "Database file is outside the configured DB_DIRS")

    # Build the SQLAlchemy URL with forward slashes
    db_path_fwd = str(resolved).replace("\\", "/")
    new_url = f"sqlite+aiosqlite:///{db_path_fwd}"

    result = await switch_database(new_url)
    return result
