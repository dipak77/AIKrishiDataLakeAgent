"""Tests for V6 2b: pluggable reranker/compactor + golden-QA benchmark."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.compactor import (  # noqa: E402
    CompactorUnavailable,
    TruncationCompactor,
    get_compactor,
)
from reasoning.gateway import Segment  # noqa: E402
from reasoning.reranker import (  # noqa: E402
    CrossEncoderReranker,
    DeterministicReranker,
    RerankerUnavailable,
    get_reranker,
)


# ─────────────────────────── reranker ──────────────────────────────────────


def test_default_reranker_is_deterministic(monkeypatch):
    monkeypatch.delenv("AGRI_RERANKER", raising=False)
    assert isinstance(get_reranker(), DeterministicReranker)


def test_deterministic_reranker_sorts_by_score():
    segs = [
        Segment("evidence", "tomato blight", 1.0, "doc", "a"),
        Segment("evidence", "tomato blight management", 0.5, "doc", "b"),
    ]
    out = DeterministicReranker().rerank("tomato blight", segs)
    assert out[0].score >= out[-1].score
    assert all(s.score > 0 for s in out)


def test_cross_encoder_raises_when_unavailable(monkeypatch):
    monkeypatch.delenv("AGRI_CROSS_ENCODER_MODEL", raising=False)
    with pytest.raises(RerankerUnavailable):
        CrossEncoderReranker().rerank("q", [])


def test_unknown_reranker_raises(monkeypatch):
    monkeypatch.setenv("AGRI_RERANKER", "nope")
    with pytest.raises(RerankerUnavailable):
        get_reranker()


# ─────────────────────────── compactor ─────────────────────────────────────


def test_default_compactor_is_truncation(monkeypatch):
    monkeypatch.delenv("AGRI_COMPACTOR", raising=False)
    assert isinstance(get_compactor(), TruncationCompactor)


def test_truncation_compactor_caps_budget():
    segs = [Segment("graph", "word " * 500, 1.0, "s", "t") for _ in range(5)]
    out = TruncationCompactor().compact("", segs, top_k=3, max_chars_per=100)
    assert len(out) == 3
    assert all(len(s.text) <= 101 for s in out)


def test_unknown_compactor_raises(monkeypatch):
    monkeypatch.setenv("AGRI_COMPACTOR", "nope")
    with pytest.raises(CompactorUnavailable):
        get_compactor()


# ─────────────────────────── golden-QA benchmark ───────────────────────────


def test_benchmark_pass_rate_above_threshold():
    from scripts.benchmark_gateway import DEFAULT_FIXTURE, run_benchmark

    cases = __import__("json").loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    report = run_benchmark(cases, top_k=5, runs=1)
    assert report["pass_rate"] >= 0.95, report
    assert report["metrics"]["routing"] == 1.0
    assert report["metrics"]["intent"] == 1.0
    assert report["checks_total"] > 0
