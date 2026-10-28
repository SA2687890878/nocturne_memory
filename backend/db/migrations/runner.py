import asyncio
import os
import importlib.util
import logging
import json
import sys
import uuid
from pathlib import Path
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import MetaData, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def _get_app_root() -> str:
    """Return the backend app root so backups land in a stable location."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _announce_backup(message: str):
    """Emit backup status without polluting MCP stdio transport."""
    logger.info(message)
    print(message, file=sys.stderr, flush=True)


_SQLITE_BACKUP_SUFFIX = ".bak"


def _sqlite_copy_file(source_path: str, target_path: str) -> None:
    """Copy a live SQLite database with the stdlib online backup API."""
    import sqlite3

    expected_source = Path(source_path).resolve()
    source = sqlite3.connect(expected_source.as_uri() + "?mode=ro", uri=True)
    try:
        actual_source = next(row[2] for row in source.execute("PRAGMA database_list") if row[1] == "main")
        if Path(actual_source).resolve() != expected_source:
            raise RuntimeError("SQLite backup source does not match the expected database")
        source.execute("PRAGMA query_only=ON")
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _sqlite_integrity_verdict(path: str) -> str:
    """Return the integrity_check verdict of a SQLite file."""
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


async def _backup_sqlite_online(db_path: str, timestamp: str) -> str:
    """Back up a live SQLite database without stalling the event loop.

    WAL: a plain file copy is not a valid snapshot, so the copy goes through the
    stdlib online backup API in a worker thread. The result is written to a
    unique pending file, verified, then published with an atomic rename. A failed
    artifact is kept on disk on purpose so the original file can be inspected,
    and the migration aborts.
    """
    unique = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    pending_path = f"{db_path}.{timestamp}.{unique}{_SQLITE_BACKUP_SUFFIX}.pending"
    final_path = f"{db_path}.{timestamp}.{unique}{_SQLITE_BACKUP_SUFFIX}"

    _announce_backup(
        f"Pending migrations detected. Backing up SQLite database to {final_path}"
    )
    try:
        await asyncio.to_thread(_sqlite_copy_file, db_path, pending_path)
        verdict = await asyncio.to_thread(_sqlite_integrity_verdict, pending_path)
        if verdict.strip().lower() != "ok":
            raise RuntimeError(f"SQLite backup integrity_check failed: {verdict}")
        os.replace(pending_path, final_path)
    except Exception as e:
        logger.error(f"Failed to backup database: {e}. Aborting migration.")
        raise RuntimeError(
            f"Database backup failed: {e} (artifacts left at {pending_path})"
        ) from e

    return final_path


def _json_safe(value):
    """Convert DB-native values into JSON-serializable primitives."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


async def _backup_postgresql_via_python(engine: AsyncEngine, backup_path: str):
    """Fallback data export for PostgreSQL when pg_dump is unavailable.

    This exports all reflected tables in dependency order as JSON.
    WARNING: This ONLY exports data. It does NOT include schema (DDL),
    indexes, constraints, or sequences. It cannot automatically recover
    the database from structural migration failures (like DROP TABLE).
    There is currently no automated restore script for this format.
    """
    metadata = MetaData()

    # Use REPEATABLE READ to ensure a consistent snapshot across all tables.
    iso_engine = engine.execution_options(isolation_level="REPEATABLE READ")

    async with iso_engine.connect() as conn:
        async with conn.begin():
            await conn.run_sync(lambda sync_conn: metadata.reflect(sync_conn))

            table_order = [table.name for table in metadata.sorted_tables]
            
            # Stream the JSON to disk instead of materializing everything in memory
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write('{\n')
                f.write('  "format": "nocturne-postgresql-backup-v1",\n')
                f.write(f'  "created_at": "{datetime.now().isoformat()}Z",\n')
                f.write(f'  "table_order": {json.dumps(table_order)},\n')
                f.write('  "tables": {\n')

                for i, table in enumerate(metadata.sorted_tables):
                    if i > 0:
                        f.write(',\n')
                    f.write(f'    {json.dumps(table.name)}: [\n')
                    
                    # yield_per(1000) enables server-side cursors in supported drivers (like asyncpg)
                    # to prevent loading the entire table into memory at once.
                    result = await conn.stream(select(table).execution_options(yield_per=1000))
                    first_row = True
                    
                    async for row in result:
                        if not first_row:
                            f.write(',\n')
                        else:
                            first_row = False
                        
                        row_dict = {key: _json_safe(value) for key, value in row._mapping.items()}
                        f.write('      ' + json.dumps(row_dict, ensure_ascii=False))
                    
                    f.write('\n    ]')
                
                f.write('\n  }\n}\n')


