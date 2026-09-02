"""Weather advisory CLI (Track 7).

Usage:
    python scripts/weather.py --district Pune
    python scripts/weather.py --district Nagpur --crop orange
    python scripts/weather.py --district Pune --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.weather import agromet_advisory, weather_flags, rainfall_mm  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agromet weather advisory for a district")
    parser.add_argument("--district", required=True, help="district name (e.g. Pune)")
    parser.add_argument("--crop", default=None, help="optional crop filter")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    adv = agromet_advisory(args.district, crop=args.crop)
    if adv is None:
        print(f"No advisory for district '{args.district}'.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(adv.as_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"\nWeather advisory - {adv.district}, {adv.state} "
          f"({adv.valid_from} -> {adv.valid_to})\n")
    w = adv.weather
    print(f"  Forecast: {w.get('rainfall', '-')} | {w.get('temp_min')}-{w.get('temp_max')} deg C "
          f"| humidity {w.get('humidity')}% | wind {w.get('wind')} km/h\n")
    if adv.flags:
        print("  Risk flags:")
        for f in adv.flags:
            print(f"    [{f.flag:<14} {f.severity:<6}] {f.note}")
    else:
        print("  Risk flags: none triggered.")
    if adv.crops:
        print("\n  Crop advisories:")
        for c in adv.crops:
            print(f"    - {c.crop} ({c.growth_stage}): {c.risk}")
            if c.action:
                print(f"        -> {c.action}")
    if adv.notes:
        print("\n  Notes:")
        for n in adv.notes:
            print(f"    - {n}")
    print(f"\n  Evidence: {adv.evidence['source']} ({adv.evidence['authority']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
