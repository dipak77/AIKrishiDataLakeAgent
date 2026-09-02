"""Diagnose a farmer query over the lake (pure DuckDB, no LLM).

Usage:
    python scripts/diagnose.py --crop tomato --symptoms "black spots, lower leaves yellowing"
    python scripts/diagnose.py --crop "टोमॅटो" --symptoms "पानावर काळे डाग" --stage vegetative
    python scripts/diagnose.py --crop tomato --symptoms "black spots" --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.diagnose import diagnose  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a crop problem from farmer symptoms")
    parser.add_argument("--crop", required=True, help="crop name / id / Indian-language alias")
    parser.add_argument("--symptoms", required=True, help="free-text symptom description")
    parser.add_argument("--stage", default=None, help="optional growth stage (e.g. vegetative)")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = diagnose(args.crop, args.symptoms, growth_stage=args.stage, top_n=args.top)

    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2, ensure_ascii=False))
        return 0

    print(f"\nDiagnosis for crop='{args.crop}' symptoms='{args.symptoms}'"
          + (f" stage='{args.stage}'" if args.stage else "") + "\n")
    if not results:
        print("  No candidates matched. Try more/different symptom words.")
        return 0
    for r in results:
        print(f"  [{r.entity_type.upper():<10}] {r.name:<32} score={r.score}")
        print(f"      symptoms: {', '.join(r.matched_symptoms) or '-'}")
        if r.causal_agent:
            print(f"      causal agent: {r.causal_agent}")
        if r.pathogen_type:
            print(f"      pathogen type: {r.pathogen_type}")
        if r.growth_stage:
            print(f"      stages: {r.growth_stage}")
        if r.economic_threshold:
            print(f"      ETL: {r.economic_threshold}")
        if r.differential_diagnosis:
            print(f"      differential: {r.differential_diagnosis}")
        if r.management:
            for k, v in r.management.items():
                if v:
                    print(f"      {k}: {v}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
