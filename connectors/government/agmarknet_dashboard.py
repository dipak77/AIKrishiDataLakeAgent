"""Agmarknet dashboard connector — district-wise modal prices + arrivals + MSP.

The OGD/daily-price feed (``GOI_AGMARKNET``) is market × commodity × day with
min/max/modal. The Agmarknet portal dashboard API underneath
https://agmarknet.gov.in/ answers a different, complementary question:

    district × commodity → 3-day average price + arrival + MSP + trend

``POST https://api.agmarknet.gov.in/v1/dashboard-data/`` with::

    {"dashboard": "marketwise_price_arrival", "date": "YYYY-MM-DD",
     "group": [100000], "commodity": [100001], "variety": 100021,
     "state": <state_id>, "district": [<district_id>], "grades": [4],
     "limit": 50, "format": "json"}

Master codes (state/district/commodity/…) come from::

    GET .../v1/dashboard-filters?dashboard_name=marketwise_price_arrival

No API key is required. Verified live 2026-09-03: Maharashtra is
``state_id=20`` with 38 districts; district queries return per-commodity
aggregates whose ``reported_date`` lags the request date by ~2 days (the
``as_on_*`` columns always describe the latest *available* day, never a
forecast — the payload says so explicitly).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.entities import resolve_crop
from pipelines.geocode import resolve_geography
from pipelines.http import CassetteMiss, HttpClient, TransportOffline
from pipelines.refine import to_iso
from pipelines.storage import FIXTURES_DIR

logger = logging.getLogger("agrilake.connectors.agmarknet_dashboard")

DASHBOARD_BASE = os.environ.get(
    "AGMARKNET_DASHBOARD_BASE", "https://api.agmarknet.gov.in/v1"
)
DASHBOARD_NAME = "marketwise_price_arrival"

#: Cold-start state when the user does not configure one. Maharashtra-first
#: per the product request; override with ``AGRILAKE_AMD_STATE``.
DEFAULT_STATE = os.environ.get("AGRILAKE_AMD_STATE", "Maharashtra")

#: Browser-ish headers the dashboard API expects (verified live).
DASHBOARD_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://agmarknet.gov.in",
    "Referer": "https://agmarknet.gov.in/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
}

#: Masters change rarely (new markets/districts a few times a year).
MASTERS_TTL_S = 7 * 24 * 3600


def _masters_cache_path() -> Any:
    from pathlib import Path

    from pipelines.storage import DATA_DIR, ensure_dir

    return ensure_dir(DATA_DIR / "cache") / "agmarknet_masters.json"


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


class AgmarknetDashboardConnector(AgricultureSourceConnector):
    """District-wise Agmarknet dashboard prices (default: Maharashtra)."""

    source_id = "AGMARKNET_DASHBOARD"
    domain = "market_dashboard"

    _http: HttpClient | None = None

    def http(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient()
        return self._http

    # ── masters ──────────────────────────────────────────────────────────
    def load_masters(self) -> dict[str, Any]:
        """Master tables (states/districts/commodities), cached 7 days.

        Transport-aware: in replay mode the recorded masters cassette is
        served; offline raises (fail-closed) unless a fresh-enough cache file
        exists on disk.
        """
        path = _masters_cache_path()
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - float(cached.get("_cached_at", 0)) < MASTERS_TTL_S:
                    return cached
            except (ValueError, TypeError, OSError):
                pass
        try:
            payload = self.http().get(
                f"{DASHBOARD_BASE}/dashboard-filters",
                params={"dashboard_name": DASHBOARD_NAME},
                timeout=25,
            ).json()
            data = payload.get("data") or {}
            if not data.get("state_data"):
                raise ValueError("masters payload has no state_data")
        except (TransportOffline, CassetteMiss):
            raise
        except Exception as exc:  # noqa: BLE001 - fall back to cache/fixture
            logger.warning("dashboard masters fetch failed (%s)", type(exc).__name__)
            if path.is_file():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    pass
            fixture = FIXTURES_DIR / "agmarknet_dashboard_masters.json"
            if fixture.is_file():
                return json.loads(fixture.read_text(encoding="utf-8"))
            return {}
        data["_cached_at"] = time.time()
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return data

    def state_row(self, masters: dict[str, Any], state: str | None = None) -> dict[str, Any] | None:
        want = (state or DEFAULT_STATE).strip().lower()
        for row in masters.get("state_data", []):
            if str(row.get("state_name", "")).strip().lower() == want:
                return row
        return None

    def districts_for(self, masters: dict[str, Any], state_id: int) -> list[dict[str, Any]]:
        out = [
            r for r in masters.get("district_data", [])
            if r.get("state_id") == state_id and r.get("id") != 100007
        ]
        return sorted(out, key=lambda r: r.get("id"))

    def markets_for(self, masters: dict[str, Any], district_id: int) -> list[str]:
        return sorted(
            str(m.get("mkt_name", "")).strip()
            for m in masters.get("market_data", [])
            if m.get("district_id") == district_id and str(m.get("mkt_name", "")).strip()
        )

    # ── lifecycle ────────────────────────────────────────────────────────
    def discover(self) -> list[dict[str, Any]]:
        """One resource per district of the configured state."""
        try:
            masters = self.load_masters()
        except (TransportOffline, CassetteMiss) as exc:
            logger.warning("dashboard discover unavailable (%s)", type(exc).__name__)
            raise
        state = self.state_row(masters)
        if not state:
            logger.warning("state %r not in dashboard masters; no resources", DEFAULT_STATE)
            return []
        districts = self.districts_for(masters, int(state["state_id"]))
        resources = [
            {
                "resource_id": f"MH-{d['id']}",
                "description": f"{state['state_name']} / {d['district_name']} district prices",
                "state_id": int(state["state_id"]),
                "state_name": state["state_name"],
                "district_id": int(d["id"]),
                "district_name": d["district_name"],
                "date": _today(),
            }
            for d in districts
        ]
        if self.limit and len(resources) > self.limit:
            resources = resources[: self.limit]
        return resources

    def _payload(self, resource: dict[str, Any], page_url: str | None = None) -> dict[str, Any]:
        base_payload: dict[str, Any] = {
            "dashboard": DASHBOARD_NAME,
            "date": resource.get("date") or _today(),
            "group": [100000],
            "commodity": [100001],
            "variety": 100021,
            "state": resource["state_id"],
            "district": [resource["district_id"]],
            "grades": [4],
            "limit": 50,
            "format": "json",
        }
        if page_url:
            return self.http().post_json(page_url, payload=base_payload, headers=DASHBOARD_HEADERS)
        return self.http().post_json(
            f"{DASHBOARD_BASE}/dashboard-data/", payload=base_payload, headers=DASHBOARD_HEADERS
        )

    def fetch(self, resource: dict[str, Any]) -> Any:
        """POST all pages for one district; None → fixture fallback."""
        try:
            first = self._payload(resource)
            if str(first.get("status", "")).lower() != "success":
                raise ValueError(f"dashboard error: {first.get('message')}")
            records = list((first.get("data") or {}).get("records") or [])
            pagination = first.get("pagination") or {}
            total_pages = int(pagination.get("total_pages") or 1)
            next_page = pagination.get("next_page")
            page = 1
            while next_page and page < min(total_pages, 5):
                chunk = self._payload(resource, page_url=next_page)
                records.extend((chunk.get("data") or {}).get("records") or [])
                next_page = (chunk.get("pagination") or {}).get("next_page")
                page += 1
            mode = self.http().mode
            return {
                "_method": "live" if mode in ("live", "record") else mode,
                "resource": resource,
                "records": records,
            }
        except (TransportOffline, CassetteMiss):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("dashboard fetch failed for %s (%s); using fixtures.", resource.get("resource_id"), type(exc).__name__)
            return None

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        if raw is None:
            return self.fixture_records()
        return [self._map(row, resource) for row in raw.get("records", []) if row.get("cmdt_name")]

    @staticmethod
    def _map(row: dict[str, Any], resource: dict[str, Any]) -> dict[str, Any]:
        commodity = str(row.get("cmdt_name") or "").strip()
        crop = resolve_crop(commodity) if commodity else None
        state = resource.get("state_name") or "Maharashtra"
        district = resource.get("district_name")
        geo = resolve_geography(state, district)
        reported = str(row.get("reported_date") or "").strip()  # DD-MM-YYYY
        price_date = to_iso(reported, "DD-MM-YYYY") if reported else None
        record: dict[str, Any] = {
            "record_id": (
                f"AMND-{resource.get('district_id')}-{commodity[:32]}-{price_date or 'nodate'}"
            ),
            "source": "Agmarknet dashboard (marketwise price arrival)",
            "source_id": "AGMARKNET_DASHBOARD",
            "country": "IN",
            "state": state,
            "district": district,
            "market": None,  # district aggregate, not a single market
            "commodity_raw": commodity,
            "commodity_group": row.get("cmdt_grp_name"),
            "crop": (crop or {}).get("crop_id") if crop else None,
            "crop_canonical": (crop or {}).get("canonical_en") if crop else None,
            "modal_price": _num(row.get("as_on_price")),
            "prev_day_price": _num(row.get("one_day_ago_price")),
            "prev_2day_price": _num(row.get("two_day_ago_price")),
            "arrival_tonnes": _num(row.get("as_on_arrival")),
            "msp_price": _num(row.get("msp_price")),
            "trend": str(row.get("trend") or "").strip().lower() or None,
            "unit": "INR/quintal",
            "price_date": price_date,
            "price_kind": "district_average",
            "authority": "government",
            "authority_level": "government",
            "source_url": "https://agmarknet.gov.in/",
        }
        if reported and reported != price_date:
            record["price_date_raw"] = reported
        if geo:
            record.update(
                {
                    "state_code": geo.get("state_code"),
                    "district_code": geo.get("district_code"),
                    "agroclimatic_zone": geo.get("agroclimatic_zone"),
                }
            )
        return record

    def fixture_records(self) -> list[dict[str, Any]]:
        path = FIXTURES_DIR / "agmarknet_dashboard_sample.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []
