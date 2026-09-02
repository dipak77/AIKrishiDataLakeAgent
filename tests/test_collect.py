"""Tests for collection primitives + connector run semantics (Phase B)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.collect import (  # noqa: E402
    RunLedger,
    RunSummary,
    WatermarkStore,
    attach_provenance,
    canonical_json,
    dedupe_records,
    new_run_id,
    partition_of,
    record_hash,
)


@pytest.fixture(autouse=True)
def isolated_lake_dirs(tmp_path, monkeypatch):
    """Keep connector runs out of the real data/silver + data/bronze trees."""
    import pipelines.storage as storage

    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path / "silver")
    monkeypatch.setattr(storage, "BRONZE_DIR", tmp_path / "bronze")
    return tmp_path



# ─────────────────────────── identity + idempotency ────────────────────────


def test_record_hash_is_stable_across_runs():
    record = {"market": "Lasalgaon", "commodity_raw": "Onion", "modal_price": 1700}
    first = attach_provenance([record], run_id="run-1", method="live")[0]
    second = attach_provenance([record], run_id="run-2", method="live")[0]
    assert first["record_hash"] == second["record_hash"]      # identity ignores run metadata
    assert first["run_id"] != second["run_id"]


def test_record_hash_ignores_volatile_fields_only():
    base = {"market": "Lasalgaon", "modal_price": 1700}
    assert record_hash(base) == record_hash({**base, "ingested_at": "2026-09-02T00:00:00+00:00"})
    assert record_hash(base) == record_hash({**base, "quality": {"quality_score": 0.9}})
    assert record_hash(base) != record_hash({**base, "modal_price": 1701})


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_attach_provenance_stamps_method_and_rejects_unknown_methods():
    rows = attach_provenance([{"x": 1}], run_id="r", method="replay", source_id="SRC")
    assert rows[0]["ingestion_method"] == "replay"
    assert rows[0]["source_id"] == "SRC"
    assert rows[0]["record_hash"]
    with pytest.raises(ValueError):
        attach_provenance([{"x": 1}], run_id="r", method="guessed")


def test_attach_provenance_does_not_mutate_inputs():
    original = {"x": 1}
    attach_provenance([original], run_id="r", method="live")
    assert original == {"x": 1}


def test_dedupe_separates_duplicates_from_conflicts():
    rows = attach_provenance(
        [{"k": "a", "v": 1}, {"k": "a", "v": 1}, {"k": "a", "v": 2}], run_id="r", method="live"
    )
    unique, duplicates, conflicts = dedupe_records(rows, key_fields=["k"])
    assert len(unique) == 1 and len(duplicates) == 1 and len(conflicts) == 1


def test_new_run_id_is_unique_and_prefixed():
    a, b = new_run_id("goi_agmarknet"), new_run_id("goi_agmarknet")
    assert a != b and a.startswith("goi_agmarknet-")


def test_partition_of_normalises_dates():
    assert partition_of("2026-09-02") == "dt=2026-09-02"
    assert partition_of(None) == "dt=unknown"
    assert partition_of("02/09/2026") == "dt=unknown"     # non-ISO is not silently accepted


# ─────────────────────────── watermarks + ledger ───────────────────────────


def test_watermark_advances_only_forward(tmp_path):
    lake = tmp_path / "lake.duckdb"
    store = WatermarkStore(lake)
    assert store.get("SRC", "RES") is None
    assert store.advance("SRC", "RES", ["2026-09-01", "2026-09-02"]) == "2026-09-02"
    assert store.get("SRC", "RES") == "2026-09-02"
    # an older batch must not move the watermark backwards
    assert store.advance("SRC", "RES", ["2026-08-30"]) == "2026-09-02"
    assert store.advance("SRC", "RES", ["2026-09-03"]) == "2026-09-03"


def test_watermarks_are_partition_scoped(tmp_path):
    lake = tmp_path / "lake.duckdb"
    store = WatermarkStore(lake)
    store.advance("SRC", "RES", ["2026-09-01"], partition="state=Odisha")
    store.advance("SRC", "RES", ["2026-08-01"], partition="state=Maharashtra")
    assert store.get("SRC", "RES", "state=Odisha") == "2026-09-01"
    assert store.get("SRC", "RES", "state=Maharashtra") == "2026-08-01"


def test_run_ledger_records_and_reads_back(tmp_path):
    lake = tmp_path / "lake.duckdb"
    ledger = RunLedger(lake)
    summary = RunSummary(
        run_id="run-1", source_id="GOI_AGMARKNET", resource_id="9ef84268",
        transport="replay", status="ok", rows_raw=17800, rows_pass=17790,
        rows_quarantine=10, watermark_after="2026-09-02",
    )
    ledger.record(summary)
    rows = ledger.recent()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1" and rows[0]["rows_raw"] == 17800
    # re-recording the same run replaces it rather than duplicating
    ledger.record(summary)
    assert len(ledger.recent()) == 1
    assert ledger.recent(source_id="NOPE") == []


# ─────────────────────────── connector run semantics ───────────────────────


class _RecordingConnector:
    """Minimal connector exercising the real lifecycle in connectors/base.py."""

    def __init__(self, raw):
        from connectors.base import AgricultureSourceConnector

        connector = self

        class Dummy(AgricultureSourceConnector):
            source_id = "GOI_AGMARKNET"
            domain = "market"

            def discover(self_inner):
                return [{"resource_id": "res-1", "description": "test"}]

            def fetch(self_inner, resource):
                return raw

            def normalize(self_inner, payload, resource):
                return list(payload or [])

        self.connector = Dummy()
        self.connector.limit = 5


def test_run_stamps_run_id_and_ingestion_method(tmp_path):
    _RecordingConnector([{"market": "X", "modal_price": 1}])
    from connectors.government.agmarknet import AgmarknetConnector

    connector = AgmarknetConnector()
    connector.limit = 1
    summary = connector.run(transport="replay", lake=tmp_path / "lake.duckdb", ledger=False)
    assert summary["run_id"]
    for entry in summary["resources"]:
        assert entry["status"] == "ok"
        assert entry["method"] in ("live", "replay", "fixture")
        for path in entry["paths"]:
            row = json.loads(Path(path).read_text(encoding="utf-8").splitlines()[0])
            assert row["ingestion_method"] == entry["method"]
            assert row["run_id"] and row["record_hash"]


def test_require_live_fails_closed_instead_of_emitting_fixtures(tmp_path):
    from connectors.government.agmarknet import AgmarknetConnector

    connector = AgmarknetConnector()
    connector.limit = 1
    # offline transport → fetch() cannot reach the endpoint → fixture fallback
    summary = connector.run(
        transport="offline", require_live=True, lake=tmp_path / "lake.duckdb", ledger=False
    )
    assert summary["status"] == "failed"
    entry = summary["resources"][0]
    assert entry["status"] == "error"
    assert "require_live" in entry["error"]
    assert entry.get("records") is None            # nothing was persisted


def test_run_writes_a_ledger_row_per_resource(tmp_path):
    from connectors.government.agmarknet import AgmarknetConnector

    lake = tmp_path / "lake.duckdb"
    connector = AgmarknetConnector()
    connector.limit = 1
    summary = connector.run(transport="offline", lake=lake)
    rows = RunLedger(lake).recent()
    assert len(rows) == 1
    assert rows[0]["source_id"] == "GOI_AGMARKNET"
    assert rows[0]["status"] in ("ok", "failed")
    assert summary["resources"][0]["run_id"].startswith(summary["run_id"])
