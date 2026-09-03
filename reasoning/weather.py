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
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR

from domain.seed_data import (
    CROP_WATER_NEED_MM_WEEK,
    RAINFALL_TEXT_PROXY,
    WEATHER_RISK_THRESHOLDS,
)

log = logging.getLogger("agrilake.weather")

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
    # Honest provenance: "bulletin" = IMD bulletin, "live" = Open-Meteo
    # observation, "synthetic" = seasonal baseline (NOT an observation).
    data_source: str = "bulletin"
    is_live: bool = False
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
            "data_source": self.data_source,
            "is_live": self.is_live,
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
        try:
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
        except Exception as exc:  # noqa: BLE001 - corrupt/missing lake → fixture
            log.info("bulletin load failed (%s); using fixture.", type(exc).__name__)
    fixture = FIXTURES_DIR / "imd_agromet_advisory.json"
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8"))
    return []


def _offline() -> bool:
    return os.environ.get("AGRILAKE_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def fetch_live_weather(lat: float, lon: float, timeout: float = 3.5) -> dict[str, Any] | None:
    """Fetch real-time weather & forecast from Open-Meteo for coordinates.

    Returns None when offline, unreachable, or malformed — never raises.
    Honours AGRILAKE_OFFLINE so air-gapped runs never touch the network.
    """
    if _offline():
        return None
    import requests
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Asia%2FKolkata"
        )
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            curr = data.get("current", {})
            daily = data.get("daily", {})
            t_max_list = daily.get("temperature_2m_max") or []
            t_min_list = daily.get("temperature_2m_min") or []
            temp_max = round(float(t_max_list[0]), 1) if t_max_list else round(float(curr.get("temperature_2m", 30)), 1)
            temp_min = round(float(t_min_list[0]), 1) if t_min_list else round(float(curr.get("temperature_2m", 22)), 1)
            humidity = round(float(curr.get("relative_humidity_2m", 65)), 1)
            wind = round(float(curr.get("wind_speed_10m", 10)), 1)
            p_list = daily.get("precipitation_sum") or []
            precip = round(float(p_list[0]), 1) if p_list else round(float(curr.get("precipitation", 0.0)), 1)
            if precip > 15:
                rain_text = f"Moderate to heavy rain ({precip} mm)"
            elif precip > 2:
                rain_text = f"Light rain/showers ({precip} mm)"
            else:
                rain_text = "Dry conditions / no significant rainfall"
            return {
                "temp_max": temp_max,
                "temp_min": temp_min,
                "humidity": humidity,
                "wind": wind,
                "rainfall": rain_text,
                "precipitation_mm": precip,
            }
        log.warning("Open-Meteo HTTP %s for (%s, %s)", resp.status_code, lat, lon)
    except Exception as exc:  # noqa: BLE001 - weather must degrade, never crash
        log.info("Open-Meteo unreachable (%s); falling back.", type(exc).__name__)
    return None


