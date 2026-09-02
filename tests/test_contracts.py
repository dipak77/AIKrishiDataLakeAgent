"""Tests for source contracts + drift detection (Phase A: pipelines/contracts.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.contracts import (  # noqa: E402
    FieldSpec,
    SourceContract,
    all_contracts,
    contract_for,
    contract_from_dict,
    normalize_type,
)


# ─────────────────────────── loading from the registry ─────────────────────


def test_agmarknet_contract_is_declared_in_the_registry():
    contract = contract_for("GOI_AGMARKNET")
    assert contract is not None
    assert contract.version == "2026-09-02"
    assert contract.resource_id == "9ef84268-d588-465a-a308-a864a43d0070"
    assert contract.source_field_names() == [
        "arrival_date", "commodity", "district", "grade", "market",
        "max_price", "min_price", "modal_price", "state", "variety",
    ]
    assert contract.business_key == ["market", "commodity_raw", "variety", "grade", "price_date"]


def test_contract_encodes_the_verified_upstream_quirks():
    contract = contract_for("GOI_AGMARKNET")
    # arrival_date really is DD/MM/YYYY upstream (verified live 2026-09-02)
    assert contract.source_fields["arrival_date"].format == "DD/MM/YYYY"
    # and it is NOT filterable, so incremental pulls must scan client-side
    assert "arrival_date" not in contract.filterable
    assert contract.incremental.strategy == "full_scan_client_filter"
    # the watermark is read from the canonical silver field; the upstream alias
    # is still declared, because that is what the publisher actually sends
    assert contract.incremental.key == "price_date"
    assert "arrival_date" in contract.source_date_fields
    assert contract.rate_limit.honor_retry_after is True


def test_kcc_declares_no_resource_and_no_fictional_source_fields():
    contract = contract_for("GOI_KCC")
    assert contract is not None
    assert contract.source_fields == {}          # retired resource: nothing to assert
    assert contract.fields["query_original"].required is True


def test_unregistered_source_returns_none():
    assert contract_for("NO_SUCH_SOURCE") is None


def test_all_contracts_returns_declared_sources_only():
    contracts = all_contracts()
    assert "GOI_AGMARKNET" in contracts and "GOI_KCC" in contracts
    assert all(isinstance(c, SourceContract) for c in contracts.values())


def test_invalid_contract_raises_value_error():
    with pytest.raises(ValueError):
        contract_from_dict({"version": "x", "pagination": {"mode": 123, "bogus": True}})


# ─────────────────────────── hashing / drift ───────────────────────────────


def test_contract_hash_is_stable_and_schema_sensitive():
    a = contract_for("GOI_AGMARKNET")
    b = contract_from_dict(a.model_dump())
    assert a.contract_hash() == b.contract_hash()

    mutated = a.model_dump()
    mutated["source_fields"]["min_price"]["type"] = "str"
    assert contract_from_dict(mutated).contract_hash() != a.contract_hash()


def test_drift_detects_added_removed_and_type_changes():
    contract = contract_for("GOI_AGMARKNET")
    discovered = {
        name: {"type": meta.type, "exposed": True} for name, meta in contract.source_fields.items()
    }
    assert contract.drift_from(discovered) == {
        "added": [], "removed": [], "type_changed": [], "no_longer_filterable": [],
    }

    discovered.pop("grade")                                     # removed
    discovered["new_field"] = {"type": "keyword", "exposed": False}   # added
    discovered["min_price"]["type"] = "keyword"                   # double -> str
    discovered["state"]["exposed"] = False                        # no longer filterable
    drift = contract.drift_from(discovered)
    assert drift["removed"] == ["grade"]
    assert drift["added"] == ["new_field"]
    assert drift["type_changed"] == ["min_price"]
    assert drift["no_longer_filterable"] == ["state"]


def test_upstream_type_vocabulary_is_normalised():
    # OGD returns keyword/double/long; the contract speaks str/float/int
    assert normalize_type("keyword") == "str"
    assert normalize_type("double") == "float"
    assert normalize_type("long") == "int"
    assert normalize_type("DATE") == "date"
    assert normalize_type(None) == ""


# ─────────────────────────── row conformance ───────────────────────────────


LIVE_ROW = {
    "state": "Odisha", "district": "Mayurbhanja", "market": "Baripada APMC",
    "commodity": "Brinjal", "variety": "Brinjal", "grade": "Medium",
    "arrival_date": "02/09/2026", "min_price": 4000, "max_price": 5000, "modal_price": 4500,
}


def test_live_upstream_row_conforms_to_source_contract():
    assert contract_for("GOI_AGMARKNET").check_source_row(LIVE_ROW) == []


def test_source_contract_rejects_bad_date_and_negative_price():
    contract = contract_for("GOI_AGMARKNET")
    bad = dict(LIVE_ROW, arrival_date="2026-09-02", min_price=-5)
    problems = contract.check_source_row(bad)
    assert any("arrival_date" in p for p in problems)
    assert any("min_price" in p for p in problems)


def test_source_contract_flags_missing_required_field():
    contract = contract_for("GOI_AGMARKNET")
    row = {k: v for k, v in LIVE_ROW.items() if k != "market"}
    assert any("market" in p for p in contract.check_source_row(row))


def test_date_parsing_uses_the_declared_format():
    spec = FieldSpec(type="date", format="DD/MM/YYYY")
    assert spec.parse_date("02/09/2026").isoformat() == "2026-09-02"
    assert spec.parse_date("2026-09-02") is None      # ISO is not DD/MM/YYYY
    assert spec.parse_date("") is None


def test_unknown_date_format_is_rejected():
    with pytest.raises(ValueError):
        FieldSpec(type="date", format="MM-DD-YY").parse_date("09-02-26")


def test_business_key_and_incremental_key_extraction():
    contract = contract_for("GOI_AGMARKNET")
    silver = {
        "market": "Baripada APMC", "commodity_raw": "Brinjal", "variety": "Brinjal",
        "grade": "Medium", "price_date": "2026-09-02", "arrival_date": "02/09/2026",
    }
    assert contract.business_key_of(silver) == (
        "Baripada APMC", "Brinjal", "Brinjal", "Medium", "2026-09-02"
    )
    # the incremental key normalises the upstream date to ISO so watermarks sort
    source_contract = contract_from_dict(
        {**contract.model_dump(), "incremental": {"strategy": "full_scan_client_filter", "key": "arrival_date"}}
    )
    assert source_contract.incremental_key_of(LIVE_ROW) == "2026-09-02"


def test_enum_and_range_constraints():
    contract = contract_from_dict({
        "version": "t",
        "fields": {
            "grade": {"type": "str", "enum": ["A", "B"]},
            "ph": {"type": "float", "min": 0, "max": 14},
        },
    })
    assert contract.check_row({"grade": "A", "ph": 6.5}) == []
    problems = contract.check_row({"grade": "Z", "ph": 99})
    assert any("enum" in p for p in problems)
    assert any("above max" in p for p in problems)
