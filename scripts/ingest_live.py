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
    AgmarknetDashboardConnector,
    ImdConnector,
    KccConnector,
    SoilHealthConnector,
)
from connectors.research import FaostatConnector, IcarConnector  # noqa: E402
from connectors.vision import PlantDocConnector, PlantVillageConnector  # noqa: E402

CONNECTORS = {
    "kcc": KccConnector,
    "agmarknet": AgmarknetConnector,
    "agmarknet_dashboard": AgmarknetDashboardConnector,
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
    parser.add_argument(
        "--kcc-archive", action="store_true",
        help="use the bundled KCC fixture bundle (same as AGRILAKE_KCC_ARCHIVE=1)",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    import os
    if args.kcc_archive:
        os.environ["AGRILAKE_KCC_ARCHIVE"] = "1"

    sources = list(CONNECTORS) if args.source == "all" else [args.source]
    summaries = []
    for src in sources:
        if src == "kcc" and not args.kcc_archive and os.environ.get("AGRILAKE_KCC_ARCHIVE") is None:
            # Backwards-compat: `make ingest SOURCE=kcc` historically produced
            # the fixture bundle. Keep that, but say so — silence is how
            # fixtures masquerade as live data.
            os.environ["AGRILAKE_KCC_ARCHIVE"] = "1"
            print("  [note] KCC has no live resource registered; using the bundled fixture bundle")
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
                        f"  [ok] {res['resource'].get('description')} -> "
                        f"{res.get('records', 0)} records ({res.get('method', 'live')})"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
