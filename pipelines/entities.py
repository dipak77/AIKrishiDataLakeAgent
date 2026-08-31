"""Agriculture entity extraction: link free text to canonical ontologies.

Resolution order for a mention:
  1. canonical English name / scientific name
  2. Indian-language alias (crop_alias)
  3. normalized token match

Returns canonical ids (e.g. ``CROP_TOMATO``) rather than raw strings so that
raw dataset names never leak into the gold layer.
"""

from __future__ import annotations

import re
from typing import Any

from domain.catalog import CROP_LOOKUP

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)  # keeps Devanagari etc. (str \w is Unicode)


def _norm(s: str) -> str:
    return _TOKEN_RE.sub(" ", s).strip().lower()


def resolve_crop(text: str | None) -> dict[str, Any] | None:
    """Resolve a raw crop string to a canonical dim_crop row (or None)."""
    if not text:
        return None
    t = _norm(str(text))
    if not t:
        return None
    if t in CROP_LOOKUP["by_norm_en"]:
        crop_id = CROP_LOOKUP["by_norm_en"][t]
    elif t in CROP_LOOKUP["by_alias"]:
        crop_id = CROP_LOOKUP["by_alias"][t]
    else:
        # substring fallback on canonical names only (aliases are too risky)
        for name, crop_id in CROP_LOOKUP["by_norm_en"].items():
            if name in t or t in name:
                return dict(CROP_LOOKUP["rows"][crop_id], resolved_via="substring")
        return None
    return dict(CROP_LOOKUP["rows"][crop_id], resolved_via="exact")


def extract_crops(text: str) -> list[dict[str, Any]]:
    """Extract all canonical crops mentioned in a text block."""
    found: dict[str, dict[str, Any]] = {}
    t = _norm(text)
    for name, crop_id in list(CROP_LOOKUP["by_norm_en"].items()) + list(
        CROP_LOOKUP["by_alias"].items()
    ):
        if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", t):
            found[crop_id] = dict(CROP_LOOKUP["rows"][crop_id])
    return list(found.values())


def resolve_season(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    for season in ("kharif", "rabi", "zaid", "summer", "whole_year", "perennial"):
        if season.replace("_", " ") in t or season in t:
            return season
    return None
