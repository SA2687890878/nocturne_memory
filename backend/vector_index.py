"""Small sqlite-vec index used by isolated semantic-retrieval experiments.

This module is intentionally independent from SearchIndexer. It owns only the
vector store; lexical search and final ranking remain outside this class.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class VectorIndexError(RuntimeError):
    """Raised when the vector index is unavailable or incompatible."""


class VectorIndex:
    def __init__(
        self,
        path: str | Path,
        *,
        dimensions: int,
        model_name: str,
        document_format_version: int = 1,
        read_only: bool = False,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        self.path = Path(path)
        self.dimensions = dimensions
        self.model_name = model_name
        self.document_format_version = document_format_version
        self.read_only = read_only
        self._connection: sqlite3.Connection | None = None

    def open(self) -> "VectorIndex":
        if self._connection is not None:
            return self
        if self.read_only and not self.path.is_file():
            raise FileNotFoundError(f"vector index does not exist: {self.path}")
        if not self.read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import sqlite_vec
            if self.read_only:
                connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            else:
                connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(True)
            sqlite_vec.load(connection)
            if self.read_only:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                ).fetchall()}
                required = {"memory_meta", "memory_vectors", "index_state"}
                if not required.issubset(tables):
                    raise VectorIndexError("vector index schema is incomplete")
                state = connection.execute(
                    "SELECT model_name,dimensions,document_format_version FROM index_state WHERE singleton=1"
                ).fetchone()
                if not state:
                    raise VectorIndexError("vector index identity is missing")
                if state["dimensions"] != self.dimensions:
                    raise VectorIndexError(
                        f"dimension mismatch: stored={state['dimensions']}, requested={self.dimensions}"
                    )
                if state["model_name"] != self.model_name or state["document_format_version"] != self.document_format_version:
                    raise VectorIndexError("index identity mismatch")
                self._connection = connection
                return self
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""CREATE TABLE IF NOT EXISTS memory_meta (
                rowid INTEGER PRIMARY KEY,
                memory_id INTEGER NOT NULL,
                uri TEXT NOT NULL UNIQUE,
                content_hash TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                lifecycle_status TEXT NOT NULL DEFAULT 'unspecified',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(embedding float[{self.dimensions}])"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS index_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                model_name TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                document_format_version INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            state = connection.execute(
                "SELECT model_name, dimensions, document_format_version FROM index_state WHERE singleton=1"
            ).fetchone()
            if state:
                if state["dimensions"] != self.dimensions:
                    raise VectorIndexError(
                        f"dimension mismatch: stored={state['dimensions']}, requested={self.dimensions}; use a fresh index"
                    )
                if state["model_name"] != self.model_name or state["document_format_version"] != self.document_format_version:
                    raise VectorIndexError("index identity mismatch; rebuild into a fresh index")
            elif connection.execute("SELECT COUNT(*) FROM memory_meta").fetchone()[0]:
                raise VectorIndexError("legacy index has no identity; rebuild into a fresh index")
            connection.execute(
                "INSERT OR IGNORE INTO index_state(singleton, model_name, dimensions, document_format_version) VALUES(1,?,?,?)",
                (self.model_name, self.dimensions, self.document_format_version),
            )
            connection.commit()
            self._connection = connection
            return self
        except Exception:
            if 'connection' in locals():
                connection.close()
            raise

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "VectorIndex":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise VectorIndexError("index is not open")
        return self._connection

    def _validate_vector(self, vector: Iterable[float]) -> list[float]:
        values = list(vector)
        if len(values) != self.dimensions:
            raise ValueError(f"expected {self.dimensions} dimensions, got {len(values)}")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values):
            raise ValueError("vector values must be finite numbers")
        return [float(v) for v in values]

    def list_documents(self) -> dict[str, dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT memory_id,uri,content_hash,namespace,domain,path,lifecycle_status FROM memory_meta ORDER BY uri"
        ).fetchall()
        return {row["uri"]: dict(row) for row in rows}

    def apply_changes(
        self,
        upserts: Iterable[dict[str, Any]],
        delete_uris: Iterable[str] = (),
    ) -> dict[str, int]:
        """Atomically apply vector upserts and URI deletions in one transaction."""
        import sqlite_vec
        docs = list(upserts)
        deletes = list(dict.fromkeys(delete_uris))
        prepared = []
        seen = set()
        for doc in docs:
            uri = doc.get("uri")
            if not isinstance(uri, str) or not uri.strip() or uri in seen:
                raise ValueError("documents must have unique, non-empty URIs")
            seen.add(uri)
            content_hash = doc.get("content_hash")
            if not isinstance(content_hash, str) or not content_hash:
                raise ValueError(f"content_hash is required for {uri}")
            if "memory_id" not in doc:
                raise ValueError(f"memory_id is required for {uri}")
            prepared.append((doc, self._validate_vector(doc.get("vector", []))))
        con = self.connection
        con.execute("BEGIN IMMEDIATE")
        try:
            deleted = 0
            for uri in deletes:
                row = con.execute("SELECT rowid FROM memory_meta WHERE uri=?", (uri,)).fetchone()
                if row:
                    con.execute("DELETE FROM memory_vectors WHERE rowid=?", (row["rowid"],))
                    con.execute("DELETE FROM memory_meta WHERE rowid=?", (row["rowid"],))
                    deleted += 1
            for doc, vector in prepared:
                old = con.execute("SELECT rowid FROM memory_meta WHERE uri=?", (doc["uri"],)).fetchone()
                rowid = old["rowid"] if old else con.execute(
                    "SELECT COALESCE(MAX(rowid),0)+1 FROM memory_meta"
                ).fetchone()[0]
                if old:
                    con.execute("DELETE FROM memory_vectors WHERE rowid=?", (rowid,))
                con.execute(
                    "INSERT OR REPLACE INTO memory_meta(rowid,memory_id,uri,content_hash,namespace,domain,path,lifecycle_status,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                    (rowid, doc["memory_id"], doc["uri"], doc["content_hash"],
                     doc.get("namespace", ""), doc.get("domain", ""), doc.get("path", ""),
                     doc.get("lifecycle_status", "unspecified")),
                )
                con.execute(
                    "INSERT INTO memory_vectors(rowid,embedding) VALUES(?,?)",
                    (rowid, sqlite_vec.serialize_float32(vector)),
                )
            meta_count = con.execute("SELECT COUNT(*) FROM memory_meta").fetchone()[0]
            vector_count = con.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
            if meta_count != vector_count:
                raise RuntimeError(f"index integrity failure: metadata={meta_count}, vectors={vector_count}")
            con.commit()
            return {"upserted": len(prepared), "deleted": deleted}
        except Exception:
            con.rollback()
            raise

    def upsert_many(self, documents: Iterable[dict[str, Any]]) -> int:
        return self.apply_changes(documents)["upserted"]

    def delete_uris(self, uris: Iterable[str]) -> int:
        return self.apply_changes([], uris)["deleted"]

    def search(
        self,
        query_vector: Iterable[float],
        *,
        limit: int = 10,
        namespace: str | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        import sqlite_vec
        if limit < 1:
            raise ValueError("limit must be at least 1")
        vector = self._validate_vector(query_vector)
        con = self.connection
        total = con.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
        if total == 0:
            return []
        # sqlite-vec applies k before ordinary metadata predicates. Fetch nearest
        # candidates progressively until the filtered result is full or exhausted.
        candidate_count = min(total, limit)
        serialized = sqlite_vec.serialize_float32(vector)
        while True:
            rows = con.execute("""SELECT m.memory_id,m.uri,m.content_hash,m.namespace,m.domain,
                        m.path,m.lifecycle_status,v.distance
                FROM memory_vectors v JOIN memory_meta m ON m.rowid=v.rowid
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance""", (serialized, candidate_count)).fetchall()
            results = [dict(row) for row in rows]
            if namespace is not None:
                results = [row for row in results if row["namespace"] == namespace]
            if domain is not None:
                results = [row for row in results if row["domain"] == domain]
            if len(results) >= limit or candidate_count >= total:
                return results[:limit]
            candidate_count = min(total, max(candidate_count + 1, candidate_count * 2))

    def health_check(self) -> dict[str, Any]:
        con = self.connection
        metadata_count = con.execute("SELECT COUNT(*) FROM memory_meta").fetchone()[0]
        vector_count = con.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
        state = con.execute(
            "SELECT model_name,dimensions,document_format_version,updated_at FROM index_state WHERE singleton=1"
        ).fetchone()
        return {
            "ok": metadata_count == vector_count and state is not None,
            "metadata_count": metadata_count,
            "vector_count": vector_count,
            "model_name": state["model_name"] if state else None,
            "dimensions": state["dimensions"] if state else None,
            "document_format_version": state["document_format_version"] if state else None,
            "updated_at": state["updated_at"] if state else None,
            "database_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }
