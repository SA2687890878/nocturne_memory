"""NVIDIA-compatible embedding API client for Nocturne.

Credentials are read from the local config.json embedding.api_key field.
This module is intentionally independent from the FTS search path until
semantic-recall evaluation justifies enabling it.
"""

from __future__ import annotations

from typing import Any, Sequence
import math

import httpx

import config


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the embedding provider is not configured."""


class EmbeddingAPIError(RuntimeError):
    """Raised when the embedding provider returns an invalid response."""


def _settings() -> dict[str, Any]:
    value = config.get("embedding") or {}
    if not isinstance(value, dict):
        raise EmbeddingConfigurationError("embedding config must be an object")
    return value


async def embed_texts(
    texts: Sequence[str],
    *,
    input_type: str = "query",
) -> list[list[float]]:
    """Convert texts to vectors using the configured OpenAI-compatible endpoint."""
    if not texts:
        return []
    if any(not isinstance(item, str) or not item.strip() for item in texts):
        raise ValueError("texts must contain non-empty strings")

    settings = _settings()
    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        raise EmbeddingConfigurationError("embedding.api_key is empty in config.json")

    endpoint = str(settings.get("base_url") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not endpoint or not model:
        raise EmbeddingConfigurationError("embedding.base_url and embedding.model are required")

    payload = {
        "input": list(texts),
        "model": model,
        "input_type": input_type,
        "encoding_format": settings.get("encoding_format", "float"),
        "truncate": settings.get("truncate", "END"),
    }
    timeout = float(settings.get("timeout_seconds", 30))

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.is_error:
        # Do not include request headers or the API key in exception text.
        detail = response.text[:500]
        raise EmbeddingAPIError(
            f"Embedding API returned HTTP {response.status_code}: {detail}"
        )

    try:
        body = response.json()
        rows = body["data"]
        vectors = [row["embedding"] for row in sorted(rows, key=lambda row: row["index"])]
        if len(vectors) != len(texts):
            raise ValueError("embedding count does not match input count")
        if any(not isinstance(vector, list) or not vector for vector in vectors):
            raise ValueError("embedding vector is empty or invalid")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for vector in vectors
            for value in vector
        ):
            raise ValueError("embedding vector contains non-finite or non-numeric values")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding vectors have inconsistent dimensions")
        return [[float(value) for value in vector] for vector in vectors]
    except (KeyError, TypeError, ValueError) as exc:
        raise EmbeddingAPIError(f"Invalid embedding API response: {exc}") from exc
