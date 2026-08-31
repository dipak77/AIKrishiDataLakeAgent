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
    management: Optional[str] = None


class Pest(BaseModel):
    pest_id: str
    name: str
    scientific_name: Optional[str] = None
    crop_hosts: Optional[str] = None
    damage_symptoms: Optional[str] = None
    cultural_control: Optional[str] = None
    biological_control: Optional[str] = None
    chemical_control: Optional[str] = None


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
