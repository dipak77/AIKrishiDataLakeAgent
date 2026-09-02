"""Weather advisory (Track 7).

Classifies IMD agromet bulletin weather into risk flags (heat, frost, humidity,
wind, waterlogging, dry spell) and ties each crop advisory to a resolved crop +
growth stage. Optionally compares rainfall against the crop's peak water need
to flag a deficit/excess — a first-order stand-in for the blueprint's
"environment" input in the diagnosis chain (symptom → candidate → environment
→ stage).

All flags are descriptive advisories with their source + threshold recorded —
never forecasts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR

from domain.seed_data import (
    CROP_WATER_NEED_MM_WEEK,
    RAINFALL_TEXT_PROXY,
    WEATHER_RISK_THRESHOLDS,
)

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"


@dataclass
class WeatherFlag:
    flag: str
    severity: str
    metric: str
    value: float
    threshold: float
    note: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class CropWeatherNote:
    crop: str
    crop_id: str | None
    growth_stage: str | None
    risk: str | None
    action: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class WeatherAdvisory:
    state: str | None
    district: str | None
    valid_from: str | None
    valid_to: str | None
    weather: dict[str, Any] = field(default_factory=dict)
    flags: list[WeatherFlag] = field(default_factory=list)
    crops: list[CropWeatherNote] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(
        default_factory=lambda: {
            "source": "IMD Agromet Advisory Service",
            "authority": "government",
            "license": {"type": "GODL-India"},
        }
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "district": self.district,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "weather": self.weather,
            "flags": [f.as_dict() for f in self.flags],
            "crops": [c.as_dict() for c in self.crops],
            "notes": self.notes,
            "evidence": self.evidence,
        }


def rainfall_mm(text: str | None) -> float:
    """Approximate daily rainfall (mm) from an IMD text description."""
    if not text:
        return 0.0
    t = text.lower()
    for keyword, mm in RAINFALL_TEXT_PROXY:
        if keyword in t:
            return mm
    return 0.0


def _num(weather: dict[str, Any], key: str) -> float | None:
    v = weather.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def weather_flags(weather: dict[str, Any]) -> list[WeatherFlag]:
    """Apply risk thresholds to a weather dict (temp_max/temp_min/humidity/wind/rainfall)."""
    flags: list[WeatherFlag] = []
    w = dict(weather)
    w["rainfall_mm"] = rainfall_mm(w.get("rainfall"))
    for rule in WEATHER_RISK_THRESHOLDS:
        value = _num(w, rule["metric"])
        if value is None:
            continue
        hit = value >= rule["threshold"] if rule["operator"] == ">=" else value <= rule["threshold"]
        if hit:
            flags.append(
                WeatherFlag(
                    flag=rule["flag"],
                    severity=rule["severity"],
                    metric=rule["metric"],
                    value=value,
                    threshold=rule["threshold"],
                    note=rule["note"],
                )
            )
    return flags


def crop_water_flag(crop_id: str | None, rainfall_text: str | None) -> str | None:
    """Compare rainfall (mm) against the crop's peak weekly need → deficit/excess note."""
    need = next((r for r in CROP_WATER_NEED_MM_WEEK if r["crop_id"] == crop_id), None)
    if not need:
        return None
    mm = rainfall_mm(rainfall_text)
    daily = mm * 7.0  # crude weekly estimate
    if daily < need["mm_week"] * 0.5:
        return (
            f"Rainfall (~{mm:g} mm/day ≈ {daily:g} mm/wk) well below peak need "
            f"({need['mm_week']:g} mm/wk) — arrange irrigation."
        )
    if daily > need["mm_week"] * 1.5:
        return (
            f"Rainfall (~{mm:g} mm/day) well above peak need "
            f"({need['mm_week']:g} mm/wk) — ensure drainage to avoid waterlogging."
        )
    return None


def load_bulletins(lake: Path | None = None) -> list[dict[str, Any]]:
    """Read `fact_agromet_advisory` from the lake; fall back to the fixture."""
    from pipelines.storage import FIXTURES_DIR, get_read_connection

    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        con = get_read_connection(lake)
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='gold'"
            ).fetchall()
        }
        if "fact_agromet_advisory" in tables:
            cols = [
                r[1]
                for r in con.execute("PRAGMA table_info('gold.fact_agromet_advisory')").fetchall()
            ]
            select = ",".join(f'"{c}"' for c in cols)
            return [
                dict(zip(cols, row))
                for row in con.execute(f"SELECT {select} FROM gold.fact_agromet_advisory").fetchall()
            ]
    fixture = FIXTURES_DIR / "imd_agromet_advisory.json"
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8"))
    return []


def agromet_advisory(
    district: str,
    bulletins: list[dict[str, Any]] | None = None,
    *,
    crop: str | None = None,
    lake: Path | None = None,
) -> WeatherAdvisory | None:
    """Build a weather advisory for a district (optionally a single crop)."""
    from pipelines.entities import resolve_crop

    bulletins = bulletins if bulletins is not None else load_bulletins(lake)
    matches = [
        b for b in bulletins
        if str(b.get("district") or "").strip().lower() == district.strip().lower()
    ]
    if not matches:
        # try state-level or partial district match
        matches = [
            b for b in bulletins
            if district.strip().lower() in str(b.get("district") or "").strip().lower()
            or district.strip().lower() in str(b.get("state") or "").strip().lower()
        ]
    if not matches:
        return None
    b = matches[0]
    weather = b.get("weather", {}) or {}
    flags = weather_flags(weather)
    adv = WeatherAdvisory(
        state=b.get("state"),
        district=b.get("district"),
        valid_from=b.get("valid_from"),
        valid_to=b.get("valid_to"),
        weather=weather,
        flags=flags,
        evidence={"source": b.get("source", "IMD Agromet Advisory Service"),
                  "authority": b.get("authority", "government"),
                  "license": {"type": "GODL-India"},
                  "source_url": b.get("source_url")},
    )
    for c in b.get("crop_advisories", []):
        resolved = resolve_crop(c.get("crop"))
        canon = (resolved or {}).get("canonical_en") or c.get("crop_canonical") or c.get("crop")
        if crop and (not canon or str(canon).lower() != crop.lower()):
            continue
        note = CropWeatherNote(
            crop=canon,
            crop_id=(resolved or {}).get("crop_id"),
            growth_stage=c.get("growth_stage"),
            risk=c.get("risk"),
            action=c.get("action"),
        )
        adv.crops.append(note)
        water = crop_water_flag(note.crop_id, weather.get("rainfall"))
        if water:
            adv.notes.append(f"{canon}: {water}")
    for f in flags:
        adv.notes.append(f"[{f.flag} ({f.severity})] {f.note}")
    return adv
