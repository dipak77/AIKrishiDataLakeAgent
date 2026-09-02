"""Crop planning CLI (Track 8).

Usage:
    python scripts/crop_plan.py --crop tomato
    python scripts/crop_plan.py --crop rice --state Maharashtra --district Pune
    python scripts/crop_plan.py --month 6 --state Maharashtra      # what to sow in June
    python scripts/crop_plan.py --crop tomato --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.crop_plan import crop_plan, crops_to_sow, sow_risk  # noqa: E402

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt(months: list[int]) -> str:
    return ", ".join(_MONTH_NAMES[m - 1] for m in months)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crop calendar planning")
    parser.add_argument("--crop", default=None, help="crop name / id / alias")
    parser.add_argument("--month", type=int, default=None, help="month 1-12 (with no --crop: what to sow)")
    parser.add_argument("--state", default=None)
    parser.add_argument("--district", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.crop:
        plan = crop_plan(args.crop, state=args.state, district=args.district)
        if plan is None:
            print(f"No calendar for crop '{args.crop}'.", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(plan.as_dict(), indent=2, ensure_ascii=False))
            return 0
        loc = (plan.location.get("district") or plan.location.get("state") or "India")
        print(f"\nCrop plan - {plan.crop} @ {loc}\n")
        print(f"  Seasons: {', '.join(plan.seasons)}")
        print(f"  Sow window: {_fmt(plan.sow_window)}")
        print(f"  Harvest window: {_fmt(plan.harvest_window)}")
        if plan.duration_months:
            print(f"  Duration: ~{plan.duration_months} months")
        print("\n  Timeline:")
        for t in plan.timeline:
            note = f" - {t.note}" if t.note else ""
            print(f"    {t.stage:<14} {_fmt(t.months)}{note}")
        print(f"\n  Evidence: {plan.evidence['source']} ({plan.evidence['authority']})")
        return 0

    if args.month is not None:
        if not (1 <= args.month <= 12):
            print("--month must be 1-12", file=sys.stderr)
            return 2
        crops = crops_to_sow(args.month, state=args.state, district=args.district)
        if args.json:
            print(json.dumps(crops, indent=2, ensure_ascii=False))
            return 0
        loc = args.district or args.state or "India"
        print(f"\nCrops to sow in {_MONTH_NAMES[args.month - 1]} @ {loc}:")
        if not crops:
            print("  (none in the seed calendar)")
        for c in crops:
            print(f"  - {c['crop']:<14} [{c['season']}] sow {_fmt(c['sow_months'])}")
        return 0

    parser.error("provide --crop or --month")


if __name__ == "__main__":
    raise SystemExit(main())
