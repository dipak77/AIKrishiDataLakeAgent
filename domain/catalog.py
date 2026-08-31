"""Lookup indexes built from `seed_data.py` (crops, aliases, geography).

These are the canonical resolution tables used by the enrichment pipeline
(`pipelines/entities.py`, `pipelines/geocode.py`).
"""

from __future__ import annotations

import re
from typing import Any

from domain.seed_data import (
    CROP_ALIASES,
    CROPS,
    EXTRA_ALIASES,
    GEOGRAPHY,
    GEOGRAPHY_ALIASES,
)

# Unicode-aware: preserves Devanagari/Gujarati/... scripts in alias keys.
_TOKEN_RE = re.compile(r"[^\w]+")


def _norm(s: str) -> str:
    return _TOKEN_RE.sub(" ", s.lower()).strip()


def _build_crop_lookup() -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    by_norm_en: dict[str, str] = {}
    by_alias: dict[str, str] = {}
    for crop in CROPS:
        crop_id = crop["crop_id"]
        rows[crop_id] = crop
        by_norm_en[_norm(crop["canonical_en"])] = crop_id
        by_norm_en[_norm(crop["scientific_name"])] = crop_id
    for crop_id, langs in CROP_ALIASES.items():
        for _lang, name in langs.items():
            n = _norm(name)
            if n:
                by_alias.setdefault(n, crop_id)
    for name, crop_id in EXTRA_ALIASES.items():
        n = _norm(name)
        if n:
            by_alias.setdefault(n, crop_id)
    return {"rows": rows, "by_norm_en": by_norm_en, "by_alias": by_alias}


def _build_geography_lookup() -> dict[str, Any]:
    by_state: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}
    by_district: dict[tuple[str, str], dict[str, Any]] = {}
    by_district_alias: dict[tuple[str, str], dict[str, Any]] = {}
    for state in GEOGRAPHY:
        scode = state["state_code"]
        state_row = {k: v for k, v in state.items() if k != "districts"}
        by_state[_norm(state["name"])] = state_row
        for alias in GEOGRAPHY_ALIASES.get(scode, []):
            by_alias[_norm(alias)] = state_row
        for dist in state.get("districts", []):
            drow = dict(dist)
            drow.update(
                {
                    "state_code": scode,
                    "state_name": state["name"],
                    "district_code": dist["code"],
                    "district_name": dist["name"],
                }
            )
            by_district[(scode, _norm(drow["name"]))] = drow
            for alias in drow.get("aliases", []):
                by_district_alias[(scode, _norm(alias))] = drow
    return {
        "by_state": by_state,
        "by_alias": by_alias,
        "by_district": by_district,
        "by_district_alias": by_district_alias,
    }


CROP_LOOKUP = _build_crop_lookup()
GEOGRAPHY_LOOKUP = _build_geography_lookup()
