"""FAOSTAT connector (global statistical baseline).

Used for India-vs-world comparisons, production/yield trends, fertilizer and
land-use trends — NOT as an agronomy advice source.

Endpoint (no key required):
    GET https://fenixservices.fao.org/faostat/api/v1/en/data/QCL
        ?area=100&area_cs=FAO&element=5510&element_cs=FAO
        &item={item}&item_cs=FAO&year={year}&show_codes=true&show_unit=true&output_type=csv
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from typing import Any

import requests

from connectors.base import AgricultureSourceConnector
from pipelines.entities import resolve_crop
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.faostat")

def _faostat_base() -> str:
    from pipelines.config import load_settings

    return load_settings().faostat_base_url or os.environ.get(
        "FAOSTAT_BASE_URL", "https://fenixservices.fao.org/faostat/api/v1"
    )


FAOSTAT_BASE = _faostat_base()

# (element_code, element) used by the crop-production fact table.
ELEMENT_PRODUCTION = 5510
ELEMENT_AREA = 5312
INDIA_AREA_CODE = 100

# FAO item code/name → canonical crop hint (name-level resolve falls back to alias).
# A representative subset; extend as the corpus grows.
FAO_ITEM_ALIASES = {
    "Rice, paddy": "rice",
    "Wheat": "wheat",
    "Maize": "maize",
    "Sorghum": "jowar",
    "Millet": "bajra",
    "Pulses, nes": "pulses",
    "Groundnuts, with shell": "groundnut",
    "Soybeans": "soybean",
    "Seed cotton": "cotton",
    "Sugar cane": "sugarcane",
    "Onions, dry": "onion",
    "Tomatoes": "tomato",
    "Potatoes": "potato",
    "Chillies and peppers, dry": "chilli",
    "Mangoes, mangosteens, guavas": "mango",
    "Bananas": "banana",
}


class FaostatConnector(AgricultureSourceConnector):
    source_id = "FAO_FAOSTAT"
    domain = "production"

    def discover(self) -> list[dict[str, Any]]:
        # A small, representative pull: India production for key crops, latest years.
        return [
            {
                "resource_id": "QCL",
                "area": INDIA_AREA_CODE,
                "items": list(FAO_ITEM_ALIASES.items()),
                "years": [2021, 2022, 2023],
            }
        ]

    def fetch(self, resource: dict[str, Any]) -> Any:
        try:
            params = {
                "area": resource["area"],
                "area_cs": "FAO",
                "element": f"{ELEMENT_PRODUCTION},{ELEMENT_AREA}",
                "element_cs": "FAO",
                "item": ",".join(str(code) for code, _ in resource["items"]),
                "item_cs": "FAO",
                "year": ",".join(str(y) for y in resource["years"]),
                "show_codes": "true",
                "show_unit": "true",
                "output_type": "csv",
            }
            resp = requests.get(f"{FAOSTAT_BASE}/en/data/QCL", params=params, timeout=30)
            resp.raise_for_status()
            return {"_method": "live", "csv": resp.text}
        except Exception as exc:  # noqa: BLE001
            logger.warning("FAOSTAT fetch failed (%s); using fixtures.", type(exc).__name__)
            return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        if raw is None:
            return self.fixture_records()
        reader = csv.DictReader(io.StringIO(raw["csv"]))

        # Pivot (item, year) → {area_hectares, production_tonnes} → fact_crop_production.
        pivoted: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for row in reader:
            item_name = row.get("Item") or ""
            year = row.get("Year") or ""
            element_code = row.get("Element Code") or ""
            try:
                value = float(row.get("Value") or "")
            except ValueError:
                continue
            key = (item_name, year)
            if key not in pivoted:
                pivoted[key] = {"item_name": item_name, "year": year}
                order.append(key)
            if element_code == str(ELEMENT_PRODUCTION):
                pivoted[key]["production_tonnes"] = value
            elif element_code == str(ELEMENT_AREA):
                pivoted[key]["area_hectares"] = value

        records: list[dict[str, Any]] = []
        for key in order:
            rec = pivoted[key]
            alias = FAO_ITEM_ALIASES.get(rec["item_name"])
            crop = resolve_crop(alias) if alias else resolve_crop(rec["item_name"])
            area = rec.get("area_hectares")
            prod = rec.get("production_tonnes")
            yield_kg_ha = round(prod * 1000 / area, 2) if (prod is not None and area) else None
            records.append(
                {
                    "record_id": f"FAO-{INDIA_AREA_CODE}-{rec['item_name']}-{rec['year']}",
                    "source": "FAOSTAT",
                    "source_id": self.source_id,
                    "country": "IN",
                    "faostat_item": rec["item_name"],
                    "crop": (crop or {}).get("crop_id") if crop else None,
                    "crop_canonical": (crop or {}).get("canonical_en") if crop else None,
                    "year": int(rec["year"]) if str(rec["year"]).isdigit() else None,
                    "area_hectares": area,
                    "production_tonnes": prod,
                    "yield_kg_ha": yield_kg_ha,
                    "authority": "research",
                    "authority_level": "research",
                    "source_url": "https://www.fao.org/faostat/",
                }
            )
        return records

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "faostat_crop_production.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
