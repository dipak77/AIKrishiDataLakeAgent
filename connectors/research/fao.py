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

from connectors.base import AgricultureSourceConnector
from pipelines.entities import resolve_crop
from pipelines.http import HttpClient
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.faostat")


def faostat_base() -> str:
    """Resolve the FAOSTAT base URL lazily (env wins, so tests can override)."""
    from pipelines.config import load_settings

    try:
        configured = load_settings().faostat_base_url
    except Exception:  # noqa: BLE001 - config must never break ingestion
        configured = ""
    return configured or os.environ.get(
        "FAOSTAT_BASE_URL", "https://fenixservices.fao.org/faostat/api/v1"
    )


# Backwards-compat alias: resolved once at import for callers that reference
# the constant, but `fetch()` always calls `faostat_base()` fresh.
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


# FAO item name → FAO numeric code (QCL domain standard).
# Covers every key in FAO_ITEM_ALIASES so `discover()` never emits an item the
# `fetch()` cannot encode (previously 4 aliases silently dropped out).
FAO_ITEM_CODES: dict[str, int] = {
    "Wheat": 15,
    "Rice, paddy": 27,
    "Maize": 56,
    "Millet": 79,
    "Sorghum": 83,
    "Pulses, nes": 92,
    "Potatoes": 116,
    "Sugar cane": 156,
    "Soybeans": 236,
    "Groundnuts, with shell": 242,
    "Seed cotton": 328,
    "Tomatoes": 388,
    "Onions, dry": 403,
    "Chillies and peppers, dry": 406,
    "Bananas": 486,
    "Mangoes, mangosteens, guavas": 508,
}


class FaostatConnector(AgricultureSourceConnector):
    source_id = "FAO_FAOSTAT"
    domain = "production"

    #: per-instance transport handle (mirrors DataGovConnector so the
    #: orchestrator's --transport flag controls FAOSTAT too).
    _http: HttpClient | None = None

    def http(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient()
        return self._http

    def discover(self) -> list[dict[str, Any]]:
        # A small, representative pull: India production for key crops, latest years.
        return [
            {
                "resource_id": "QCL",
                "description": "FAOSTAT crop production (India)",
                "area": INDIA_AREA_CODE,
                "items": list(FAO_ITEM_ALIASES.items()),
                "years": [2021, 2022, 2023],
            }
        ]

    def fetch(self, resource: dict[str, Any]) -> Any:
        import urllib.parse

        from pipelines.http import CassetteMiss, TransportOffline
        try:
            item_codes = [
                str(FAO_ITEM_CODES[name])
                for name, _ in resource["items"]
                if name in FAO_ITEM_CODES
            ]
            params = {
                "area": resource["area"],
                "area_cs": "FAO",
                "element": f"{ELEMENT_PRODUCTION},{ELEMENT_AREA}",
                "element_cs": "FAO",
                "item": ",".join(item_codes) if item_codes else "27,15,56",
                "item_cs": "FAO",
                "year": ",".join(str(y) for y in resource["years"]),
                "show_codes": "true",
                "show_unit": "true",
                "output_type": "csv",
            }
            url = f"{faostat_base()}/en/data/QCL?{urllib.parse.urlencode(params)}"
            # Route through the shared transport so live/record/replay/offline
            # semantics (cassettes, throttling, redaction) apply to FAOSTAT too.
            resp = self.http().get(url, timeout=15)
            mode = self.http().mode
            return {
                "_method": "live" if mode in ("live", "record") else mode,
                "csv": resp.text,
            }
        except (TransportOffline, CassetteMiss) as exc:
            # Fail-closed transports must surface, never silently become fixtures.
            logger.warning("FAOSTAT %s (%s); no fallback.", type(exc).__name__, exc)
            raise
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
