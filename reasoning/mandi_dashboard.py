"""District-wise mandi intelligence (Agmarknet dashboard feed).

The OGD feed (``reasoning.mandi``) answers *market × commodity × day*. This
module answers the farmer's actual question — *"what is the rate in MY
district today?"* — from the Agmarknet dashboard aggregates
(``gold.fact_mandi_dashboard``):

* per-commodity modal price (district average, INR/quintal) + 3-day history
* arrival (metric tonnes) + MSP + above/below-MSP signal + trend flag

Every view carries ``data_source`` (``lake`` | ``fixture``) and the
``reported_date`` the prices actually describe (the dashboard lags ~2 days —
``as_on`` is the latest *available* day, never a forecast).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import FIXTURES_DIR, LAKE_DIR

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"

#: Post-2023 Maharashtra renames: dashboard uses the new names, farmers (and
#: our geography seed) often use the old ones. Both resolve.
DISTRICT_ALIASES: dict[str, str] = {
    "ahmednagar": "ahilyanagar",
    "aurangabad": "chattrapatisambhajinagar",
    "osmanabad": "dharashiv",
}


def _norm(name: str | None) -> str:
    import re

    return re.sub(r"[^\w]+", "", str(name or "").lower())


def _normalize_dates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        r = dict(r)
        for key in ("price_date",):
            v = r.get(key)
            if v is not None and hasattr(v, "isoformat"):
                r[key] = v.isoformat()
        out.append(r)
    return out


def load_dashboard_rows(lake: Path | None = None, limit: int = 20000) -> list[dict[str, Any]]:
    """Read ``fact_mandi_dashboard`` from the lake; fall back to the fixture."""
    from pipelines.storage import get_read_connection

    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        try:
            con = get_read_connection(lake)
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='gold'"
                ).fetchall()
            }
            if "fact_mandi_dashboard" in tables:
                cols = [
                    r[1]
                    for r in con.execute("PRAGMA table_info('gold.fact_mandi_dashboard')").fetchall()
                ]
                select = ",".join(f'"{c}"' for c in cols)
                rows = [
                    dict(zip(cols, r))
                    for r in con.execute(
                        f"SELECT {select} FROM gold.fact_mandi_dashboard ORDER BY price_date LIMIT ?",
                        [limit],
                    ).fetchall()
                ]
                rows = _normalize_dates(rows)
                if rows:
                    return rows
        except Exception:  # noqa: BLE001 - broken lake → fixture
            pass
    fixture = FIXTURES_DIR / "agmarknet_dashboard_sample.json"
    if fixture.exists():
        return _normalize_dates(json.loads(fixture.read_text(encoding="utf-8")))
    return []


def dashboard_source(lake: Path | None = None) -> str:
    """Where would :func:`load_dashboard_rows` read from?"""
    from pipelines.storage import get_read_connection

    lake_p = Path(lake or DEFAULT_LAKE)
    if lake_p.exists():
        try:
            con = get_read_connection(lake_p)
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='gold'"
                ).fetchall()
            }
            if "fact_mandi_dashboard" in tables:
                n = con.execute("SELECT count(*) FROM gold.fact_mandi_dashboard").fetchone()[0]
                if n:
                    return "lake"
        except Exception:  # noqa: BLE001
            pass
    return "fixture" if (FIXTURES_DIR / "agmarknet_dashboard_sample.json").exists() else "empty"


def known_districts(rows: list[dict[str, Any]] | None = None, lake: Path | None = None) -> list[str]:
    """District names present in the dashboard data (sorted)."""
    rows = rows if rows is not None else load_dashboard_rows(lake)
    return sorted({str(r.get("district") or "") for r in rows if r.get("district")})


def covered_districts(lake: Path | None = None) -> list[str]:
    """Districts the API can answer: lake coverage ∪ bundled sample.

    A thin lake (``--limit`` run) covers a few districts; the picker still
    offers every district with a sample fallback, and each view labels its
    own ``data_source`` honestly.
    """
    names = set(known_districts(lake=lake))
    fixture = FIXTURES_DIR / "agmarknet_dashboard_sample.json"
    if fixture.exists():
        try:
            names.update(known_districts(_normalize_dates(json.loads(fixture.read_text(encoding="utf-8")))))
        except ValueError:
            pass
    return sorted(names)


def resolve_dashboard_district(query: str, known: list[str]) -> str | None:
    """Match a user district string (any rename/spelling) to a dashboard district."""
    q = _norm(query)
    if not q:
        return None
    q = DISTRICT_ALIASES.get(q, q)
    normed = {name: DISTRICT_ALIASES.get(_norm(name), _norm(name)) for name in known}
    for name, n in normed.items():
        if n == q:
            return name
    for name, n in normed.items():
        if q and (q in n or n in q):
            return name
    return None


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    try:
        return round((a - b) / b * 100, 1)
    except (TypeError, ZeroDivisionError):
        return None


@dataclass
class DistrictCommodityRate:
    commodity: str
    commodity_group: str | None
    modal_price: float | None
    prev_day_price: float | None
    prev_2day_price: float | None
    day_change_pct: float | None
    arrival_tonnes: float | None
    msp_price: float | None
    vs_msp_pct: float | None
    vs_msp: str | None          # "above MSP" | "below MSP" | "at MSP" | None
    trend: str | None
    price_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class DistrictMandiView:
    state: str
    district: str
    price_date: str | None
    rates: list[DistrictCommodityRate] = field(default_factory=list)
    data_source: str = "lake"
    notes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "district": self.district,
            "price_date": self.price_date,
            "rates": [r.as_dict() for r in self.rates],
            "data_source": self.data_source,
            "notes": self.notes,
            "evidence": self.evidence,
        }


def district_view(
    district: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    lake: Path | None = None,
    state: str | None = None,
    commodity: str | None = None,
) -> DistrictMandiView | None:
    """District-wise rates for today (optionally one commodity).

    ``district`` is the user's current location (e.g. from phone GPS
    reverse-geocoding): renames, case and spacing are tolerated.
    Returns None when the district has no dashboard coverage.
    """
    from pipelines.entities import resolve_crop

    rows_was_default = rows is None
    rows = rows if rows is not None else load_dashboard_rows(lake)
    data_source = dashboard_source(lake) if rows_was_default else "provided"

    match = resolve_dashboard_district(district, known_districts(rows))
    if not match and rows_was_default and data_source == "lake":
        # The lake is real but thin (a --limit run covers a few districts).
        # Fall back to the bundled sample — labelled — instead of 404.
        fixture = FIXTURES_DIR / "agmarknet_dashboard_sample.json"
        if fixture.exists():
            rows = _normalize_dates(json.loads(fixture.read_text(encoding="utf-8")))
            match = resolve_dashboard_district(district, known_districts(rows))
            if match:
                data_source = "fixture"
    if not match:
        return None
    pool = [r for r in rows if str(r.get("district") or "") == match]
    if state and pool:
        pool = [r for r in pool if str(r.get("state") or "").lower() == state.lower()] or pool
    if commodity:
        crop_row = resolve_crop(commodity)
        canon = crop_row["canonical_en"] if crop_row else commodity
        crop_id = crop_row["crop_id"] if crop_row else None
        pool = [
            r for r in pool
            if str(r.get("commodity_raw") or "").lower() == commodity.lower()
            or str(r.get("crop_canonical") or "").lower() == canon.lower()
            or (crop_id and r.get("crop") == crop_id)
        ]
    if not pool:
        return None

    # Latest reported date first; one row per commodity (latest wins).
    pool = sorted(pool, key=lambda r: str(r.get("price_date") or ""), reverse=True)
    seen: set[str] = set()
    rates: list[DistrictCommodityRate] = []
    for r in pool:
        key = str(r.get("commodity_raw") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        modal = r.get("modal_price")
        modal_f = float(modal) if modal is not None else None
        msp = r.get("msp_price")
        msp_f = float(msp) if msp is not None else None
        vs_pct = _pct(modal_f, msp_f)
        vs = None
        if vs_pct is not None:
            vs = "above MSP" if vs_pct > 0.5 else ("below MSP" if vs_pct < -0.5 else "at MSP")
        rates.append(
            DistrictCommodityRate(
                commodity=key,
                commodity_group=r.get("commodity_group"),
                modal_price=modal_f,
                prev_day_price=float(r["prev_day_price"]) if r.get("prev_day_price") is not None else None,
                prev_2day_price=float(r["prev_2day_price"]) if r.get("prev_2day_price") is not None else None,
                day_change_pct=_pct(modal_f, float(r["prev_day_price"]) if r.get("prev_day_price") is not None else None),
                arrival_tonnes=float(r["arrival_tonnes"]) if r.get("arrival_tonnes") is not None else None,
                msp_price=msp_f,
                vs_msp_pct=vs_pct,
                vs_msp=vs,
                trend=r.get("trend"),
                price_date=r.get("price_date"),
            )
        )
    rates.sort(key=lambda x: x.commodity)
    latest = max((r.price_date or "" for r in rates), default=None)
    state_name = pool[0].get("state") or state or "Maharashtra"

    evidence = {
        "source": "Agmarknet dashboard (marketwise price arrival)",
        "authority": "government",
        "license": {"type": "GODL-India"},
        "unit": "INR/quintal",
        "source_url": "https://agmarknet.gov.in/",
    }
    notes = [
        f"District-average modal prices reported {latest or 'on the latest available day'} "
        "(dashboard lags ~2 days; as_on = latest available, not a forecast)."
    ]
    if data_source == "fixture":
        evidence["source"] = "Bundled Agmarknet dashboard sample (offline fixture — not live prices)"
        notes.append("Sample data: ingest AGMARKNET_DASHBOARD for live district rates.")
    return DistrictMandiView(
        state=str(state_name),
        district=match,
        price_date=latest,
        rates=rates,
        data_source=data_source,
        notes=notes,
        evidence=evidence,
    )
