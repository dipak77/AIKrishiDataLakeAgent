"""Agmarknet mandi price connector (via data.gov.in, GODL-India).

Daily wholesale min/max/modal prices per market × commodity × variety.
Primary resource id: 9ef84268-d588-465a-a308-a864a43d0070
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from connectors.government.data_gov import DataGovConnector
from pipelines.entities import resolve_crop
from pipelines.geocode import resolve_geography
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.agmarknet")

MANDI_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"


class AgmarknetConnector(DataGovConnector, AgricultureSourceConnector):
    source_id = "GOI_AGMARKNET"
    domain = "market"

    def discover(self) -> list[dict[str, Any]]:
        return [{"resource_id": MANDI_RESOURCE_ID, "description": "daily mandi prices", "limit": self.limit}]

    def fetch(self, resource: dict[str, Any]) -> Any:
        try:
            payload = self.fetch_resource(resource["resource_id"], limit=resource.get("limit", 10))
            return {"_method": "live", "resource": resource, "payload": payload}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Agmarknet live fetch failed (%s); using fixtures.", type(exc).__name__)
            return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        if raw is None:
            return self.fixture_records()
        rows = (raw.get("payload") or {}).get("records") or []
        return [self._map(row) for row in rows]

    @staticmethod
    def _price(row: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            val = row.get(key)
            if val in (None, ""):
                continue
            try:
                return float(str(val).replace(",", ""))
            except ValueError:
                continue
        return None

    def _map(self, row: dict[str, Any]) -> dict[str, Any]:
        state = str(row.get("State") or row.get("state") or "").strip() or None
        district = str(row.get("District") or row.get("district") or "").strip() or None
        market = str(row.get("Market") or row.get("APMC") or "").strip() or None
        commodity = str(row.get("Commodity") or row.get("commodity") or "").strip() or None
        variety = str(row.get("Variety") or row.get("variety") or "").strip() or None
        arrival_date = str(row.get("Arrival_Date") or row.get("Price Date") or row.get("arrival_date") or "")

        crop = resolve_crop(commodity) if commodity else None
        geo = resolve_geography(state, district)

        record: dict[str, Any] = {
            "record_id": f"AMN-{market}-{commodity}-{arrival_date}",
            "source": "Agmarknet",
            "source_id": self.source_id,
            "country": "IN",
            "state": state,
            "district": district,
            "market": market,
            "commodity_raw": commodity,
            "crop": (crop or {}).get("crop_id") if crop else None,
            "crop_canonical": (crop or {}).get("canonical_en") if crop else None,
            "variety": variety,
            "grade": str(row.get("Grade") or row.get("grade") or "").strip() or None,
            "min_price": self._price(row, "Min Price (Rs./Quintal)", "Min_Price", "min_price"),
            "max_price": self._price(row, "Max Price (Rs./Quintal)", "Max_Price", "max_price"),
            "modal_price": self._price(row, "Modal Price (Rs./Quintal)", "Modal_Price", "modal_price"),
            "unit": "INR/quintal",
            "price_date": arrival_date or None,
            "authority": "government",
            "authority_level": "government",
            "source_url": f"https://api.data.gov.in/resource/{MANDI_RESOURCE_ID}",
        }
        if geo:
            record.update(
                {
                    "state_code": geo.get("state_code"),
                    "agroclimatic_zone": geo.get("agroclimatic_zone"),
                }
            )
        return record

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "agmarknet_mandi_price.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
