"""Tests for V5-F: trained intent classifier + NER tagger."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning import nlu  # noqa: E402
from reasoning.nlu import (  # noqa: E402
    EntityTagger,
    IntentClassifier,
    NLUPipeline,
    build_intent_examples,
    build_ner_examples,
    classify_intent_trained,
    extract_entities,
    tokenize,
    train_models,
)


@pytest.fixture(scope="module")
def clf() -> IntentClassifier:
    nlu._RNG.seed(42)
    return IntentClassifier().train(build_intent_examples())


@pytest.fixture(scope="module")
def tagger() -> EntityTagger:
    nlu._RNG.seed(42)
    return EntityTagger().train(build_ner_examples())


def test_intent_english(clf):
    cases = {
        "my tomato has black spots and wilting leaves": "diagnosis",
        "how much urea and dap for tomato": "fertilizer",
        "price of onion in mandi": "mandi_price",
        "when to sow wheat": "crop_planning",
        "weather in Pune": "weather",
        "package of practices for rice": "evidence",
    }
    for q, want in cases.items():
        assert clf.predict(q)[0] == want, q


def test_intent_indic(clf):
    assert clf.predict("टोमॅटोवर काळे डाग आहेत")[0] == "diagnosis"
    assert clf.predict("தக்காளியில் கருப்பு புள்ளிகள்")[0] == "diagnosis"
    assert clf.predict("मंडी भाव")[0] == "mandi_price"


def test_intent_general_fallback(clf):
    for q in ["hello", "namaste", "who are you", "thanks", "zzzzz qqqq", "आहे"]:
        assert clf.predict(q)[0] == "general", q


def test_train_accuracy_high(clf):
    nlu._RNG.seed(7)
    examples = build_intent_examples()
    acc = clf.accuracy(examples)
    assert acc > 0.95, acc


def test_model_serialization_roundtrip(tmp_path):
    nlu._RNG.seed(42)
    model = train_models()
    path = tmp_path / "m.json"
    path.write_text(
        __import__("json").dumps(nlu._serialize_model(model), ensure_ascii=False),
        encoding="utf-8",
    )
    loaded = nlu._load_model(path)
    assert loaded is not None
    for q in ["tomato black spots", "price of onion", "टोमॅटोवर काळे डाग"]:
        assert loaded.intent.predict(q) == model.intent.predict(q)


def test_model_deterministic():
    queries = ["tomato black spots", "urea dose for paddy", "काळे डाग", "hello"]
    nlu._RNG.seed(42)
    m1 = train_models()
    nlu._RNG.seed(42)
    m2 = train_models()
    for q in queries:
        assert m1.intent.predict(q) == m2.intent.predict(q)
        assert m1.tagger.tag(tokenize(q)) == m2.tagger.tag(tokenize(q))


def test_ner_crop_and_symptoms(tagger):
    ents = extract_entities(tagger, "tomato has black spots on lower leaves")
    assert ents["crop"]["crop_id"] == "CROP_TOMATO"
    assert "black spots" in ents["symptoms"]


def test_ner_location(tagger):
    ents = extract_entities(tagger, "weather in Pune")
    assert ents["district"] == "Pune"
    assert ents["state"] == "Maharashtra"
    assert ents["crop"] is None  # no false crop


def test_ner_indic_crop(tagger):
    ents = extract_entities(tagger, "टोमॅटोवर काळे डाग आहेत")
    assert ents["crop"]["crop_id"] == "CROP_TOMATO"
    assert "काळे डाग" in ents["symptoms"]


def test_ner_plural_crop(tagger):
    ents = extract_entities(tagger, "tomatoes have brown patches")
    assert ents["crop"]["crop_id"] == "CROP_TOMATO"


def test_ner_no_false_symptom(tagger):
    ents = extract_entities(tagger, "how much urea for tomato")
    assert ents["crop"]["crop_id"] == "CROP_TOMATO"
    assert ents["symptoms"] == []  # "urea" is not a symptom


def test_pipeline_trained_predict(tmp_path, monkeypatch):
    pipe = NLUPipeline(model_path=tmp_path / "m.json")
    res = pipe.predict("tomato has black spots on leaves")
    assert res.intent == "diagnosis"
    assert res.model == "trained"
    assert res.crop["crop_id"] == "CROP_TOMATO"
    assert res.intent_confidence > 0.5
    assert (tmp_path / "m.json").is_file()


def test_pipeline_heuristic_fallback():
    res = NLUPipeline._heuristic("tomato has black spots")
    assert res.model == "heuristic"
    assert res.intent == "diagnosis"
    assert res.crop["crop_id"] == "CROP_TOMATO"


def test_ask_uses_trained_model():
    from reasoning.assistant import ask

    resp = ask("tomato black spots on leaves")
    assert resp.nlu_model == "trained"
    assert resp.intent_confidence > 0.5
    assert resp.intent == "diagnosis"
    assert resp.entities["crop"] == "Tomato"
    assert resp.entities["symptoms"]  # NER symptoms surface in the response
