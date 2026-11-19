"""Explicit semantic candidate search over the separate sqlite-vec index."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote
from typing import Any

import config
from embedding import embed_texts
from vector_index import VectorIndex

EXPECTED_DIMENSIONS = 2048
DOCUMENT_FORMAT_VERSION = 2


def vector_index_path() -> Path:
    """Place the vector index beside the configured SQLite memory database."""
    database_url = str(config.get("database_url") or "")
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise RuntimeError("semantic search currently requires a SQLite memory database")
    database_path = Path(unquote(database_url[len(prefix):]))
    return database_path.with_name("work-memory-vectors.db")


async def search_semantic_memories(
    query: str, *, limit: int = 10, namespace: str | None = None, domain: str | None = None
) -> list[dict[str, Any]]:
    """Return nearest vector matches as candidates; distance is not a relevance probability."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must not be empty")
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")
    settings = config.get("embedding") or {}
    if not settings.get("api_key"):
        raise RuntimeError("semantic search is not configured: embedding API key is missing")
    model_name = str(settings.get("model") or "nvidia/nemotron-3-embed-1b")
    index_path = vector_index_path()
    if not index_path.is_file():
        raise RuntimeError("semantic index is not initialized; run the Nocturne vector sync first")
    query_type = str(settings.get("query_input_type") or "query")
    vectors = await embed_texts([query], input_type=query_type)
    if len(vectors) != 1 or len(vectors[0]) != EXPECTED_DIMENSIONS:
        raise RuntimeError("query embedding does not match the semantic index dimensions")
    with VectorIndex(index_path, dimensions=EXPECTED_DIMENSIONS, model_name=model_name,
                     document_format_version=DOCUMENT_FORMAT_VERSION, read_only=True) as index:
        health = index.health_check()
        if not health["ok"]:
            raise RuntimeError("semantic index integrity check failed")
        return index.search(vectors[0], limit=limit, namespace=namespace, domain=domain)
