"""Tests for Track 2: geography expansion + language (hi/mr, transliteration)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.seed_data import GEOGRAPHY, SYMPTOM_LEXICON  # noqa: E402
from pipelines.geocode import resolve_geography  # noqa: E402
from pipelines.language import (  # noqa: E402
    detect_language,
    disambiguate_devanagari,
    transliterate_devanagari,
)
from reasoning.symptoms import match_score, tokenize_symptoms  # noqa: E402


def test_district_coverage():
    total = sum(len(g["districts"]) for g in GEOGRAPHY)
    assert len(GEOGRAPHY) == 36
    assert total >= 700, f"expected full district coverage, got {total}"


def test_iso_suffix_and_abbreviations():
    assert resolve_geography("MH", "Pune")["district_code"] == "IN-MH-PUNE"
    assert resolve_geography("UP", "Kanpur")["district_code"] == "IN-UP-KANPURNAGAR"
    assert resolve_geography("Orissa", "Cuttack")["state_code"] == "IN-OD"
    assert resolve_geography("CG", "Raipur")["state_code"] == "IN-CT"


def test_geography_latlon_and_aer():
    geo = resolve_geography("Maharashtra", "Pune")
    assert geo["latitude"] == 18.52
    assert geo["agroecological_region"]
    assert geo["agroclimatic_zone"]


def test_hindi_marathi_disambiguation():
    assert disambiguate_devanagari("टमाटर की पत्तियों पर काले धब्बे")[0] == "hi"
    assert disambiguate_devanagari("टोमॅटोच्या पानावर काळे डाग आले आहेत")[0] == "mr"


def test_detect_language_returns_marathi():
    assert detect_language("टोमॅटोच्या पानावर काळे डाग")["language"] == "mr"


def test_transliterate_devanagari():
    assert transliterate_devanagari("टमाटर") == "tamaatara"
    assert transliterate_devanagari("काळे").startswith("kaa")
    assert transliterate_devanagari("धान") == "dhaana"


def test_indic_symptom_tokenizer():
    tokens = tokenize_symptoms("पानावर काळे डाग")
    assert "black" in tokens and "spots" in tokens
    assert match_score(tokens, "concentric ring spots on lower leaves") >= 2


def test_lexicon_loaded():
    assert "hi" in SYMPTOM_LEXICON and "mr" in SYMPTOM_LEXICON
    assert SYMPTOM_LEXICON["hi"]["काले"] == "black"
    assert SYMPTOM_LEXICON["mr"]["डाग"] == "spots"
