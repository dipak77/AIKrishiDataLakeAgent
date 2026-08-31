"""Vision dataset connectors (Tier A licensed research datasets only).

PlantVillage / PlantDoc are bootstrap corpora for crop/healthy-unhealthy
classification and representation learning. They are NOT sufficient for Indian
field deployment (controlled backgrounds vs. dirty leaves, shadow, mixed
disease, low-end phones). First-party farmer uploads (consented) are the
long-term multimodal dataset.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.vision")


class PlantVillageConnector(AgricultureSourceConnector):
    source_id = "PLANTVILLAGE"
    domain = "images"

    def discover(self) -> list[dict[str, Any]]:
        return [{"resource_id": "plantvillage_meta", "description": "PlantVillage dataset metadata"}]

    def fetch(self, resource: dict[str, Any]) -> Any:
        logger.info("PlantVillage bulk download deferred to V2; metadata only.")
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return self.fixture_records()

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "plantvillage_meta.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []


class PlantDocConnector(AgricultureSourceConnector):
    source_id = "PLANTDOC"
    domain = "images"

    def discover(self) -> list[dict[str, Any]]:
        return [{"resource_id": "plantdoc_meta", "description": "PlantDoc dataset metadata"}]

    def fetch(self, resource: dict[str, Any]) -> Any:
        logger.info("PlantDoc bulk download deferred to V2; metadata only.")
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return self.fixture_records()

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "plantdoc_meta.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
