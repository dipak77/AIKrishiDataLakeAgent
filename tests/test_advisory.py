"""Tests for Track 5: fertilizer advisory engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.models import SoilTestInput  # noqa: E402
from reasoning.advisory import (  # noqa: E402
    assess_soil,
    persist_advisory,
    recommend_fertilizer,
    timing_for_stage,
)
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    """Ensure the lakehouse exists before the module runs."""
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    yield


def test_timing_for_stage():
    assert timing_for_stage("vegetative") == "vegetative"
    assert timing_for_stage("fruiting") == "reproductive"
    assert timing_for_stage("sowing") == "basal"
    assert timing_for_stage(None) is None


def test_soil_assessment_low_n_high_k():
    flags = assess_soil({"available_n": 200, "available_k": 350, "ph": 6.0})
    by_param = {f.parameter: f for f in flags}
    assert by_param["available_n"].status == "low"
    assert by_param["available_k"].status == "high"
    assert by_param["ph"].status == "acidic"
    assert "lime" in by_param["ph"].note.lower()


def test_soil_assessment_micro_deficient():
    flags = assess_soil({"zn": 0.3})
    assert flags[0].parameter == "zn"
    assert flags[0].status == "deficient"
    assert "ZnSO4" in flags[0].note


def test_recommend_tomato_blanket():
    adv = recommend_fertilizer("tomato")
    assert adv is not None
    assert adv.crop_id == "CROP_TOMATO"
    assert adv.version == "2026.08"
    # DAP-first mix: DAP for P2O5, Urea for remaining N, MOP for K2O.
    products = {p.product_id for p in adv.plan}
    assert {"FERT_DAP", "FERT_UREA", "FERT_MOP"} <= products
    # Basal, vegetative, reproductive timings all present.
    assert {p.timing for p in adv.plan} == {"basal", "vegetative", "reproductive"}


def test_recommend_tomato_soil_adjusted():
    # Low P and high K → more P2O5, less K2O than the blanket plan.
    blanket = recommend_fertilizer("tomato")
    adjusted = recommend_fertilizer(
        "tomato", soil_test={"available_p": 5.0, "available_k": 400.0}
    )
    b_p = sum(p.kg_ha for p in blanket.plan if p.nutrient_form == "P2O5")
    a_p = sum(p.kg_ha for p in adjusted.plan if p.nutrient_form == "P2O5")
    b_k = sum(p.kg_ha for p in blanket.plan if p.nutrient_form == "K2O")
    a_k = sum(p.kg_ha for p in adjusted.plan if p.nutrient_form == "K2O")
    assert a_p > b_p
    assert a_k < b_k


def test_recommend_unknown_crop_returns_none():
    assert recommend_fertilizer("NoSuchCropXYZ") is None


def test_recommend_indic_alias():
    adv = recommend_fertilizer("टोमॅटो")
    assert adv is not None and adv.crop_id == "CROP_TOMATO"


def test_soil_input_model_validation():
    ok = SoilTestInput(ph=6.8, available_n=300, zn=0.8)
    assert ok.ph == 6.8
    with pytest.raises(Exception):
        SoilTestInput(ph=15)  # out of range


def test_persist_advisory_csv(tmp_path):
    adv = recommend_fertilizer("tomato")
    path = persist_advisory(adv, tmp_path / "fertilizer_advisory@2026.08.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("advisory_id,version,crop_id")
    assert len(lines) > 1  # header + at least one plan row
