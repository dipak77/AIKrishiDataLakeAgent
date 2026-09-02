"""Graph query API (Track 12).

Queries the graph-native lakehouse (`gold.graph_nodes`, `gold.graph_edges`)
with recursive CTE traversals — no Neo4j dependency. If the tables are absent,
`ensure_graph_tables()` builds them from the seed ontologies on first use.

Helpers are domain-shaped for the assistant:

  - graph_neighbors(id, direction)      → direct neighbors with edge types
  - crop_health_map(crop)               → diseases/pests/deficiencies + symptoms
  - symptom_candidates(text)            → ranked (disease|pest|deficiency) by
                                          matched symptom tokens (reverse index)
  - graph_path(from, to)                → shortest path (recursive CTE, capped)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from pipelines.storage import LAKE_DIR, get_read_connection

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"


def ensure_graph_tables(lake: Path | None = None) -> None:
    """Build graph tables into the lake if they don't exist yet."""
    from knowledge_graph.build import build_knowledge_graph
    from scripts.build_graph import persist_graph_tables

    lake = Path(lake or DEFAULT_LAKE)
    if not lake.exists():
        persist_graph_tables(build_knowledge_graph(), lake)
        return
    con = get_read_connection(lake)
    has = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='gold' AND table_name='graph_nodes'"
    ).fetchone()[0] > 0
    if not has:
        persist_graph_tables(build_knowledge_graph(), lake)


def graph_neighbors(
    node_id: str,
    *,
    direction: str = "out",
    lake: Path | None = None,
) -> list[dict[str, Any]]:
    """Return neighbors of `node_id` (direction: out | in | both)."""
    lake = Path(lake or DEFAULT_LAKE)
    ensure_graph_tables(lake)
    con = get_read_connection(lake)
    rows: list[tuple[Any, ...]] = []
    if direction in ("out", "both"):
        rows += con.execute(
            "SELECT e.type, n.id, n.type, n.label FROM gold.graph_edges e "
            "JOIN gold.graph_nodes n ON n.id = e.target WHERE e.source = ?",
            [node_id],
        ).fetchall()
    if direction in ("in", "both"):
        rows += con.execute(
            "SELECT e.type, n.id, n.type, n.label FROM gold.graph_edges e "
            "JOIN gold.graph_nodes n ON n.id = e.source WHERE e.target = ?",
            [node_id],
        ).fetchall()
    return [
        {"relation": r[0], "id": r[1], "type": r[2], "label": r[3]} for r in rows
    ]


def crop_health_map(crop: str, *, lake: Path | None = None) -> dict[str, Any]:
    """Diseases, pests and deficiencies linked to a crop, with symptoms."""
    from pipelines.entities import resolve_crop

    crop_row = resolve_crop(crop)
    if not crop_row:
        return {"crop": crop, "found": False, "diseases": [], "pests": [], "deficiencies": []}
    crop_id = crop_row["crop_id"]

    out: dict[str, Any] = {
        "crop": crop_row["canonical_en"],
        "crop_id": crop_id,
        "found": True,
        "diseases": [],
        "pests": [],
        "deficiencies": [],
    }
    for kind, rel in (("diseases", "hasDisease"), ("pests", "hasPest"), ("deficiencies", "hasDeficiency")):
        for nb in graph_neighbors(crop_id, direction="out", lake=lake):
            if nb["relation"] == rel:
                symptoms = [
                    s["label"]
                    for s in graph_neighbors(nb["id"], direction="out", lake=lake)
                    if s["relation"] == "hasSymptom"
                ]
                out[kind].append(
                    {"id": nb["id"], "label": nb["label"], "symptoms": symptoms[:8]}
                )
    return out


