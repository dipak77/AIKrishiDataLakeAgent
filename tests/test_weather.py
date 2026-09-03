"""Tests for Track 7: weather advisory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.weather import (  # noqa: E402
    agromet_advisory,
    crop_water_flag,
    rainfall_mm,
    weather_flags,
)

FIXTURE = json.loads(
    (ROOT / "data" / "fixtures" / "imd_agromet_advisory.json").read_text(encoding="utf-8")
)


def test_rainfall_mm_proxy():
    assert rainfall_mm("Light to moderate rain expected") == 25.0  # 'moderate' wins first match? order matters
    assert rainfall_mm("Scattered showers") == 8.0
    assert rainfall_mm("no rain") == 0.0
    assert rainfall_mm(None) == 0.0


def test_weather_flags_heat_and_humidity():
    flags = weather_flags({"temp_max": 38, "temp_min": 22, "humidity": 85, "wind": 10, "rainfall": "light rain"})
    names = {f.flag for f in flags}
    assert "heat_stress" in names
    assert "high_humidity" in names


def test_weather_flags_frost():
    flags = weather_flags({"temp_min": 2})
    assert any(f.flag == "frost_risk" for f in flags)


def test_weather_flags_waterlogging():
    flags = weather_flags({"rainfall": "heavy rain"})
    assert any(f.flag == "waterlogging" for f in flags)


def test_crop_water_flag_deficit():
    note = crop_water_flag("CROP_RICE", "dry")
    assert note and "irrigation" in note
    assert crop_water_flag("CROP_NO_SUCH", "dry") is None


def test_agromet_advisory_pune():
    adv = agromet_advisory("Pune", FIXTURE)
    assert adv is not None
    assert adv.state == "Maharashtra"
    assert {c.crop for c in adv.crops} == {"Soybean", "Tomato"}
    assert adv.evidence["license"]["type"] == "GODL-India"


def test_agromet_advisory_crop_filter():
    adv = agromet_advisory("Pune", FIXTURE, crop="tomato")
    assert adv is not None
    assert [c.crop for c in adv.crops] == ["Tomato"]


def test_agromet_advisory_unknown_district():
    assert agromet_advisory("NoSuchDistrict", FIXTURE) is None


def test_agromet_advisory_dynamic_all_india():
    # Calling without explicit fixture triggers dynamic resolution
    adv = agromet_advisory("Nashik", crop="tomato")
    assert adv is not None
    assert "Nashik" in adv.district
    assert adv.weather
    assert "temp_max" in adv.weather
    assert adv.evidence["source"]
    assert any("Tomato" in c.crop for c in adv.crops)
