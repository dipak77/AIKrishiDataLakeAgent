"""ICAR / IARI research-document connector.

V1: source registration + chunk schema + fixture. The full PDF→chunks pipeline
lives in `research_pdf.py`; ICAR/IARI/KVK/SAU documents are run through it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.icar")


class IcarConnector(AgricultureSourceConnector):
    source_id = "ICAR"
    domain = "research"

    def discover(self) -> list[dict[str, Any]]:
        return [{"resource_id": "icar_sample", "description": "ICAR research chunk fixture"}]

    def fetch(self, resource: dict[str, Any]) -> Any:
        logger.info("ICAR corpus crawl deferred to V2 (PDF pipeline); using fixture.")
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return self.fixture_records()

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "icar_research_chunk.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
