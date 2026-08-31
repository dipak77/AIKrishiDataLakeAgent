"""Emit JSON Schema files for the canonical record models.

Usage: python scripts/gen_json_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.storage import ensure_dir  # noqa: E402
from schemas.records import (  # noqa: E402
    AgriImage,
    AgrometAdvisory,
    CropProduction,
    FarmerQuery,
    MandiPrice,
    ResearchChunk,
    SoilTest,
    UnifiedAgricultureRecord,
)

MODELS = {
    "farmer_query": FarmerQuery,
    "crop_production": CropProduction,
    "mandi_price": MandiPrice,
    "agromet_advisory": AgrometAdvisory,
    "soil_test": SoilTest,
    "research_chunk": ResearchChunk,
    "agri_image": AgriImage,
    "unified_agriculture_record": UnifiedAgricultureRecord,
}


def main() -> int:
    out_dir = ensure_dir(ROOT / "schemas" / "json")
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
