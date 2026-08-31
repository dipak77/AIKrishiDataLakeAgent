"""Smoke tests for the V1 foundation (offline; no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from connectors.web.license_checker import LicenseChecker, LicenseClass  # noqa: E402
from domain.seed_data import CROPS, DISEASES, GEOGRAPHY  # noqa: E402
from knowledge_graph.build import build_knowledge_graph  # noqa: E402
from ontology.validate import validate_ontologies  # noqa: E402
from pipelines.entities import resolve_crop  # noqa: E402
from pipelines.geocode import resolve_geography  # noqa: E402
from pipelines.language import detect_language  # noqa: E402
from pipelines.quality import score_record  # noqa: E402
from schemas.records import UnifiedAgricultureRecord  # noqa: E402
from scripts.seed_lake import emit_seed_csvs  # noqa: E402


def test_crop_resolution_english_and_indic():
    assert resolve_crop("Tomato")["crop_id"] == "CROP_TOMATO"
    assert resolve_crop("टोमॅटो")["crop_id"] == "CROP_TOMATO"   # Marathi
    assert resolve_crop("paddy")["crop_id"] == "CROP_RICE"
    assert resolve_crop("தக்காளி")["crop_id"] == "CROP_TOMATO"  # Tamil
    assert resolve_crop("NoSuchCropXYZ") is None


def test_geography_resolution():
    geo = resolve_geography("Maharashtra", "Pune")
    assert geo["state_code"] == "IN-MH"
    assert geo["district_code"] == "IN-MH-PUNE"
    assert resolve_geography("Orissa", None)["state_code"] == "IN-OD"


def test_language_detection():
    assert detect_language("टोमॅटोच्या पानावर काळे डाग")["language"] in ("hi", "mr")
    assert detect_language("black spots on leaves")["language"] == "en"


def test_license_checker():
    checker = LicenseChecker()
    assert checker.classify("https://icar.gov.in/abc", "GODL-India").decision is LicenseClass.ALLOW
    assert checker.classify("https://instagram.com/p/abc").decision is LicenseClass.BLOCK
    assert checker.classify("https://example.com/blog", None).decision is LicenseClass.REVIEW


def test_quality_scoring_hierarchy():
    gov = score_record({"source": "ICAR", "license": {"type": "GODL-India"}, "ingested_at": "x",
                        "state": "Maharashtra", "crop": "CROP_TOMATO", "expert_verified": True},
                       authority="government")
    social = score_record({"source": "forum", "license": "unknown", "ingested_at": "x"},
                          authority="social")
    assert gov["quality_score"] > social["quality_score"]
    assert gov["authority_score"] == 1.0
    assert social["authority_score"] == 0.2


def test_unified_record():
    rec = UnifiedAgricultureRecord(
        record_id="x", domain="crop_protection", crop="tomato", season="kharif",
        location={"state": "Maharashtra", "district": "Pune"},
        problem={"type": "disease", "symptoms": ["leaf spots"]},
        quality={"confidence": 0.94},
    )
    assert rec.location.state == "Maharashtra"


def test_ontology_validation_passes():
    report = validate_ontologies()
    assert report["ok"], report["errors"]
    assert report["counts"]["crops"] >= 100


def test_knowledge_graph_has_edges():
    graph = build_knowledge_graph()
    assert graph["summary"]["node_count"] > 0
    assert graph["summary"]["edge_count"] > 0
    types = graph["summary"]["node_types"]
    assert "crop" in types and "disease" in types


def test_seed_csvs_emit_and_load():
    paths = emit_seed_csvs()
    assert len(paths) >= 15
    con = duckdb.connect(":memory:")
    try:
        n = con.execute(
            f"SELECT count(*) FROM read_csv_auto('{ROOT / 'data' / 'seeds' / 'dim_crop.csv'}', header=true)"
        ).fetchone()[0]
        assert n == len(CROPS)
    finally:
        con.close()