def resolve_district_coords(
    district: str, lake: Path | None = None
) -> tuple[str | None, str, float | None, float | None, str | None]:
    """Return (state, district_canonical, lat, lon, agroclimatic_zone).

    Lake lookup is exact-first (no fuzzy LIKE): a LIKE ``%pur%`` match once
    resolved "Nashik" to the wrong district. The hosted geocoder is a
    last resort and is skipped entirely in offline mode.
    """
    from pipelines.storage import get_read_connection
    d_clean = district.strip().lower()
    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        try:
            con = get_read_connection(lake)
            rows = con.execute(
                "SELECT state_name, district_name, latitude, longitude, agroclimatic_zone "
                "FROM gold.dim_geography WHERE district_name IS NOT NULL AND "
                "LOWER(district_name) = ? LIMIT 1",
                [d_clean],
            ).fetchall()
            if not rows:
                # Explicit contains-match only when the query names a full district
                # (e.g. "North 24 Parganas" typed partially) — still ordered to
                # prefer coordinate-bearing rows.
                rows = con.execute(
                    "SELECT state_name, district_name, latitude, longitude, agroclimatic_zone "
                    "FROM gold.dim_geography WHERE district_name IS NOT NULL AND ("
                    "LOWER(district_name) LIKE ? OR ? LIKE '%' || LOWER(district_name) || '%') "
                    "ORDER BY (latitude IS NOT NULL) DESC LIMIT 1",
                    [f"%{d_clean}%", d_clean],
                ).fetchall()
            if rows:
                st, dist, lat, lon, zone = rows[0]
                if lat is not None and lon is not None:
                    return st, dist, float(lat), float(lon), zone
                return st, dist, None, None, zone
        except Exception as exc:  # noqa: BLE001
            log.info("district lookup failed (%s)", type(exc).__name__)

    if _offline():
        return None, district.strip().title() or district, None, None, None

    # Open-Meteo geocoding search for Indian districts if coords missing from table
    import requests
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": district, "count": 1, "country_code": "IN", "language": "en"},
            timeout=2.5,
        )
        if resp.status_code == 200:
            res = resp.json().get("results")
            if res and len(res) > 0:
                item = res[0]
                return item.get("admin1"), item.get("name") or district, float(item["latitude"]), float(item["longitude"]), None
        else:
            log.warning("geocoding HTTP %s for %r", resp.status_code, district)
    except Exception as exc:  # noqa: BLE001
        log.info("geocoding unreachable (%s)", type(exc).__name__)

    return None, district.title(), None, None, None


def dynamic_crop_advisories(
    crop_canonical: str | None, crop_id: str | None, weather: dict[str, Any]
) -> list[CropWeatherNote]:
    """Synthesize agronomic risk and action notes based on live meteorological metrics."""
    notes: list[CropWeatherNote] = []
    if not crop_canonical:
        return notes
    hum = weather.get("humidity", 50)
    tmax = weather.get("temp_max", 30)
    tmin = weather.get("temp_min", 20)
    wind = weather.get("wind", 10)

    # Fungal disease trigger
    if hum >= 75:
        notes.append(
            CropWeatherNote(
                crop=crop_canonical,
                crop_id=crop_id,
                growth_stage="vegetative / flowering",
                risk="High relative humidity promotes fungal blights, mildew and leaf spots.",
                action="Avoid overhead irrigation; ensure field drainage; inspect lower leaf canopy for lesions.",
            )
        )
    # Heat stress trigger
    if tmax >= 38:
        notes.append(
            CropWeatherNote(
                crop=crop_canonical,
                crop_id=crop_id,
                growth_stage="flowering / fruit development",
                risk="High temperature stress may cause flower/fruit drop or pollen desiccation.",
                action="Provide light and frequent irrigation during early morning/evening; avoid foliar sprays during peak heat.",
            )
        )
    # Cold/frost trigger
    if tmin <= 8:
        notes.append(
            CropWeatherNote(
                crop=crop_canonical,
                crop_id=crop_id,
                growth_stage="early vegetative",
                risk="Low minimum temperature and cold/frost hazard.",
                action="Apply evening irrigation or create protective shelter/smoke on field borders to elevate microclimate temperatures.",
            )
        )
    # High wind trigger
    if wind >= 25:
        notes.append(
            CropWeatherNote(
                crop=crop_canonical,
                crop_id=crop_id,
                growth_stage="tall standing / fruit bearing",
                risk="Strong wind speeds may cause crop lodging or floral damage.",
                action="Postpone high-pressure spraying; provide staking support for horticultural crops.",
            )
        )
    if not notes:
        notes.append(
            CropWeatherNote(
                crop=crop_canonical,
                crop_id=crop_id,
                growth_stage="active growth",
                risk="Favorable seasonal weather; normal disease pressure.",
                action="Carry out routine field intercultural operations, weeding, and nutrient top-dressing as planned.",
            )
        )
    return notes


