"""End-to-end tests for the production orchestrator (scripts/pipeline_run.py).

These run the *real* pipeline — discovery, collection, the 23-rule quality gate,
the watermark and the gap register — against the recorded live payload, writing
into a throwaway lake and medallion tree. No egress, no repository mutation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pipelines.storage as storage  # noqa: E402
from scripts.pipeline_run import (  # noqa: E402
    SOURCE_CONNECTORS,
    declared_resources,
    main,
    price_stats,
    run_source,
)

CASSETTE_DIR = ROOT / "tests" / "fixtures" / "cassettes"
SOURCE = "GOI_AGMARKNET"
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Every artefact of a run lands in tmp: bronze, silver, discovery JSON."""
    monkeypatch.setattr(storage, "SILVER_DIR", tmp_path / "silver")
    monkeypatch.setattr(storage, "BRONZE_DIR", tmp_path / "bronze")
    monkeypatch.setattr("pipelines.discovery.DISCOVERED_DIR", tmp_path / "discovered")
    return tmp_path


def _run(tmp_path, **kwargs):
    return run_source(
        SOURCE,
        transport=kwargs.pop("transport", "replay"),
        limit=kwargs.pop("limit", 2),
        lake=tmp_path / "lake.duckdb",
        discovered_dir=tmp_path / "discovered",
        cassette_dir=CASSETTE_DIR,
        **kwargs,
    )


# ─────────────────────────── happy path ────────────────────────────────────


def test_full_pipeline_promotes_a_real_batch(sandbox):
    out = _run(sandbox)
    assert out["status"] == "promoted", out
    assert out["contract_version"] == "2026-09-02"
    assert out["contract_hash"]

    discovery = out["discovery"]
    assert discovery["status"] == "ok"
    res = discovery["resources"][0]
    assert res["resource_id"] == RESOURCE
    assert res["total_records"] == 17800
    assert res["license"] == "GODL-India" and res["license_decision"] == "ALLOW"
    assert res["has_drift"] is False
    assert res["updated_at"] == "2026-09-02T17:01:08Z"

    collect = out["collection"]["resources"][0]
    assert collect["method"] == "replay", "replayed rows must not be labelled live"
    assert collect["records"] == 2
    assert collect["bronze"] and Path(collect["bronze"]).is_file()

    quality = out["quality"]
    assert quality["promoted"] is True
    card = quality["scorecard"]
    assert (card["rows_pass"], card["rows_quarantine"], card["rows_reject"]) == (2, 0, 0)
    assert card["block_count"] == 0 and card["warn_rate"] == 0.0
    # the real vocabulary gap is reported, not swallowed
    assert quality["rule_counts"].get("DQ-CROP-RESOLVED") == 1

    assert out["watermark"]["watermark"] == "2026-09-02"
    assert out["gaps"]["new"] >= 1


def test_pipeline_writes_every_audit_table(sandbox):
    _run(sandbox)
    lake = sandbox / "lake.duckdb"
    con = duckdb.connect(str(lake), read_only=True)
    try:
        def count(table):
            return con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]

        assert count("source_catalog") == 1
        assert count("ingest_run") == 1
        assert count("dq_scorecard") == 1
        assert count("ingest_watermark") == 1
        assert count("gap_register") > 0
        assert count("dq_violation") >= 0

        run = con.execute(
            "SELECT source_id, resource_id, transport, status, rows_raw, rows_pass "
            "FROM gold.ingest_run"
        ).fetchone()
        assert run[0] == SOURCE and run[1] == RESOURCE
        assert run[2] == "replay" and run[3] == "ok"
        assert run[4] == 2 and run[5] == 2

        catalog = con.execute(
            "SELECT license_decision, has_drift, total_records, contract_version "
            "FROM gold.source_catalog"
        ).fetchone()
        assert catalog == ("ALLOW", False, 17800, "2026-09-02")

        gap = con.execute(
            "SELECT type, key, status FROM gold.gap_register "
            "WHERE type='UNRESOLVED_ENTITY' ORDER BY demand_signal DESC LIMIT 1"
        ).fetchone()
        assert gap == ("UNRESOLVED_ENTITY", "Ridgeguard(Tori)", "open")
    finally:
        con.close()


def test_second_run_is_idempotent(sandbox):
    first = _run(sandbox)
    second = _run(sandbox)
    assert second["status"] == "promoted"
    assert second["gaps"]["new"] == 0
    assert second["gaps"]["refreshed"] == first["gaps"]["new"] + first["gaps"]["refreshed"]
    assert second["watermark"]["watermark"] == "2026-09-02"


