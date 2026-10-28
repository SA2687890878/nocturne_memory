"""Schema-level tests for the memory lifecycle v3 data foundation.

Covers T01-T06 from docs/features/memory-lifecycle-v3/03-design.md section 26.
Every test works on its own temporary SQLite file; no shared or live database is
touched.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import String, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from db.migrations import runner
from db.models import Base, LIFECYCLE_STATUSES


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_ROOT / "db" / "migrations"
MIGRATION_015 = "015_add_node_lifecycle_status.py"

LEGACY_NODES_DDL = (
    "CREATE TABLE nodes ("
    " uuid VARCHAR(36) NOT NULL PRIMARY KEY,"
    " created_at DATETIME,"
    " last_accessed_at DATETIME"
    ")"
)

SCHEMA_MIGRATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version TEXT PRIMARY KEY,"
    " applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ")"
)


@pytest_asyncio.fixture
async def tmp_engine(tmp_path):
    db_path = tmp_path / "schema.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        yield engine, db_path
    finally:
        await engine.dispose()


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(
        "test_migration_" + filename[:-3], MIGRATIONS_DIR / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_files():
    return sorted(
        path.name
        for path in MIGRATIONS_DIR.iterdir()
        if path.suffix == ".py" and path.name[0].isdigit()
    )


def _read_lifecycle_column(sync_conn):
    columns = {column["name"]: column for column in inspect(sync_conn).get_columns("nodes")}
    column = columns["lifecycle_status"]
    return {
        "is_string": isinstance(column["type"], String),
        "length": getattr(column["type"], "length", None),
        "nullable": column["nullable"],
        "default": str(column["default"] or ""),
    }


def _lifecycle_columns(sync_conn):
    return [
        column["name"]
        for column in inspect(sync_conn).get_columns("nodes")
        if column["name"] == "lifecycle_status"
    ]


def _sqlite_verdict(path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def _assert_contract(shape):
    assert shape["is_string"] is True
    assert shape["length"] == 16
    assert shape["nullable"] is False
    assert "'unspecified'" in shape["default"]


@pytest.mark.asyncio
async def test_fresh_model_schema_matches_contract(tmp_engine):
    """T01: the model-created schema carries type, default and NOT NULL."""
    engine, _ = tmp_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        shape = await conn.run_sync(_read_lifecycle_column)

    _assert_contract(shape)


@pytest.mark.asyncio
async def test_fresh_schema_accepts_four_values_and_rejects_bad_ones(tmp_engine):
    """T04 + T05: four legal values round-trip; invalid, empty and NULL are refused."""
    engine, _ = tmp_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for status in LIFECYCLE_STATUSES:
            await conn.execute(
                text("INSERT INTO nodes (uuid, lifecycle_status) VALUES (:uuid, :status)"),
                {"uuid": "node-" + status, "status": status},
            )
        rows = (
            await conn.execute(text("SELECT uuid, lifecycle_status FROM nodes ORDER BY uuid"))
        ).all()

    assert len(rows) == len(LIFECYCLE_STATUSES) == 4
    assert {row[1] for row in rows} == set(LIFECYCLE_STATUSES)

    for bad in ("unknown", "", None):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO nodes (uuid, lifecycle_status) VALUES (:uuid, :status)"),
                    {"uuid": "bad-" + str(bad), "status": bad},
                )


@pytest.mark.asyncio
async def test_default_applies_when_status_omitted(tmp_engine):
    """T06: a create without an explicit status reads back the database default."""
    engine, _ = tmp_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("INSERT INTO nodes (uuid) VALUES ('default-node')"))
        status = (
            await conn.execute(
                text("SELECT lifecycle_status FROM nodes WHERE uuid = 'default-node'")
            )
        ).scalar_one()

    assert status == "unspecified"


@pytest.mark.asyncio
async def test_migration_015_upgrades_frozen_old_schema(tmp_engine):
    """T02: a pre-v3 nodes table gains the column; existing rows become unspecified."""
    engine, _ = tmp_engine
    async with engine.begin() as conn:
        await conn.execute(text(LEGACY_NODES_DDL))
        await conn.execute(text("INSERT INTO nodes (uuid) VALUES ('legacy-node')"))

    migration = _load_migration(MIGRATION_015)
    await migration.up(engine)

    async with engine.connect() as conn:
        shape = await conn.run_sync(_read_lifecycle_column)
        status = (
            await conn.execute(
                text("SELECT lifecycle_status FROM nodes WHERE uuid = 'legacy-node'")
            )
        ).scalar_one()

    assert status == "unspecified"
    _assert_contract(shape)


@pytest.mark.asyncio
async def test_migration_015_retry_after_committed_ddl_is_safe(tmp_engine):
    """T03: DDL committed without a migration record, then a real retry.

    The retry must verify the existing column instead of adding a second one or
    weakening the constraints, and the runner must record it and write a valid
    SQLite backup.
    """
    engine, db_path = tmp_engine
    async with engine.begin() as conn:
        await conn.execute(text(LEGACY_NODES_DDL))
        await conn.execute(text("INSERT INTO nodes (uuid) VALUES ('legacy-node')"))
        await conn.execute(text(SCHEMA_MIGRATIONS_DDL))
        for name in _migration_files():
            if name != MIGRATION_015:
                await conn.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": name},
                )

    migration = _load_migration(MIGRATION_015)
    await migration.up(engine)

    await runner.run_migrations(engine)

    async with engine.connect() as conn:
        statuses = (await conn.execute(text("SELECT lifecycle_status FROM nodes"))).scalars().all()
        recorded = (
            await conn.execute(
                text("SELECT version FROM schema_migrations WHERE version = :version"),
                {"version": MIGRATION_015},
            )
        ).scalar_one()
        lifecycle_columns = await conn.run_sync(_lifecycle_columns)
        shape = await conn.run_sync(_read_lifecycle_column)

    assert statuses == ["unspecified"]
    assert recorded == MIGRATION_015
    assert lifecycle_columns == ["lifecycle_status"]
    _assert_contract(shape)

    backups = sorted(Path(db_path).parent.glob(db_path.name + ".*.bak"))
    assert len(backups) == 1
    assert not backups[0].name.endswith(".pending")
    assert _sqlite_verdict(backups[0]).startswith("ok")

    await runner.run_migrations(engine)
    assert len(sorted(Path(db_path).parent.glob(db_path.name + ".*.bak"))) == 1


@pytest.mark.asyncio
async def test_migration_015_stops_on_preexisting_column_outside_contract(tmp_engine):
    """First-site preflight: an unexpected existing column stops the migration."""
    engine, _ = tmp_engine
    definitions = [
        "lifecycle_status TEXT",
        "lifecycle_status VARCHAR(16) DEFAULT 'unspecified'",
        "lifecycle_status VARCHAR(16) NOT NULL DEFAULT 'unknown'",
        "lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'unspecified'",
    ]

    for definition in definitions:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS nodes"))
            await conn.execute(
                text(
                    "CREATE TABLE nodes ("
                    " uuid VARCHAR(36) NOT NULL PRIMARY KEY, " + definition + ")"
                )
            )

        migration = _load_migration(MIGRATION_015)
        with pytest.raises(RuntimeError):
            await migration.up(engine)


@pytest.mark.asyncio
async def test_sqlite_backup_publishes_verified_unique_copy(tmp_path):
    """A live WAL database is copied through the online backup API and published."""
    db_path = tmp_path / "live.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES ('kept')")
        conn.commit()

        first = await runner._backup_sqlite_online(str(db_path), "20261028_120000")
        second = await runner._backup_sqlite_online(str(db_path), "20261028_120000")
    finally:
        conn.close()

    assert first != second
    assert not first.endswith(".pending")
    assert not second.endswith(".pending")
    assert _sqlite_verdict(first).startswith("ok")

    copy_conn = sqlite3.connect(first)
    try:
        rows = copy_conn.execute("SELECT name FROM sample").fetchall()
    finally:
        copy_conn.close()
    assert rows == [("kept",)]


@pytest.mark.asyncio
async def test_sqlite_backup_failure_keeps_artifact_and_raises(tmp_path):
    """A failed backup must abort the migration and keep the broken artifact."""
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite database" * 64)

    with pytest.raises(RuntimeError):
        await runner._backup_sqlite_online(str(corrupt), "20261028_120000")

    pendings = sorted(tmp_path.glob("corrupt.db.*.bak.pending"))
    assert len(pendings) == 1
    assert not sorted(tmp_path.glob("corrupt.db.*.bak"))
