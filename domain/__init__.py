"""Canonical agriculture ontologies (crops, pests, diseases, soils, nutrients,
fertilizers, pesticides, weather, geography, seasons, growth stages).

Seed content lives in `seed_data.py`; lookup indexes in `catalog.py`; Pydantic
entity models in `models.py`.
"""

from .catalog import CROP_LOOKUP, GEOGRAPHY_LOOKUP, CROPS, GEOGRAPHY
from .models import (
    Crop,
    Disease,
    Fertilizer,
    Geography,
    GrowthStage,
    Nutrient,
    Pest,
    Season,
    Soil,
)

__all__ = [
    "CROP_LOOKUP",
    "GEOGRAPHY_LOOKUP",
    "CROPS",
    "GEOGRAPHY",
    "Crop",
    "Disease",
    "Fertilizer",
    "Geography",
    "GrowthStage",
    "Nutrient",
    "Pest",
    "Season",
    "Soil",
]
