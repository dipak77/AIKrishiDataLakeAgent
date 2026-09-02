"""Tests for the data-quality refinery (Phase C: pipelines/dq.py).

Every rule family gets a positive and a negative case, and the gate itself is
asserted: nothing is dropped without a violation row, and a blocking violation
parks the run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.collect import attach_provenance  # noqa: E402
from pipelines.contracts import contract_for  # noqa: E402
from pipelines.dq import (  # noqa: E402
    DQContext,
    Outcome,
    Severity,
    Status,
    classify,
    evaluate,
    gate,
    persist_report,
    rules_for,
)

CONTRACT = contract_for("GOI_AGMARKNET")


def base_record(**overrides):
    """A clean, live-sourced mandi record (shape verified against the real feed)."""
    record = {
        "record_id": "AMN-baripada_apmc-brinjal-2026-09-02",
        "state": "Odisha",
        "district": "Mayurbhanja",
        "market": "Baripada APMC",
        "commodity_raw": "Brinjal",
        "crop": "CROP_BRINJAL",
        "crop_canonical": "Brinjal (Eggplant)",
        "variety": "Brinjal",
        "grade": "Medium",
        "min_price": 4000.0,
        "modal_price": 4500.0,
        "max_price": 5000.0,
        "unit": "INR/quintal",
        "price_date": "2026-09-02",
        "source": "Agmarknet",
        "source_id": "GOI_AGMARKNET",
        "source_url": "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
        "license": {"type": "GODL-India"},
        "authority": "government",
    }
    record.update(overrides)
    return attach_provenance([record], run_id="run-test", method="replay")[0]


def ctx(**overrides):
    params = dict(source_id="GOI_AGMARKNET", domain="market", contract=CONTRACT, run_id="run-test")
    params.update(overrides)
    return DQContext(**params)


def rules_hit(record, context):
    return {v.rule_id for v in classify(record, context).violations}


# ─────────────────────────── baseline ──────────────────────────────────────


def test_clean_live_record_passes():
    decision = classify(base_record(), ctx())
    assert decision.status is Status.PASS
    assert decision.passed and not decision.blocks


def test_rule_registry_covers_the_documented_families():
    ids = {r.id for r in rules_for(ctx(), scope="row")} | {r.id for r in rules_for(ctx(), scope="batch")}
    assert {
        "DQ-SCHEMA-CONFORM", "DQ-DATE-PARSE", "DQ-DATE-NOT-FUTURE", "DQ-PRICE-TRIANGLE",
        "DQ-SOURCE-URL", "DQ-LICENSE-ALLOW", "DQ-INGEST-METHOD", "DQ-PII-REDACT",
        "DQ-PII-IDENTIFIER", "DQ-BUSINESS-KEY-UNIQUE", "DQ-VOLUME-BAND", "DQ-FRESHNESS",
    } <= ids
    assert len(ids) >= 20


# ─────────────────────────── schema / dates ────────────────────────────────


def test_schema_conformance_blocks_an_unparseable_silver_date():
    hits = rules_hit(base_record(price_date="02/09/2026"), ctx())
    assert "DQ-SCHEMA-CONFORM" in hits


def test_date_parse_blocks_garbage():
    assert "DQ-DATE-PARSE" in rules_hit(base_record(price_date="not-a-date"), ctx())


def test_future_date_is_blocked():
    assert "DQ-DATE-NOT-FUTURE" in rules_hit(base_record(price_date="2099-12-31"), ctx())


def test_schema_drift_warns_on_unknown_upstream_field():
    hits = rules_hit(base_record(some_new_upstream_field=1), ctx())
    assert "DQ-SCHEMA-DRIFT" in hits


def test_refinement_artefacts_are_not_drift():
    # *_raw siblings and pii_* markers are ours, not upstream drift
    assert "DQ-SCHEMA-DRIFT" not in rules_hit(
        base_record(price_date_raw="02/09/2026", pii_redacted=True), ctx()
    )


# ─────────────────────────── domain rules ──────────────────────────────────


def test_price_triangle_blocks_min_above_modal():
    assert "DQ-PRICE-TRIANGLE" in rules_hit(base_record(min_price=9000.0), ctx())


def test_price_triangle_blocks_negative_price():
    assert "DQ-PRICE-TRIANGLE" in rules_hit(base_record(modal_price=-1), ctx())


def test_price_outlier_uses_mad_baseline():
    context = ctx(price_stats={("Baripada APMC", "Brinjal"): (4500.0, 50.0)})
    assert "DQ-PRICE-OUTLIER-MAD" in rules_hit(base_record(modal_price=45000.0), context)
    assert "DQ-PRICE-OUTLIER-MAD" not in rules_hit(base_record(), context)


def test_geo_must_exist():
    assert "DQ-GEO-EXISTS" in rules_hit(base_record(state="Atlantis"), ctx())


def test_crop_and_market_novelty_are_informational_gap_signals():
    decision = classify(base_record(crop=None, market="Some New APMC"), ctx())
    by_rule = {v.rule_id: v for v in decision.violations}
    assert by_rule["DQ-CROP-RESOLVED"].severity is Severity.INFO
    assert by_rule["DQ-MARKET-KNOWN"].severity is Severity.INFO
    assert decision.status is Status.PASS          # gap signals never park a run


def test_soil_rules_apply_only_to_the_soil_domain():
    soil_ctx = ctx(domain="soil")
    assert "DQ-SOIL-PH" in rules_hit(
        base_record(soil_test={"pH": 91, "N": 120}), soil_ctx
    )
    assert "DQ-SOIL-RANGE" in rules_hit(base_record(soil_test={"pH": 6.5, "N": 99999}), soil_ctx)
    # and are not applied to a market record
    assert "DQ-SOIL-PH" not in rules_hit(base_record(soil_test={"pH": 91}), ctx())


def test_language_consistency_warns_on_mismatch():
    record = base_record(query_original="black spots on leaves", farmer_language="ta")
    assert "DQ-LANG-CONSISTENT" in rules_hit(record, ctx())


def test_hindi_marathi_are_treated_as_equivalent_scripts():
    record = base_record(query_original="टोमॅटोच्या पानावर काळे डाग", farmer_language="hi")
    assert "DQ-LANG-CONSISTENT" not in rules_hit(record, ctx())


def test_mojibake_is_quarantined_but_devanagari_is_not():
    assert "DQ-MOJIBAKE" in rules_hit(base_record(text="tomato Ã©tÃ© leaf"), ctx())
    assert "DQ-MOJIBAKE" not in rules_hit(base_record(text="टोमॅटोच्या पानावर काळे डाग"), ctx())


# ─────────────────────────── provenance / licence / PII ────────────────────


def test_missing_source_url_blocks():
    assert "DQ-SOURCE-URL" in rules_hit(base_record(source_url=""), ctx())


def test_blocked_licence_rejects_the_record():
    decision = classify(base_record(license={"type": "all-rights-reserved"}), ctx())
    assert decision.status is Status.REJECT
    assert any(v.outcome is Outcome.REJECT for v in decision.violations)


def test_review_licence_quarantines_without_rejecting():
    decision = classify(base_record(license={"type": "institutional"}), ctx())
    assert decision.status is Status.QUARANTINE


def test_fixture_rows_are_rejected_in_a_production_run():
    record = attach_provenance([base_record()], run_id="r", method="fixture")[0]
    decision = classify(record, ctx(require_live=True))
    assert decision.status is Status.REJECT
    # …but are allowed through in an explicitly offline/demo run
    assert classify(record, ctx(require_live=False)).status is Status.PASS


def test_contact_details_warn_and_national_identifiers_reject():
    assert "DQ-PII-REDACT" in rules_hit(base_record(text="call 9876543210"), ctx())
    decision = classify(base_record(text="my aadhaar is 1234 5678 9012"), ctx())
    assert decision.status is Status.REJECT


# ─────────────────────────── batch rules + gate ────────────────────────────


def test_conflicting_business_key_quarantines_the_second_row():
    first = base_record(modal_price=4500.0)
    second = base_record(modal_price=6000.0)      # same key, different value
    report = evaluate([first, second], ctx())
    assert len(report.passed) == 1 and len(report.quarantined) == 1
    assert "DQ-BUSINESS-KEY-UNIQUE" in report.rule_counts


def test_identical_rows_are_dedupe_not_conflict():
    first = base_record()
    second = base_record()
    report = evaluate([first, second], ctx())
    assert "DQ-BUSINESS-KEY-UNIQUE" not in report.rule_counts
    assert len(report.passed) == 2                # dedupe is the loader's job, not a violation


def test_volume_band_blocks_a_collapsed_run():
    contract = CONTRACT.model_copy(deep=True)
    contract.volume.expected_rows_per_run = [100, 40000]
    report = evaluate([base_record()], ctx(contract=contract))
    assert "DQ-VOLUME-BAND" in report.rule_counts
    assert report.promoted is False


def test_freshness_warns_on_a_stale_batch():
    report = evaluate([base_record(price_date="2020-01-01")], ctx(max_age_days=30))
    assert "DQ-FRESHNESS" in report.rule_counts


def test_gate_parks_on_any_block_and_on_high_warn_rate():
    assert gate({"block_count": 0, "warn_rate": 0.0}) is True
    assert gate({"block_count": 1, "warn_rate": 0.0}) is False
    assert gate({"block_count": 0, "warn_rate": 0.5}, warn_max=0.02) is False


def test_every_non_pass_row_carries_its_violations():
    report = evaluate(
        [base_record(), base_record(min_price=9000.0, price_date="nope")], ctx()
    )
    assert len(report.passed) == 1 and len(report.quarantined) == 1
    quarantined = report.quarantined[0]
    assert quarantined["_dq_violations"]
    assert all(v["rule_id"].startswith("DQ-") for v in quarantined["_dq_violations"])
    # and the scorecard accounts for every row exactly once
    card = report.scorecard()
    assert card["rows_pass"] + card["rows_quarantine"] + card["rows_reject"] == card["rows_total"]


def test_rejected_payloads_are_never_carried_forward():
    report = evaluate([base_record(license={"type": "all-rights-reserved"})], ctx())
    assert len(report.rejected) == 1
    assert set(report.rejected[0].keys()) == {"record_hash", "_dq_status"}
    assert report.violations, "a rejection must still be explained by a violation row"


def test_a_broken_rule_degrades_to_a_warning_not_a_crash(monkeypatch):
    from pipelines import dq

    class Boom(dq.Rule):
        id = "DQ-BOOM"
        severity = Severity.WARN
        scope = "row"

        def check(self, record, context):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(dq, "RULES", dq.RULES + [Boom()])
    decision = classify(base_record(), ctx())
    assert "DQ-BOOM" in {v.rule_id for v in decision.violations}
    assert decision.status is Status.PASS


def test_persist_report_writes_violations_quarantine_and_scorecard(tmp_path):
    lake = tmp_path / "lake.duckdb"
    report = evaluate(
        [base_record(), base_record(min_price=9000.0)], ctx(run_id="run-persist")
    )
    counts = persist_report(report, lake)
    assert counts["violations"] >= 1 and counts["quarantined"] == 1

    import duckdb

    con = duckdb.connect(str(lake), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM gold.dq_violation").fetchone()[0] >= 1
        assert con.execute("SELECT count(*) FROM gold.quarantine").fetchone()[0] == 1
        row = con.execute(
            "SELECT rows_total, rows_pass, rows_quarantine, promoted FROM gold.dq_scorecard"
        ).fetchone()
        assert row[0] == 2 and row[1] == 1 and row[2] == 1 and row[3] is False
        payload = json.loads(
            con.execute("SELECT payload FROM gold.quarantine").fetchone()[0]
        )
        assert payload["record_id"].startswith("AMN-")
    finally:
        con.close()
