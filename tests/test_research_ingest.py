"""Tests for V6 Phase 3: live-capable research ingestion → gold.research_chunk."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.research.icar import IcarConnector  # noqa: E402
from scripts.ingest_research import _run_connector, _upsert  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_medallion_dirs(tmp_path, monkeypatch):
    """`_run_connector` persists bronze+silver; keep it out of the real tree."""
    import pipelines.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path / "silver")
    monkeypatch.setattr(storage, "BRONZE_DIR", tmp_path / "bronze")
    return tmp_path


def test_icar_connector_falls_back_to_fixture_offline(monkeypatch):
    # Simulate no network: requests.get raises → fetch returns None (fixture).
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    conn = IcarConnector()
    raw = conn.fetch(conn.discover()[0])
    assert raw is None
    assert conn.normalize(None, {})  # fixture records present


def test_icar_connector_normalizes_live_payload(monkeypatch):
    conn = IcarConnector()
    live = [{"chunk_id": "live-1", "document": "D", "institution": "ICAR", "text": "x"}]
    assert conn.normalize(live, {}) == live


def test_ingest_research_upserts_to_lake(tmp_path):
    records, summaries = _run_connector()
    assert records, "fixture baseline must produce records offline"
    lake = tmp_path / "r.duckdb"
    report = _upsert(lake, records)
    assert report["upserted"] >= 26
    assert report["total"] >= 26
    assert report["documents"] >= 20

    import duckdb

    con = duckdb.connect(str(lake), read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
    finally:
        con.close()
    assert n == report["total"]


def test_ingest_research_is_idempotent(tmp_path):
    records, _ = _run_connector()
    lake = tmp_path / "r2.duckdb"
    first = _upsert(lake, records)
    second = _upsert(lake, records)
    assert second["total"] == first["total"]
    assert second["upserted"] == first["upserted"]
