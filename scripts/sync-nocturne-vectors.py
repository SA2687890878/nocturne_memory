"""Manually synchronize the configured memory corpus into its sidecar vector index."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from backend.semantic_sync import sync_configured_vector_index

if __name__ == "__main__":
    print(json.dumps(asyncio.run(sync_configured_vector_index()), ensure_ascii=False))
