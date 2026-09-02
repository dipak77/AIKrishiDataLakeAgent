"""Tests for Track 12: graph-native lakehouse + query API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning import graph_query as gq  # noqa: E402
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    gq.ensure_graph_tables()
    yield


def test_graph_summary():
    s = gq.graph_summary()
    assert s["nodes"] >= 1400
    assert s["edges"] >= 1600
    assert "crop" in s["node_types"] and "disease" in s["node_types"]


def test_neighbors_tomato():
    nb = gq.graph_neighbors("CROP_TOMATO", direction="out")
    rels = {n["relation"] for n in nb}
    assert "hasDisease" in rels and "hasSeason" in rels


def test_crop_health_map():
    hm = gq.crop_health_map("tomato")
    assert hm["found"] is True
    assert any(d["label"] == "Early blight" for d in hm["diseases"])


def test_symptom_candidates_ranked():
    cands = gq.symptom_candidates("black spots yellowing")
    assert cands
    assert cands[0]["matched"] >= cands[-1]["matched"]


def test_symptom_candidates_crop_filtered():
    cands = gq.symptom_candidates("black spots", crop="tomato")
    assert cands
    assert all("tomato" in c["id"].lower() or c["type"] == "deficiency" for c in cands[:3])


def test_graph_path_shortest():
    path = gq.graph_path("CROP_TOMATO", "PATHOGEN:alternaria solani")
    labels = [p["label"] for p in path]
    assert labels == ["Tomato", "Early blight", "Alternaria solani"]


def test_graph_path_none():
    assert gq.graph_path("CROP_TOMATO", "CROP_MANGO") == []
