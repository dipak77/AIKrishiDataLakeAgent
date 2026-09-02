"""Fertilizer advisory engine (Track 5).

Pure DuckDB + seed data — no LLM. Turns a crop + (optional) soil test into a
versioned, evidence-separated fertilizer plan:

    crop × stage × target yield  →  nutrient requirement (kg N/P2O5/K2O per ha)
        → soil-test adjustment (low/optimal/high, pH/EC, micronutrients)
        → product mix (Urea / DAP / MOP, DAP-first so the N credit is correct)
        → per-timing application schedule (basal / vegetative / reproductive)

The result keeps **observation** (soil-test readings + flags) separate from
**recommendation** (what to apply) separate from **evidence** (source, license,
authority) — per the blueprint's non-negotiables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from domain.models import FertilizerAdvisoryRecord, SoilTestInput
from domain.seed_data import (
    CROP_NUTRIENT_REQUIREMENT,
    FERTILIZER_ADVISORY_VERSION,
    SOIL_TEST_INTERPRETATION,
)

ADVISORY_SOURCE = "ICAR/SAU package of practices (representative blanket recommendations)"
ADVISORY_AUTHORITY = "government_extension"
ADVISORY_LICENSE = {"type": "GODL-India"}

# Stage id → application timing bucket.
_STAGE_TO_TIMING = {
    "nursery": "basal",
    "sowing": "basal",
    "germination": "basal",
    "transplanting": "basal",
    "establishment": "basal",
    "tillering": "vegetative",
    "vegetative": "vegetative",
    "flowering": "reproductive",
    "fruiting": "reproductive",
    "fruit_set": "reproductive",
    "pod_set": "reproductive",
    "boll_set": "reproductive",
    "grain_fill": "reproductive",
    "maturity": "reproductive",
    "harvest": "reproductive",
    "post_harvest": "reproductive",
}

# Nutrient form → product preference order (first that supplies the form).
_PRODUCT_PREFERENCE: dict[str, list[str]] = {
    "N": ["FERT_UREA"],
    "P2O5": ["FERT_DAP", "FERT_SSP"],
    "K2O": ["FERT_MOP", "FERT_SOP"],
}

_SOIL_STATUS_LABEL = {
    "available_n": "N",
    "available_p": "P2O5",
    "available_k": "K2O",
}


@dataclass
class SoilFlag:
    parameter: str
    label: str
    value: float
    unit: str
    status: str          # low | optimal | high | acidic | neutral | alkaline | normal | saline | critical | deficient | sufficient
    note: str | None


@dataclass
class ProductApplication:
    timing: str
    nutrient_form: str
    kg_ha: float
    product_id: str
    product_name: str
    product_kg_ha: float
    share_of_season: float


@dataclass
class FertilizerAdvisory:
    crop_id: str
    crop: str
    growth_stage: str | None
    target_yield_tha: float
    version: str
    soil_flags: list[SoilFlag] = field(default_factory=list)
    plan: list[ProductApplication] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(
        default_factory=lambda: {
            "source": ADVISORY_SOURCE,
            "authority": ADVISORY_AUTHORITY,
            "license": ADVISORY_LICENSE,
            "version": FERTILIZER_ADVISORY_VERSION,
        }
    )
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "crop_id": self.crop_id,
            "crop": self.crop,
            "growth_stage": self.growth_stage,
            "target_yield_tha": self.target_yield_tha,
            "version": self.version,
            "soil_flags": [f.__dict__ for f in self.soil_flags],
            "plan": [p.__dict__ for p in self.plan],
            "observations": self.observations,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
            "notes": self.notes,
        }

    def to_records(self) -> list[FertilizerAdvisoryRecord]:
        """Flatten the plan into versioned `fertilizer_advisory@<version>` rows."""
        return [
            FertilizerAdvisoryRecord(
                advisory_id=f"{self.version}:{self.crop_id}:{p.nutrient_form}:{p.timing}",
                version=self.version,
                crop_id=self.crop_id,
                crop=self.crop,
                growth_stage=self.growth_stage,
                target_yield_tha=self.target_yield_tha,
                nutrient_form=p.nutrient_form,
                recommended_kg_ha=p.kg_ha,
                timing=p.timing,
                product_id=p.product_id,
                product_name=p.product_name,
                product_kg_ha=p.product_kg_ha,
                soil_status="; ".join(f"{f.label}={f.status}" for f in self.soil_flags) or "not tested",
                source=self.evidence["source"],
                authority=self.evidence["authority"],
            )
            for p in self.plan
        ]


def _get_requirement(crop_id: str) -> dict[str, Any] | None:
    for row in CROP_NUTRIENT_REQUIREMENT:
        if row["crop_id"] == crop_id:
            return row
    return None


def timing_for_stage(growth_stage: str | None) -> str | None:
    """Map a growth-stage id/name to an application timing bucket."""
    if not growth_stage:
        return None
    key = str(growth_stage).strip().lower().replace(" ", "_")
    return _STAGE_TO_TIMING.get(key) or _STAGE_TO_TIMING.get(key.split("_")[0])


def assess_soil(soil: SoilTestInput | dict[str, Any] | None) -> list[SoilFlag]:
    """Classify a soil test against the interpretation thresholds."""
    if soil is None:
        return []
    data = soil.model_dump() if isinstance(soil, SoilTestInput) else dict(soil)
    flags: list[SoilFlag] = []
    for rule in SOIL_TEST_INTERPRETATION:
        value = data.get(rule["parameter"])
        if value in (None, ""):
            continue
        value = float(value)
        kind = rule["kind"]
        low_max, high_min = rule["low_max"], rule["high_min"]
        if kind == "condition":
            if rule["parameter"] == "ph":
                status = "acidic" if value < low_max else ("alkaline" if value > high_min else "neutral")
                note = rule["low_note"] if status == "acidic" else (rule["high_note"] if status == "alkaline" else None)
            else:  # ec
                status = "normal" if value <= low_max else ("saline" if value <= high_min else "critical")
                note = rule["high_note"] if status in ("saline", "critical") else None
        elif kind == "micro":
            status = "deficient" if value < low_max else "sufficient"
            note = rule["low_note"] if status == "deficient" else None
        else:  # nutrient / organic
            status = "low" if value < low_max else ("high" if value > high_min else "optimal")
            if status == "low":
                note = rule["low_note"]
            elif status == "high":
                note = rule["high_note"]
            else:
                note = None
            if note and "{pct" in note:
                note = note.format(pct=rule["adjustment"])
        flags.append(
            SoilFlag(
                parameter=rule["parameter"],
                label=rule["label"],
                value=value,
                unit=rule["unit"],
                status=status,
                note=note,
            )
        )
    return flags


def _status_of(flags: list[SoilFlag], parameter: str) -> str | None:
    for f in flags:
        if f.parameter == parameter:
            return f.status
    return None


def _product_composition(lake: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Return (fertilizer_id → [{form, percent}], fertilizer_id → name)."""
    from pipelines.storage import get_read_connection

    con = get_read_connection(lake)
    rows = con.execute(
        "SELECT fertilizer_id, nutrient_id, form, percent FROM gold.fertilizer_nutrient"
    ).fetchall()
    names = {
        r[0]: r[1]
        for r in con.execute("SELECT fertilizer_id, name FROM gold.dim_fertilizer").fetchall()
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for fid, _nid, form, pct in rows:
        out.setdefault(fid, []).append({"form": form.upper(), "percent": float(pct)})
    return out, names


def recommend_fertilizer(
    crop: str,
    *,
    growth_stage: str | None = None,
    soil_test: SoilTestInput | dict[str, Any] | None = None,
    target_yield: float | None = None,
    lake: Path | None = None,
) -> FertilizerAdvisory | None:
    """Build a fertilizer advisory for a crop (None if the crop has no recipe).

    `crop` accepts a canonical id or English name (aliases via `resolve_crop`).
    """
    from pipelines.entities import resolve_crop
    from pipelines.storage import LAKE_DIR

    lake = Path(lake or LAKE_DIR / "agrilake.duckdb")
    crop_row = resolve_crop(crop)
    if not crop_row:
        return None
    crop_id = crop_row["crop_id"]
    req = _get_requirement(crop_id)
    if not req:
        return None

    # 1. Soil assessment (observation).
    flags = assess_soil(soil_test)
    adj: dict[str, float] = {"N": 0.0, "P2O5": 0.0, "K2O": 0.0}
    for rule in SOIL_TEST_INTERPRETATION:
        if rule.get("nutrient_form") in adj:
            st = _status_of(flags, rule["parameter"])
            if st == "low":
                adj[rule["nutrient_form"]] = +rule["adjustment"]
            elif st == "high":
                adj[rule["nutrient_form"]] = -rule["adjustment"]

    # 2. Soil-adjusted nutrient requirement per form (recommendation).
    req_kg: dict[str, float] = {}
    for form in ("N", "P2O5", "K2O"):
        base = req["total_kg_ha"].get(form, 0.0)
        req_kg[form] = round(base * (1.0 + adj[form]), 2)

    # 3. Product mix (DAP-first so the N credit from DAP is accounted).
    products, names = _product_composition(lake)

    def _compose(form: str) -> str | None:
        for fid in _PRODUCT_PREFERENCE[form]:
            if fid in products:
                return fid
        return None

    def _kg_for(fid: str, form: str) -> float:
        for row in products[fid]:
            if row["form"] == form:
                return row["percent"] / 100.0
        return 0.0

    p_product = _compose("P2O5")
    n_product = _compose("N")
    k_product = _compose("K2O")

    dap_kg = req_kg["P2O5"] / _kg_for(p_product, "P2O5") if p_product and _kg_for(p_product, "P2O5") else 0.0
    n_from_dap = dap_kg * (_kg_for(p_product, "N") if p_product else 0.0)
    urea_kg = max(0.0, (req_kg["N"] - n_from_dap) / _kg_for(n_product, "N")) if n_product and _kg_for(n_product, "N") else 0.0
    mop_kg = req_kg["K2O"] / _kg_for(k_product, "K2O") if k_product and _kg_for(k_product, "K2O") else 0.0

    product_kg = {
        "N": {n_product: urea_kg} if n_product else {},
        "P2O5": {p_product: dap_kg} if p_product else {},
        "K2O": {k_product: mop_kg} if k_product else {},
    }

    # 4. Per-timing application plan.
    plan: list[ProductApplication] = []
    for timing in ("basal", "vegetative", "reproductive"):
        for form in ("N", "P2O5", "K2O"):
            share = req["stage_split"][timing].get(form, 0.0)
            if share <= 0:
                continue
            kg_ha = round(req_kg[form] * share, 2)
            for fid, season_kg in product_kg[form].items():
                plan.append(
                    ProductApplication(
                        timing=timing,
                        nutrient_form=form,
                        kg_ha=kg_ha,
                        product_id=fid,
                        product_name=names.get(fid, fid),
                        product_kg_ha=round(season_kg * share, 2),
                        share_of_season=round(share, 4),
                    )
                )

    # 5. Observations / recommendations / notes (evidence-separated).
    observations = [
        f"{f.label}: {f.value:g} {f.unit} ({f.status})" for f in flags
    ]
    recommendations = [
        f"Apply {round(urea_kg, 1)} kg/ha {names.get(n_product, 'Urea')}",
        f"Apply {round(dap_kg, 1)} kg/ha {names.get(p_product, 'DAP')}",
        f"Apply {round(mop_kg, 1)} kg/ha {names.get(k_product, 'MOP')}",
    ]
    notes = [f.note for f in flags if f.note]
    if growth_stage:
        timing = timing_for_stage(growth_stage)
        notes.append(f"Reported stage '{growth_stage}' → application timing bucket '{timing}'.")
    notes.append(
        f"Blanket seasonal recommendation for {req['target_yield_tha']:g} t/ha "
        f"target yield; refine with STCR/soil-health-card lab data."
    )

    return FertilizerAdvisory(
        crop_id=crop_id,
        crop=crop_row["canonical_en"],
        growth_stage=growth_stage,
        target_yield_tha=req["target_yield_tha"],
        version=FERTILIZER_ADVISORY_VERSION,
        soil_flags=flags,
        plan=plan,
        observations=observations,
        recommendations=recommendations,
        notes=notes,
    )


def persist_advisory(adv: FertilizerAdvisory, path: Path | None = None) -> Path:
    """Write a versioned advisory CSV (``fertilizer_advisory@<version>.csv``)."""
    import csv

    from pipelines.storage import GOLD_DIR, ensure_dir

    path = path or GOLD_DIR / f"fertilizer_advisory@{adv.version}.csv"
    ensure_dir(path.parent)
    records = adv.to_records()
    fieldnames = list(FertilizerAdvisoryRecord.model_fields)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.model_dump())
    return path
