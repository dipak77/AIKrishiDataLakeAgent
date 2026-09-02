"""Nutrient-math helpers (fertilizer advisory substrate).

Keeps the four concepts distinct (nutrient / fertilizer / organic input /
biofertilizer) and computes how much elemental/oxide nutrient a fertilizer
product supplies — the numeric foundation the full recommendation engine
(crop × variety × stage × soil test × target yield) will build on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from pipelines.storage import LAKE_DIR

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"


def fertilizer_composition(fertilizer_id: str, lake: Path | None = None) -> list[dict[str, Any]]:
    """Return the nutrient composition rows for a fertilizer product."""
    from pipelines.storage import get_read_connection

    con = get_read_connection(Path(lake or DEFAULT_LAKE))
    return [
        {"nutrient_id": r[0], "form": r[1], "percent": r[2]}
        for r in con.execute(
            "SELECT nutrient_id, form, percent FROM gold.fertilizer_nutrient "
            "WHERE fertilizer_id = ? ORDER BY percent DESC",
            [fertilizer_id],
        ).fetchall()
    ]


def nutrient_from_fertilizer(fertilizer_id: str, kg: float, lake: Path | None = None) -> dict[str, float]:
    """Kilograms of each nutrient (as its oxide/elemental form) supplied by `kg` of product."""
    out: dict[str, float] = {}
    for row in fertilizer_composition(fertilizer_id, lake):
        out[row["form"]] = round(kg * row["percent"] / 100.0, 3)
    return out


def supply_for_kg(fertilizer_id: str, nutrient_form: str, kg_target: float, lake: Path | None = None) -> float:
    """Kg of `fertilizer_id` required to supply `kg_target` of `nutrient_form`."""
    for row in fertilizer_composition(fertilizer_id, lake):
        if row["form"].upper() == nutrient_form.upper():
            return round(kg_target / (row["percent"] / 100.0), 3)
    raise KeyError(f"{fertilizer_id} does not supply {nutrient_form}")


# N/P/K shorthand accessors.
def n_p2o5_k2o(fertilizer_id: str, kg: float, lake: Path | None = None) -> dict[str, float]:
    supply = nutrient_from_fertilizer(fertilizer_id, kg, lake)
    return {
        "N": supply.get("N", 0.0),
        "P2O5": supply.get("P2O5", 0.0),
        "K2O": supply.get("K2O", 0.0),
    }
