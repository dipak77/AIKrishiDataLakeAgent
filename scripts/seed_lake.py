"""Load seed ontologies into the lakehouse.

1. Emit `data/seeds/*.csv` from `domain.seed_data`.
2. Load them into DuckDB (`data/lake/agrilake.duckdb`) under schema `gold`.
3. Export Parquet copies under `data/lake/parquet/`.

Usage: python scripts/seed_lake.py [--no-parquet]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from domain import seed_data as sd  # noqa: E402
from pipelines.geocode import resolve_geography  # noqa: E402
from pipelines.storage import (  # noqa: E402
    LAKE_DIR,
    SEEDS_DIR,
    content_hash,
    ensure_dir,
    read_write_connection,
)

# Bump when the *emission logic* (not the data) changes, to force a rebuild of
# derived CSVs/lake tables even when the ontology source is byte-identical.
SEED_SCHEMA_VERSION = "0.3.0"


def seed_fingerprint() -> str:
    """Content hash of the ontology source + schema version.

    Drives idempotent seeding: if the source hasn't changed, skip the rebuild.
    """
    source = Path(sd.__file__).read_bytes()
    return content_hash(source + SEED_SCHEMA_VERSION.encode("utf-8"))


def _write_csv(name: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> Path:
    path = ensure_dir(SEEDS_DIR) / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        # `lineterminator` must be pinned: csv's default is "\r\n", which made
        # every emit rewrite the committed LF seed CSVs (CRLF churn) and made
        # `verify_seeds` contradict itself depending on whether the build had
        # already run. LF everywhere keeps the drift gate byte-stable.
        writer = csv.DictWriter(
            fh, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def emit_seed_csvs() -> list[Path]:
    paths: list[Path] = []
    paths.append(_write_csv("dim_crop", ["crop_id", "canonical_en", "scientific_name", "family", "type", "group"], sd.CROPS))

    alias_rows = [
        {"crop_id": cid, "language": lang, "name": name}
        for cid, langs in sd.CROP_ALIASES.items()
        for lang, name in langs.items()
    ]
    alias_rows += [
        {"crop_id": cid, "language": "romanized", "name": name}
        for name, cid in sd.EXTRA_ALIASES.items()
    ]
    paths.append(_write_csv("crop_alias", ["crop_id", "language", "name"], alias_rows))

    geo_rows: list[dict[str, Any]] = []
    for state in sd.GEOGRAPHY:
        geo_rows.append(
            {
                "state_code": state["state_code"],
                "state_name": state["name"],
                "type": state["type"],
                "agroclimatic_zone": state["agroclimatic_zone"],
                "agroecological_region": state.get("agroecological_region"),
                "district_code": "",
                "district_name": "",
                "latitude": state.get("latitude"),
                "longitude": state.get("longitude"),
            }
        )
        for dist in state.get("districts", []):
            geo_rows.append(
                {
                    "state_code": state["state_code"],
                    "state_name": state["name"],
                    "type": state["type"],
                    "agroclimatic_zone": state["agroclimatic_zone"],
                    "agroecological_region": state.get("agroecological_region"),
                    "district_code": dist["code"],
                    "district_name": dist["name"],
                    "latitude": dist.get("latitude"),
                    "longitude": dist.get("longitude"),
                }
            )
    paths.append(
        _write_csv(
            "dim_geography",
            ["state_code", "state_name", "type", "agroclimatic_zone", "agroecological_region",
             "district_code", "district_name", "latitude", "longitude"],
            geo_rows,
        )
    )

    # Subdistrict / tehsil / taluk / block / village hierarchy (representative).
    subdist_rows: list[dict[str, Any]] = []
    for ex in sd.SUBDISTRICT_EXAMPLES:
        for sd_ in ex["subdistricts"]:
            subdist_rows.append(
                {
                    "state_code": ex["state_code"],
                    "district_code": ex["district_code"],
                    "name": sd_["name"],
                    "type": sd_["type"],
                }
            )
        for village in ex.get("villages", []):
            subdist_rows.append(
                {
                    "state_code": ex["state_code"],
                    "district_code": ex["district_code"],
                    "name": village,
                    "type": "village",
                }
            )
    paths.append(
        _write_csv(
            "dim_subdistrict",
            ["state_code", "district_code", "name", "type"],
            subdist_rows,
        )
    )

    paths.append(_write_csv("dim_season", ["season_id", "name", "months", "description"], sd.SEASONS))
    paths.append(_write_csv("dim_growth_stage", ["stage_id", "name", "description"], sd.GROWTH_STAGES))
    paths.append(_write_csv("crop_season_map", ["crop_id", "season_id"], sd.CROP_SEASON))

    # Crop calendar = exemplar (kharif/rabi core) + top-20 expansion.
    calendar_rows = sd.CROP_CALENDAR + sd.CROP_CALENDAR_TOP20
    paths.append(
        _write_csv("crop_calendar", ["crop_id", "season_id", "stage_id", "month_start", "month_end", "note"], calendar_rows)
    )
    paths.append(
        _write_csv(
            "crop_calendar_override",
            ["crop_id", "season_id", "stage_id", "location_scope", "state_code", "district_code", "month_start", "month_end", "note"],
            sd.CROP_CALENDAR_OVERRIDES,
        )
    )

    # Diseases: merge deeper clinical fields (growth_stage, differential_diagnosis).
    disease_rows = [
        {**d, **sd.DISEASE_CLINICAL.get(d["disease_id"], {})} for d in sd.DISEASES
    ]
    paths.append(
        _write_csv(
            "dim_disease",
            ["disease_id", "name", "crop_id", "crop", "pathogen_type", "causal_agent", "symptoms", "affected_parts",
             "favourable_conditions", "growth_stage", "differential_diagnosis", "management"],
            disease_rows,
        )
    )

    # Pests: merge IPM depth (growth_stage, economic_threshold, monitoring).
    pest_rows = [
        {**p, **sd.PEST_IPM.get(p["pest_id"], {})} for p in sd.PESTS
    ]
    paths.append(
        _write_csv(
            "dim_pest",
            ["pest_id", "name", "scientific_name", "crop_hosts", "damage_symptoms", "growth_stage",
             "economic_threshold", "monitoring", "cultural_control", "biological_control", "chemical_control"],
            pest_rows,
        )
    )
    paths.append(_write_csv("dim_weed", ["weed_id", "name", "scientific_name", "hosts", "management"], sd.WEEDS))
    paths.append(_write_csv("dim_nutrient", ["nutrient_id", "symbol", "name", "role", "deficiency_symptoms"], sd.NUTRIENTS))
    paths.append(_write_csv("dim_fertilizer", ["fertilizer_id", "name", "category", "composition", "notes"], sd.FERTILIZERS))
    paths.append(
        _write_csv(
            "fertilizer_nutrient",
            ["fertilizer_id", "nutrient_id", "form", "percent"],
            sd.FERTILIZER_NUTRIENTS,
        )
    )
    paths.append(
        _write_csv(
            "nutrient_deficiency",
            ["deficiency_id", "nutrient_id", "crop_id", "crop", "symptoms", "correction"],
            sd.NUTRIENT_DEFICIENCIES,
        )
    )
    paths.append(_write_csv("biofertilizer", ["biofertilizer_id", "name", "target", "function"], sd.BIOFERTILIZERS))
    paths.append(_write_csv("biocontrol", ["biocontrol_id", "name", "type", "target"], sd.BIOCONTROLS))
    paths.append(_write_csv("dim_pesticide", ["pesticide_id", "name", "type", "target", "class"], sd.PESTICIDES))
    paths.append(_write_csv("dim_soil", ["soil_id", "name", "characteristics", "crops"], sd.SOILS))
    paths.append(_write_csv("authority_levels", ["key", "name", "score"], sd.AUTHORITY_LEVELS))

    # Fertilizer-advisory substrate (Track 5): crop nutrient requirement + soil-test interpretation.
    req_rows = [
        {
            "crop_id": r["crop_id"],
            "crop": r["crop"],
            "target_yield_tha": r["target_yield_tha"],
            "nutrient_form": form,
            "total_kg_ha": r["total_kg_ha"][form],
            "basal_frac": r["stage_split"]["basal"][form],
            "vegetative_frac": r["stage_split"]["vegetative"][form],
            "reproductive_frac": r["stage_split"]["reproductive"][form],
        }
        for r in sd.CROP_NUTRIENT_REQUIREMENT
        for form in ("N", "P2O5", "K2O")
    ]
    paths.append(
        _write_csv(
            "crop_nutrient_requirement",
            ["crop_id", "crop", "target_yield_tha", "nutrient_form", "total_kg_ha",
             "basal_frac", "vegetative_frac", "reproductive_frac"],
            req_rows,
        )
    )
    paths.append(
        _write_csv(
            "soil_test_interpretation",
            ["parameter", "label", "unit", "kind", "nutrient_form", "low_max", "high_min",
             "adjustment", "low_note", "high_note"],
            sd.SOIL_TEST_INTERPRETATION,
        )
    )

    # Mandi intelligence (Track 6): major APMC markets, geo-resolved.
    market_rows: list[dict[str, Any]] = []
    for m in sd.MARKETS:
        geo = resolve_geography(m["state"], m["district"])
        market_rows.append(
            {
                "market_id": m["market_id"],
                "name": m["name"],
                "state": m["state"],
                "district": m["district"],
                "state_code": geo.get("state_code") if geo else None,
                "district_code": geo.get("district_code") if geo else None,
                "latitude": m["latitude"],
                "longitude": m["longitude"],
                "key_commodities": m["key_commodities"],
            }
        )
    paths.append(
        _write_csv(
            "dim_market",
            ["market_id", "name", "state", "district", "state_code", "district_code",
             "latitude", "longitude", "key_commodities"],
            market_rows,
        )
    )
    return paths


TABLE_TO_CSV = {
    "dim_crop": "dim_crop.csv",
    "crop_alias": "crop_alias.csv",
    "dim_geography": "dim_geography.csv",
    "dim_subdistrict": "dim_subdistrict.csv",
    "dim_season": "dim_season.csv",
    "dim_growth_stage": "dim_growth_stage.csv",
    "crop_season_map": "crop_season_map.csv",
    "crop_calendar": "crop_calendar.csv",
    "crop_calendar_override": "crop_calendar_override.csv",
    "dim_disease": "dim_disease.csv",
    "dim_pest": "dim_pest.csv",
    "dim_weed": "dim_weed.csv",
    "dim_nutrient": "dim_nutrient.csv",
    "dim_fertilizer": "dim_fertilizer.csv",
    "fertilizer_nutrient": "fertilizer_nutrient.csv",
    "nutrient_deficiency": "nutrient_deficiency.csv",
    "biofertilizer": "biofertilizer.csv",
    "biocontrol": "biocontrol.csv",
    "dim_pesticide": "dim_pesticide.csv",
    "dim_soil": "dim_soil.csv",
    "authority_levels": "authority_levels.csv",
    "crop_nutrient_requirement": "crop_nutrient_requirement.csv",
    "soil_test_interpretation": "soil_test_interpretation.csv",
    "dim_market": "dim_market.csv",
}


def load_lake(con: duckdb.DuckDBPyConnection, *, export_parquet: bool = True) -> dict[str, int]:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    counts: dict[str, int] = {}
    for table, csv_name in TABLE_TO_CSV.items():
        path = SEEDS_DIR / csv_name
        con.execute(
            f"CREATE OR REPLACE TABLE gold.{table} AS "
            f"SELECT * FROM read_csv_auto('{path}', header = true)"
        )
        counts[table] = con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]
        if export_parquet:
            parquet_dir = ensure_dir(LAKE_DIR / "parquet")
            con.execute(f"COPY gold.{table} TO '{parquet_dir / (table + '.parquet')}' (FORMAT PARQUET)")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Agri Intelligence Lake")
    parser.add_argument("--no-parquet", action="store_true", help="skip Parquet export")
    parser.add_argument("--force", action="store_true", help="rebuild even if unchanged")
    args = parser.parse_args(argv)

    fingerprint = seed_fingerprint()
    stamp_path = SEEDS_DIR / "_seed_sha.txt"
    lake_path = ensure_dir(LAKE_DIR) / "agrilake.duckdb"
    if (
        not args.force
        and stamp_path.is_file()
        and lake_path.exists()
        and stamp_path.read_text(encoding="utf-8").strip() == fingerprint
    ):
        print(f"Seeds unchanged (fingerprint {fingerprint[:12]}); lakehouse up to date.")
        print("Use --force to rebuild.")
        return 0

    paths = emit_seed_csvs()
    print(f"Emitted {len(paths)} seed CSVs into {SEEDS_DIR}")

    con = read_write_connection(lake_path)
    try:
        counts = load_lake(con, export_parquet=not args.no_parquet)
        con.execute(
            "CREATE OR REPLACE TABLE gold.meta AS "
            "SELECT 'agrilake' AS name, '0.1.0' AS version, current_timestamp AS seeded_at"
        )
    finally:
        con.close()

    ensure_dir(SEEDS_DIR).joinpath("_seed_sha.txt").write_text(
        fingerprint + "\n", encoding="utf-8"
    )

    print(f"Lakehouse ready: {lake_path}")
    for table, count in counts.items():
        print(f"  gold.{table:<22} {count:>6} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
