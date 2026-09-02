"""Graph export: DuckDB graph tables → Neo4j Cypher + Apache AGE SQL (V5-B).

Reads `gold.graph_nodes` / `gold.graph_edges` (the graph-native lakehouse from
Track 12) and emits loadable scripts so the knowledge graph can be promoted to
a real graph database without any code changes:

    data/gold/knowledge_graph.cypher   → Neo4j (MERGE idempotent, constraints)
    data/gold/knowledge_graph_age.sql  → Apache AGE (PostgreSQL, cypher())

Design notes:
  - Node `id` is the merge key; `label` becomes the `name` property; `props`
    (JSON) are expanded into node/edge properties.
  - Every statement is idempotent (MERGE), so re-export / re-run is safe.
  - String literals escape backslashes + single quotes for both dialects.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipelines.storage import GOLD_DIR, LAKE_DIR, ensure_dir

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"
DEFAULT_OUT = GOLD_DIR

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ── literal serializers (shared escaping) ─────────────────────────────────────
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _literal(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return "'" + _esc(v) + "'"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_literal(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(_key(k) + ": " + _literal(val) for k, val in v.items()) + "}"
    return _literal(str(v))


def _key(k: str) -> str:
    """Map key → identifier or backtick-quoted literal for map entries."""
    if _IDENT_RE.match(str(k)):
        return str(k)
    return "`" + str(k).replace("`", "``") + "`"


# ── node/edge loading ─────────────────────────────────────────────────────────
def load_graph(lake: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (nodes, edges) with parsed `props`, from the lake or in-memory build."""
    import duckdb

    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        con = duckdb.connect(str(lake), read_only=True)
        try:
            has = con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='gold' AND table_name='graph_nodes'"
            ).fetchone()[0]
            if has:
                nodes = [
                    {"id": r[0], "type": r[1], "label": r[2], "props": json.loads(r[3]) if r[3] else {}}
                    for r in con.execute("SELECT id, type, label, props FROM gold.graph_nodes").fetchall()
                ]
                edges = [
                    {"source": r[0], "target": r[1], "type": r[2], "props": json.loads(r[3]) if r[3] else {}}
                    for r in con.execute("SELECT source, target, type, props FROM gold.graph_edges").fetchall()
                ]
                return nodes, edges
        finally:
            con.close()
    from knowledge_graph.build import build_knowledge_graph

    graph = build_knowledge_graph()
    nodes = [dict(n) for n in graph["nodes"]]
    edges = [dict(e) for e in graph["edges"]]
    return nodes, edges


def _node_label(ntype: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(ntype)).strip("_").capitalize() or "Node"


def _rel_type(etype: str) -> str:
    t = re.sub(r"[^A-Za-z0-9]+", "_", str(etype))
    if t and t[0].isdigit():
        t = "r_" + t
    return t or "RELATED"


# ── Cypher (Neo4j) ────────────────────────────────────────────────────────────
def to_cypher(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "// Agri Intelligence Lake — knowledge graph export (Neo4j Cypher)",
        "// Idempotent: MERGE on node id; safe to re-run.",
        "// Nodes: %d   Edges: %d" % (len(nodes), len(edges)),
        "",
    ]
    node_types: dict[str, str] = {}
    for n in nodes:
        node_types.setdefault(n["type"], _node_label(n["type"]))

    # Unique constraints for clean MERGE (one per node type).
    for ntype, label in sorted(node_types.items()):
        lines.append(f"CREATE CONSTRAINT node_id_{ntype} IF NOT EXISTS")
        lines.append(f"FOR (n:{label}) REQUIRE n.id IS UNIQUE;")
    lines.append("")

    for n in nodes:
        label = node_types[n["type"]]
        props = dict(n.get("props") or {})
        props["name"] = n.get("label") or n["id"]
        sets = ", ".join(f"n.{_key(k)} = {_literal(v)}" for k, v in props.items())
        lines.append(f"MERGE (n:{label} {{id: {_literal(n['id'])}}})")
        if sets:
            lines.append(f"  SET {sets};")
    lines.append("")

    for e in edges:
        src_t, dst_t = node_types.get(_type_of(nodes, e["source"]), "Node"), node_types.get(_type_of(nodes, e["target"]), "Node")
        rel = _rel_type(e["type"])
        props = dict(e.get("props") or {})
        match = (
            f"MATCH (a:{src_t} {{id: {_literal(e['source'])}}}), "
            f"(b:{dst_t} {{id: {_literal(e['target'])}}})"
        )
        if props:
            sets = ", ".join(f"r.{_key(k)} = {_literal(v)}" for k, v in props.items())
            lines.append(f"{match} MERGE (a)-[r:{rel}]->(b) SET {sets};")
        else:
            lines.append(f"{match} MERGE (a)-[r:{rel}]->(b);")
    return "\n".join(lines) + "\n"


