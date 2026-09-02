"""Tests for Track 8: crop planning."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.crop_plan import crop_plan, crops_to_sow, sow_risk  # noqa: E402
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    yield


def test_tomato_plan_has_seasons_and_timeline():
    plan = crop_plan("tomato")
    assert plan is not None
    assert plan.crop == "Tomato"
    assert plan.seasons
    assert plan.timeline
    assert plan.sow_window and plan.harvest_window


def test_plan_unknown_crop_returns_none():
    assert crop_plan("NoSuchCropXYZ") is None


def test_plan_indic_alias():
    plan = crop_plan("टोमॅटो")
    assert plan is not None and plan.crop_id == "CROP_TOMATO"


def test_state_override_applied():
    # Wheat sowing in Punjab is overridden to Oct-Nov (early to escape heat).
    plan = crop_plan("wheat", state="Punjab")
    assert plan is not None
    assert 10 in plan.sow_window  # October


def test_crops_to_sow_june_kharif():
    crops = crops_to_sow(6)  # June
    ids = {c["crop_id"] for c in crops}
    assert "CROP_RICE" in ids or any(c["crop"] == "Rice" for c in crops)
    assert all(6 in c["sow_months"] for c in crops)


def test_sow_risk_labels():
    plan = crop_plan("tomato")
    # Tomato (rabi/zaid-ish windows) — pick a month we know is off-window.
    if plan.sow_window:
        on = plan.sow_window[0]
        assert sow_risk(plan, on) == "on_window"
        off = next(m for m in range(1, 13) if m not in plan.sow_window)
        assert sow_risk(plan, off) in ("off_window", "near_window")
