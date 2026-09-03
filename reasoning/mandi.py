"""Mandi intelligence (Track 6).

Turns `fact_mandi_price` rows (Agmarknet modal/min/max prices per market ×
commodity × day) into market snapshots and simple, clearly-evidenced signals:

  - latest price + daily stats (mean/min/max/spread/volatility)
  - trend direction (up / down / flat) over the observed window
  - season signal from the crop calendar (harvest glut vs lean window)

All signals are heuristics over the observed window and are labelled with their
evidence and uncertainty — never presented as price predictions.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"

# Crop calendar months → price-pressure signal.
_HARVEST_SIGNAL = {
    "harvest": "Harvest/arrival season — supply typically peaks, prices soften.",
    "lean": "Lean (off-harvest) window — arrivals typically thin, prices firm.",
    "transition": "Transition window — arrivals moderate, prices variable.",
    "unknown": "No crop-calendar entry — season signal unavailable.",
}


@dataclass
class PriceStat:
    crop_id: str | None
    commodity: str
    market: str
    state: str | None
    district: str | None
    n_days: int
    latest_date: str
    latest_modal: float
    mean_modal: float
    min_price: float
    max_price: float
    spread_pct: float          # (max-min)/mean over the window
    volatility_pct: float      # stdev / mean of modal prices
    trend: str                 # rising | falling | flat

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class MandiAdvisory:
    commodity: str
    market: str | None
    stats: list[PriceStat] = field(default_factory=list)
    season_signal: str = "unknown"
    season_note: str = ""
    notes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(
        default_factory=lambda: {
            "source": "Agmarknet (via data.gov.in)",
            "authority": "government",
            "license": {"type": "GODL-India"},
            "unit": "INR/quintal",
        }
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "commodity": self.commodity,
            "market": self.market,
            "stats": [s.as_dict() for s in self.stats],
            "season_signal": self.season_signal,
            "season_note": self.season_note,
            "notes": self.notes,
            "evidence": self.evidence,
        }


def _normalize_dates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce date/datetime objects to ISO strings (DuckDB returns native dates)."""
    out: list[dict[str, Any]] = []
    for r in rows:
        r = dict(r)
        for key in ("price_date", "arrival_date"):
            v = r.get(key)
            if v is not None and hasattr(v, "isoformat"):
                r[key] = v.isoformat()
        out.append(r)
    return out


def load_price_rows(lake: Path | None = None, limit: int = 10000) -> list[dict[str, Any]]:
    """Read `fact_mandi_price` from the lake; fall back to the fixture."""
    from pipelines.storage import FIXTURES_DIR, get_read_connection
    import json

    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        con = get_read_connection(lake)
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='gold'"
            ).fetchall()
        }
        if "fact_mandi_price" in tables:
            cols = [
                r[1]
                for r in con.execute("PRAGMA table_info('gold.fact_mandi_price')").fetchall()
            ]
            select = ",".join(f'"{c}"' for c in cols)
            rows = [
                dict(zip(cols, r))
                for r in con.execute(
                    f"SELECT {select} FROM gold.fact_mandi_price ORDER BY price_date LIMIT ?",
                    [limit],
                ).fetchall()
            ]
            return _normalize_dates(rows)
    # Fallback: bundled fixture.
    fixture = FIXTURES_DIR / "agmarknet_mandi_price.json"
    if fixture.exists():
        return _normalize_dates(json.loads(fixture.read_text(encoding="utf-8")))
    return []


