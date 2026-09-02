"""Export the knowledge graph to Neo4j Cypher + Apache AGE SQL (V5-B).

Usage:
    python scripts/export_graph.py
    python scripts/export_graph.py --out data/gold
    python scripts/export_graph.py --format cypher      # or age
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_graph.export import export_graph  # noqa: E402
from knowledge_graph.export import load_graph  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the knowledge graph (Neo4j + Apache AGE)")
    parser.add_argument("--out", default=None, help="output directory (default: data/gold)")
    parser.add_argument("--format", choices=["cypher", "age", "both"], default="both")
    args = parser.parse_args(argv)

    nodes, edges = load_graph()
    out_dir = Path(args.out) if args.out else None
    paths = export_graph(out_dir)

    print(f"Knowledge graph: {len(nodes)} nodes, {len(edges)} edges")
    if args.format in ("cypher", "both"):
        print(f"  Cypher (Neo4j)  -> {paths['cypher']}")
    if args.format in ("age", "both"):
        print(f"  AGE SQL (PG)    -> {paths['age']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