def test_discovery_snapshot_is_written_outside_the_repository(sandbox):
    _run(sandbox)
    snapshots = list((sandbox / "discovered").glob("*.json"))
    assert snapshots, "no discovery snapshot written"
    payload = json.loads(snapshots[0].read_text(encoding="utf-8"))
    row = payload["resources"][0]
    assert row["resource_id"] == RESOURCE
    assert row["field_schema"]["arrival_date"]["type"] == "date"
    assert row["license_decision"] == "ALLOW"
    assert len(snapshots) == 1 and snapshots[0].name == "goi_agmarknet.json"
    # metadata/discovered/ holds per-environment run artefacts, never source
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "metadata/discovered/" in gitignore


# ─────────────────────────── fail-closed behaviour ─────────────────────────


def test_require_live_refuses_to_promote_fixtures(sandbox):
    """An unreachable source must fail, never quietly ship bundled samples."""
    out = _run(sandbox, transport="offline", require_live=True)
    assert out["status"] == "failed"
    assert "require_live" in out["error"]


def test_allow_fixtures_is_an_explicit_opt_out(sandbox):
    out = _run(sandbox, transport="offline", require_live=False)
    assert out["status"] == "promoted"
    assert out["collection"]["resources"][0]["method"] == "fixture"
    assert out["collection"]["resources"][0]["bronze"] is None


def test_a_retired_resource_reports_empty_rather_than_failing(sandbox):
    out = run_source(
        "GOI_KCC", transport="replay", lake=sandbox / "lake.duckdb",
        discovered_dir=sandbox / "discovered", cassette_dir=CASSETTE_DIR,
    )
    assert out["status"] == "empty"
    assert out["collection"]["discovered"] == 0


def test_unknown_source_is_reported_not_guessed(sandbox):
    out = run_source("NOPE", lake=sandbox / "lake.duckdb")
    assert out["status"] == "unknown_source"


def test_drift_gate_can_abort_a_source(sandbox, monkeypatch):
    """If upstream changes shape, --fail-on-drift stops the run before collection."""
    from pipelines import contracts as contracts_module
    from pipelines import discovery as discovery_module

    contract = contracts_module.contract_for(SOURCE)
    mutated = contract.model_dump()
    mutated["source_fields"]["modal_price"]["type"] = "str"
    replacement = contracts_module.contract_from_dict(mutated)
    monkeypatch.setattr(contracts_module, "contract_for", lambda _sid: replacement)
    monkeypatch.setattr(discovery_module, "contract_for", lambda _sid: replacement)
    monkeypatch.setattr("scripts.pipeline_run.contract_for", lambda _sid: replacement)

    out = _run(sandbox, fail_on_drift=True)
    assert out["status"] == "drift"
    assert out["discovery"]["resources"][0]["has_drift"] is True
    assert "collection" not in out, "a drifted source must not be collected"


# ─────────────────────────── helpers ───────────────────────────────────────


def test_price_stats_needs_a_sample_before_judging_outliers():
    assert price_stats([{"market": "M", "commodity_raw": "C", "modal_price": 100}]) == {}
    stats = price_stats(
        [
            {"market": "M", "commodity_raw": "C", "modal_price": 100},
            {"market": "M", "commodity_raw": "C", "modal_price": 110},
            {"market": "M", "commodity_raw": "C", "modal_price": 90},
            {"market": "M", "commodity_raw": "C", "modal_price": None},
        ]
    )
    assert stats == {("M", "C"): (100.0, 10.0)}


def test_declared_resources_falls_back_to_the_contract_id():
    assert declared_resources(SOURCE, None) == [RESOURCE]
    assert declared_resources("NOPE", None) == []


def test_every_registered_connector_is_reachable_from_the_orchestrator():
    for source_id, factory in SOURCE_CONNECTORS.items():
        connector = factory()
        assert connector.source_id == source_id


def test_cli_exit_codes(sandbox, capsys):
    code = main(
        ["--source", SOURCE, "--transport", "replay", "--limit", "2",
         "--lake", str(sandbox / "cli.duckdb"), "--cassette-dir", str(CASSETTE_DIR), "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "promoted"

    # a source that cannot be reached in offline mode exits non-zero
    assert main(
        ["--source", SOURCE, "--transport", "offline", "--lake", str(sandbox / "cli2.duckdb")]
    ) == 1
