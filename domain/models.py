"""Pydantic models for canonical ontology entities (used for validation)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Crop(BaseModel):
    crop_id: str
    canonical_en: str
    scientific_name: str
    family: str
    type: str
    group: str


class Season(BaseModel):
    season_id: str
    name: str
    months: Optional[str] = None
    description: Optional[str] = None


class GrowthStage(BaseModel):
    stage_id: str
    name: str
    description: Optional[str] = None


class Geography(BaseModel):
    state_code: str
    name: str
    type: str = "state"
    agroclimatic_zone: Optional[str] = None
    agroecological_region: Optional[str] = None


class Disease(BaseModel):
    disease_id: str
    name: str
    crop_id: Optional[str] = None
    crop: Optional[str] = None
    pathogen_type: Optional[str] = None
    causal_agent: Optional[str] = None
    symptoms: Optional[str] = None
    affected_parts: Optional[str] = None
    favourable_conditions: Optional[str] = None
    growth_stage: Optional[str] = None
    differential_diagnosis: Optional[str] = None
    management: Optional[str] = None


class Pest(BaseModel):
    pest_id: str
    name: str
    scientific_name: Optional[str] = None
    crop_hosts: Optional[str] = None
    damage_symptoms: Optional[str] = None
    growth_stage: Optional[str] = None
    economic_threshold: Optional[str] = None
    monitoring: Optional[str] = None
    cultural_control: Optional[str] = None
    biological_control: Optional[str] = None
    chemical_control: Optional[str] = None


class FertilizerNutrient(BaseModel):
    fertilizer_id: str
    nutrient_id: str
    form: str
    percent: float = Field(gt=0)


class NutrientDeficiency(BaseModel):
    deficiency_id: str
    nutrient_id: str
    crop_id: Optional[str] = None
    crop: Optional[str] = None
    symptoms: Optional[str] = None
    correction: Optional[str] = None


class CalendarOverride(BaseModel):
    crop_id: str
    season_id: str
    stage_id: str
    location_scope: str  # state | district
    state_code: str
    district_code: Optional[str] = None
    month_start: int = Field(ge=1, le=12)
    month_end: int = Field(ge=1, le=12)
    note: Optional[str] = None


class Nutrient(BaseModel):
    nutrient_id: str
    symbol: str
    name: str
    role: Optional[str] = None
    deficiency_symptoms: Optional[str] = None


class Fertilizer(BaseModel):
    fertilizer_id: str
    name: str
    category: str
    composition: Optional[str] = None
    notes: Optional[str] = None


class Soil(BaseModel):
    soil_id: str
    name: str
    characteristics: Optional[str] = None
    crops: Optional[str] = None


class AuthorityLevel(BaseModel):
    key: str
    name: str
    score: float = Field(ge=0.0, le=1.0)


# ── Fertilizer advisory (Track 5) ────────────────────────────────────────────
class SoilTestInput(BaseModel):
    """A farmer's / lab soil-test report. All nutrient values optional."""

    soil_id: Optional[str] = None
    ph: Optional[float] = Field(default=None, ge=0, le=14)
    ec: Optional[float] = Field(default=None, ge=0)
    oc: Optional[float] = Field(default=None, ge=0)          # %
    available_n: Optional[float] = Field(default=None, ge=0)  # kg/ha
    available_p: Optional[float] = Field(default=None, ge=0)  # kg/ha
    available_k: Optional[float] = Field(default=None, ge=0)  # kg/ha
    zn: Optional[float] = Field(default=None, ge=0)
    fe: Optional[float] = Field(default=None, ge=0)
    b: Optional[float] = Field(default=None, ge=0)
    mn: Optional[float] = Field(default=None, ge=0)
    cu: Optional[float] = Field(default=None, ge=0)
    s: Optional[float] = Field(default=None, ge=0)


class NutrientRequirement(BaseModel):
    crop_id: str
    crop: str
    target_yield_tha: float = Field(ge=0)
    total_kg_ha: dict[str, float]
    stage_split: dict[str, dict[str, float]]


class SoilInterpretation(BaseModel):
    parameter: str
    label: str
    unit: str
    kind: str  # nutrient | organic | condition | micro
    low_max: Optional[float] = None
    high_min: Optional[float] = None
    adjustment: float = 0.0
    low_note: Optional[str] = None
    high_note: Optional[str] = None
    nutrient_form: Optional[str] = None


class FertilizerAdvisoryRecord(BaseModel):
    """Versioned, evidence-separated recommendation (the blueprint's
    ``fertilizer_advisory@<version>`` table shape)."""

    advisory_id: str
    version: str
    crop_id: str
    crop: str
    growth_stage: Optional[str] = None
    target_yield_tha: float
    nutrient_form: str
    recommended_kg_ha: float
    timing: str  # basal | vegetative | reproductive
    product_id: str
    product_name: str
    product_kg_ha: float
    soil_status: str
    source: str
    authority: str
