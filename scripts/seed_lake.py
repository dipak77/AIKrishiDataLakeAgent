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
from pipelines.storage import SEEDS_DIR, LAKE_DIR, ensure_dir  # noqa: E402


def _write_csv(name: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> Path:
    path = ensure_dir(SEEDS_DIR) / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
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
                }
            )
    paths.append(
        _write_csv(
            "dim_geography",
            ["state_code", "state_name", "type", "agroclimatic_zone", "agroecological_region", "district_code", "district_name"],
            geo_rows,
        )
    )

    paths.append(_write_csv("dim_season", ["season_id", "name", "months", "description"], sd.SEASONS))
    paths.append(_write_csv("dim_growth_stage", ["stage_id", "name", "description"], sd.GROWTH_STAGES))
    paths.append(_write_csv("crop_season_map", ["crop_id", "season_id"], sd.CROP_SEASON))
    paths.append(
        _write_csv("crop_calendar", ["crop_id", "season_id", "stage_id", "month_start", "month_end", "note"], sd.CROP_CALENDAR)
    )
    paths.append(
        _write_csv(
            "dim_disease",
            ["disease_id", "name", "crop_id", "crop", "pathogen_type", "causal_agent", "symptoms", "affected_parts", "favourable_conditions", "management"],
            sd.DISEASES,
        )
    )
    paths.append(
        _write_csv(
            "dim_pest",
            ["pest_id", "name", "scientific_name", "crop_hosts", "damage_symptoms", "cultural_control", "biological_control", "chemical_control"],
            sd.PESTS,
        )
    )
    paths.append(_write_csv("dim_weed", ["weed_id", "name", "scientific_name", "hosts", "management"], sd.WEEDS))
    paths.append(_write_csv("dim_nutrient", ["nutrient_id", "symbol", "name", "role", "deficiency_symptoms"], sd.NUTRIENTS))
    paths.append(_write_csv("dim_fertilizer", ["fertilizer_id", "name", "category", "composition", "notes"], sd.FERTILIZERS))
    paths.append(_write_csv("biofertilizer", ["biofertilizer_id", "name", "target", "function"], sd.BIOFERTILIZERS))
    paths.append(_write_csv("biocontrol", ["biocontrol_id", "name", "type", "target"], sd.BIOCONTROLS))
    paths.append(_write_csv("dim_pesticide", ["pesticide_id", "name", "type", "target", "class"], sd.PESTICIDES))
    paths.append(_write_csv("dim_soil", ["soil_id", "name", "characteristics", "crops"], sd.SOILS))
    paths.append(_write_csv("authority_levels", ["key", "name", "score"], sd.AUTHORITY_LEVELS))
    return paths


TABLE_TO_CSV = {
    "dim_crop": "dim_crop.csv",
    "crop_alias": "crop_alias.csv",
    "dim_geography": "dim_geography.csv",
    "dim_season": "dim_season.csv",
    "dim_growth_stage": "dim_growth_stage.csv",
    "crop_season_map": "crop_season_map.csv",
    "crop_calendar": "crop_calendar.csv",
    "dim_disease": "dim_disease.csv",
    "dim_pest": "dim_pest.csv",
    "dim_weed": "dim_weed.csv",
    "dim_nutrient": "dim_nutrient.csv",
    "dim_fertilizer": "dim_fertilizer.csv",
    "biofertilizer": "biofertilizer.csv",
    "biocontrol": "biocontrol.csv",
    "dim_pesticide": "dim_pesticide.csv",
    "dim_soil": "dim_soil.csv",
    "authority_levels": "authority_levels.csv",
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
    args = parser.parse_args(argv)

    paths = emit_seed_csvs()
    print(f"Emitted {len(paths)} seed CSVs into {SEEDS_DIR}")

    lake_path = ensure_dir(LAKE_DIR) / "agrilake.duckdb"
    con = duckdb.connect(str(lake_path))
    try:
        counts = load_lake(con, export_parquet=not args.no_parquet)
        con.execute(
            "CREATE OR REPLACE TABLE gold.meta AS "
            "SELECT 'agrilake' AS name, '0.1.0' AS version, current_timestamp AS seeded_at"
        )
    finally:
        con.close()

    print(f"Lakehouse ready: {lake_path}")
    for table, count in counts.items():
        print(f"  gold.{table:<22} {count:>6} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
