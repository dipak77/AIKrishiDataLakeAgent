"""Tests for V5-E: LGD subdistrict import + lake-backed resolve_subdistrict."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pipelines.storage as storage  # noqa: E402
from pipelines.geocode import resolve_subdistrict  # noqa: E402
from scripts.import_lgd import (  # noqa: E402
    build_baseline_rows,
    coverage_report,
    load_from_lgd_dir,
    parse_lgd_blocks,
    parse_lgd_villages,
    write_lake,
)

FIXTURES = ROOT / "data" / "fixtures" / "lgd"


def test_parse_lgd_blocks():
    rows = parse_lgd_blocks(FIXTURES / "blocks.csv")
    assert len(rows) == 15
    assert {"state_code": "IN-MH", "district_code": "IN-MH-PUNE", "name": "Haveli", "type": "tehsil"} in rows


def test_parse_lgd_villages():
    rows = parse_lgd_villages(FIXTURES / "villages.csv")
    assert len(rows) == 4
    assert {"state_code": "IN-MH", "district_code": "IN-MH-PUNE", "name": "Saswad", "type": "village"} in rows


def test_load_from_lgd_dir_missing_returns_none(tmp_path):
    assert load_from_lgd_dir(tmp_path) is None


def test_load_from_lgd_dir_combines(tmp_path):
    rows = load_from_lgd_dir(FIXTURES)
    assert rows is not None and len(rows) == 19  # 15 blocks + 4 villages


def test_baseline_real_and_typed():
    rows = build_baseline_rows()
    assert len(rows) > 200
    # every row is a real name with a valid LGD-ish type and code
    for r in rows:
        assert r["name"] and r["state_code"].startswith("IN-") and r["district_code"].startswith("IN-")
        assert r["type"] in {"tehsil", "taluka", "taluk", "block", "village", "subdistrict"}
    # district HQ towns are present (real place names)
    names = {r["name"] for r in rows}
    assert "Pune" in names and "Nagpur" in names


def test_baseline_covers_hq_districts():
    rows = build_baseline_rows()
    report = coverage_report(rows)
    assert report["districts_total"] == 764
    assert report["districts_covered"] == 174  # exactly the districts with a known HQ
    assert 20 < report["coverage_pct"] < 30


def test_write_lake_roundtrip(tmp_path):
    rows = build_baseline_rows()
    csv_path, lake_path = write_lake(rows, lake_path=tmp_path / "lake.duckdb")
    assert csv_path.is_file() and lake_path.is_file()
    con = duckdb.connect(str(lake_path), read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM gold.dim_subdistrict").fetchone()[0]
        assert n == len(rows)
        types = con.execute("SELECT DISTINCT type FROM gold.dim_subdistrict").fetchall()
        assert ("tehsil",) in types
    finally:
        con.close()


def test_resolve_subdistrict_fallback_no_lake(monkeypatch, tmp_path):
    # no lake → representative SUBDISTRICT_EXAMPLES still resolves
    monkeypatch.setattr(storage, "LAKE_DIR", tmp_path)
    r = resolve_subdistrict("Junnar", state="Maharashtra", district="Pune")
    assert r is not None and r["type"] in ("tehsil", "taluka")
    assert r["district_code"] == "IN-MH-PUNE"


def test_resolve_subdistrict_from_lake(monkeypatch, tmp_path):
    rows = build_baseline_rows()
    write_lake(rows, lake_path=tmp_path / "agrilake.duckdb")
    monkeypatch.setattr(storage, "LAKE_DIR", tmp_path)
    # HQ town now resolvable via the full-coverage table
    r = resolve_subdistrict("Pune", state="Maharashtra", district="Pune")
    assert r is not None
    assert r["type"] == "tehsil"
    assert r["district_code"] == "IN-MH-PUNE"
    assert resolve_subdistrict("NoSuchPlaceXYZ") is None
