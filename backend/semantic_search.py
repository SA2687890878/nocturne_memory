"""Explicit semantic candidate search over the separate sqlite-vec index."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from sqlalchemy.engine import make_url

import config
from embedding import embed_texts
from vector_index import VectorIndex
from db import get_effective_database_url, get_graph_service
from db.namespace import get_namespace

EXPECTED_DIMENSIONS = 2048
DOCUMENT_FORMAT_VERSION = 2


def vector_index_path() -> Path:
    """Place the vector index beside the configured SQLite memory database."""
    url = make_url(get_effective_database_url())
    if url.get_backend_name() != "sqlite":
        raise RuntimeError("semantic search currently requires a SQLite memory database")
    raw_path = url.database
    if raw_path.startswith("file:"):
        raw_path = url2pathname(urlsplit(raw_path).path)
    database_path = Path(raw_path)
    return database_path.with_name("work-memory-vectors.db")


async def search_semantic_memories(
    query: str, *, limit: int = 10, namespace: str | None = None, domain: str | None = None
) -> list[dict[str, Any]]:
    """Return nearest vector matches as candidates; distance is not a relevance probability."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must not be empty")
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")
    namespace = get_namespace() if namespace is None else namespace
    settings = config.get("embedding") or {}
    if not settings.get("api_key"):
        raise RuntimeError("semantic search is not configured: embedding API key is missing")
    model_name = str(settings.get("model") or "nvidia/nemotron-3-embed-1b")
    index_path = vector_index_path()
    if not index_path.is_file():
        raise RuntimeError("semantic index is not initialized; run the Nocturne vector sync first")
    query_type = str(settings.get("query_input_type") or "query")
    with VectorIndex(index_path, dimensions=EXPECTED_DIMENSIONS, model_name=model_name,
                     document_format_version=DOCUMENT_FORMAT_VERSION, read_only=True) as index:
        health = index.health_check()
        if not health["ok"]:
            raise RuntimeError("semantic index integrity check failed")
        total = health["metadata_count"]
        if not total:
            return []
        vectors = await embed_texts([query], input_type=query_type)
        if len(vectors) != 1 or len(vectors[0]) != EXPECTED_DIMENSIONS:
            raise RuntimeError("query embedding does not match the semantic index dimensions")
        candidate_count = min(total, max(limit * 3, 10))
        graph = get_graph_service()
        while True:
            candidates = index.search(vectors[0], limit=candidate_count, namespace=namespace, domain=domain)
            # Query only current path/version/summary fields. Never trust cached
            # namespace, lifecycle or version metadata as current source truth.
            current = await graph.get_memory_summaries_by_uris(
                [item["uri"] for item in candidates], namespace=namespace,
            )
            verified = []
            by_node = {}
            for candidate in candidates:
                live = current.get(candidate["uri"])
                if (live is None or live["memory_id"] != candidate["memory_id"]
                        or live["lifecycle_status"] == "obsolete"
                        or (domain is not None and live["domain"] != domain)):
                    continue
                if live["node_uuid"] in by_node:
                    by_node[live["node_uuid"]]["aliases"].append(live["uri"])
                    continue
                item = {**candidate, **live, "aliases": []}
                by_node[live["node_uuid"]] = item
                verified.append(item)
            if len(verified) >= limit or len(candidates) < candidate_count or candidate_count >= total:
                return verified[:limit]
            # Refill after stale paths/versions and aliases have been removed;
            # reuse the same query vector, without another paid API request.
            candidate_count = min(total, candidate_count * 2)
