"""Build + persist the knowledge graph.

Usage: python scripts/build_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from knowledge_graph.build import build_knowledge_graph  # noqa: E402
from pipelines.storage import (  # noqa: E402
    GOLD_DIR,
    LAKE_DIR,
    ensure_dir,
    read_write_connection,
    write_json,
)


def persist_graph_tables(graph: dict, lake_path: Path | None = None) -> Path:
    """Write the graph as `gold.graph_nodes` / `gold.graph_edges` (DuckDB)."""
    lake_path = lake_path or ensure_dir(LAKE_DIR) / "agrilake.duckdb"
    con = read_write_connection(lake_path)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute("DROP TABLE IF EXISTS gold.graph_nodes")
        con.execute(
            "CREATE TABLE gold.graph_nodes (id VARCHAR PRIMARY KEY, type VARCHAR, label VARCHAR, props JSON)"
        )
        con.execute("DROP TABLE IF EXISTS gold.graph_edges")
        con.execute(
            "CREATE TABLE gold.graph_edges (source VARCHAR, target VARCHAR, type VARCHAR, props JSON)"
        )
        con.executemany(
            "INSERT INTO gold.graph_nodes VALUES (?, ?, ?, ?)",
            [(n["id"], n["type"], n["label"], json_dumps(n.get("props", {}))) for n in graph["nodes"]],
        )
        con.executemany(
            "INSERT INTO gold.graph_edges VALUES (?, ?, ?, ?)",
            [(e["source"], e["target"], e["type"], json_dumps(e.get("props", {}))) for e in graph["edges"]],
        )
    finally:
        con.close()
    return lake_path


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)


def main() -> int:
    graph = build_knowledge_graph()
    path = write_json(GOLD_DIR / "knowledge_graph.json", graph)
    lake_path = persist_graph_tables(graph)
    s = graph["summary"]
    print(f"Knowledge graph -> {path}")
    print(f"  graph tables -> {lake_path} (gold.graph_nodes / gold.graph_edges)")
    print(f"  nodes: {s['node_count']}  edges: {s['edge_count']}")
    for ntype, count in sorted(s["node_types"].items()):
        print(f"  {ntype:<10} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

