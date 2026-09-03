"""Canonical record models for silver/gold layers.

These models define the target shape for every ingested record. Connector
outputs are validated (and coerced) against them where practical; `extra` is
allowed so provenance/quality fields added by enrichment are preserved.

Generated JSON Schema lives in `schemas/json/` (via `scripts/gen_json_schema.py`).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Provenance(BaseModel):
    """Provenance fields carried by every record."""

    model_config = ConfigDict(extra="allow")

    source_id: Optional[str] = None
    source: Optional[str] = None
    country: Optional[str] = None
    authority: Optional[str] = None
    authority_level: Optional[str] = None
    license: Optional[Any] = None
    source_url: Optional[str] = None
    ingested_at: Optional[str] = None
    version: Optional[str] = None
    quality: Optional[dict[str, Any]] = None


class Location(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: Optional[str] = None
    state_code: Optional[str] = None
    district: Optional[str] = None
    district_code: Optional[str] = None
    block: Optional[str] = None
    agroclimatic_zone: Optional[str] = None
    agroecological_region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class FarmerQuery(Provenance):
    """KCC-style farmer question + expert answer."""

    query_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    block: Optional[str] = None
    farmer_language: Optional[str] = None
    query_original: Optional[str] = None
    query_en: Optional[str] = None
    crop: Optional[str] = None
    crop_canonical: Optional[str] = None
    crop_scientific_name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    growth_stage: Optional[str] = None
    answer_original: Optional[str] = None
    answer_normalized: Optional[str] = None
    season: Optional[str] = None
    month: Optional[int] = None
    expert_verified: Optional[bool] = None


class CropProduction(Provenance):
    """district × crop × season × year × area × production."""

    record_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    crop: Optional[str] = None
    crop_canonical: Optional[str] = None
    season: Optional[str] = None
    year: Optional[int] = None
    area_hectares: Optional[float] = None
    production_tonnes: Optional[float] = None
    yield_kg_ha: Optional[float] = None


class MandiPrice(Provenance):
    record_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    market: Optional[str] = None
    commodity_raw: Optional[str] = None
    crop: Optional[str] = None
    crop_canonical: Optional[str] = None
    variety: Optional[str] = None
    grade: Optional[str] = None
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    modal_price: Optional[float] = Field(default=None, ge=0)
    unit: Optional[str] = "INR/quintal"
    price_date: Optional[str] = None

    @model_validator(mode="after")
    def _triangle(self) -> "MandiPrice":
        lo, modal, hi = self.min_price, self.modal_price, self.max_price
        if lo is not None and modal is not None and lo > modal:
            raise ValueError(f"min_price ({lo}) > modal_price ({modal})")
        if modal is not None and hi is not None and modal > hi:
            raise ValueError(f"modal_price ({modal}) > max_price ({hi})")
        return self


class AgrometAdvisory(Provenance):
    record_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    weather: Optional[dict[str, Any]] = None
    crop_advisories: Optional[list[dict[str, Any]]] = None


class SoilTest(Provenance):
    record_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    sample_id: Optional[str] = None
    soil_type: Optional[str] = None
    previous_crop: Optional[str] = None
    target_crop: Optional[str] = None
    target_yield: Optional[float] = None
    irrigation: Optional[str] = None
    drainage: Optional[str] = None
    water_source: Optional[str] = None
    soil_test: Optional[dict[str, Any]] = None
    recommendation: Optional[Any] = None


class ResearchChunk(Provenance):
    chunk_id: Optional[str] = None
    document: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None
    crop: Optional[list[str]] = None
    topics: Optional[list[str]] = None
    section: Optional[str] = None
    page: Optional[int] = None
    text: Optional[str] = None
    authority_score: Optional[float] = None


class AgriImage(Provenance):
    image_id: Optional[str] = None
    dataset: Optional[str] = None
    crop: Optional[str] = None
    crop_canonical: Optional[str] = None
    label: Optional[str] = None
    label_type: Optional[str] = None  # healthy | disease | pest | nutrient_deficiency
    split: Optional[str] = None  # train | val | test
    license_tier: Optional[str] = None  # A | review | block
    file_path: Optional[str] = None


class UnifiedAgricultureRecord(BaseModel):
    """The single shape that lets fundamentally different datasets coexist (gold export)."""

    model_config = ConfigDict(extra="allow")

    record_id: Optional[str] = None
    domain: Optional[str] = None
    crop: Optional[str] = None
    variety: Optional[str] = None
    season: Optional[str] = None
    location: Optional[Location] = None
    growth_stage: Optional[str] = None
    problem: Optional[dict[str, Any]] = None
    weather_context: Optional[dict[str, Any]] = None
    soil_context: Optional[dict[str, Any]] = None
    recommendation: Optional[Any] = None
    source: Optional[dict[str, Any]] = None
    quality: Optional[dict[str, Any]] = None
