"""Benchmark VectorIndex against the existing isolated 48-document vector corpus.

No NVIDIA API calls and no writes to the source or real memory databases.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sqlite_vec
from backend.vector_index import VectorIndex

SOURCE = ROOT / ".tmp" / "nvidia_embedding_incremental.db"
TARGET = ROOT / ".tmp" / "vector_index_benchmark.db"
OUTPUT = ROOT / ".tmp" / "vector_index_benchmark.json"
DIMENSIONS = 2048
MODEL = "nvidia/nemotron-3-embed-1b"


def main() -> dict:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    src = sqlite3.connect(SOURCE)
    src.enable_load_extension(True)
    sqlite_vec.load(src)
    rows = src.execute("""SELECT m.memory_id,m.uri,m.content_hash,v.embedding
        FROM memory_meta m JOIN memory_vectors v ON v.rowid=m.rowid ORDER BY m.uri""").fetchall()
    src.close()
    docs = []
    for memory_id, uri, content_hash, blob in rows:
        vector = struct.unpack(f"<{DIMENSIONS}f", blob)
        docs.append({"memory_id": memory_id, "uri": uri, "content_hash": content_hash,
                     "vector": vector, "namespace": "", "domain": "", "path": "",
                     "lifecycle_status": "unspecified"})

    if TARGET.exists():
        TARGET.unlink()
    started = time.perf_counter()
    with VectorIndex(TARGET, dimensions=DIMENSIONS, model_name=MODEL, document_format_version=2) as index:
        open_seconds = time.perf_counter() - started
        write_started = time.perf_counter()
        index.upsert_many(docs)
        write_seconds = time.perf_counter() - write_started
        query = docs[0]["vector"]
        index.search(query, limit=10)  # warm-up
        samples = []
        for _ in range(30):
            tick = time.perf_counter()
            result = index.search(query, limit=10)
            samples.append((time.perf_counter() - tick) * 1000)
        health = index.health_check()
        top1_uri = result[0]["uri"] if result else None
    size_bytes = TARGET.stat().st_size
    report = {
        "corpus_documents": len(docs),
        "dimensions": DIMENSIONS,
        "database_bytes": size_bytes,
        "database_mib": round(size_bytes / 1024 / 1024, 3),
        "open_and_initialize_seconds": round(open_seconds, 6),
        "bulk_insert_seconds": round(write_seconds, 6),
        "query_count": len(samples),
        "query_ms_median": round(statistics.median(samples), 4),
        "query_ms_p95": round(sorted(samples)[int(len(samples) * 0.95) - 1], 4),
        "top1_self_match": top1_uri == docs[0]["uri"],
        "health": health,
        "source": "isolated .tmp vector corpus; no production database writes",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
