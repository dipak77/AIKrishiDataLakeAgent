"""Tests for the frontier-only model-selection policy (Phase F: pipelines/models.py).

The policy is the code enforcement of the standing instruction: upper-boundary
models only, cross-vendor quorum for ontology writes, fail closed rather than
degrade, and every call audited with a cost.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.models import (  # noqa: E402
    DEFAULT_ALLOWLIST,
    BudgetExceeded,
    ModelPolicy,
    ModelTierViolation,
    ModelUnavailable,
    QuorumNotMet,
    persist_audit,
)


# ─────────────────────────── frontier-only selection ───────────────────────


def test_defaults_are_the_frontier_pair():
    policy = ModelPolicy()
    primary = policy.select("gap_analysis")
    secondary = policy.select("gap_analysis", role="secondary")
    assert primary.model_id == "grok-4.6"
    assert secondary.model_id == "qwen3.8-max"
    assert primary.tier == "T1"
    assert primary.vendor != secondary.vendor          # genuinely independent


def test_non_frontier_model_is_refused_for_authoring():
    policy = ModelPolicy()
    with pytest.raises(ModelTierViolation):
        policy.select("ontology_proposal", model_id="qwen3-8b-local")


def test_allowlist_is_configurable_but_still_enforced():
    policy = ModelPolicy.from_env({"AGRI_MODEL_ALLOWLIST": "grok-4.6,claude-opus-5"})
    assert policy.select("gap_analysis").model_id == "grok-4.6"
    with pytest.raises(ModelTierViolation):
        policy.select("gap_analysis", model_id="qwen3.8-max")


def test_fail_closed_when_no_allowlisted_model_is_reachable():
    policy = ModelPolicy(available=frozenset())
    with pytest.raises(ModelUnavailable):
        policy.select("compaction")


def test_falls_back_to_another_frontier_model_not_a_weaker_one():
    policy = ModelPolicy(available=frozenset({"claude-opus-5"}))
    assert policy.select("compaction").model_id == "claude-opus-5"


def test_deterministic_stage_may_not_use_any_llm():
    from pipelines.models import TIER_OF_STAGE

    TIER_OF_STAGE["dedupe"] = "T3"
    try:
        with pytest.raises(ModelTierViolation):
            ModelPolicy().select("dedupe")
    finally:
        TIER_OF_STAGE.pop("dedupe")


# ─────────────────────────── quorum ────────────────────────────────────────


def test_cross_vendor_quorum_accepts_agreement():
    policy = ModelPolicy()
    agreed = policy.agree_or_raise([("grok-4.6", "CROP_RIDGE_GOURD"), ("qwen3.8-max", "CROP_RIDGE_GOURD")])
    assert agreed == "CROP_RIDGE_GOURD"


def test_quorum_rejects_disagreement():
    policy = ModelPolicy()
    with pytest.raises(QuorumNotMet):
        policy.agree_or_raise([("grok-4.6", "CROP_RIDGE_GOURD"), ("qwen3.8-max", "CROP_TORAI")])


def test_quorum_rejects_same_vendor_double_vote():
    # two votes from one vendor are not independent evidence, even if both are
    # frontier models and both agree
    policy = ModelPolicy(allowlist=("grok-4.6", "grok-4.5", "qwen3.8-max"))
    with pytest.raises(QuorumNotMet):
        policy.agree_or_raise([("grok-4.6", "X"), ("grok-4.5", "X")])


def test_quorum_ignores_votes_from_non_frontier_models():
    policy = ModelPolicy()
    with pytest.raises(ModelTierViolation):
        policy.agree_or_raise([("grok-4.6", "X"), ("phi-4", "X")])


def test_pair_selection_is_cross_vendor_even_when_defaults_collide():
    policy = ModelPolicy(
        allowlist=("grok-4.6", "grok-4.5", "qwen3.8-max"),
        primary="grok-4.6", secondary="grok-4.5",
    )
    primary, secondary = policy.pair("ontology_proposal")
    assert primary.model_id == "grok-4.6"
    assert secondary.model_id == "qwen3.8-max"
    assert primary.vendor != secondary.vendor


# ─────────────────────────── budget + audit ────────────────────────────────


def test_budget_caps_are_enforced():
    policy = ModelPolicy(budget_run_usd=1.0, budget_day_usd=10.0)
    policy.charge(0.6)
    with pytest.raises(BudgetExceeded):
        policy.charge(0.5)
    assert policy.spend_run_usd == 0.6                  # failed charge is not applied


def test_daily_budget_is_tracked_separately():
    policy = ModelPolicy(budget_run_usd=100.0, budget_day_usd=1.0)
    policy.charge(0.9)
    with pytest.raises(BudgetExceeded):
        policy.charge(0.2)


def test_negative_cost_is_rejected():
    with pytest.raises(ValueError):
        ModelPolicy().charge(-1.0)


def test_audit_row_carries_model_tier_cost_and_prompt_hash():
    policy = ModelPolicy()
    selection = policy.select("gap_analysis")
    row = policy.audit(
        selection=selection, run_id="run-1", task="alias-gap triage",
        tokens_in=1200, tokens_out=300, cost_usd=0.0042, latency_ms=850,
        prompt="Which canonical crop does 'Ridgeguard(Tori)' refer to?",
    )
    assert row["model_id"] == "grok-4.6" and row["tier"] == "T1"
    assert row["vendor"] == "xai"
    assert row["cost_usd"] == 0.0042
    assert len(row["prompt_hash"]) == 16
    assert policy.spend_run_usd == 0.0042
    assert policy.audit_trail == [row]


def test_failed_call_is_audited_without_charging():
    policy = ModelPolicy()
    selection = policy.select("compaction")
    row = policy.audit(selection=selection, run_id="r", task="compact", status="error", cost_usd=0.0)
    assert row["status"] == "error"
    assert policy.spend_run_usd == 0.0


def test_persist_audit_writes_to_the_lake(tmp_path):
    import duckdb

    policy = ModelPolicy()
    selection = policy.select("gap_analysis")
    row = policy.audit(selection=selection, run_id="run-1", task="t", cost_usd=0.01)
    lake = tmp_path / "lake.duckdb"
    assert persist_audit([row], lake) == 1
    con = duckdb.connect(str(lake), read_only=True)
    try:
        rows = con.execute("SELECT model_id, tier, cost_usd, policy_version FROM gold.model_call_audit").fetchall()
        assert rows == [("grok-4.6", "T1", 0.01, policy.policy_version)]
    finally:
        con.close()


def test_env_configuration_round_trip():
    policy = ModelPolicy.from_env({
        "AGRI_MODEL_PRIMARY": "qwen3.8-max",
        "AGRI_MODEL_SECONDARY": "grok-4.6",
        "AGRI_MODEL_QUORUM": "2",
        "AGRI_MODEL_BUDGET_RUN_USD": "2.5",
        "AGRI_MODEL_BUDGET_DAY_USD": "25",
    })
    assert policy.select("gap_analysis").model_id == "qwen3.8-max"
    assert policy.budget_run_usd == 2.5 and policy.budget_day_usd == 25.0


def test_every_allowlisted_model_has_a_known_vendor():
    from pipelines.models import VENDORS

    assert set(DEFAULT_ALLOWLIST) <= set(VENDORS)
