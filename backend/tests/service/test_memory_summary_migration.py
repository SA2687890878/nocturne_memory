import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "016_add_memory_summary.py"
)


@pytest.mark.asyncio
async def test_sqlite_summary_migration_is_idempotent_and_rebuilds_fts():
    spec = importlib.util.spec_from_file_location("migration_016", MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT NOT NULL)"))
            await conn.execute(text("INSERT INTO memories (id, content) VALUES (1, 'body text')"))
            await conn.execute(text(
                "CREATE TABLE search_documents ("
                "namespace VARCHAR(64) NOT NULL, domain VARCHAR(64) NOT NULL, path VARCHAR(512) NOT NULL, "
                "node_uuid VARCHAR(36) NOT NULL, memory_id INTEGER NOT NULL, uri TEXT NOT NULL, "
                "content TEXT NOT NULL, disclosure TEXT, search_terms TEXT NOT NULL DEFAULT '', "
                "priority INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMP, "
                "PRIMARY KEY(namespace, domain, path))"
            ))
            await conn.execute(text(
                "CREATE VIRTUAL TABLE search_documents_fts USING fts5("
                "namespace UNINDEXED, domain UNINDEXED, path, node_uuid UNINDEXED, uri, "
                "content, disclosure, search_terms, tokenize='unicode61')"
            ))
            await conn.execute(text(
                "INSERT INTO search_documents VALUES "
                "('', 'core', 'migration_note', 'node-1', 1, 'core://migration_note', "
                "'body text', NULL, '', 0, CURRENT_TIMESTAMP)"
            ))

        await migration.up(engine)
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE memories SET summary_content='migration_summary_unique' WHERE id=1"
            ))
        await migration.up(engine)

        async with engine.connect() as conn:
            memory_columns = {
                row[1] for row in (await conn.execute(text("PRAGMA table_info(memories)"))).all()
            }
            search_columns = {
                row[1] for row in (await conn.execute(text("PRAGMA table_info(search_documents)"))).all()
            }
            assert {"summary_content", "summary_updated_at"} <= memory_columns
            assert "summary_content" in search_columns

            indexed_summary = (await conn.execute(text(
                "SELECT summary_content FROM search_documents WHERE path='migration_note'"
            ))).scalar_one()
            assert indexed_summary == "migration_summary_unique"
            hits = (await conn.execute(text(
                "SELECT path FROM search_documents_fts "
                "WHERE search_documents_fts MATCH 'migration_summary_unique'"
            ))).all()
            assert hits == [("migration_note",)]
    finally:
        await engine.dispose()
