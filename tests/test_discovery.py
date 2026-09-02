"""Tests for source discovery + drift (Phase A: pipelines/discovery.py).

Runs entirely against the recorded live payload in
``tests/fixtures/cassettes/goi_agmarknet_daily_mandi_price.json`` — real
upstream shapes, zero egress.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.contracts import contract_for  # noqa: E402
from pipelines.discovery import (  # noqa: E402
    DataGovDiscovery,
    catalog_rows,
    load_discovered,
    save_discovered,
    upsert_catalog,
)
from pipelines.http import CassetteMiss, HttpClient  # noqa: E402

CASSETTE_DIR = ROOT / "tests" / "fixtures" / "cassettes"
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"


@pytest.fixture()
def discovery():
    return DataGovDiscovery(HttpClient(mode="replay", cassette_dir=CASSETTE_DIR))


def test_discovery_reads_the_real_resource_metadata(discovery):
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    assert found.title.startswith("Current Daily Price of Various Commodities")
    assert found.org == ["Ministry of Agriculture and Farmers Welfare",
                         "Department of Agriculture and Farmers Welfare"]
    assert found.total_records == 17800
    assert found.upstream_updated_at == "2026-09-02T17:01:08Z"
    assert found.discovery_method == "resource_meta"


def test_discovery_extracts_the_true_filterable_subset(discovery):
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    # verified live: exactly six fields are exposed for filters[...]
    assert found.field_exposed == ["commodity", "district", "grade", "market", "state", "variety"]
    assert "arrival_date" not in found.field_exposed
    assert found.field_schema["min_price"]["type"] == "double"


def test_discovery_stamps_the_governance_licence_decision(discovery):
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    assert found.license_declared == "GODL-India"
    assert found.license_decision == "ALLOW"


def test_discovery_reports_no_drift_for_a_matching_contract(discovery):
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    assert found.has_drift is False
    assert found.contract_hash == contract_for("GOI_AGMARKNET").contract_hash()


def test_discovery_flags_upstream_schema_drift(discovery, monkeypatch):
    contract = contract_for("GOI_AGMARKNET")
    mutated = contract.model_dump()
    mutated["source_fields"]["modal_price"]["type"] = "str"     # upstream says double
    mutated["source_fields"]["new_upstream_field"] = {"type": "str"}
    from pipelines import contracts as contracts_module

    monkeypatch.setattr(contracts_module, "contract_for", lambda _sid: contracts_module.contract_from_dict(mutated))
    from pipelines import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "contract_for", lambda _sid: contracts_module.contract_from_dict(mutated))

    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    assert found.has_drift is True
    assert "modal_price" in found.drift["type_changed"]
    assert "new_upstream_field" in found.drift["removed"]


def test_discovery_raises_for_a_retired_resource():
    """The KCC id documented in the old code is gone; discovery must say so."""
    import json as _json

    from pipelines.http import Cassette, CassetteEntry

    cassette = Cassette(path=Path("unused.json"), entries=[
        CassetteEntry(
            request_url="https://api.data.gov.in/resource/5f039cdb2e054ab5b74bfc2a6e1a860b?format=json&limit=1",
            method="GET", status=200, headers={},
            body=_json.dumps({"message": "Meta not found", "status": "error"}),
            recorded_at="2026-09-02T17:35:00+00:00",
        )
    ])
    client = HttpClient(mode="replay", cassette=cassette)
    with pytest.raises(LookupError, match="not available"):
        DataGovDiscovery(client).discover_resource("GOI_KCC", "5f039cdb2e054ab5b74bfc2a6e1a860b")


def test_discovery_propagates_cassette_miss_rather_than_guessing():
    client = HttpClient(mode="replay", cassette_dir=Path("."))
    with pytest.raises(CassetteMiss):
        DataGovDiscovery(client).discover_resource("GOI_AGMARKNET", "no-such-resource")


def test_discovered_snapshot_roundtrip(tmp_path, discovery):
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    paths = save_discovered([found], tmp_path)
    assert len(paths) == 1 and paths[0].name == "goi_agmarknet.json"
    rows = load_discovered("GOI_AGMARKNET", tmp_path)
    assert rows[0]["total_records"] == 17800
    assert rows[0]["field_schema"]["arrival_date"]["type"] == "date"
    assert load_discovered("NOPE", tmp_path) == []


def test_catalog_upsert_is_idempotent(tmp_path, discovery):
    lake = tmp_path / "lake.duckdb"
    found = discovery.discover_resource("GOI_AGMARKNET", RESOURCE_ID)
    assert upsert_catalog([found], lake) == 1
    assert upsert_catalog([found], lake) == 1
    rows = catalog_rows(lake)
    assert len(rows) == 1
    assert rows[0]["source_id"] == "GOI_AGMARKNET"
    assert rows[0]["has_drift"] is False
    assert json.loads(rows[0]["field_schema"])["modal_price"]["type"] == "double"
