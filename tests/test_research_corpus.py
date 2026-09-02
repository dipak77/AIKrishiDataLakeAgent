"""Tests for V6 Phase 3: research corpus depth + gold.research_chunk build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_research_corpus import DEFAULT_FIXTURE, build  # noqa: E402


def test_fixture_has_cross_crop_coverage():
    chunks = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    crops = {c for ch in chunks for c in ch.get("crop", [])}
    docs = {ch["document"] for ch in chunks}
    assert len(chunks) >= 26
    assert len(docs) >= 20
    assert len(crops) >= 12, "corpus should span a broad crop set"
    # every chunk carries provenance
    for ch in chunks:
        assert ch.get("chunk_id") and ch.get("text") and ch.get("institution")
        assert ch.get("authority") and ch.get("source_url")


def test_build_research_corpus_writes_lake(tmp_path):
    lake = tmp_path / "lake.duckdb"
    report = build(DEFAULT_FIXTURE, lake)
    assert report["chunks"] >= 26
    assert report["documents"] >= 20

    import duckdb

    con = duckdb.connect(str(lake), read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
        sample = con.execute("SELECT crop FROM gold.research_chunk LIMIT 1").fetchone()[0]
    finally:
        con.close()
    assert n == report["chunks"]
    assert isinstance(sample, list) and sample, "crop must be stored as a list"


def test_rag_reads_lake_corpus():
    from reasoning.rag import load_chunks

    chunks = load_chunks()
    assert len(chunks) >= 26, "load_chunks should now read the lake table"
