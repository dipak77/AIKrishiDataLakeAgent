"""Materialize the medallion layers (V6 Phase 4 — blueprint non-negotiable).

The lake currently materializes **gold** directly from seed CSVs. This script
adds the two layers the blueprint demands in front of gold:

  * **bronze** — immutable raw artifacts: each seed CSV copied verbatim under
    ``data/bronze/seed_ontology/<table>/`` with a ``_manifest.json``
    (sha256, bytes, retrieved_at). Bronze is never rewritten for a given
    content hash; re-running with changed seeds writes a new timestamped file.
  * **silver** — normalized records: each seed CSV read back and emitted as
    JSONL under ``data/silver/ontology/<table>.jsonl`` with ``source_id``,
    ``source``, ``license``, ``ingested_at`` and a ``quality`` object attached
    per record (via ``pipelines.quality.score_record``).

``scripts/build_gold.py`` already reads silver → gold for fact domains; the
seed dimensions remain gold via ``scripts/seed_lake.py``. Together they close
the bronze → silver → gold chain.

Usage:
    python scripts/build_medallion.py [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.quality import score_record  # noqa: E402
from pipelines.storage import (  # noqa: E402
    BRONZE_DIR,
    SEEDS_DIR,
    SILVER_DIR,
    content_hash,
    ensure_dir,
    utcnow_iso,
    write_bronze,
    write_jsonl,
)
from scripts.seed_lake import TABLE_TO_CSV  # noqa: E402

# Ontology seed rows carry no external evidence; mark provenance accordingly.
SEED_SOURCE = "seed_ontology"
SEED_LICENSE = {"type": "GODL-India"}
SEED_AUTHORITY = "government"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _materialize_bronze(table: str, csv_path: Path, raw: bytes) -> dict[str, object]:
    """Write an immutable bronze artifact; skip if identical content exists."""
    target_dir = ensure_dir(BRONZE_DIR / SEED_SOURCE / table)
    existing = sorted(target_dir.glob(f"{table}-*.csv"))
    for f in existing:
        if f.read_bytes() == raw:
            return {"table": table, "status": "unchanged", "sha256": content_hash(raw)[:12]}
    artifact = target_dir / f"{table}-{utcnow_iso()[:19].replace(':', '')}.csv"
    artifact.write_bytes(raw)
    manifest = {
        "source_id": SEED_SOURCE,
        "resource_id": table,
        "filename": artifact.name,
        "sha256": content_hash(raw),
        "bytes": len(raw),
        "retrieved_at": utcnow_iso(),
        "ingestion_method": "seed",
        "meta": {"csv": csv_path.name},
    }
    import pipelines.storage as storage

    storage.write_json(target_dir / "_manifest.json", manifest)
    return {"table": table, "status": "written", "sha256": manifest["sha256"][:12], "bytes": len(raw)}


def _materialize_silver(table: str, rows: list[dict[str, str]]) -> dict[str, object]:
    """Normalize + quality-score seed rows → silver JSONL per table."""
    out: list[dict[str, object]] = []
    for row in rows:
        rec: dict[str, object] = dict(row)
        rec.setdefault("source_id", SEED_SOURCE)
        rec.setdefault("source", SEED_SOURCE)
        rec.setdefault("license", SEED_LICENSE)
        rec.setdefault("ingested_at", utcnow_iso())
        quality = score_record(rec, authority=SEED_AUTHORITY)
        rec["quality"] = quality
        out.append(rec)
    path = write_jsonl(SILVER_DIR / "ontology" / f"{table}.jsonl", out)
    return {"table": table, "rows": len(out), "path": str(path)}


def build_medallion() -> dict[str, object]:
    bronze: list[dict[str, object]] = []
    silver: list[dict[str, object]] = []
    for table, csv_name in sorted(TABLE_TO_CSV.items()):
        csv_path = SEEDS_DIR / csv_name
        if not csv_path.is_file():
            bronze.append({"table": table, "status": "missing", "csv": csv_name})
            continue
        raw = csv_path.read_bytes()
        bronze.append(_materialize_bronze(table, csv_path, raw))
        silver.append(_materialize_silver(table, _read_csv_rows(csv_path)))
    return {
        "bronze_tables": len([b for b in bronze if b.get("status") != "missing"]),
        "bronze_artifacts": [b for b in bronze],
        "silver_tables": len(silver),
        "silver_total_rows": sum(s["rows"] for s in silver),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize bronze + silver medallion layers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_medallion()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
        return 0

    written = [b for b in report["bronze_artifacts"] if b.get("status") == "written"]
    unchanged = [b for b in report["bronze_artifacts"] if b.get("status") == "unchanged"]
    print(f"bronze: {report['bronze_tables']} tables "
          f"({len(written)} written, {len(unchanged)} unchanged)")
    print(f"silver: {report['silver_tables']} files, {report['silver_total_rows']} normalized rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
