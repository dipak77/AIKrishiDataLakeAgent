"""Connector contract test: Agmarknet against the REAL recorded payload.

This is the test that fixtures could never provide. The cassette holds the
response captured live from ``api.data.gov.in`` on 2026-09-02, so the assertions
below are about the world, not about a hand-written sample:

* the upstream field set still matches the declared contract (drift gate);
* ``arrival_date`` really is ``DD/MM/YYYY`` and is canonicalized to ISO;
* the business key is unique across the batch;
* a real live row survives the data-quality gate and promotes;
* a real live vocabulary gap (``Ridgeguard(Tori)``) is reported, not hidden.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from connectors.government.agmarknet import AgmarknetConnector  # noqa: E402
from pipelines.contracts import contract_for  # noqa: E402
from pipelines.dq import DQContext, Status, evaluate  # noqa: E402
from pipelines.http import HttpClient  # noqa: E402

CASSETTE_DIR = ROOT / "tests" / "fixtures" / "cassettes"
RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
CONTRACT = contract_for("GOI_AGMARKNET")


@pytest.fixture()
def live_rows():
    """The recorded upstream rows, exactly as the publisher returned them."""
    client = HttpClient(mode="replay", cassette_dir=CASSETTE_DIR)
    payload = client.get_json(RESOURCE_URL, params={"api-key": "x", "format": "json", "limit": 2})
    return payload["records"]


def test_upstream_field_set_still_matches_the_contract(live_rows):
    assert set(live_rows[0]) == set(CONTRACT.source_field_names())
    for row in live_rows:
        assert CONTRACT.check_source_row(row) == []


def test_upstream_date_format_is_really_dd_mm_yyyy(live_rows):
    assert live_rows[0]["arrival_date"] == "02/09/2026"
    spec = CONTRACT.source_fields["arrival_date"]
    assert spec.format == "DD/MM/YYYY"
    assert spec.parse_date("02/09/2026").isoformat() == "2026-09-02"


def test_connector_canonicalizes_dates_and_keeps_the_original(live_rows):
    connector = AgmarknetConnector()
    for raw, record in zip(live_rows, (connector._map(r) for r in live_rows)):
        assert record["price_date"] == "2026-09-02"
        assert record["price_date_raw"] == raw["arrival_date"]
        assert record["unit"] == "INR/quintal"
        assert record["source_url"].endswith("9ef84268-d588-465a-a308-a864a43d0070")


def test_record_ids_are_slugified_and_stable(live_rows):
    connector = AgmarknetConnector()
    ids = [connector._map(r)["record_id"] for r in live_rows]
    assert ids[0] == "AMN-baripada_apmc-brinjal-2026-09-02"
    assert ids[1] == "AMN-baripada_apmc-ridgeguard_tori-2026-09-02"
    assert all(" " not in i and "/" not in i for i in ids)


def test_prices_are_read_from_the_renamed_upstream_columns(live_rows):
    connector = AgmarknetConnector()
    record = connector._map(live_rows[0])
    assert (record["min_price"], record["modal_price"], record["max_price"]) == (4000.0, 4500.0, 5000.0)


def test_business_key_is_unique_across_the_batch(live_rows):
    connector = AgmarknetConnector()
    rows = [connector._map(r) for r in live_rows]
    keys = {CONTRACT.business_key_of(r) for r in rows}
    assert len(keys) == len(rows)


def test_real_live_rows_pass_the_quality_gate(live_rows):
    connector = AgmarknetConnector()
    records = connector.enrich([connector._map(r) for r in live_rows], run_id="run-ct", method="replay")
    report = evaluate(
        records,
        DQContext(source_id="GOI_AGMARKNET", domain="market", contract=CONTRACT, run_id="run-ct"),
    )
    card = report.scorecard()
    assert card["rows_reject"] == 0 and card["rows_quarantine"] == 0
    assert card["block_count"] == 0
    assert report.promoted is True, card


def test_a_real_vocabulary_gap_is_reported_not_hidden(live_rows):
    """`Ridgeguard(Tori)` is genuine live vocabulary the ontology does not know."""
    connector = AgmarknetConnector()
    records = connector.enrich([connector._map(r) for r in live_rows], run_id="run-ct", method="replay")
    unresolved = [r for r in records if r["commodity_raw"] and not r["crop"]]
    assert [r["commodity_raw"] for r in unresolved] == ["Ridgeguard(Tori)"]

    report = evaluate(
        records,
        DQContext(source_id="GOI_AGMARKNET", domain="market", contract=CONTRACT, run_id="run-ct"),
    )
    assert report.rule_counts.get("DQ-CROP-RESOLVED") == 1
    # an unknown crop is a gap signal, not a reason to park the run
    assert report.promoted is True


def test_unmodified_upstream_rows_do_not_pass_the_silver_contract(live_rows):
    """Guard against silently shipping raw upstream shapes as silver records."""
    assert CONTRACT.check_row(live_rows[0]), "raw upstream rows must not satisfy the silver contract"


def test_discovery_from_the_registry_matches_the_connector():
    connector = AgmarknetConnector()
    resources = connector.discover()
    assert [r["resource_id"] for r in resources] == [CONTRACT.resource_id]
