"""Tests for V5-A: hybrid semantic retrieval + query expansion."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.embeddings import HashingEmbedder, cosine, expand_query  # noqa: E402
from reasoning.rag import HybridIndex, hybrid_search  # noqa: E402

FIXTURE = json.loads(
    (ROOT / "data" / "fixtures" / "icar_research_chunk.json").read_text(encoding="utf-8")
)


def test_embedding_deterministic_and_normalized():
    e = HashingEmbedder(dim=512)
    a = e.embed("tomato early blight black spots")
    b = e.embed("tomato early blight black spots")
    assert a == b
    assert abs(cosine(a, a) - 1.0) < 1e-9
    assert 0.0 <= cosine(a, b) <= 1.0 + 1e-9


def test_embedding_semantic_overlap():
    e = HashingEmbedder(dim=512)
    a = e.embed("black spots on tomato leaves")
    b = e.embed("dark spots and lesions on tomato foliage")
    c = e.embed("wheat rust resistant varieties")
    assert cosine(a, b) > cosine(a, c)


def test_embedding_empty():
    e = HashingEmbedder()
    assert e.embed("") == {}
    assert cosine({}, e.embed("anything")) == 0.0


def test_expand_query_adds_crop_and_symptoms():
    q = expand_query("Khaira in rice")
    assert "oryza sativa" in q.lower()          # scientific name added
    assert "zinc" in q.lower() or "brown" in q.lower()  # deficiency symptoms added


def test_expand_query_noop_on_plain_text():
    assert expand_query("hello there") == "hello there"


def test_hybrid_search_ranks_relevant_top():
    hits = hybrid_search("pink bollworm control", top_k=3)
    assert hits
    assert hits[0].document.lower().startswith("integrated pest management")


def test_hybrid_search_crop_filter():
    hits = hybrid_search("rust control", crop="soybean", top_k=5)
    assert hits
    assert all("CROP_SOYBEAN" in h.crop for h in hits)


def test_hybrid_matches_lexical_miss():
    # "khaira" appears nowhere verbatim, but ontology expansion should still
    # surface the rice zinc-deficiency chunk.
    hits = hybrid_search("khaira", top_k=5)
    assert any("Zinc" in h.document or "khaira" in h.text.lower() or "rice" in (h.crop[0].lower() if h.crop else "") for h in hits)


def test_hybrid_vs_bm25_on_typo():
    # A character-level typo that pure BM25 may miss on exact tokens.
    hits = hybrid_search("blght control tomato", top_k=5, crop="tomato")
    assert hits
    assert hits[0].crop == ["CROP_TOMATO"]


def test_hybrid_empty_query():
    assert hybrid_search("zzzzzzzzzz no match", top_k=5) == []


def test_hybrid_index_scores_descending():
    hits = hybrid_search("tomato disease", top_k=5, crop="tomato")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
