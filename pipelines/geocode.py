"""Geography normalization: map free-text state/district/subdistrict to codes.

Uses the seeded `dim_geography` catalog (domain/catalog.py) plus the
representative `SUBDISTRICT_EXAMPLES` (tehsil/taluk/block/village). The full
LGD block/zilla/village import remains a later milestone; this resolves the
state/UT + district + subdistrict + agro-climatic/ecological zone links that
most records carry.
"""

from __future__ import annotations

import re
from typing import Any

from domain.catalog import GEOGRAPHY_LOOKUP
from domain.seed_data import SUBDISTRICT_EXAMPLES

_NORM_RE = re.compile(r"[^\w]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub(" ", s.lower()).strip()


def resolve_geography(state: str | None, district: str | None = None) -> dict[str, Any] | None:
    """Resolve a (state, district) pair to canonical geography metadata."""
    if not state:
        return None
    skey = _norm(state)
    state_row = GEOGRAPHY_LOOKUP["by_state"].get(skey)
    if state_row is None:
        # try common aliases like "odisha"→"orissa", "nct of delhi"→"delhi"
        state_row = GEOGRAPHY_LOOKUP["by_alias"].get(skey)
    if state_row is None:
        return None

    result = dict(state_row)
    result["_state_match"] = "exact" if GEOGRAPHY_LOOKUP["by_state"].get(skey) else "alias"

    if district:
        dkey = _norm(district)
        dist_row = GEOGRAPHY_LOOKUP["by_district"].get((state_row["state_code"], dkey))
        if dist_row is None:
            dist_row = GEOGRAPHY_LOOKUP["by_district_alias"].get((state_row["state_code"], dkey))
        if dist_row is not None:
            result.update(dist_row)
            result["_district_match"] = "exact"
        else:
            result["_district_match"] = "unresolved"
            result["district_name"] = district.strip()
    return result


def country_code(name: str | None) -> str | None:
    if not name:
        return None
    n = _norm(name)
    return "IN" if n in {"in", "ind", "india", "bharat", "भारत"} else None


def _resolve_from_lake(
    key: str, state_code: str | None, district_code: str | None, district_hint: str | None
) -> dict[str, Any] | None:
    """Look up a subdistrict in the persisted full-coverage table (import_lgd)."""
    from pipelines.storage import LAKE_DIR, get_read_connection

    lake = LAKE_DIR / "agrilake.duckdb"
    if not lake.exists():
        return None

    con = get_read_connection(lake)
    has = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='gold' AND table_name='dim_subdistrict'"
    ).fetchone()[0]
    if not has:
        return None
    rows = con.execute(
        "SELECT state_code, district_code, name, type FROM gold.dim_subdistrict"
    ).fetchall()

    best: dict[str, Any] | None = None
    for sc, dc, name, typ in rows:
        if state_code and sc != state_code:
            continue
        if district_hint:
            # Match either the resolved district code or the code's trailing name
            # segment (handles district-only hints without a state).
            if dc != district_code and district_hint not in (
                _norm(dc.split("-")[-1]),
                _norm(dc),
            ):
                continue
        elif district_code and dc != district_code:
            continue
        if _norm(name) == key:
            candidate = {"name": name, "type": typ, "state_code": sc, "district_code": dc}
            if dc == district_code:
                return candidate  # exact district match wins
            best = best or candidate
    return best


def resolve_subdistrict(
    name: str,
    *,
    state: str | None = None,
    district: str | None = None,
) -> dict[str, Any] | None:
    """Resolve a tehsil/taluk/block/village name to its (state, district) codes.

    Reads the persisted `gold.dim_subdistrict` (full coverage after
    `scripts/import_lgd.py`) and falls back to the representative
    `SUBDISTRICT_EXAMPLES` when the lake is unavailable. State/district hints
    narrow the search.
    """
    if not name:
        return None
    key = _norm(name)
    geo_state = resolve_geography(state, None) if state else None
    state_code = geo_state.get("state_code") if geo_state else None
    geo = resolve_geography(state, district) if state else None
    district_code = geo.get("district_code") if geo else None
    district_hint = _norm(district) if district else None

    lake_hit = _resolve_from_lake(key, state_code, district_code, district_hint)
    if lake_hit is not None:
        return lake_hit

    for ex in SUBDISTRICT_EXAMPLES:
        if state_code and ex["state_code"] != state_code:
            continue
        if district_hint:
            # Match either a resolved district code or the code's trailing name
            # segment (handles district-only hints without a state).
            if ex["district_code"] != district_code and district_hint not in (
                _norm(ex["district_code"].split("-")[-1]),
                _norm(ex["district_code"]),
            ):
                continue
        for sd_ in ex["subdistricts"]:
            if _norm(sd_["name"]) == key:
                return {
                    "name": sd_["name"],
                    "type": sd_["type"],
                    "state_code": ex["state_code"],
                    "district_code": ex["district_code"],
                }
        for v in ex.get("villages", []):
            if _norm(v) == key:
                return {
                    "name": v,
                    "type": "village",
                    "state_code": ex["state_code"],
                    "district_code": ex["district_code"],
                }
    return None
