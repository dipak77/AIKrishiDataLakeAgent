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
from pipelines.refine import to_iso
from pipelines.storage import FIXTURES_DIR, slugify

logger = logging.getLogger("agrilake.connectors.agmarknet")

MANDI_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"


class AgmarknetConnector(DataGovConnector, AgricultureSourceConnector):
    source_id = "GOI_AGMARKNET"
    domain = "market"

    def discover(self) -> list[dict[str, Any]]:
        """Resources declared in the registry; the known daily-price id is the default."""
        raw = (self.metadata.acquisition or {}).get("resources") or [
            {"resource_id": MANDI_RESOURCE_ID, "description": "daily mandi prices"}
        ]
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and item.get("resource_id"):
                out.append(
                    {
                        "resource_id": str(item["resource_id"]),
                        "description": str(item.get("description") or "daily mandi prices"),
                        "limit": self.limit,
                    }
                )
        return out

    def fetch(self, resource: dict[str, Any]) -> Any:
        try:
            payload = self.fetch_resource(resource["resource_id"], limit=resource.get("limit", 10))
            # `record` still talks to the publisher, so its rows are live rows
            # that happen to be captured for replay.
            mode = self.http().mode
            return {
                "_method": "live" if mode in ("live", "record") else mode,
                "resource": resource,
                "payload": payload,
            }
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
        market = str(row.get("Market") or row.get("market") or row.get("APMC") or "").strip() or None
        commodity = str(row.get("Commodity") or row.get("commodity") or "").strip() or None
        variety = str(row.get("Variety") or row.get("variety") or "").strip() or None
        grade = str(row.get("Grade") or row.get("grade") or "").strip() or None
        arrival_raw = str(
            row.get("Arrival_Date") or row.get("arrival_date") or row.get("Price Date") or ""
        ).strip()

        crop = resolve_crop(commodity) if commodity else None
        geo = resolve_geography(state, district)

        # The live feed publishes DD/MM/YYYY ("02/09/2026"); the lake standard is
        # ISO-8601. Converting here is what keeps `season_signal()` and the
        # mandi trend aggregate chronologically correct (docs/v7-plan.md F9).
        price_date = to_iso(arrival_raw, self._arrival_date_format()) if arrival_raw else None

        record: dict[str, Any] = {
            "record_id": (
                f"AMN-{slugify(market or 'NA')}-{slugify(commodity or 'NA')}-{price_date or 'nodate'}"
            ),
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
            "grade": grade,
            "min_price": self._price(row, "Min Price (Rs./Quintal)", "Min_x0020_Price", "Min_Price", "min_price"),
            "max_price": self._price(row, "Max Price (Rs./Quintal)", "Max_x0020_Price", "Max_Price", "max_price"),
            "modal_price": self._price(
                row, "Modal Price (Rs./Quintal)", "Modal_x0020_Price", "Modal_Price", "modal_price"
            ),
            "unit": "INR/quintal",
            "price_date": price_date,
            "authority": "government",
            "authority_level": "government",
            "source_url": f"https://api.data.gov.in/resource/{MANDI_RESOURCE_ID}",
        }
        if arrival_raw and arrival_raw != price_date:
            record["price_date_raw"] = arrival_raw
        if geo:
            record.update(
                {
                    "state_code": geo.get("state_code"),
                    "district_code": geo.get("district_code"),
                    "agroclimatic_zone": geo.get("agroclimatic_zone"),
                }
            )
        return record

    @staticmethod
    def _arrival_date_format() -> str | None:
        """Date format declared for ``arrival_date`` in the source contract."""
        from pipelines.contracts import contract_for

        contract = contract_for("GOI_AGMARKNET")
        if contract is None:
            return None
        spec = contract.source_fields.get("arrival_date")
        return spec.format if spec else None

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "agmarknet_mandi_price.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
