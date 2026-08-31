"""Data-quality scoring.

Every silver/gold record carries a set of quality signals so downstream
reasoning can prioritize reliable knowledge. The authority hierarchy is seeded
in `domain/seed_data.py::AUTHORITY_LEVELS`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from domain.seed_data import AUTHORITY_LEVELS

# Field groups used to compute completeness / specificity from a record.
REQUIRED_FIELDS = ["source", "license", "ingested_at"]
GEO_FIELDS = ["state", "district", "location"]
CROP_FIELDS = ["crop", "crop_id"]
EVIDENCE_FIELDS = ["source_url", "evidence", "document", "page", "references"]

# Weights for the composite score.
WEIGHTS = {
    "authority_score": 0.30,
    "freshness_score": 0.15,
    "completeness_score": 0.15,
    "location_specificity": 0.10,
    "crop_specificity": 0.10,
    "evidence_score": 0.10,
    "expert_verified": 0.05,
    "license_score": 0.05,
}

LICENSE_SCORES = {
    "GODL-India": 1.0,
    "CC0": 1.0,
    "CC-BY": 0.9,
    "public-domain": 1.0,
    "open": 0.8,
    "institutional": 0.6,
    "unknown": 0.3,
    "all-rights-reserved": 0.1,
}


def authority_score(authority: str | None) -> float:
    if not authority:
        return 0.35
    key = str(authority).strip().lower()
    for row in AUTHORITY_LEVELS:
        if key in (row["key"], row["name"].lower()):
            return float(row["score"])
    return 0.35


def freshness_score(published: Any, retrieved: Any = None) -> float:
    """Newer is better; old-but-authoritative documents still score reasonably."""
    try:
        if isinstance(published, str):
            published = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if published is None:
            return 0.5
        age_days = (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).days
    except (ValueError, AttributeError):
        return 0.5
    if age_days < 0:
        return 0.9
    if age_days <= 365:
        return 0.95
    if age_days <= 3 * 365:
        return 0.8
    if age_days <= 10 * 365:
        return 0.6
    return 0.4


def _has(record: dict[str, Any], keys: list[str]) -> bool:
    return any(record.get(k) not in (None, "", [], {}) for k in keys)


def license_score(license_value: Any) -> float:
    if not license_value:
        return LICENSE_SCORES["unknown"]
    if isinstance(license_value, dict):
        license_value = license_value.get("type") or license_value.get("name", "")
    key = str(license_value).strip()
    for token, score in LICENSE_SCORES.items():
        if token.lower() in key.lower():
            return score
    return LICENSE_SCORES["unknown"]


def score_record(
    record: dict[str, Any],
    *,
    authority: str | None = None,
    published: Any = None,
    retrieved: Any = None,
) -> dict[str, Any]:
    """Attach quality signals + composite confidence to a record."""
    authority_value = authority or record.get("authority") or record.get("authority_level")
    authority_val = authority_score(authority_value)

    signals = {
        "authority_score": authority_val,
        "freshness_score": freshness_score(published or record.get("published_date"), retrieved),
        "completeness_score": (
            sum(1 for f in REQUIRED_FIELDS if record.get(f)) / len(REQUIRED_FIELDS)
        ),
        "location_specificity": 1.0 if _has(record, GEO_FIELDS) else 0.0,
        "crop_specificity": 1.0 if _has(record, CROP_FIELDS) else 0.0,
        "evidence_score": (1.0 if _has(record, EVIDENCE_FIELDS) else 0.0),
        "expert_verified": 1.0 if record.get("expert_verified") else 0.0,
        "license_score": license_score(record.get("license")),
    }

    confidence = sum(signals[k] * w for k, w in WEIGHTS.items())
    signals["quality_score"] = round(confidence, 4)
    return signals
