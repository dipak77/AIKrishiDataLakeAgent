"""Tests for V6 4: learned reranker + ranking evaluation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.gateway import Segment  # noqa: E402
from reasoning.reranker import (  # noqa: E402
    LearnedReranker,
    build_training_pairs,
    feature_vec,
    train_weights,
)


def _seg(text, title="t", authority=0.9):
    return Segment("evidence", text, 1.0, "doc", title, "", "", authority)


def test_feature_vec_is_length_five():
    f = feature_vec("tomato leaf spots", _seg("tomato has leaf spots on leaves"))
    assert len(f) == 5
    assert f[-1] == 1.0  # bias


def test_train_weights_is_deterministic():
    pairs = build_training_pairs()
    assert pairs
    w1 = train_weights(pairs, epochs=30)
    w2 = train_weights(pairs, epochs=30)
    assert w1 == w2


def test_learned_reranker_ranks_relevant_first():
    r = LearnedReranker(weights=[1.0, 4.0, 0.0, 1.0, 0.0])
    relevant = _seg("early blight causes dark concentric ring spots on lower leaves", title="icar-tomato-eb-003")
    irrelevant = _seg("wheat irrigation scheduling needs five critical irrigations", title="icar-wheat-irrig-002")
    out = r.rerank("tomato leaf spots", [irrelevant, relevant])
    assert out[0].title == "icar-tomato-eb-003"


def test_learned_reranker_loads_or_trains(tmp_path, monkeypatch):
    import reasoning.reranker as rr

    monkeypatch.setattr(rr, "LEARNED_MODEL_PATH", tmp_path / "m.json")
    r = LearnedReranker()
    segs = [_seg("early blight spots on tomato leaves"), _seg("wheat irrigation schedule")]
    out = r.rerank("tomato blight", segs)
    assert len(out) == 2
    # model persisted for reuse
    assert (tmp_path / "m.json").exists()


def test_reranker_eval_reports_metrics():
    from scripts.eval_reranker import evaluate

    report = evaluate()
    assert report["cases"] >= 1
    assert 0.0 <= report["learned"]["top1_recall"] <= 1.0
    assert 0.0 <= report["learned"]["mean_reciprocal_rank"] <= 1.0
    assert 0.0 <= report["deterministic"]["top1_recall"] <= 1.0
