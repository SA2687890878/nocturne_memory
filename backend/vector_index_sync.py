"""Incremental synchronization orchestration for VectorIndex."""
from __future__ import annotations

import hashlib
import inspect
from typing import Any, Awaitable, Callable, Iterable


def validate_source_documents(documents: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for doc in documents:
        uri = doc.get("uri")
        if not isinstance(uri, str) or not uri.strip() or uri in result:
            raise ValueError("source documents must have unique, non-empty URIs")
        text = doc.get("text")
        if not isinstance(text, str):
            raise ValueError(f"document text is required: {uri}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        supplied = doc.get("content_hash")
        if supplied is not None and supplied != digest:
            raise ValueError(f"content hash mismatch: {uri}")
        normalized = dict(doc)
        normalized["content_hash"] = digest
        result[uri] = normalized
    return result


async def sync_vector_index(index, source_documents, embed_documents: Callable[[list[str]], Any]):
    """Generate all changed vectors first; only then atomically mutate the index."""
    current = validate_source_documents(source_documents)
    existing = index.list_documents()
    changed = [doc for uri, doc in current.items()
               if uri not in existing
               or existing[uri]["content_hash"] != doc["content_hash"]
               or existing[uri]["memory_id"] != doc["memory_id"]
               or any(existing[uri].get(key, "") != doc.get(key, "")
                      for key in ("namespace", "domain", "path", "lifecycle_status"))]
    stale = sorted(set(existing) - set(current))
    if not changed and not stale:
        return {"source_count": len(current), "upserted": 0, "deleted": 0,
                "unchanged": len(current), "integrity_ok": index.health_check()["ok"]}
    vectors = embed_documents([doc["text"] for doc in changed]) if changed else []
    if inspect.isawaitable(vectors):
        vectors = await vectors
    if len(vectors) != len(changed):
        raise ValueError(f"embedding count mismatch: expected {len(changed)}, got {len(vectors)}")
    upserts = []
    for doc, vector in zip(changed, vectors):
        upserts.append({key: doc.get(key, "") for key in
                        ("memory_id", "uri", "content_hash", "namespace", "domain", "path", "lifecycle_status")}
                       | {"vector": vector})
    result = index.apply_changes(upserts, stale)
    health = index.health_check()
    if not health["ok"] or health["metadata_count"] != len(current):
        raise RuntimeError("post-sync index integrity check failed")
    return {"source_count": len(current), "upserted": result["upserted"],
            "deleted": result["deleted"], "unchanged": len(current) - len(changed),
            "integrity_ok": True}
