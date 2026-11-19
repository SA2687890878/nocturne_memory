"""Synchronize configured memory documents into the independent semantic index."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from urllib.parse import unquote
from typing import Any, Callable

import config
from embedding import embed_texts
from vector_index import VectorIndex
from vector_index_sync import sync_vector_index

DIMENSIONS = 2048
DOCUMENT_FORMAT_VERSION = 2


def load_source_documents() -> tuple[Path, list[dict[str, Any]]]:
    url = str(config.get("database_url") or "")
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        raise RuntimeError("semantic index sync currently requires a SQLite memory database")
    source = Path(unquote(url[len(prefix):]))
    if not source.is_file():
        raise FileNotFoundError("configured memory database does not exist")
    con = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT sd.memory_id,sd.uri,sd.namespace,sd.domain,sd.path,
                    sd.summary_content,sd.search_terms,sd.content,n.lifecycle_status
            FROM search_documents sd
            JOIN memories m ON m.id=sd.memory_id
            JOIN nodes n ON n.uuid=sd.node_uuid
            WHERE COALESCE(n.lifecycle_status,'unspecified') <> 'obsolete'
              AND COALESCE(m.deprecated,0)=0
            ORDER BY sd.uri""").fetchall()
    finally:
        con.close()
    documents = []
    for row in rows:
        text = "\n".join([
            f"URI: {row['uri']}", f"Path: {row['path']}",
            f"Domain: {row['domain'] or ''}", f"Namespace: {row['namespace'] or ''}",
            f"Summary: {row['summary_content'] or ''}",
            f"Keywords: {row['search_terms'] or ''}",
            f"Lifecycle: {row['lifecycle_status'] or 'unspecified'}",
            f"Memory: {row['content'] or ''}",
        ])
        documents.append({
            "memory_id": row['memory_id'], "uri": row['uri'], "namespace": row['namespace'] or '',
            "domain": row['domain'] or '', "path": row['path'] or '',
            "lifecycle_status": row['lifecycle_status'] or 'unspecified', "text": text,
        })
    return source, documents


async def sync_configured_vector_index() -> dict[str, Any]:
    started = time.perf_counter()
    source, documents = load_source_documents()
    settings = config.get("embedding") or {}
    model = str(settings.get("model") or "nvidia/nemotron-3-embed-1b")
    target = source.with_name("work-memory-vectors.db")
    async def embed(texts: list[str]):
        return await embed_texts(texts, input_type=str(settings.get("document_input_type") or "passage"))
    with VectorIndex(target, dimensions=DIMENSIONS, model_name=model,
                     document_format_version=DOCUMENT_FORMAT_VERSION) as index:
        report = await sync_vector_index(index, documents, embed)
        report.update({
            "source": source.name, "target": target.name, "model": model,
            "dimensions": DIMENSIONS, "index_health": index.health_check(),
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        })
    return report