def symptom_candidates(
    symptoms: str,
    *,
    crop: str | None = None,
    top_n: int = 8,
    lake: Path | None = None,
) -> list[dict[str, Any]]:
    """Reverse-index symptom tokens → disease/pest/deficiency candidates.

    Ranks by the number of matched symptom labels in the graph.
    """
    from reasoning.symptoms import match_score, tokenize_symptoms

    lake = Path(lake or DEFAULT_LAKE)
    ensure_graph_tables(lake)
    tokens = tokenize_symptoms(symptoms)
    if not tokens:
        return []

    con = get_read_connection(lake)
    nodes = con.execute("SELECT id, type, label FROM gold.graph_nodes").fetchall()
    symptom_nodes = con.execute(
        "SELECT id FROM gold.graph_nodes WHERE type = 'symptom'"
    ).fetchall()

    # symptom label → entity nodes that link to it (via hasSymptom)
    sym_ids = {r[0] for r in symptom_nodes}
    scored: dict[str, dict[str, Any]] = {}
    for (sym_id,) in symptom_nodes:
        label = next((n[2] for n in nodes if n[0] == sym_id), "")
        if match_score(tokens, label) == 0:
            continue
        for (etype, entity_id) in con.execute(
            "SELECT type, source FROM gold.graph_edges WHERE target = ? AND type = 'hasSymptom'",
            [sym_id],
        ).fetchall():
            ent = next((n for n in nodes if n[0] == entity_id), None)
            if ent is None or ent[1] not in ("disease", "pest", "deficiency"):
                continue
            rec = scored.setdefault(
                entity_id,
                {"id": entity_id, "type": ent[1], "label": ent[2], "matched": 0, "symptoms": []},
            )
            rec["matched"] += 1
            rec["symptoms"].append(label)

    ranked = sorted(scored.values(), key=lambda r: -r["matched"])
    if crop:
        from pipelines.entities import resolve_crop

        crop_row = resolve_crop(crop)
        crop_id = crop_row["crop_id"] if crop_row else None
        if crop_id:
            ranked = [r for r in ranked if _entity_on_crop(r["id"], crop_id, lake)]
    return ranked[:top_n]


def _entity_on_crop(entity_id: str, crop_id: str, lake: Path) -> bool:
    con = get_read_connection(lake)
    return con.execute(
        "SELECT count(*) FROM gold.graph_edges "
        "WHERE source = ? AND target = ? AND type IN ('hasDisease','hasPest','hasDeficiency')",
        [crop_id, entity_id],
    ).fetchone()[0] > 0


def graph_path(
    src: str,
    dst: str,
    *,
    max_depth: int = 5,
    lake: Path | None = None,
) -> list[dict[str, Any]]:
    """Shortest path src → dst via recursive CTE (capped at max_depth)."""
    lake = Path(lake or DEFAULT_LAKE)
    ensure_graph_tables(lake)
    con = get_read_connection(lake)
    rows = con.execute(
        """
            WITH RECURSIVE walk(id, path, depth) AS (
                SELECT target, [source, target], 1
                FROM gold.graph_edges WHERE source = ?
                UNION ALL
                SELECT e.target, list_append(w.path, e.target), w.depth + 1
                FROM gold.graph_edges e JOIN walk w ON e.source = w.id
                WHERE w.depth < ? AND NOT list_contains(w.path, e.target)
            )
            SELECT path, depth FROM walk WHERE id = ?
            ORDER BY depth LIMIT 1
            """,
            [src, max_depth, dst],
        ).fetchall()
    if not rows:
        return []
    path_ids = rows[0][0]
    out = []
    for nid in path_ids:
        r = con.execute(
            "SELECT type, label FROM gold.graph_nodes WHERE id = ?", [nid]
        ).fetchone()
        out.append({"id": nid, "type": r[0] if r else None, "label": r[1] if r else nid})
    return out


def graph_summary(lake: Path | None = None) -> dict[str, Any]:
    lake = Path(lake or DEFAULT_LAKE)
    ensure_graph_tables(lake)
    con = get_read_connection(lake)
    n = con.execute("SELECT count(*) FROM gold.graph_nodes").fetchone()[0]
    e = con.execute("SELECT count(*) FROM gold.graph_edges").fetchone()[0]
    types = con.execute(
        "SELECT type, count(*) FROM gold.graph_nodes GROUP BY type ORDER BY type"
    ).fetchall()
    return {"nodes": n, "edges": e, "node_types": {t: c for t, c in types}}
