"""Tests for Track 13: Krushi Mitra assistant router."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.assistant import ask, classify_intent, extract_crop, extract_location  # noqa: E402
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    yield


def test_classify_intent_english():
    assert classify_intent("my tomato has black spots and wilting leaves")[0] == "diagnosis"
    assert classify_intent("how much urea and dap for tomato")[0] == "fertilizer"
    assert classify_intent("price of onion in mandi")[0] == "mandi_price"
    assert classify_intent("when to sow wheat")[0] == "crop_planning"


def test_classify_intent_indic():
    assert classify_intent("टोमॅटोवर काळे डाग")[0] == "diagnosis"
    assert classify_intent("தக்காளியில் கருப்பு புள்ளிகள்")[0] == "diagnosis"


def test_extract_crop_and_location():
    assert extract_crop("my tomato leaves are yellow")["crop_id"] == "CROP_TOMATO"
    loc = extract_location("weather in Pune")
    assert loc["district"] == "Pune" and loc["state_code"] == "IN-MH"


def test_ask_diagnosis_end_to_end():
    resp = ask("tomato has black spots on lower leaves")
    assert resp.intent == "diagnosis"
    assert resp.entities["crop"] == "Tomato"
    assert resp.answers and resp.answers[0].engine == "diagnosis"
    assert any("blight" in line for line in resp.answers[0].body)


def test_ask_marathi_diagnosis():
    resp = ask("टोमॅटोवर काळे डाग आहेत")
    assert resp.language == "mr"
    assert resp.intent == "diagnosis"
    assert resp.entities["crop"] == "Tomato"


def test_ask_fertilizer_and_plan():
    fert = ask("how much urea and dap for tomato")
    assert fert.intent == "fertilizer"
    assert any("Urea" in line for line in fert.answers[0].body)
    plan = ask("when should I sow wheat in Punjab")
    assert plan.intent == "crop_planning"
    assert plan.entities["state"] == "Punjab"


def test_ask_serializes():
    d = ask("tomato black spots").as_dict()
    assert set(d) >= {"query", "language", "intent", "entities", "answers", "intent_scores"}
