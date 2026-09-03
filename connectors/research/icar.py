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
from pipelines.http import CassetteMiss, HttpClient, TransportOffline
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.icar")

# NOTE: this URL has never served a real chunk list (it 404s in production).
# It is kept as the discovery hint only; `fetch()` treats any non-list JSON
# as unavailable and falls back to the fixture — honestly marked `fixture`.
ICAR_CHUNKS_URL = os.environ.get(
    "AGRI_ICAR_CHUNKS_URL",
    "https://icar.gov.in/api/research-chunks",
)


class IcarConnector(AgricultureSourceConnector):
    source_id = "ICAR"
    domain = "research"

    _http: HttpClient | None = None

    def http(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient()
        return self._http

    def discover(self) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": "icar_research_chunks",
                "description": "ICAR research chunk corpus (live JSON, fixture fallback)",
                "_url": ICAR_CHUNKS_URL,
            }
        ]

    def fetch(self, resource: dict[str, Any]) -> Any:
        """Attempt a live fetch via the shared transport; None → fixture."""
        url = resource.get("_url") or ICAR_CHUNKS_URL
        try:
            resp = self.http().get(url, timeout=15)
            data = resp.json()
            if isinstance(data, list) and data:
                logger.info("ICAR live fetch returned %d chunks", len(data))
                mode = self.http().mode
                return {
                    "_method": "live" if mode in ("live", "record") else mode,
                    "chunks": data,
                }
            logger.info("ICAR endpoint returned no chunk list; using fixture.")
        except (TransportOffline, CassetteMiss) as exc:
            logger.warning("ICAR %s (%s); no fallback.", type(exc).__name__, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - offline → fixture fallback
            logger.info("ICAR live fetch unavailable (%s); using fixture.", type(exc).__name__)
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        # Live payload ({"chunks": [...]}) OR fixture when raw is None.
        if isinstance(raw, dict) and isinstance(raw.get("chunks"), list):
            return raw["chunks"]
        if isinstance(raw, list):
            return raw
        return self.fixture_records()

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "icar_research_chunk.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
