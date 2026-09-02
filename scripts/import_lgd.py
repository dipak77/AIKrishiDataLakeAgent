"""Import Local Government Directory (LGD) subdistricts into `gold.dim_subdistrict`.

Full-coverage path: parse LGD block/tehsil + village CSVs from a configured
directory (``LGD_DIR`` / ``--lgd-dir``, default ``data/bronze/lgd``) and load
them into the lakehouse, replacing the representative seed examples.

Offline baseline: when no LGD CSVs are present, build a deterministic,
**real-data** baseline that covers every district with a known headquarters
town (``DISTRICT_HQ``) plus the representative tehsil/village examples — real
place names only, never fabricated. A coverage report tells you how many of the
764 districts are covered and how to reach full coverage.

Usage:
    python scripts/import_lgd.py [--lgd-dir DIR] [--dry-run]

Expected CSV schema (header row required):
    blocks.csv:   state_code,district_code,subdistrict_name,subdistrict_type
    villages.csv: state_code,district_code,subdistrict_name,village_name
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from domain.catalog import GEOGRAPHY_LOOKUP  # noqa: E402
from domain.seed_data import DISTRICT_HQ, SUBDISTRICT_EXAMPLES  # noqa: E402
from pipelines.storage import GOLD_DIR, LAKE_DIR, ensure_dir, read_write_connection  # noqa: E402

FIELDNAMES = ["state_code", "district_code", "name", "type"]
DEFAULT_LGD_DIR = ROOT / "data" / "bronze" / "lgd"


def parse_lgd_blocks(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "state_code": r["state_code"].strip(),
                    "district_code": r["district_code"].strip(),
                    "name": r["subdistrict_name"].strip(),
                    "type": (r.get("subdistrict_type") or "tehsil").strip(),
                }
            )
    return rows


def parse_lgd_villages(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "state_code": r["state_code"].strip(),
                    "district_code": r["district_code"].strip(),
                    "name": r["village_name"].strip(),
                    "type": "village",
                }
            )
    return rows


def load_from_lgd_dir(lgd_dir: Path) -> list[dict[str, str]] | None:
    """Return combined rows if LGD CSVs exist in the dir, else None."""
    lgd_dir = Path(lgd_dir)
    blocks = lgd_dir / "blocks.csv"
    villages = lgd_dir / "villages.csv"
    if not blocks.exists() and not villages.exists():
        return None
    rows: list[dict[str, str]] = []
    if blocks.exists():
        rows.extend(parse_lgd_blocks(blocks))
    if villages.exists():
        rows.extend(parse_lgd_villages(villages))
    return rows


def build_baseline_rows() -> list[dict[str, str]]:
    """Real-data offline baseline: HQ towns (all districts with a known HQ)
    + representative tehsil/village examples. No fabricated names."""
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(state_code: str, district_code: str, name: str, typ: str) -> None:
        key = (state_code, district_code, name, typ)
        if key not in seen:
            seen.add(key)
            rows.append(
                {"state_code": state_code, "district_code": district_code, "name": name, "type": typ}
            )

    # District headquarters towns (recorded as tehsil; HQ town == district name).
    for (_sc, _dn), row in GEOGRAPHY_LOOKUP["by_district"].items():
        if row["district_name"] in DISTRICT_HQ:
            add(row["state_code"], row["district_code"], row["district_name"], "tehsil")

    for ex in SUBDISTRICT_EXAMPLES:
        for sd_ in ex["subdistricts"]:
            add(ex["state_code"], ex["district_code"], sd_["name"], sd_["type"])
        for v in ex.get("villages", []):
            add(ex["state_code"], ex["district_code"], v, "village")
    return rows


def coverage_report(rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(GEOGRAPHY_LOOKUP["by_district"])
    covered = {r["district_code"] for r in rows}
    return {
        "subdistrict_rows": len(rows),
        "districts_covered": len(covered),
        "districts_total": total,
        "coverage_pct": round(100 * len(covered) / total, 2) if total else 0.0,
    }


def write_lake(rows: list[dict[str, str]], lake_path: Path | None = None) -> tuple[Path, Path]:
    """Replace ``gold.dim_subdistrict`` with the imported rows."""
    lake_path = Path(lake_path or (LAKE_DIR / "agrilake.duckdb"))
    ensure_dir(lake_path.parent)
    csv_path = ensure_dir(GOLD_DIR) / "dim_subdistrict_full.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    con = read_write_connection(lake_path)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute(
            f"CREATE OR REPLACE TABLE gold.dim_subdistrict AS "
            f"SELECT * FROM read_csv_auto('{csv_path}', header = true)"
        )
    finally:
        con.close()
    return csv_path, lake_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import LGD subdistricts into the lakehouse.")
    parser.add_argument("--lgd-dir", default=None, help="directory with blocks.csv/villages.csv")
    parser.add_argument("--out", default=None, help="lake file (default: data/lake/agrilake.duckdb)")
    parser.add_argument("--dry-run", action="store_true", help="report only, do not write")
    args = parser.parse_args(argv)

    lgd_dir = Path(args.lgd_dir or os.environ.get("LGD_DIR") or DEFAULT_LGD_DIR)
    rows = load_from_lgd_dir(lgd_dir)
    source = "lgd" if rows is not None else "baseline"
    if rows is None:
        rows = build_baseline_rows()

    report = coverage_report(rows)
    print(f"source: {source}  ({lgd_dir})")
    print(
        f"rows: {report['subdistrict_rows']}  districts covered: "
        f"{report['districts_covered']}/{report['districts_total']} "
        f"({report['coverage_pct']}%)"
    )
    if source == "baseline":
        print("  -> offline baseline (HQ towns + examples). For full coverage, "
              "provide LGD blocks.csv/villages.csv.")

    if args.dry_run:
        return 0
    csv_path, lake_path = write_lake(rows, Path(args.out) if args.out else None)
    print(f"wrote {csv_path}")
    print(f"loaded into {lake_path} (gold.dim_subdistrict)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
