"""Crop planning (Track 8).

Reads the phenological crop calendar (with location overrides) from the lake
and produces:

  - `crop_plan(crop, location)` → season(s), ordered stage timeline with months,
    sowing window, harvest window, duration
  - `crops_to_sow(month, location)` → reverse lookup: what can be sown in a
    given month at a location
  - off-window risk note when the current month falls outside the sowing window

Location overrides are applied district-first, then state, then the India-wide
base calendar (mirrors the blueprint's calendar override hierarchy).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"


@dataclass
class StageWindow:
    stage: str
    months: list[int]
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "months": self.months, "note": self.note}


@dataclass
class CropPlan:
    crop: str
    crop_id: str
    seasons: list[str] = field(default_factory=list)
    timeline: list[StageWindow] = field(default_factory=list)
    sow_window: list[int] = field(default_factory=list)
    harvest_window: list[int] = field(default_factory=list)
    duration_months: int | None = None
    location: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(
        default_factory=lambda: {
            "source": "ICAR/SAU crop calendars (seed ontology)",
            "authority": "government_extension",
            "license": {"type": "GODL-India"},
        }
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "crop": self.crop,
            "crop_id": self.crop_id,
            "seasons": self.seasons,
            "timeline": [t.as_dict() for t in self.timeline],
            "sow_window": self.sow_window,
            "harvest_window": self.harvest_window,
            "duration_months": self.duration_months,
            "location": self.location,
            "notes": self.notes,
            "evidence": self.evidence,
        }


def _months_between(start: int, end: int) -> list[int]:
    """Inclusive month range that wraps around the year (e.g. 10 → 2 = [10,11,12,1,2])."""
    out: list[int] = []
    m = start
    while True:
        out.append(m)
        if m == end:
            break
        m = m % 12 + 1
    return out


def _load_calendar(lake: Path) -> list[dict[str, Any]]:
    from pipelines.storage import get_read_connection

    con = get_read_connection(lake)
    cols = [r[1] for r in con.execute("PRAGMA table_info('gold.crop_calendar')").fetchall()]
    select = ",".join(f'"{c}"' for c in cols)
    return [dict(zip(cols, r)) for r in con.execute(f"SELECT {select} FROM gold.crop_calendar").fetchall()]


def _load_overrides(lake: Path) -> list[dict[str, Any]]:
    from pipelines.storage import get_read_connection

    con = get_read_connection(lake)
    cols = [r[1] for r in con.execute("PRAGMA table_info('gold.crop_calendar_override')").fetchall()]
    select = ",".join(f'"{c}"' for c in cols)
    return [dict(zip(cols, r)) for r in con.execute(f"SELECT {select} FROM gold.crop_calendar_override").fetchall()]


def _resolve_location(state: str | None, district: str | None) -> tuple[str | None, str | None]:
    from pipelines.geocode import resolve_geography

    if not state and not district:
        return None, None
    geo = resolve_geography(state, district)
    if not geo:
        return state, district
    return geo.get("state_code"), geo.get("district_code")


def _key(r: dict[str, Any]) -> tuple[str, str, str]:
    return (r["crop_id"], r["season_id"], r["stage_id"])


def _apply_overrides(
    base: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    state_code: str | None,
    district_code: str | None,
) -> list[dict[str, Any]]:
    """Overlay district/state overrides onto the India-wide base calendar."""
    overlaid = {_key(r): dict(r) for r in base}
    # District overrides win first, then state-level, then the base calendar.
    for ov in overrides:
        if district_code and ov.get("district_code") == district_code:
            overlaid[_key(ov)] = dict(ov)
    for ov in overrides:
        if state_code and ov.get("state_code") == state_code and not ov.get("district_code"):
            k = _key(ov)
            if k not in overlaid or overlaid[k].get("district_code") is None:
                overlaid[k] = dict(ov)
    return list(overlaid.values())


def crop_plan(
    crop: str,
    *,
    state: str | None = None,
    district: str | None = None,
    lake: Path | None = None,
) -> CropPlan | None:
    """Return a season-by-season calendar plan for a crop at a location."""
    from pipelines.entities import resolve_crop

    lake = Path(lake or DEFAULT_LAKE)
    crop_row = resolve_crop(crop)
    if not crop_row:
        return None
    crop_id = crop_row["crop_id"]

    state_code, district_code = _resolve_location(state, district)
    rows = _apply_overrides(
        _load_calendar(lake), _load_overrides(lake), state_code, district_code
    )
    rows = [r for r in rows if r.get("crop_id") == crop_id]
    if not rows:
        return None

    stage_names = {
        r[0]: r[1]
        for r in _q(
            lake, "SELECT stage_id, name FROM gold.dim_growth_stage"
        )
    }
    season_names = {
        r[0]: r[1]
        for r in _q(lake, "SELECT season_id, name FROM gold.dim_season")
    }

    plan = CropPlan(crop=crop_row["canonical_en"], crop_id=crop_id)
    plan.location = {
        "state": state,
        "district": district,
        "state_code": state_code,
        "district_code": district_code,
    }

    seasons = sorted({r["season_id"] for r in rows})
    plan.seasons = [season_names.get(s, s) for s in seasons]

    # Timeline per season: stages ordered by month_start (wrap-aware via numeric).
    ordered = sorted(rows, key=lambda r: (r["season_id"], r["month_start"]))
    seen: set[tuple[str, str]] = set()
    for r in ordered:
        k = (r["season_id"], r["stage_id"])
        if k in seen:
            continue
        seen.add(k)
        months = _months_between(r["month_start"], r["month_end"])
        plan.timeline.append(
            StageWindow(stage=stage_names.get(r["stage_id"], r["stage_id"]), months=months, note=r.get("note"))
        )
        if r["stage_id"] in ("STAGE_SOWING", "STAGE_NURSERY", "STAGE_TRANSPLANTING"):
            for m in months:
                if m not in plan.sow_window:
                    plan.sow_window.append(m)
        if r["stage_id"] in ("STAGE_HARVEST", "STAGE_MATURITY"):
            for m in months:
                if m not in plan.harvest_window:
                    plan.harvest_window.append(m)

    if plan.timeline:
        # Duration ≈ number of distinct months the crop occupies (sow → harvest).
        all_months = {m for t in plan.timeline for m in t.months}
        plan.duration_months = len(all_months)

    plan.sow_window.sort(key=lambda m: (m - 6) % 12)  # order from July-ish
    plan.notes.append(
        f"Sow window months: {plan.sow_window or '-'}. Harvest window: {plan.harvest_window or '-'}."
    )
    return plan


def crops_to_sow(
    month: int,
    *,
    state: str | None = None,
    district: str | None = None,
    lake: Path | None = None,
) -> list[dict[str, Any]]:
    """Crops whose sowing/transplanting window includes `month` at a location."""
    lake = Path(lake or DEFAULT_LAKE)
    state_code, district_code = _resolve_location(state, district)
    rows = _apply_overrides(
        _load_calendar(lake), _load_overrides(lake), state_code, district_code
    )
    crop_names = {r[0]: r[1] for r in _q(lake, "SELECT crop_id, canonical_en FROM gold.dim_crop")}
    season_names = {r[0]: r[1] for r in _q(lake, "SELECT season_id, name FROM gold.dim_season")}

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["stage_id"] not in ("STAGE_SOWING", "STAGE_NURSERY", "STAGE_TRANSPLANTING"):
            continue
        if month in _months_between(r["month_start"], r["month_end"]):
            cid = r["crop_id"]
            out.setdefault(
                cid,
                {
                    "crop_id": cid,
                    "crop": crop_names.get(cid, cid),
                    "season": season_names.get(r["season_id"], r["season_id"]),
                    "sow_months": _months_between(r["month_start"], r["month_end"]),
                },
            )
    return sorted(out.values(), key=lambda x: x["crop"])


def sow_risk(plan: CropPlan, current_month: int) -> str:
    """On-window / off-window / near-window label for a plan."""
    if not plan.sow_window:
        return "unknown"
    if current_month in plan.sow_window:
        return "on_window"
    dist = min((m - current_month) % 12 for m in plan.sow_window)
    return "near_window" if dist <= 2 else "off_window"


def _q(lake: Path, sql: str) -> list[tuple[Any, ...]]:
    from pipelines.storage import get_read_connection

    return get_read_connection(lake).execute(sql).fetchall()