def price_stats(rows: list[dict[str, Any]]) -> list[PriceStat]:
    """Aggregate modal/min/max prices per (commodity, market)."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = (str(r.get("commodity_raw") or r.get("crop_canonical") or ""),
               str(r.get("market") or ""))
        if key[0]:
            groups.setdefault(key, []).append(r)

    out: list[PriceStat] = []
    for (commodity, market), recs in groups.items():
        modal = [float(r["modal_price"]) for r in recs if r.get("modal_price") is not None]
        if not modal:
            continue
        mins = [float(r["min_price"]) for r in recs if r.get("min_price") is not None]
        maxs = [float(r["max_price"]) for r in recs if r.get("max_price") is not None]
        latest = max(recs, key=lambda r: r.get("price_date") or "")
        mean = statistics.mean(modal)
        stdev = statistics.pstdev(modal) if len(modal) > 1 else 0.0
        first, last = modal[0], modal[-1]
        if len(modal) >= 2 and last > first * 1.01:
            trend = "rising"
        elif len(modal) >= 2 and last < first * 0.99:
            trend = "falling"
        else:
            trend = "flat"
        out.append(
            PriceStat(
                crop_id=latest.get("crop") or recs[0].get("crop"),
                commodity=commodity,
                market=market,
                state=latest.get("state") or recs[0].get("state"),
                district=latest.get("district") or recs[0].get("district"),
                n_days=len(modal),
                latest_date=latest.get("price_date") or "",
                latest_modal=round(float(latest["modal_price"]), 2),
                mean_modal=round(mean, 2),
                min_price=round(min(mins), 2) if mins else 0.0,
                max_price=round(max(maxs), 2) if maxs else 0.0,
                spread_pct=round((max(maxs) - min(mins)) / mean * 100, 1) if mins and mean else 0.0,
                volatility_pct=round(stdev / mean * 100, 1) if mean else 0.0,
                trend=trend,
            )
        )
    out.sort(key=lambda s: s.commodity)
    return out


def season_signal(crop_id: str | None, price_date: str | None, lake: Path | None = None) -> tuple[str, str]:
    """Map a price date onto the crop calendar → harvest/lean/transition."""
    from domain.seed_data import CROP_CALENDAR, CROP_CALENDAR_TOP20

    if not crop_id or not price_date:
        return "unknown", _HARVEST_SIGNAL["unknown"]
    try:
        month = int(price_date.split("-")[1])
    except (IndexError, ValueError):
        return "unknown", _HARVEST_SIGNAL["unknown"]

    calendar = CROP_CALENDAR + CROP_CALENDAR_TOP20
    matches = [c for c in calendar if c["crop_id"] == crop_id]
    harvest_months: set[int] = set()
    for c in matches:
        if c["stage_id"] in ("STAGE_HARVEST", "STAGE_MATURITY"):
            m = c["month_start"]
            while True:
                harvest_months.add(m)
                if m == c["month_end"]:
                    break
                m = m % 12 + 1
    if not harvest_months:
        return "unknown", _HARVEST_SIGNAL["unknown"]
    if month in harvest_months:
        return "harvest", _HARVEST_SIGNAL["harvest"]
    # Lean = a couple of months just before the next harvest window.
    next_harvest = min((h for h in harvest_months), key=lambda h: (h - month) % 12)
    dist = (next_harvest - month) % 12
    if dist in (1, 2):
        return "lean", _HARVEST_SIGNAL["lean"]
    return "transition", _HARVEST_SIGNAL["transition"]


def market_advisory(
    commodity: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    lake: Path | None = None,
    market: str | None = None,
) -> MandiAdvisory | None:
    """Snapshot + trend + season signal for a commodity (optionally one market)."""
    from pipelines.entities import resolve_crop

    rows_was_default = rows is None
    rows = rows if rows is not None else load_price_rows(lake)
    crop_row = resolve_crop(commodity)
    crop_id = crop_row["crop_id"] if crop_row else None
    canon = crop_row["canonical_en"] if crop_row else commodity

    matches = [
        r for r in rows
        if str(r.get("commodity_raw") or "").lower() == commodity.lower()
        or str(r.get("crop_canonical") or "").lower() == canon.lower()
        or (crop_id and r.get("crop") == crop_id)
    ]
    if market:
        matches = [r for r in matches if str(r.get("market") or "").lower() == market.lower()]

    if not matches and rows_was_default:
        from pipelines.storage import FIXTURES_DIR
        import json
        fixture = FIXTURES_DIR / "agmarknet_mandi_price.json"
        if fixture.exists():
            fixture_rows = _normalize_dates(json.loads(fixture.read_text(encoding="utf-8")))
            matches = [
                r for r in fixture_rows
                if str(r.get("commodity_raw") or "").lower() == commodity.lower()
                or str(r.get("crop_canonical") or "").lower() == canon.lower()
                or (crop_id and r.get("crop") == crop_id)
            ]
            if market:
                matches = [r for r in matches if str(r.get("market") or "").lower() == market.lower()]

    if not matches:
        return None

    stats = price_stats(matches)
    latest_date = max((s.latest_date for s in stats), default="")
    signal, note = season_signal(crop_id, latest_date, lake)

    adv = MandiAdvisory(
        commodity=canon,
        market=market,
        stats=stats,
        season_signal=signal,
        season_note=note,
    )
    for s in stats:
        adv.notes.append(
            f"{s.market}: modal {s.latest_modal} INR/q on {s.latest_date} "
            f"({s.trend} over {s.n_days} days, ±{s.volatility_pct}% volatility)"
        )
    adv.notes.append(
        "Signals are descriptive heuristics over the observed window — not price predictions."
    )
    return adv


def list_markets(lake: Path | None = None) -> list[dict[str, Any]]:
    """Return `dim_market` rows (id, name, state, district, key commodities)."""
    from pipelines.storage import get_read_connection

    lake = Path(lake or DEFAULT_LAKE)
    con = get_read_connection(lake)
    cols = [r[1] for r in con.execute("PRAGMA table_info('gold.dim_market')").fetchall()]
    return [
        dict(zip(cols, r))
        for r in con.execute(
            "SELECT * FROM gold.dim_market ORDER BY name"
        ).fetchall()
    ]
