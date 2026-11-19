import logging

from sqlalchemy import DateTime, Text, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def _ensure_column(conn, table_name: str, column_name: str, column_type: str) -> None:
    columns = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_columns(table_name))
    existing = next((column for column in columns if column["name"] == column_name), None)
    if existing is None:
        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
        return

    expected = Text if column_type == "TEXT" else DateTime
    if not isinstance(existing.get("type"), expected) or existing.get("nullable") is False:
        raise RuntimeError(
            f"Migration 016 found {table_name}.{column_name} with an unexpected schema; "
            "stop and reconcile it manually."
        )


async def up(engine: AsyncEngine):
    """Add version-scoped summaries and rebuild the derived full-text index."""
    is_postgres = "postgresql" in str(engine.url)

    async with engine.begin() as conn:
        await _ensure_column(conn, "memories", "summary_content", "TEXT")
        await _ensure_column(conn, "memories", "summary_updated_at", "TIMESTAMP")
        await _ensure_column(conn, "search_documents", "summary_content", "TEXT")

        # SearchDocument is a derived cache. Reconcile it from the source Memory
        # rows before rebuilding either database's full-text index.
        await conn.execute(text(
            """
            UPDATE search_documents
            SET summary_content = (
                SELECT memories.summary_content
                FROM memories
                WHERE memories.id = search_documents.memory_id
            )
            WHERE summary_content IS NULL
            """
        ))

        if is_postgres:
            search_text_expr = (
                "coalesce(path, '') || ' ' || "
                "coalesce(uri, '') || ' ' || "
                "coalesce(summary_content, '') || ' ' || "
                "coalesce(content, '') || ' ' || "
                "coalesce(disclosure, '') || ' ' || "
                "coalesce(search_terms, '')"
            )
            await conn.execute(text("DROP INDEX IF EXISTS idx_search_documents_fts"))
            await conn.execute(text(
                "CREATE INDEX idx_search_documents_fts "
                f"ON search_documents USING GIN (to_tsvector('simple', {search_text_expr}))"
            ))
        else:
            # FTS5 column order is part of the BM25 weighting contract.
            await conn.execute(text("DROP TABLE IF EXISTS search_documents_fts"))
            await conn.execute(text(
                """
                CREATE VIRTUAL TABLE search_documents_fts
                USING fts5(
                    namespace UNINDEXED,
                    domain UNINDEXED,
                    path,
                    node_uuid UNINDEXED,
                    uri,
                    summary_content,
                    content,
                    disclosure,
                    search_terms,
                    tokenize = 'unicode61'
                )
                """
            ))
            await conn.execute(text(
                """
                INSERT INTO search_documents_fts (
                    namespace, domain, path, node_uuid, uri,
                    summary_content, content, disclosure, search_terms
                )
                SELECT
                    namespace, domain, path, node_uuid, uri,
                    coalesce(summary_content, ''), content,
                    coalesce(disclosure, ''), search_terms
                FROM search_documents
                """
            ))

    logger.info("Migration 016: added Memory summaries and rebuilt full-text search index")
