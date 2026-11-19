r"""NVIDIA Embedding + sqlite-vec smoke test using synthetic text only.

Run from repository root:
  .venv\Scripts\python.exe scripts\experiments\nvidia_embedding_smoke.py

Uses an in-memory SQLite database; never reads or writes the memory database.
"""

import asyncio
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import sqlite_vec  # noqa: E402
from embedding import embed_texts  # noqa: E402


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise ValueError("embedding vector has zero norm")
    return dot / (left_norm * right_norm)


async def main() -> None:
    queries = await embed_texts(["把之前的开发任务接着做"], input_type="query")
    passages = await embed_texts(
        ["恢复之前的开发任务", "今天的天气怎么样"], input_type="passage"
    )
    query = queries[0]
    dimensions = len(query)
    if any(len(vector) != dimensions for vector in passages):
        raise RuntimeError("query and passage vector dimensions differ")

    # Verify the local vector index independently in an in-memory database.
    connection = sqlite3.connect(":memory:")
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.execute(
        f"CREATE VIRTUAL TABLE memory_vectors USING vec0(embedding float[{dimensions}])"
    )
    for row_id, vector in enumerate(passages, start=1):
        connection.execute(
            "INSERT INTO memory_vectors(rowid, embedding) VALUES (?, ?)",
            (row_id, sqlite_vec.serialize_float32(vector)),
        )
    ranked = connection.execute(
        "SELECT rowid, distance FROM memory_vectors "
        "WHERE embedding MATCH ? AND k = 2 ORDER BY distance",
        (sqlite_vec.serialize_float32(query),),
    ).fetchall()

    print("NVIDIA embedding API: OK")
    print(f"Model vector dimensions: {dimensions}")
    print(f"Paraphrase cosine: {cosine(query, passages[0]):.6f}")
    print(f"Unrelated cosine: {cosine(query, passages[1]):.6f}")
    print(f"sqlite-vec TopK (rowid, distance): {ranked}")
    print("Data source: synthetic examples only; in-memory SQLite only")
    connection.close()


if __name__ == "__main__":
    asyncio.run(main())
