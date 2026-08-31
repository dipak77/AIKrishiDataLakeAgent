"""Build + persist the knowledge graph.

Usage: python scripts/build_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_graph.build import build_knowledge_graph  # noqa: E402
from pipelines.storage import GOLD_DIR, write_json  # noqa: E402


def main() -> int:
    graph = build_knowledge_graph()
    path = write_json(GOLD_DIR / "knowledge_graph.json", graph)
    s = graph["summary"]
    print(f"Knowledge graph → {path}")
    print(f"  nodes: {s['node_count']}  edges: {s['edge_count']}")
    for ntype, count in sorted(s["node_types"].items()):
        print(f"  {ntype:<10} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
