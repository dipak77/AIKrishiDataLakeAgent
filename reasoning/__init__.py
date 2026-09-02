"""Reasoning substrate (V1.5) — pure-DuckDB, no LLM, no vector DB.

Converts the entity catalog into something that can *answer*:

    diagnosis : crop + symptoms → ranked candidate diseases/pests/deficiencies
                → stage/environment filter → management options + source
    fertilizer: nutrient-math helpers (supply computation, N/P/K conversions)

See `docs/phase-2-review.md` for the design.
"""

from .diagnose import diagnose, DiagnosisResult
from .fertilizer import fertilizer_composition, nutrient_from_fertilizer, supply_for_kg
from .symptoms import tokenize_symptoms

__all__ = [
    "diagnose",
    "DiagnosisResult",
    "fertilizer_composition",
    "nutrient_from_fertilizer",
    "supply_for_kg",
    "tokenize_symptoms",
]
