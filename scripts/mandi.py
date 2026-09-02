"""Mandi price intelligence CLI (Track 6).

Usage:
    python scripts/mandi.py --commodity tomato
    python scripts/mandi.py --commodity onion --market Lasalgaon
    python scripts/mandi.py --markets
    python scripts/mandi.py --commodity tomato --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.mandi import list_markets, market_advisory  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mandi price snapshot + trend + season signal")
    parser.add_argument("--commodity", default=None, help="commodity name (e.g. tomato, onion)")
    parser.add_argument("--market", default=None, help="optional market filter (e.g. Lasalgaon)")
    parser.add_argument("--markets", action="store_true", help="list known mandis")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.markets:
        markets = list_markets()
        if args.json:
            print(json.dumps(markets, indent=2, ensure_ascii=False))
        else:
            print(f"\nKnown mandis ({len(markets)}):")
            for m in markets:
                print(f"  - {m['name']:<12} {m['state']}, {m['district']} "
                      f"({m['state_code']}/{m['district_code']}) — {m['key_commodities']}")
        return 0

    if not args.commodity:
        parser.error("provide --commodity (or --markets)")

    adv = market_advisory(args.commodity, market=args.market)
    if adv is None:
        print(f"No price data for '{args.commodity}'"
              + (f" at market '{args.market}'" if args.market else "") + ".", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(adv.as_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"\nMandi snapshot - {adv.commodity}"
          + (f" @ {adv.market}" if adv.market else "") + "\n")
    for s in adv.stats:
        print(f"  {s.market} ({s.state}, {s.district}):")
        print(f"    latest modal {s.latest_modal} INR/q on {s.latest_date}")
        print(f"    window: {s.n_days} days | mean {s.mean_modal} | "
              f"min {s.min_price} | max {s.max_price}")
        print(f"    spread {s.spread_pct}% | volatility +/-{s.volatility_pct}% | trend {s.trend}")
    print(f"\n  Season: [{adv.season_signal}] {adv.season_note}")
    print(f"  Evidence: {adv.evidence['source']} ({adv.evidence['authority']}, "
          f"license {adv.evidence['license']['type']})")
    print("  Note: descriptive heuristics, not price predictions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
