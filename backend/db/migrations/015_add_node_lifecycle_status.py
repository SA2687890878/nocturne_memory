import logging

from sqlalchemy import String, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

COLUMN_NAME = "lifecycle_status"
DEFAULT_SENTINEL = "unspecified"

# One statement so an old database never sees a bare column with weak defaults.
# PostgreSQL and SQLite both accept a named column constraint inside ADD COLUMN.
ADD_COLUMN_SQL = (
    "ALTER TABLE nodes ADD COLUMN lifecycle_status VARCHAR(16) NOT NULL "
    "DEFAULT 'unspecified' "
    "CONSTRAINT ck_nodes_lifecycle_status "
    "CHECK (lifecycle_status IN ('active', 'completed', 'obsolete', 'unspecified'))"
)


def _find_existing_column(sync_conn):
    """Return the reflected nodes.lifecycle_status column, or None."""
    for column in inspect(sync_conn).get_columns("nodes"):
        if column["name"] == COLUMN_NAME:
            return column
    return None


def _verify_existing_column(column):
    """Accept only the v3 contract for a column created by the new model.

    Deliberately checks shape, not SQL text: no CHECK reflection comparison, no
    default-expression parsing, and no general SQL parser.
    """
    problems = []
    column_type = column.get("type")
    if not isinstance(column_type, String):
        problems.append(f"type={column_type!r} (expected a String type)")
    elif getattr(column_type, "length", None) != 16:
        problems.append(f"length={getattr(column_type, 'length', None)!r} (expected 16)")
    if column.get("nullable", True):
        problems.append("nullable=True (expected NOT NULL)")
    default_sql = str(column.get("default") or "")
    # Tolerate PostgreSQL casts such as 'unspecified'::character varying; only
    # require the exact quoted literal.
    if f"'{DEFAULT_SENTINEL}'" not in default_sql:
        problems.append(
            f"default={default_sql!r} (expected a database default containing 'unspecified')"
        )
    if problems:
        raise RuntimeError(
            "Migration 015 found an existing nodes.lifecycle_status column outside the "
            "v3 contract: "
            + "; ".join(problems)
            + ". Stop and reconcile the schema manually before migrating."
        )


async def up(engine: AsyncEngine):
    """
    Add nodes.lifecycle_status for the memory lifecycle v3 work.

    Old databases get the column, its NOT NULL constraint and its CHECK in one
    statement; existing rows become 'unspecified' through the default. Databases
    already created by the new model are recognised and only verified, so this
    migration is safe to re-run after an interrupted run.

    See docs/features/memory-lifecycle-v3/03-design.md section 17.
    """
    async with engine.begin() as conn:
        existing = await conn.run_sync(_find_existing_column)
        if existing is not None:
            _verify_existing_column(existing)
            logger.info(
                "Migration 015: nodes.lifecycle_status already present and matches the "
                "v3 contract; no DDL applied."
            )
            return

        await conn.execute(text(ADD_COLUMN_SQL))

    logger.info("Migration 015: added nodes.lifecycle_status (default 'unspecified')")
