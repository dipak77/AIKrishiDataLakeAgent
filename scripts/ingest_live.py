"""Run a source connector (live if internet+keys available, else fixtures).

Usage:
    python scripts/ingest_live.py --source agmarknet --limit 5
    python scripts/ingest_live.py --source all --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.government import (  # noqa: E402
    AgmarknetConnector,
    ImdConnector,
    KccConnector,
    SoilHealthConnector,
)
from connectors.research import FaostatConnector, IcarConnector  # noqa: E402
from connectors.vision import PlantDocConnector, PlantVillageConnector  # noqa: E402

CONNECTORS = {
    "kcc": KccConnector,
    "agmarknet": AgmarknetConnector,
    "faostat": FaostatConnector,
    "imd": ImdConnector,
    "shc": SoilHealthConnector,
    "icar": IcarConnector,
    "plantvillage": PlantVillageConnector,
    "plantdoc": PlantDocConnector,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a source connector")
    parser.add_argument("--source", choices=sorted(CONNECTORS) + ["all"], default="agmarknet")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="print summary as JSON")
    args = parser.parse_args(argv)

    sources = list(CONNECTORS) if args.source == "all" else [args.source]
    summaries = []
    for src in sources:
        connector = CONNECTORS[src]()
        connector.limit = args.limit
        summary = connector.run()
        summaries.append(summary)

    if args.json:
        print(json.dumps(summaries, indent=2, ensure_ascii=False, default=str))
    else:
        for summary in summaries:
            print(f"\n=== {summary['source_id']} (discovered {summary['discovered']} resources) ===")
            for res in summary["resources"]:
                status = res.get("status")
                if status == "error":
                    print(f"  [error] {res['resource'].get('description')}: {res['error']}")
                else:
                    print(
                        f"  [ok] {res['resource'].get('description')} → "
                        f"{res.get('records', 0)} records ({res.get('method', 'live')})"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
