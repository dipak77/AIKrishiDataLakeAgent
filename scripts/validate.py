"""Validate ontologies, build the knowledge graph, demo data-quality scoring.

Usage: python scripts/validate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_graph.build import build_knowledge_graph  # noqa: E402
from ontology.validate import validate_ontologies  # noqa: E402
from pipelines.quality import score_record  # noqa: E402
from pipelines.storage import GOLD_DIR, write_json  # noqa: E402


def main() -> int:
    report = validate_ontologies()
    print("Ontology validation:")
    for check in report["checks"]:
        mark = "ok " if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['name']}")
        if not check["ok"]:
            print(f"         {check['detail']}")
    print(f"  counts: {json.dumps(report['counts'], ensure_ascii=False)}")
    for warn in report["warnings"]:
        print(f"  [warn] {warn}")

    graph = build_knowledge_graph()
    graph_path = write_json(GOLD_DIR / "knowledge_graph.json", graph)
    print(f"\nKnowledge graph: {graph['summary']['node_count']} nodes, "
          f"{graph['summary']['edge_count']} edges -> {graph_path}")

    demo = score_record(
        {
            "source": "ICAR",
            "license": {"type": "GODL-India"},
            "ingested_at": "2026-08-31T00:00:00+00:00",
            "state": "Maharashtra",
            "district": "Pune",
            "crop": "CROP_TOMATO",
            "source_url": "https://icar.gov.in/...",
            "expert_verified": True,
        },
        authority="government",
    )
    print("\nQuality scoring demo (ICAR tomato advisory):")
    for k, v in demo.items():
        print(f"  {k:<22} {v}")

    if report["ok"]:
        print("\nALL CHECKS PASSED")
        return 0
    print("\nVALIDATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
