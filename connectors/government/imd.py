"""IMD Agromet Advisory Service (AAS) connector.

Bulletins are published as PDFs/HTML at district, block, state and national
level. We convert each bulletin into structured weather + crop advisories (not
store PDFs blindly). V1 ships the mapping + a fixture bulletin; the PDF/HTML
parser hooks are in `connectors/research/research_pdf.py`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.entities import resolve_crop
from pipelines.geocode import resolve_geography
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.imd")

IMD_AAS_URL = "https://mausam.imd.gov.in"  # advisories portal (agromet section)


class ImdConnector(AgricultureSourceConnector):
    source_id = "IMD_AAS"
    domain = "weather"

    def discover(self) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": "advisory_sample",
                "url": IMD_AAS_URL,
                "description": "Agromet advisory bulletin (structured)",
            }
        ]

    def fetch(self, resource: dict[str, Any]) -> Any:
        # Full crawler lands in V2 (PDF + HTML parsing). V1: fixture path.
        logger.info("IMD AAS crawl deferred to V2; using fixture bulletin.")
        return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        return self.fixture_records()

    @staticmethod
    def from_bulletin(bulletin: dict[str, Any]) -> dict[str, Any]:
        """Map a parsed bulletin (dict) to a canonical agromet advisory record."""
        geo = resolve_geography(bulletin.get("state"), bulletin.get("district"))
        crop_advisories = []
        for adv in bulletin.get("crop_advisories", []):
            crop = resolve_crop(adv.get("crop"))
            crop_advisories.append(
                {
                    "crop": (crop or {}).get("crop_id") if crop else None,
                    "crop_canonical": (crop or {}).get("canonical_en") if crop else None,
                    "growth_stage": adv.get("growth_stage"),
                    "risk": adv.get("risk"),
                    "action": adv.get("action"),
                }
            )
        record: dict[str, Any] = {
            "record_id": f"IMD-{bulletin.get('state')}-{bulletin.get('valid_from')}",
            "source": "IMD Agromet Advisory Service",
            "source_id": "IMD_AAS",
            "country": "IN",
            "state": bulletin.get("state"),
            "district": bulletin.get("district"),
            "valid_from": bulletin.get("valid_from"),
            "valid_to": bulletin.get("valid_to"),
            "weather": bulletin.get("weather", {}),
            "crop_advisories": crop_advisories,
            "authority": "government",
            "authority_level": "government",
            "source_url": bulletin.get("source_url"),
        }
        if geo:
            record.update({"state_code": geo.get("state_code"), "agroclimatic_zone": geo.get("agroclimatic_zone")})
        return record

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "imd_agromet_advisory.json"
        if path.exists():
            return [self.from_bulletin(b) for b in json.loads(path.read_text(encoding="utf-8"))]
        return []
