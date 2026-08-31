"""Geography normalization: map free-text state/district to canonical codes.

Uses the seeded `dim_geography` catalog (domain/catalog.py). Full
subdistrict/block/village resolution is a V2 import; this resolves the
state/UT + district + agro-climatic/ecological zone links that most records
carry.
"""

from __future__ import annotations

import re
from typing import Any

from domain.catalog import GEOGRAPHY_LOOKUP

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
