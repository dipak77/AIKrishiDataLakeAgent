"""Tests for V6 4: real model backend inference paths (opt-in seams)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vision.inference import (  # noqa: E402
    BackendUnavailable,
    OnnxBackend,
    TfliteBackend,
    TransformersBackend,
    _probs_to_candidates,
)
from pipelines.language import APIMTBackend, IndicTrans2Backend, MTBackendUnavailable  # noqa: E402


# ─────────────────────────── vision backends ────────────────────────────────


@pytest.mark.parametrize("cls", [OnnxBackend, TfliteBackend, TransformersBackend])
def test_vision_backends_raise_without_weights(monkeypatch, cls):
    monkeypatch.delenv("AGRI_VISION_MODEL", raising=False)
    with pytest.raises(BackendUnavailable):
        cls().predict(None)


def test_probs_to_candidates_maps_to_ontology():
    probs = [0.0] * 30
    probs[0] = 0.9
    probs[1] = 0.05
    cands = _probs_to_candidates(probs, top_k=2)
    assert cands
    assert cands[0].entity_id  # mapped onto seed ontology rows
    assert cands[0].score == 90.0


def test_probs_to_candidates_uses_label_map(tmp_path, monkeypatch):
    import json

    labels = [{"id": "DIS_X", "type": "disease", "name": "Blight"}]
    lpath = tmp_path / "labels.json"
    lpath.write_text(json.dumps(labels), encoding="utf-8")
    monkeypatch.setenv("AGRI_VISION_LABELS", str(lpath))

    cands = _probs_to_candidates([0.8, 0.1, 0.1], top_k=1)
    assert cands[0].entity_id == "DIS_X"
    assert cands[0].name == "Blight"


# ─────────────────────────── MT backends ────────────────────────────────────


def test_mt_backends_raise_without_runtime(monkeypatch):
    monkeypatch.delenv("AGRI_MT_MODEL_DIR", raising=False)
    monkeypatch.delenv("AGRI_MT_API_URL", raising=False)
    with pytest.raises(MTBackendUnavailable):
        IndicTrans2Backend().translate("नमस्ते")
    with pytest.raises(MTBackendUnavailable):
        APIMTBackend().translate("नमस्ते")


def test_api_mt_backend_calls_configured_url(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"translation": "hello"}

    import pipelines.language as lang

    monkeypatch.setenv("AGRI_MT_API_URL", "http://mt.local/translate")
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp())
    out = APIMTBackend().translate("नमस्ते", target="en")
    assert out["translation"] == "hello"
    assert out["backend"] == "api"
