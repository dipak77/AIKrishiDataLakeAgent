"""Soil Health Card (SHC) connector.

SHC soil status uses N, P, K, S, Zn, Fe, Cu, Mn, B, pH, EC, Organic Carbon and
provides fertilizer/soil-amendment recommendations. Context captured by the SHC
app (previous crop, soil type, drainage, water source, target yield) is
preserved so fertilizer advice can become context-aware rather than
crop → fertilizer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.entities import resolve_crop
from pipelines.geocode import resolve_geography
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.soil_health")

SHC_PARAMS = ["N", "P", "K", "S", "Zn", "Fe", "Cu", "Mn", "B", "pH", "EC", "OC"]


class SoilHealthConnector(AgricultureSourceConnector):
    source_id = "GOI_SHC"
    domain = "soil"

    def discover(self) -> list[dict[str, Any]]:
        return [{"resource_id": "shc_sample", "description": "Soil Health Card sample"}]

    def fetch(self, resource: dict[str, Any]) -> Any:
        logger.info("SHC bulk download deferred to V2; using fixture sample.")
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return self.fixture_records()

    @staticmethod
    def from_sample(sample: dict[str, Any]) -> dict[str, Any]:
        geo = resolve_geography(sample.get("state"), sample.get("district"))
        prev = resolve_crop(sample.get("previous_crop"))
        target = resolve_crop(sample.get("target_crop"))
        record: dict[str, Any] = {
            "record_id": f"SHC-{sample.get('state')}-{sample.get('district')}-{sample.get('sample_id')}",
            "source": "Soil Health Card",
            "source_id": "GOI_SHC",
            "country": "IN",
            "state": sample.get("state"),
            "district": sample.get("district"),
            "sample_id": sample.get("sample_id"),
            "soil_type": sample.get("soil_type"),
            "previous_crop": (prev or {}).get("crop_id") if prev else None,
            "target_crop": (target or {}).get("crop_id") if target else None,
            "target_yield": sample.get("target_yield"),
            "irrigation": sample.get("irrigation"),
            "drainage": sample.get("drainage"),
            "water_source": sample.get("water_source"),
            "soil_test": {k: sample.get(k) for k in SHC_PARAMS},
            "recommendation": sample.get("recommendation"),
            "authority": "government",
            "authority_level": "government",
            "source_url": sample.get("source_url"),
        }
        if geo:
            record.update({"state_code": geo.get("state_code"), "agroclimatic_zone": geo.get("agroclimatic_zone")})
        return record

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "soil_health_sample.json"
        if path.exists():
            return [self.from_sample(s) for s in json.loads(path.read_text(encoding="utf-8"))]
        return []