def _type_of(nodes: list[dict[str, Any]], node_id: str) -> str:
    for n in nodes:
        if n["id"] == node_id:
            return n["type"]
    return "Node"


# ── Apache AGE (PostgreSQL) ───────────────────────────────────────────────────
def to_age_sql(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], graph_name: str = "agrilake") -> str:
    lines: list[str] = [
        "-- Agri Intelligence Lake — knowledge graph export (Apache AGE / PostgreSQL)",
        "-- Run once, as a superuser:",
        "--   CREATE EXTENSION IF NOT EXISTS age;",
        "--   LOAD 'age';",
        "--   SET search_path = ag_catalog, \"$user\", public;",
        f"-- Create the graph (drop first if re-running):",
        f"--   SELECT create_graph('{graph_name}');",
        f"--   (or: SELECT drop_graph('{graph_name}', true); then create_graph again)",
        "-- Statements below are idempotent (MERGE on node id).",
        "-- Nodes: %d   Edges: %d" % (len(nodes), len(edges)),
        "",
    ]
    node_types: dict[str, str] = {}
    for n in nodes:
        node_types.setdefault(n["type"], _node_label(n["type"]))

    for n in nodes:
        label = node_types[n["type"]]
        props = dict(n.get("props") or {})
        props["name"] = n.get("label") or n["id"]
        sets = ", ".join(f"n.{_key(k)} = {_literal(v)}" for k, v in props.items())
        stmt = f"MERGE (n:{label} {{id: {_literal(n['id'])}}})"
        if sets:
            stmt += f" SET {sets}"
        lines.append(f"SELECT * FROM cypher('{graph_name}', $$ {stmt} $$) AS (a agtype);")

    for e in edges:
        src_t = node_types.get(_type_of(nodes, e["source"]), "Node")
        dst_t = node_types.get(_type_of(nodes, e["target"]), "Node")
        rel = _rel_type(e["type"])
        props = dict(e.get("props") or {})
        stmt = (
            f"MATCH (a:{src_t} {{id: {_literal(e['source'])}}}), "
            f"(b:{dst_t} {{id: {_literal(e['target'])}}}) "
            f"MERGE (a)-[r:{rel}]->(b)"
        )
        if props:
            stmt += " SET " + ", ".join(f"r.{_key(k)} = {_literal(v)}" for k, v in props.items())
        lines.append(f"SELECT * FROM cypher('{graph_name}', $$ {stmt} $$) AS (a agtype);")

    return "\n".join(lines) + "\n"


# ── orchestration ─────────────────────────────────────────────────────────────
def export_graph(out_dir: Path | None = None, lake: Path | None = None) -> dict[str, Path]:
    """Write cypher + AGE SQL exports; returns {format: path}."""
    out_dir = Path(out_dir or DEFAULT_OUT)
    ensure_dir(out_dir)
    nodes, edges = load_graph(lake)

    cypher_path = out_dir / "knowledge_graph.cypher"
    cypher_path.write_text(to_cypher(nodes, edges), encoding="utf-8")

    age_path = out_dir / "knowledge_graph_age.sql"
    age_path.write_text(to_age_sql(nodes, edges), encoding="utf-8")

    return {"cypher": cypher_path, "age": age_path}
