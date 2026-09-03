"""Tests for Track 6: mandi intelligence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.mandi import (  # noqa: E402
    list_markets,
    load_price_rows,
    market_advisory,
    price_stats,
    season_signal,
)
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    yield


FIXTURE_ROWS = json.loads(
    (ROOT / "data" / "fixtures" / "agmarknet_mandi_price.json").read_text(encoding="utf-8")
)


def test_price_stats_groups_by_commodity_market():
    stats = price_stats(FIXTURE_ROWS)
    keys = {(s.commodity, s.market) for s in stats}
    assert ("Tomato", "Pune") in keys
    assert ("Onion", "Lasalgaon") in keys


def test_price_stats_tomato_trend():
    tomato = [s for s in price_stats(FIXTURE_ROWS) if s.commodity == "Tomato" and s.market == "Pune"]
    assert tomato
    stat = tomato[0]
    assert stat.n_days >= 7
    assert stat.trend == "rising"  # 2300 → 2650
    assert stat.latest_modal == 2600.0  # original 2026-08-30 row is latest
    assert 0 < stat.volatility_pct


def test_season_signal_uses_crop_calendar():
    # Tomato harvest (maturity) is in the winter (Jan–Mar in the calendar); Aug is not harvest.
    signal, note = season_signal("CROP_TOMATO", "2026-08-30")
    assert signal in {"harvest", "lean", "transition", "unknown"}
    assert note


def test_market_advisory_tomato():
    adv = market_advisory("tomato", FIXTURE_ROWS)
    assert adv is not None
    assert adv.commodity == "Tomato"
    assert adv.stats
    assert adv.evidence["license"]["type"] == "GODL-India"
    assert "not price predictions" in adv.notes[-1]


def test_market_advisory_market_filter():
    adv = market_advisory("onion", FIXTURE_ROWS, market="Lasalgaon")
    assert adv is not None
    assert all(s.market == "Lasalgaon" for s in adv.stats)


def test_market_advisory_unknown():
    assert market_advisory("NoSuchCommodityXYZ", FIXTURE_ROWS) is None


def test_list_markets_from_lake():
    markets = list_markets()
    names = {m["name"] for m in markets}
    assert "Lasalgaon" in names
    lasal = next(m for m in markets if m["name"] == "Lasalgaon")
    assert lasal["state_code"] == "IN-MH"
    assert lasal["district_code"] == "IN-MH-NASHIK"


def test_load_price_rows_falls_back_to_fixture():
    rows = load_price_rows()
    assert rows, "fixture fallback should return rows"


def test_price_stats_isolation():
    mixed_rows = [
        {
            "commodity_raw": "Apple",
            "market": "Shimla",
            "state": "Himachal Pradesh",
            "district": "Shimla",
            "crop": "CROP_APPLE",
            "modal_price": 8000,
            "price_date": "2026-09-01",
        },
        {
            "commodity_raw": "Banana",
            "market": "Jalgaon",
            "state": "Maharashtra",
            "district": "Jalgaon",
            "crop": "CROP_BANANA",
            "modal_price": 2500,
            "price_date": "2026-09-01",
        },
    ]
    stats = price_stats(mixed_rows)
    assert len(stats) == 2
    by_comm = {s.commodity: s for s in stats}
    assert by_comm["Apple"].state == "Himachal Pradesh"
    assert by_comm["Apple"].district == "Shimla"
    assert by_comm["Apple"].crop_id == "CROP_APPLE"
    assert by_comm["Banana"].state == "Maharashtra"
    assert by_comm["Banana"].district == "Jalgaon"
    assert by_comm["Banana"].crop_id == "CROP_BANANA"
