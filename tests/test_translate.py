"""Tests for V5-D: pluggable MT behind language.translate()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.language import (  # noqa: E402
    MTBackendUnavailable,
    get_translator,
    translate,
)


def test_translate_english_passthrough():
    r = translate("tomato leaf spots are spreading")
    assert r["status"] == "ok"
    assert r["translation"] == "tomato leaf spots are spreading"
    assert r["source_language"] == "en"
    assert r["coverage"] == 1.0


def test_translate_marathi_crop_and_symptoms():
    r = translate("टोमॅटो काळे डाग")
    assert r["source_language"] == "mr"
    assert "Tomato" in r["translation"]
    assert "black" in r["translation"] and "spots" in r["translation"]
    assert r["backend"] == "lexicon"


def test_translate_hindi():
    r = translate("धान में काला धब्बे")
    assert r["source_language"] == "hi"
    assert "Rice" in r["translation"]
    assert "black" in r["translation"] and "spots" in r["translation"]


def test_translate_tamil_symptoms():
    r = translate("கருப்பு புள்ளிகள்")
    assert r["source_language"] == "ta"
    assert "black" in r["translation"] and "spots" in r["translation"]


def test_translate_telugu_symptoms():
    r = translate("వర్షం ఉంది")
    assert r["source_language"] == "te"
    assert "rain" in r["translation"]


def test_translate_oov_is_partial_and_transliterated():
    # "धब्बा" (singular) is not in the glossary → transliterated, marked partial.
    r = translate("धान में धब्बा")
    assert r["status"] == "partial"
    assert r["untranslated"]
    assert "dhabbaa" in r["translation"]  # Devanagari transliteration fallback
    assert 0.0 < r["coverage"] < 1.0


def test_translate_non_english_target_is_pending():
    r = translate("धान", target="hi")
    assert r["status"] == "pending_mt"
    assert r["translation"] is None


def test_translate_deterministic():
    assert translate("टोमॅटो काळे डाग") == translate("टोमॅटो काळे डाग")


def test_backend_registry():
    assert get_translator("lexicon").name == "lexicon"
    assert get_translator(None).name == "lexicon"
    assert get_translator("auto").name == "lexicon"
    with pytest.raises(MTBackendUnavailable):
        get_translator("does-not-exist")


def test_stub_backend_raises_on_translate():
    for name in ("indictrans2", "indicmt", "api"):
        with pytest.raises(MTBackendUnavailable):
            get_translator(name).translate("धान")


def test_translate_falls_back_to_lexicon():
    r = translate("धान में काला धब्बे", backend="indictrans2")
    assert r["backend"] == "lexicon"
    assert "fallback_reason" in r
    assert "Rice" in r["translation"]


def test_env_backend_selection(monkeypatch):
    monkeypatch.setenv("AGRI_MT_BACKEND", "lexicon")
    r = translate("धान")
    assert r["backend"] == "lexicon"
    assert r["translation"] == "Rice"
