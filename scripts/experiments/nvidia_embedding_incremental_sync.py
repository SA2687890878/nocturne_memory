"""Incrementally sync the read-only real memory corpus into an isolated sqlite-vec index.

The source database is always read-only. The target is an experiment-only database
under .tmp. All embeddings are generated and validated before the target transaction.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import runpy
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB = Path(r"E:\myPrivateSpace\记忆系统数据库\work\work-memory.db")
TARGET_DB = ROOT / ".tmp" / "vector_index_sync_migration.db"
CACHE_DB = ROOT / ".tmp" / "nvidia_embedding_embedding_cache.db"
EXPECTED_DIMENSIONS = 2048
DOCUMENT_FORMAT_VERSION = 2


def build_document_text(row):
    """Use real line breaks so field boundaries remain clear to the embedding model."""
    lifecycle_status = row["lifecycle_status"] if "lifecycle_status" in row.keys() else "unspecified"
    return "\n".join([
        f"URI: {row['uri']}",
        f"Path: {row['path']}",
        f"Domain: {row['domain']}",
        f"Namespace: {row['namespace']}",
        f"Summary: {row['summary_content'] or ''}",
        f"Keywords: {row['search_terms'] or ''}",
        f"Lifecycle: {lifecycle_status or 'unspecified'}",
        f"Memory: {row['content'] or ''}",
    ])


def validate_documents(docs):
    seen = set()
    for doc in docs:
        uri = doc.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError("source document contains an empty URI")
        if uri in seen:
            raise ValueError(f"duplicate source URI: {uri}")
        seen.add(uri)
        if not isinstance(doc.get("content_hash"), str) or not doc["content_hash"]:
            raise ValueError(f"source document has no content hash: {uri}")
    return {doc["uri"]: doc for doc in docs}


def should_rebuild_index(previous_state, existing_count, model_name, dimensions, document_format_version):
    """Return whether all vectors must be regenerated for index compatibility."""
    if previous_state is None:
        return existing_count > 0
    previous_model, previous_dimensions, previous_format = previous_state
    if previous_dimensions != dimensions:
        raise RuntimeError(
            f"vector dimension changed from {previous_dimensions} to {dimensions}; "
            "create a fresh isolated index instead of mutating this index"
        )
    return previous_model != model_name or previous_format != document_format_version


def validate_vectors(vectors, expected_count, expected_dimensions=EXPECTED_DIMENSIONS):
    if len(vectors) != expected_count:
        raise ValueError(f"embedding count mismatch: expected {expected_count}, got {len(vectors)}")
    for index, vector in enumerate(vectors):
        if not isinstance(vector, (list, tuple)) or len(vector) != expected_dimensions:
            actual = len(vector) if isinstance(vector, (list, tuple)) else "invalid"
            raise ValueError(f"embedding dimensions mismatch at index {index}: expected {expected_dimensions}, got {actual}")
        if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in vector):
            raise ValueError(f"embedding contains a non-finite or non-numeric value at index {index}")


def load_docs():
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f"source database not found: {SOURCE_DB}")
    con = sqlite3.connect(f"file:{SOURCE_DB.as_posix()}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT sd.memory_id, sd.uri, sd.namespace, sd.domain, sd.path,
                    sd.summary_content, sd.search_terms, sd.content, n.lifecycle_status
            FROM search_documents sd
            JOIN memories m ON m.id = sd.memory_id
            JOIN nodes n ON n.uuid = sd.node_uuid
            WHERE COALESCE(n.lifecycle_status, 'unspecified') <> 'obsolete'
              AND COALESCE(m.deprecated, 0) = 0
            ORDER BY sd.uri""").fetchall()
    finally:
        con.close()
    docs = []
    for row in rows:
        text = build_document_text(row)
        docs.append({
            "memory_id": row["memory_id"],
            "uri": row["uri"],
            "namespace": row["namespace"] or "",
            "domain": row["domain"] or "",
            "path": row["path"] or "",
            "lifecycle_status": row["lifecycle_status"] or "unspecified",
            "text": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    validate_documents(docs)
    return docs


async def generate_vectors(texts):
    if not texts:
        return []
    sys.path.insert(0, str(ROOT / "scripts" / "experiments"))
    helper = runpy.run_path(
        str(ROOT / "scripts" / "experiments" / "nvidia_embedding_real_memory_eval.py"),
        run_name="incremental_sync_helpers",
    )
    helper["CACHE_DB"] = CACHE_DB
    vectors = await helper["embed_batched"](texts, "passage")
    validate_vectors(vectors, len(texts))
    return vectors


async def sync():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.vector_index import VectorIndex
    from backend.vector_index_sync import sync_vector_index

    started = time.perf_counter()
    docs = load_docs()
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "config.json"
    app_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    embedding_config = app_config.get("embedding", {})
    model_name = str(embedding_config.get("model") or "nvidia/nemotron-3-embed-1b")

    async def embed(texts):
        return await generate_vectors(texts)

    with VectorIndex(
        TARGET_DB, dimensions=EXPECTED_DIMENSIONS, model_name=model_name,
        document_format_version=DOCUMENT_FORMAT_VERSION,
    ) as index:
        report = await sync_vector_index(index, docs, embed)
        report.update({
            "source": "work-memory.db (read-only)",
            "source_document_count": report["source_count"],
            "inserted_or_updated": report["upserted"],
            "deleted_stale": report["deleted"],
            "target": TARGET_DB.name,
            "full_rebuild": report["upserted"] == len(docs) and report["deleted"] == 0,
            "model_name": model_name,
            "dimensions": EXPECTED_DIMENSIONS,
            "document_format_version": DOCUMENT_FORMAT_VERSION,
            "metadata_count": index.health_check()["metadata_count"],
            "vector_count": index.health_check()["vector_count"],
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        })
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    asyncio.run(sync())
