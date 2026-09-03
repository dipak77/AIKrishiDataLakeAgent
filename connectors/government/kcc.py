"""Kisan Call Centre (KCC) connector — real Indian farmer Q&A.

The OGD catalog publishes district×month-wise queries and expert answers. This
is the central dataset for: farmer question → agriculture intent → crop →
problem → expert recommendation.

Live fetch needs a data.gov.in API key (env `DATA_GOV_IN_API_KEY`) and internet;
offline it falls back to the bundled fixture in `data/fixtures/`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from connectors.base import AgricultureSourceConnector
from connectors.government.data_gov import DataGovConnector
from pipelines.entities import resolve_crop, resolve_season
from pipelines.geocode import resolve_geography
from pipelines.language import detect_language
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.kcc")

# KCC resources are declared in the source registry, not hard-coded here:
# ``metadata/sources/goi_kcc.yaml → acquisition.resources``.
#
# Why: the previously documented resource ids are gone. Verified 2026-09-02:
# ``GET https://api.data.gov.in/resource/5f039cdb2e054ab5b74bfc2a6e1a860b``
# returns ``{"message": "Meta not found", "status": "error"}``, and the old code
# passed the literal dict *key* ``"transcripts"`` as the resource id, so the
# request URL was ``/resource/transcripts`` — it could never have worked.
# Resources are therefore discovered (``agrilake-discover``) and registered as
# data. An unconfigured source reports zero resources rather than guessing.
KCC_RESOURCES: dict[str, str] = {}

CATEGORY_MAP = {
    "horticulture": "horticulture",
    "agriculture": "agronomy",
    "animal husbandry": "livestock",
    "fisheries": "fisheries",
    "sericulture": "sericulture",
}


class KccConnector(DataGovConnector, AgricultureSourceConnector):
    source_id = "GOI_KCC"
    domain = "farmer_qa"

    def configured_resources(self) -> list[dict[str, Any]]:
        """Resources declared in the registry (``acquisition.resources``)."""
        raw = (self.metadata.acquisition or {}).get("resources") or []
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and item.get("resource_id"):
                out.append(
                    {
                        "resource_id": str(item["resource_id"]),
                        "description": str(item.get("description") or "KCC farmer Q&A"),
                        "limit": self.limit,
                    }
                )
            elif isinstance(item, str) and item.strip():
                out.append({"resource_id": item.strip(), "description": "KCC farmer Q&A", "limit": self.limit})
        return out

    def discover(self) -> list[dict[str, Any]]:
        resources = self.configured_resources()
        if not resources:
            import os
            # Opt-in offline bundle: AGRILAKE_KCC_ARCHIVE=1 exposes the committed
            # fixture as an explicit "archive" resource so `make ingest
            # SOURCE=kcc` works air-gapped. It is labelled fixture-only below —
            # never a live resource id — so require_live still fails closed.
            if os.environ.get("AGRILAKE_KCC_ARCHIVE", "").lower() in ("1", "true"):
                return [{"resource_id": "archive", "description": "KCC farmer Q&A (bundled fixture-only bundle)", "limit": self.limit, "_fixture_only": True}]
            logger.warning(
                "GOI_KCC has no resources registered. Add real resource ids to "
                "metadata/sources/goi_kcc.yaml (acquisition.resources) after running "
                "`agrilake-discover`; refusing to guess an id."
            )
        return resources

    def fetch(self, resource: dict[str, Any]) -> Any:
        """Attempt live fetch; return None (→ fixtures) when unreachable."""
        if resource.get("_fixture_only"):
            return None  # no upstream call: this resource IS the fixture bundle
        try:
            payload = self.fetch_resource(resource["resource_id"], limit=resource.get("limit", 10))
            mode = self.http().mode
            return {
                "_method": "live" if mode in ("live", "record") else mode,
                "resource": resource,
                "payload": payload,
            }
        except Exception as exc:  # noqa: BLE001 - offline/rate-limit fallback
            logger.warning("KCC live fetch failed (%s); using fixtures.", type(exc).__name__)
            return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        if raw is None:
            return self.fixture_records()
        rows = (raw.get("payload") or {}).get("records") or []
        return [self._map(row, resource) for row in rows]

    # ── mapping ────────────────────────────────────────────────────────────
    def _map(self, row: dict[str, Any], resource: dict[str, Any]) -> dict[str, Any]:
        state = str(row.get("statename") or row.get("StateName") or "").strip() or None
        district = str(row.get("districtname") or row.get("DistrictName") or "").strip() or None
        block = str(row.get("blockname") or row.get("BlockName") or "").strip() or None
        query = str(row.get("querytext") or row.get("QueryText") or "").strip()
        answer = str(row.get("kccans") or row.get("KCCAnswer") or "").strip()
        season = resolve_season(str(row.get("season") or row.get("Season") or ""))
        crop_raw = str(row.get("crop") or row.get("Crop") or "").strip()
        sector = str(row.get("sector") or row.get("Sector") or "").strip().lower()

        geo = resolve_geography(state, district)
        crop = resolve_crop(crop_raw) if crop_raw else None
        lang = detect_language(query)

        created = str(row.get("createdon") or row.get("CreatedOn") or "")
        month = int(created[5:7]) if len(created) >= 7 and created[4] == "-" else None

        record: dict[str, Any] = {
            "query_id": f"KCC-{state or 'XX'}-{district or 'XX'}-{created[:7]}-{row.get('_id') or ''}",
            "source": "Kisan Call Centre",
            "source_id": self.source_id,
            "country": "IN",
            "state": state,
            "district": district,
            "block": block,
            "farmer_language": lang["language"],
            "query_original": query,
            "query_en": None,  # translation is a separate enrichment step
            "crop": (crop or {}).get("crop_id") if crop else None,
            "crop_canonical": (crop or {}).get("canonical_en") if crop else None,
            "crop_scientific_name": (crop or {}).get("scientific_name") if crop else None,
            "category": CATEGORY_MAP.get(sector, sector or None),
            "subcategory": str(row.get("querytype") or row.get("QueryType") or "").strip() or None,
            "answer_original": answer,
            "answer_normalized": answer.strip(),
            "season": season,
            "month": month,
            "growth_stage": None,
            "authority_level": "government_extension",
            "authority": "government",
            "source_url": f"https://api.data.gov.in/resource/{resource.get('resource_id')}",
            "expert_verified": True,
        }
        if geo:
            record.update(
                {
                    "state_code": geo.get("state_code"),
                    "agroclimatic_zone": geo.get("agroclimatic_zone"),
                    "agroecological_region": geo.get("agroecological_region"),
                }
            )
        return record

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "kcc_farmer_query.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
