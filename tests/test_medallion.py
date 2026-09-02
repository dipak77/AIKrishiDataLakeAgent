"""Tests for V6 Phase 4: bronze/silver medallion materialization.

Every test in this module runs against a module-scoped temp lake tree: a test
suite must never rewrite ``data/bronze`` or ``data/silver`` (those are build
outputs, and re-emitting them churns 24 JSONL files on every run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pipelines.storage as storage  # noqa: E402
import scripts.build_medallion as medallion  # noqa: E402
from scripts.build_medallion import build_medallion  # noqa: E402


@pytest.fixture(scope="module")
def dirs(tmp_path_factory):
    """Redirect bronze + silver into a temp tree for the whole module."""
    base = tmp_path_factory.mktemp("medallion")
    bronze, silver = base / "bronze", base / "silver"
    with pytest.MonkeyPatch.context() as mp:
        # both the storage module and the script's own imported names
        for mod in (storage, medallion):
            mp.setattr(mod, "BRONZE_DIR", bronze)
            mp.setattr(mod, "SILVER_DIR", silver)
        yield {"bronze": bronze, "silver": silver}


def test_medallion_materializes_all_seed_tables(dirs):
    report = build_medallion()
    assert report["bronze_tables"] == 24
    assert report["silver_tables"] == 24
    assert report["silver_total_rows"] > 1500
    # and it really wrote into the temp tree, not the repository
    assert list((dirs["silver"] / "ontology").glob("*.jsonl")), "no silver emitted"
    assert (dirs["bronze"] / "seed_ontology").is_dir()


def test_bronze_artifacts_are_immutable(dirs):
    # every bronze artifact must carry a manifest with sha256 + bytes
    manifests = list((dirs["bronze"] / "seed_ontology").glob("*/_manifest.json"))
    assert len(manifests) == 24
    for m in manifests:
        data = json.loads(m.read_text(encoding="utf-8"))
        assert data["sha256"] and len(data["sha256"]) == 64
        assert data["bytes"] > 0
        artifact = m.parent / data["filename"]
        assert artifact.is_file()
        assert artifact.stat().st_size == data["bytes"]
        assert data["ingestion_method"] == "seed"   # seed bronze is not a live fetch


def test_bronze_is_idempotent(dirs):
    first = build_medallion()
    second = build_medallion()
    unchanged = [b for b in second["bronze_artifacts"] if b.get("status") == "unchanged"]
    assert len(unchanged) == 24, "identical seed content must not rewrite bronze"
    assert first["silver_total_rows"] == second["silver_total_rows"]


def test_silver_records_carry_provenance_and_quality(dirs):
    path = dirs["silver"] / "ontology" / "dim_crop.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows
    for row in rows:
        assert row["source_id"] == "seed_ontology"
        assert row["license"]["type"] == "GODL-India"
        assert "quality" in row and "quality_score" in row["quality"]
        assert row["ingested_at"]
    # government authority should score high
    assert rows[0]["quality"]["authority_score"] >= 0.9


def test_connector_persists_bronze_for_raw_payload(dirs):
    from connectors.base import AgricultureSourceConnector

    class Dummy(AgricultureSourceConnector):
        source_id = "DUMMY"
        domain = "research"

        def discover(self):
            return [{"resource_id": "r1"}]

        def fetch(self, resource):
            return {"title": "sample", "rows": [1, 2]}

        def normalize(self, raw, resource):
            return [{"chunk_id": "x", "text": "hello"}]

    conn = Dummy()
    path = conn.persist_bronze({"a": 1}, {"resource_id": "r1"})
    assert path and Path(path).is_file()
    assert str(dirs["bronze"]) in path
    manifest = Path(path).parent / "_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["source_id"] == "DUMMY"
    assert data["sha256"]


def test_connector_persists_no_bronze_for_fixture():
    from connectors.base import AgricultureSourceConnector

    class Dummy(AgricultureSourceConnector):
        source_id = "DUMMY2"
        domain = "research"

        def discover(self):
            return []

        def fetch(self, resource):
            return None

        def normalize(self, raw, resource):
            return []

    assert Dummy().persist_bronze(None, {"resource_id": "r1"}) is None
