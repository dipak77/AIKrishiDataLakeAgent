"""Tests for the V1.5 reasoning substrate (diagnosis + fertilizer math)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from reasoning.diagnose import diagnose  # noqa: E402
from reasoning.fertilizer import (  # noqa: E402
    fertilizer_composition,
    n_p2o5_k2o,
    nutrient_from_fertilizer,
    supply_for_kg,
)
from reasoning.symptoms import match_score, tokenize_symptoms  # noqa: E402


@pytest.fixture(scope="module")
def _seeded():
    # Ensure the lakehouse exists (tests may run before `make seed`).
    import scripts.seed_lake as sl
    from pipelines.storage import LAKE_DIR

    lake = LAKE_DIR / "agrilake.duckdb"
    if not lake.exists():
        import duckdb

        sl.emit_seed_csvs()
        con = duckdb.connect(str(lake))
        try:
            sl.load_lake(con, export_parquet=False)
        finally:
            con.close()
    yield


def test_diagnose_tomato_early_blight(_seeded):
    results = diagnose("tomato", "black spots on leaves, lower leaves yellowing",
                       growth_stage="vegetative")
    assert results, "expected at least one candidate"
    top = results[0]
    assert top.entity_type == "disease"
    assert top.name.lower().startswith("early blight")
    assert top.causal_agent == "Alternaria solani"


def test_diagnose_rice_khaira_deficiency(_seeded):
    results = diagnose("rice", "brown spots on leaves, white bud, stunted")
    assert results
    assert results[0].entity_type == "deficiency"
    assert "Zinc" in results[0].name


def test_diagnose_indic_crop_alias(_seeded):
    # 'टोमॅटो' (Marathi alias) resolves to CROP_TOMATO; English symptoms match.
    results = diagnose("टोमॅटो", "black spots on leaves, yellowing")
    assert results, "Indic crop alias should resolve via resolve_crop"
    assert results[0].entity_type in {"disease", "pest", "deficiency"}
    assert results[0].name.lower().startswith("early blight")


def test_diagnose_indic_symptoms_marathi(_seeded):
    # Track 2: Marathi crop alias + Marathi symptom text now resolves via the
    # Devanagari symptom lexicon (पानावर काळे डाग → leaf + black + spots).
    results = diagnose("टोमॅटो", "पानावर काळे डाग")
    assert results, "Marathi symptoms should resolve via the Devanagari lexicon"
    assert results[0].entity_type == "disease"
    assert results[0].name.lower().startswith("early blight")


def test_diagnose_indic_symptoms_hindi(_seeded):
    # Hindi: धान (rice) + सफेद कली = white bud → Zinc deficiency (Khaira).
    results = diagnose("धान", "पत्तियों पर भूरे धब्बे, सफेद कली")
    assert results
    assert any(r.entity_type == "deficiency" and "Zinc" in r.name for r in results)


def test_fertilizer_composition(_seeded):
    comp = {r["nutrient_id"]: r["percent"] for r in fertilizer_composition("FERT_DAP")}
    assert comp["NUT_N"] == 18.0
    assert comp["NUT_P"] == 46.0


def test_nutrient_math(_seeded):
    assert nutrient_from_fertilizer("FERT_DAP", 100)["P2O5"] == 46.0
    assert supply_for_kg("FERT_UREA", "N", 46.0) == 100.0
    assert supply_for_kg("FERT_MOP", "K2O", 30.0) == 50.0
    assert n_p2o5_k2o("FERT_NPK_102626", 50) == {"N": 5.0, "P2O5": 13.0, "K2O": 13.0}


def test_symptom_tokenizer():
    tokens = tokenize_symptoms("Black spots on leaves, lower leaves yellowing")
    assert "black spots" in tokens
    assert match_score(["black spots", "yellowing"], "black spots and yellowing of leaves") == 2
