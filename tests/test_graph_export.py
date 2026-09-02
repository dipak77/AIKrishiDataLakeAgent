"""Tests for V5-B: Neo4j Cypher + Apache AGE graph export."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_graph.export import (  # noqa: E402
    _esc,
    _literal,
    export_graph,
    load_graph,
    to_age_sql,
    to_cypher,
)
from scripts.seed_lake import main as seed_main  # noqa: E402


def _seeded():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])


def test_load_graph_counts():
    _seeded()
    nodes, edges = load_graph()
    assert len(nodes) >= 1400
    assert len(edges) >= 1600
    assert all("id" in n and "type" in n for n in nodes)
    assert all("source" in e and "target" in e and "type" in e for e in edges)


def test_cypher_contains_all_nodes_and_edges():
    _seeded()
    nodes, edges = load_graph()
    cypher = to_cypher(nodes, edges)
    assert cypher.count("\nMERGE (n:") == len(nodes)
    assert cypher.count(" MERGE (a)-[r:") == len(edges)
    assert "FOR (n:Crop) REQUIRE n.id IS UNIQUE" in cypher
    assert "MATCH (a:Crop {id: 'CROP_TOMATO'}), (b:Disease" in cypher


def test_cypher_is_idempotent():
    _seeded()
    nodes, edges = load_graph()
    cypher = to_cypher(nodes, edges)
    assert "MERGE (n:" in cypher
    assert "CREATE (" not in cypher  # no bare CREATE nodes


def test_age_sql_structure():
    _seeded()
    nodes, edges = load_graph()
    sql = to_age_sql(nodes, edges)
    assert sql.count("SELECT * FROM cypher('agrilake', $$ MERGE (n:") == len(nodes)
    assert sql.count("SELECT * FROM cypher('agrilake', $$ MATCH (a:") == len(edges)
    assert "AS (a agtype);" in sql


def test_string_escaping():
    assert _esc("a'b") == "a\\'b"
    assert _esc("a\\b") == "a\\\\b"
    assert _literal("it's") == "'it\\'s'"
    assert _literal(None) == "null"
    assert _literal(True) == "true"
    assert _literal([1, "a"]) == "[1, 'a']"
    assert _literal({"k": "v"}) == "{k: 'v'}"


def test_cypher_escapes_quotes_in_props():
    nodes = [{"id": "X", "type": "disease", "label": "O'Brien spot", "props": {"note": "it's bad"}}]
    cypher = to_cypher(nodes, [])
    assert "O\\'Brien spot" in cypher
    assert "it\\'s bad" in cypher
    # every single quote is paired (escaped), so the literal is well-formed
    assert cypher.count("\\'") == 2


def test_export_graph_writes_files(tmp_path):
    _seeded()
    paths = export_graph(tmp_path)
    assert (tmp_path / "knowledge_graph.cypher").is_file()
    assert (tmp_path / "knowledge_graph_age.sql").is_file()
    cypher = (tmp_path / "knowledge_graph.cypher").read_text(encoding="utf-8")
    assert cypher.startswith("// Agri Intelligence Lake")
    assert len(paths) == 2
