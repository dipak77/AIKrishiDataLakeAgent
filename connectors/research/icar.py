"""ICAR / IARI research-document connector.

V1: source registration + chunk schema + fixture. The full PDF→chunks pipeline
lives in `research_pdf.py`; ICAR/IARI/KVK/SAU documents are run through it.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.icar")

# Live research-chunk endpoint (JSON list of chunks). Offline/unreachable in
# this sandbox → the connector returns None → the fixture is used instead.
ICAR_CHUNKS_URL = os.environ.get(
    "AGRI_ICAR_CHUNKS_URL",
    "https://icar.gov.in/api/research-chunks",
)


class IcarConnector(AgricultureSourceConnector):
    source_id = "ICAR"
    domain = "research"

    def discover(self) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": "icar_research_chunks",
                "description": "ICAR research chunk corpus (live JSON, fixture fallback)",
                "_url": ICAR_CHUNKS_URL,
            }
        ]

    def fetch(self, resource: dict[str, Any]) -> Any:
        """Attempt a live fetch; fall back to None (fixture) on any failure."""
        import requests

        url = resource.get("_url") or ICAR_CHUNKS_URL
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                logger.info("ICAR live fetch returned %d chunks", len(data))
                return data
        except Exception as exc:  # noqa: BLE001 - offline → fixture fallback
            logger.info("ICAR live fetch unavailable (%s); using fixture.", type(exc).__name__)
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        # Live payload (list of chunk dicts) OR fixture when raw is None.
        if isinstance(raw, list):
            return raw
        return self.fixture_records()

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "icar_research_chunk.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