def agromet_advisory(
    district: str,
    bulletins: list[dict[str, Any]] | None = None,
    *,
    crop: str | None = None,
    lake: Path | None = None,
) -> WeatherAdvisory | None:
    """Build a weather advisory for a district (optionally a single crop)."""
    from datetime import datetime, timezone
    from pipelines.entities import resolve_crop

    explicit_bulletins = bulletins is not None
    active_bulletins = bulletins if explicit_bulletins else load_bulletins(lake)

    matches = [
        b for b in active_bulletins
        if str(b.get("district") or "").strip().lower() == district.strip().lower()
    ]
    if not matches:
        matches = [
            b for b in active_bulletins
            if district.strip().lower() in str(b.get("district") or "").strip().lower()
            or district.strip().lower() in str(b.get("state") or "").strip().lower()
        ]

    # If explicit bulletins passed (e.g. tests), respect test contract:
    if not matches and explicit_bulletins:
        return None

    if matches:
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
            data_source="bulletin",
            is_live=False,
            evidence={
                "source": b.get("source", "IMD Agromet Advisory Service"),
                "authority": b.get("authority", "government"),
                "license": {"type": "GODL-India"},
                "source_url": b.get("source_url"),
            },
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

    # Dynamic all-India real-time synthesis
    st, dist_canon, lat, lon, zone = resolve_district_coords(district, lake)
    if not st and lat is None and lon is None:
        return None

    now_iso = datetime.now(timezone.utc).date().isoformat()
    weather = None
    is_live = False
    if lat is not None and lon is not None:
        weather = fetch_live_weather(lat, lon)
        is_live = weather is not None

    if not weather:
        # Seasonal baseline — clearly NOT an observation. It keeps the
        # assistant usable offline, but the payload says so (data_source=
        # "synthetic", is_live=False) so it can never be mistaken for a
        # live IMD/Open-Meteo reading downstream.
        m = datetime.now().month
        if 6 <= m <= 9:  # Monsoon
            weather = {"temp_max": 31.0, "temp_min": 24.0, "humidity": 80.0, "wind": 14.0, "rainfall": "Scattered monsoon showers", "precipitation_mm": 12.0}
        elif 10 <= m <= 11:  # Post-monsoon
            weather = {"temp_max": 30.0, "temp_min": 20.0, "humidity": 65.0, "wind": 8.0, "rainfall": "Clear skies with light showers", "precipitation_mm": 2.0}
        elif 12 <= m or m <= 2:  # Winter
            weather = {"temp_max": 25.0, "temp_min": 12.0, "humidity": 55.0, "wind": 7.0, "rainfall": "Dry weather", "precipitation_mm": 0.0}
        else:  # Summer
            weather = {"temp_max": 39.0, "temp_min": 26.0, "humidity": 40.0, "wind": 15.0, "rainfall": "Dry hot conditions", "precipitation_mm": 0.0}

    flags = weather_flags(weather)
    if is_live:
        evidence = {
            "source": "Open-Meteo live observation (geocoded via IMD/LGD)",
            "authority": "research",
            "license": {"type": "CC-BY-4.0"},
            "source_url": "https://open-meteo.com",
        }
        data_source = "live"
    else:
        evidence = {
            "source": "Seasonal climatology baseline for India (synthetic — not a live observation)",
            "authority": "research",
            "license": {"type": "CC-BY-4.0"},
            "source_url": None,
        }
        data_source = "synthetic"
    adv = WeatherAdvisory(
        state=st or "India",
        district=dist_canon,
        valid_from=now_iso,
        valid_to=now_iso,
        weather=weather,
        flags=flags,
        data_source=data_source,
        is_live=is_live,
        evidence=evidence,
    )
    if not is_live:
        adv.notes.append(
            "Synthetic baseline: no IMD bulletin or live observation was "
            "available — treat values as climatology, not today's weather."
        )

    resolved_c = resolve_crop(crop) if crop else None
    c_canon = resolved_c["canonical_en"] if resolved_c else (crop.title() if crop else None)
    c_id = resolved_c["crop_id"] if resolved_c else None

    if c_canon:
        adv.crops.extend(dynamic_crop_advisories(c_canon, c_id, weather))
        water = crop_water_flag(c_id, weather.get("rainfall"))
        if water:
            adv.notes.append(f"{c_canon}: {water}")

    for f in flags:
        adv.notes.append(f"[{f.flag} ({f.severity})] {f.note}")

    return adv

