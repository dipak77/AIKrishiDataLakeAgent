"""Fertilizer advisory CLI (Track 5).

Usage:
    python scripts/fertilizer.py --crop tomato
    python scripts/fertilizer.py --crop tomato --stage fruiting --soil soil_test.json
    python scripts/fertilizer.py --crop tomato --soil-pH 6.2 --soil-N 220 --soil-P 8 --soil-K 90
    python scripts/fertilizer.py --crop "टोमॅटो" --json

The optional soil test may be passed as a JSON file or via --soil-* flags
(values: N/P/K in kg/ha, OC %, Zn/Fe/B/Mn/Cu/S in ppm, EC dS/m, pH).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.models import SoilTestInput  # noqa: E402
from reasoning.advisory import persist_advisory, recommend_fertilizer  # noqa: E402


def _load_soil(args: argparse.Namespace) -> SoilTestInput | None:
    kwargs: dict = {}
    if args.soil:
        data = json.loads(Path(args.soil).read_text(encoding="utf-8"))
        kwargs.update(data)
    for key in ("ph", "ec", "oc", "available_n", "available_p", "available_k", "zn", "fe", "b", "mn", "cu", "s"):
        val = getattr(args, f"soil_{key}", None)
        if val is not None:
            kwargs[key] = val
    return SoilTestInput.model_validate(kwargs) if kwargs else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fertilizer advisory (crop × stage × soil test)")
    parser.add_argument("--crop", required=True, help="crop name / id / Indian-language alias")
    parser.add_argument("--stage", default=None, help="growth stage (e.g. vegetative, fruiting)")
    parser.add_argument("--soil", default=None, help="path to a soil-test JSON file")
    parser.add_argument("--json", action="store_true")
    # soil test flags
    parser.add_argument("--soil-ph", type=float, default=None)
    parser.add_argument("--soil-ec", type=float, default=None)
    parser.add_argument("--soil-oc", type=float, default=None)
    parser.add_argument("--soil-N", type=float, default=None, dest="soil_available_n")
    parser.add_argument("--soil-P", type=float, default=None, dest="soil_available_p")
    parser.add_argument("--soil-K", type=float, default=None, dest="soil_available_k")
    parser.add_argument("--soil-zn", type=float, default=None, dest="soil_zn")
    parser.add_argument("--soil-fe", type=float, default=None, dest="soil_fe")
    parser.add_argument("--soil-b", type=float, default=None, dest="soil_b")
    parser.add_argument("--soil-mn", type=float, default=None, dest="soil_mn")
    parser.add_argument("--soil-cu", type=float, default=None, dest="soil_cu")
    parser.add_argument("--soil-s", type=float, default=None, dest="soil_s")
    args = parser.parse_args(argv)

    soil = _load_soil(args)
    adv = recommend_fertilizer(args.crop, growth_stage=args.stage, soil_test=soil)

    if adv is None:
        print(f"No nutrient recipe for crop '{args.crop}'.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(adv.as_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"\nFertilizer advisory for {adv.crop} ({adv.version})"
          + (f" - stage '{adv.growth_stage}'" if adv.growth_stage else "") + "\n")
    if adv.soil_flags:
        print("  Soil test (observation):")
        for f in adv.soil_flags:
            print(f"    - {f.label}: {f.value:g} {f.unit} -> {f.status}")
    else:
        print("  Soil test: not provided (blanket recommendation).")
    print("\n  Recommendation (per ha):")
    for r in adv.recommendations:
        print(f"    - {r}")
    if adv.plan:
        print("\n  Application schedule:")
        for p in adv.plan:
            print(
                f"    [{p.timing:<11}] {p.nutrient_form:<5} {p.kg_ha:>7} kg/ha "
                f"-> {p.product_name} {p.product_kg_ha:>7} kg/ha"
            )
    if adv.notes:
        print("\n  Notes:")
        for n in adv.notes:
            print(f"    - {n}")
    print(f"\n  Evidence: {adv.evidence['source']} ({adv.evidence['authority']}, "
          f"license {adv.evidence['license']['type']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
