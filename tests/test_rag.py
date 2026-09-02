"""Tests for Track 9: BM25 evidence retrieval."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.rag import SearchIndex, evidence_for_diagnosis, load_chunks, search, tokenize  # noqa: E402

FIXTURE = json.loads(
    (ROOT / "data" / "fixtures" / "icar_research_chunk.json").read_text(encoding="utf-8")
)


def test_tokenize_strips_stopwords_and_punct():
    toks = tokenize("Early blight (Alternaria solani) causes dark spots!")
    assert "early" in toks and "blight" in toks and "spots" in toks
    assert "the" not in toks and "(" not in toks


def test_search_ranks_relevant_top():
    hits = search("pink bollworm control", top_k=3)
    assert hits
    assert hits[0].document.lower().startswith("integrated pest management")


def test_search_crop_filter():
    hits = search("rust control", crop="CROP_SOYBEAN", top_k=5)
    assert hits
    assert all("CROP_SOYBEAN" in h.crop for h in hits)


def test_search_returns_evidence_fields():
    hits = search("zinc deficiency rice", top_k=1)
    assert hits
    h = hits[0]
    assert h.authority == "research"
    assert h.authority_score > 0.9
    assert h.source_url and h.institution
    assert "license" in h.as_dict()


def test_search_empty_query_no_crash():
    assert search("zzzzzz no match here", top_k=5) == []


def test_evidence_for_diagnosis_tomato():
    hits = evidence_for_diagnosis("tomato", "black spots yellowing lower leaves")
    assert hits
    assert any("CROP_TOMATO" in h.crop for h in hits)


def test_load_chunks_falls_back_to_fixture():
    chunks = load_chunks()
    assert len(chunks) >= 8


def test_search_index_bm25_consistency():
    idx = SearchIndex(FIXTURE)
    hits = idx.search("alternaria")
    assert hits
    assert hits[0].score > 0