async def run_migrations(engine: AsyncEngine):
    """
    Run all pending migrations in order.
    Keeps track of applied migrations in the 'schema_migrations' table.
    """
    # Ensure migrations table exists
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "    version TEXT PRIMARY KEY, "
            "    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        
    # Get applied migrations
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version FROM schema_migrations ORDER BY version ASC"))
        applied_versions = {row[0] for row in result.fetchall()}

    # Discover migration files
    migrations_dir = os.path.dirname(__file__)
    migration_files = []
    for file in os.listdir(migrations_dir):
        if file.endswith(".py") and file[0].isdigit():
            migration_files.append(file)
            
    migration_files.sort()

    pending_migrations = [f for f in migration_files if f not in applied_versions]

    if not pending_migrations:
        return

    # Backup database before migration
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if str(engine.url).startswith("sqlite"):
        db_path = engine.url.database
        if db_path and db_path != ":memory:" and os.path.exists(db_path):
            backup_path = await _backup_sqlite_online(db_path, timestamp)
            _announce_backup(f"SQLite backup saved to {backup_path}")
                
    elif str(engine.url).startswith("postgresql"):
        import subprocess
        db_name = engine.url.database or "db"
        
        # Store backups under the app root (<repo>/backend locally, /app in Docker).
        backup_dir = os.path.join(_get_app_root(), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_base = os.path.join(backup_dir, f"{db_name}_{timestamp}")
        dump_backup_path = f"{backup_base}.sql"
        json_backup_path = f"{backup_base}.json"
        
        _announce_backup(
            f"Pending migrations detected. Backing up PostgreSQL database to {dump_backup_path}"
        )
        try:
            # Convert asyncpg/psycopg2 URL to standard postgresql:// for pg_dump
            pg_url = engine.url.set(drivername="postgresql")
            
            # Create a URL without the password so pg_dump falls back to PGPASSWORD
            url_without_password = pg_url.set(password=None)
            safe_pg_url = url_without_password.render_as_string(hide_password=False)
            
            # pg_dump strictly requires ?sslmode=disable, asyncpg requires ?ssl=disable
            safe_pg_url = safe_pg_url.replace("ssl=disable", "sslmode=disable")
            
            # Pass password securely via environment variable
            dump_env = os.environ.copy()
            if pg_url.password:
                dump_env["PGPASSWORD"] = pg_url.password
                
            # pg_dump streams the remote database to a local file
            subprocess.run(
                ["pg_dump", safe_pg_url, "-f", dump_backup_path],
                check=True,
                capture_output=True,
                text=True,
                env=dump_env
            )
            _announce_backup(f"PostgreSQL backup successfully saved to {dump_backup_path}")
        except FileNotFoundError:
            warning_msg = (
                "================================================================================\n"
                "[EN] WARNING: 'pg_dump' not found\n"
                "\n"
                "     Cannot create a full backup. Falling back to a JSON data-only export.\n"
                "     If this migration drops tables/columns, YOU CANNOT AUTOMATICALLY RESTORE THEM.\n"
                "     Migration will continue in 10 seconds.\n"
                "     Press Ctrl+C now if you want to abort.\n"
                "\n"
                "[CN] 警告：未找到 'pg_dump'\n"
                "\n"
                "     无法创建完整备份。现降级为仅导出 JSON 数据。\n"
                "     如果本次迁移包含删除表或列的操作，您将无法自动恢复数据库！\n"
                "     迁移将在 10 秒后继续。\n"
                "     如果要中止，请现在按 Ctrl+C。\n"
                "================================================================================"
            )
            _announce_backup(warning_msg)
            
            import asyncio
            for i in range(10, 0, -1):
                msg = f"[!] Proceeding in {i}s... / {i}秒后继续... (Press Ctrl+C to abort / 按 Ctrl+C 终止)   "
                print(msg, end="\r", file=sys.stderr, flush=True)
                await asyncio.sleep(1)
            print(
                "[!] Starting migration now. Do not close this window. / 现在开始迁移。请不要关闭此窗口。                                        ",
                file=sys.stderr,
                flush=True,
            )
            
            await _backup_postgresql_via_python(engine, json_backup_path)
            _announce_backup(
                f"[!] Data export (JSON) saved to {json_backup_path}. Schema changes are NOT protected."
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"pg_dump failed: {e.stderr}. Aborting migration.")
            raise RuntimeError(f"Database backup failed: {e.stderr}") from e
        except Exception as e:
            logger.error(f"Failed to backup PostgreSQL database: {e}. Aborting migration.")
            raise RuntimeError(f"Database backup failed: {e}") from e

    for file in pending_migrations:
        logger.info(f"Applying migration: {file}")
        
        # Dynamically import the migration module
        safe_stem = file[:-3].replace(".", "_")
        module_name = f"db.migrations.{safe_stem}"
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(migrations_dir, file))
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "db.migrations"
        spec.loader.exec_module(module)
        
        # Execute the migration
        if hasattr(module, 'up'):
            await module.up(engine)
        else:
            logger.warning(f"Warning: {file} has no 'up' async function.")

        # Record the migration
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": file}
            )

    logger.info("Successfully applied all pending migrations.")

