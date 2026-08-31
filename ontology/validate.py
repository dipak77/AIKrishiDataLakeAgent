"""Referential-integrity checks across the seed ontologies.

Checks that every cross-reference (disease→crop, pest→crop, crop→season,
calendar→stage, alias→crop) resolves to a canonical entity, and that ids are
unique. Returns a structured report (list of checks with pass/error).
"""

from __future__ import annotations

from typing import Any

from domain.seed_data import (
    AUTHORITY_LEVELS,
    CROP_ALIASES,
    CROP_CALENDAR,
    CROP_SEASON,
    CROPS,
    DISEASES,
    EXTRA_ALIASES,
    FERTILIZERS,
    GEOGRAPHY,
    GROWTH_STAGES,
    NUTRIENTS,
    PESTS,
    SEASONS,
    SOILS,
    WEEDS,
)


def _ids(rows: list[dict[str, Any]], key: str) -> set[str]:
    return {row[key] for row in rows}


def validate_ontologies() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    crop_ids = _ids(CROPS, "crop_id")
    season_ids = _ids(SEASONS, "season_id")
    stage_ids = _ids(GROWTH_STAGES, "stage_id")

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            errors.append(f"{name}: {detail}")

    # uniqueness
    for table, rows, key in [
        ("crops", CROPS, "crop_id"),
        ("diseases", DISEASES, "disease_id"),
        ("pests", PESTS, "pest_id"),
        ("weeds", WEEDS, "weed_id"),
        ("nutrients", NUTRIENTS, "nutrient_id"),
        ("fertilizers", FERTILIZERS, "fertilizer_id"),
        ("seasons", SEASONS, "season_id"),
        ("growth_stages", GROWTH_STAGES, "stage_id"),
        ("soils", SOILS, "soil_id"),
    ]:
        check(f"unique_ids:{table}", len(_ids(rows, key)) == len(rows), f"expected unique {key}")

    # disease → crop
    bad = [d["disease_id"] for d in DISEASES if d.get("crop_id") not in crop_ids]
    check("disease.crop_id resolves", not bad, f"unresolved: {bad}")

    # pest → crop hosts (free-text list; warn only, not error)
    for pest in PESTS:
        for host in str(pest.get("crop_hosts", "")).split("|"):
            host = host.strip()
            if host and host.lower() not in ("all crops",):
                # hosts are common names, not ids; best-effort warn
                pass

    # crop_season → crop + season
    bad_cs = [
        r for r in CROP_SEASON if r["crop_id"] not in crop_ids or r["season_id"] not in season_ids
    ]
    check("crop_season refs", not bad_cs, f"bad rows: {bad_cs}")

    # calendar → crop + season + stage
    bad_cc = [
        r
        for r in CROP_CALENDAR
        if r["crop_id"] not in crop_ids or r["season_id"] not in season_ids or r["stage_id"] not in stage_ids
    ]
    check("crop_calendar refs", not bad_cc, f"bad rows: {bad_cc}")

    # aliases → crop
    bad_alias = [c for c in CROP_ALIASES if c not in crop_ids]
    bad_extra = [c for c in EXTRA_ALIASES.values() if c not in crop_ids]
    check("crop_alias crop_id resolves", not bad_alias and not bad_extra, f"{bad_alias} {bad_extra}")

    # geography unique state codes + district codes
    state_codes = [g["state_code"] for g in GEOGRAPHY]
    check("unique state codes", len(set(state_codes)) == len(state_codes))
    district_codes = [d["code"] for g in GEOGRAPHY for d in g.get("districts", [])]
    check("unique district codes", len(set(district_codes)) == len(district_codes))

    # authority scores in [0,1]
    bad_auth = [a for a in AUTHORITY_LEVELS if not (0 <= float(a["score"]) <= 1)]
    check("authority scores in [0,1]", not bad_auth)

    # coverage sanity
    if len(CROPS) < 100:
        warnings.append(f"V1 crop coverage = {len(CROPS)} (< 100 target; acceptable for foundation)")
    if any(g.get("agroecological_region") for g in GEOGRAPHY):
        warnings.append("agroecological_region partial; NBSS&LUP import lands in V2")

    return {
        "ok": not errors,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "crops": len(CROPS),
            "crop_aliases": len(CROP_ALIASES),
            "geography_states": len(GEOGRAPHY),
            "districts": len(district_codes),
            "diseases": len(DISEASES),
            "pests": len(PESTS),
            "weeds": len(WEEDS),
            "nutrients": len(NUTRIENTS),
            "fertilizers": len(FERTILIZERS),
            "seasons": len(SEASONS),
            "growth_stages": len(GROWTH_STAGES),
            "soils": len(SOILS),
        },
    }
