"""Build gold/ application-ready tables from silver/ (and seeds).

- Load silver jsonl files per domain into gold fact tables.
- Derive fact_yield (yield = production / area).
- Seed dims if the lake is empty.

Usage: python scripts/build_gold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from pipelines.storage import LAKE_DIR, SILVER_DIR, ensure_dir  # noqa: E402
from scripts.seed_lake import load_lake  # noqa: E402

DOMAIN_TO_TABLE = {
    "farmer_qa": "farmer_query",
    "market": "fact_mandi_price",
    "production": "fact_crop_production",
    "weather": "fact_agromet_advisory",
    "soil": "fact_soil_test",
    "research": "research_chunk",
    "images": "agri_image",
}


def _load_silver(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    loaded: dict[str, int] = {}
    for domain, table in DOMAIN_TO_TABLE.items():
        files = sorted((SILVER_DIR / domain).glob("*.jsonl")) if (SILVER_DIR / domain).is_dir() else []
        if not files:
            continue
        paths = ", ".join(f"'{f}'" for f in files)
        try:
            con.execute(
                f"CREATE OR REPLACE TABLE gold.{table} AS "
                f"SELECT * FROM read_json_auto([{paths}], format='newline_delimited', union_by_name=true)"
            )
        except Exception as exc:  # noqa: BLE001 - fall back to first file
            con.execute(
                f"CREATE OR REPLACE TABLE gold.{table} AS "
                f"SELECT * FROM read_json_auto('{files[0]}', format='newline_delimited', union_by_name=true)"
            )
            print(f"  [warn] {domain}: fell back to single file ({type(exc).__name__})")
        loaded[table] = con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]
    return loaded


def _derive_yield(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE gold.fact_yield AS
        SELECT
            *,
            CASE
                WHEN area_hectares > 0 THEN round(production_tonnes / area_hectares, 4)
                ELSE NULL
            END AS yield_tonnes_ha
        FROM gold.fact_crop_production
        """
    )


def main() -> int:
    lake_path = ensure_dir(LAKE_DIR) / "agrilake.duckdb"
    con = duckdb.connect(str(lake_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        # Ensure dimensions are present (no-op if already seeded).
        dim_counts = load_lake(con, export_parquet=False)

        silver_counts = _load_silver(con)

        # Derived yield only if production facts exist.
        has_production = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='gold' AND table_name='fact_crop_production'"
        ).fetchone()[0]
        if has_production:
            _derive_yield(con)
            n_yield = con.execute("SELECT count(*) FROM gold.fact_yield").fetchone()[0]
            print(f"  derived gold.fact_yield: {n_yield} rows")
    finally:
        con.close()

    print(f"Gold layer updated in {lake_path}")
    print("  dimensions:", ", ".join(f"{k}={v}" for k, v in dim_counts.items()))
    print("  silver→gold facts:", silver_counts or "(no silver data yet — run ingest_live)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
