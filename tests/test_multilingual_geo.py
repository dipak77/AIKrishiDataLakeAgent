"""Tests for Track 11: Tamil/Telugu symptom lexicons + subdistrict resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.seed_data import SYMPTOM_LEXICON  # noqa: E402
from pipelines.geocode import resolve_subdistrict  # noqa: E402
from reasoning.symptoms import tokenize_symptoms  # noqa: E402
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    yield


def test_lexicons_loaded():
    assert "ta" in SYMPTOM_LEXICON and "te" in SYMPTOM_LEXICON
    assert SYMPTOM_LEXICON["ta"]["கருப்பு"] == "black"
    assert SYMPTOM_LEXICON["te"]["మచ్చలు"] == "spots"


def test_tamil_symptom_tokens():
    tokens = tokenize_symptoms("இலைகளில் கருப்பு புள்ளிகள்")  # black spots on leaves
    assert "black" in tokens and "spots" in tokens and "leaves" in tokens


def test_telugu_symptom_tokens():
    tokens = tokenize_symptoms("ఆకులపై గోధుమ మచ్చలు")  # brown spots on leaves
    assert "brown" in tokens and "spots" in tokens


def test_diagnose_tamil_tomato():
    from reasoning.diagnose import diagnose

    results = diagnose("தக்காளி", "இலைகளில் கருப்பு புள்ளிகள்")
    assert results, "Tamil symptoms should resolve via the ta lexicon"
    assert results[0].entity_type == "disease"


def test_diagnose_telugu_rice_khaira():
    from reasoning.diagnose import diagnose

    # వరి (rice) + తెలుపు మొగ్గ (white bud) → Zinc deficiency (Khaira).
    results = diagnose("వరి", "తెలుపు మొగ్గ, పొట్టి మొక్కలు")
    assert results
    assert any(r.entity_type == "deficiency" and "Zinc" in r.name for r in results)


def test_resolve_subdistrict_tehsil():
    r = resolve_subdistrict("Junnar", state="Maharashtra", district="Pune")
    assert r is not None and r["type"] in ("tehsil", "taluka")
    assert r["state_code"] == "IN-MH" and r["district_code"] == "IN-MH-PUNE"


def test_resolve_subdistrict_village():
    r = resolve_subdistrict("Saswad", district="Pune")
    assert r is not None
    assert r["type"] == "village"
    assert r["district_code"] == "IN-MH-PUNE"
    assert resolve_subdistrict("NoSuchPlaceXYZ") is None
