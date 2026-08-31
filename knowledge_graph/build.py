"""Build a JSON knowledge graph from the seed ontologies.

Enables agronomic reasoning beyond RAG:

    Tomato ──hasDisease──→ Early Blight ──causedBy──→ Alternaria solani
      ├──hasPest──→ Fruit Borer
      └──season──→ Kharif

Output: data/gold/knowledge_graph.json (nodes + edges). Migrates to Neo4j/AGE
in a later milestone.
"""

from __future__ import annotations

from typing import Any

from domain.seed_data import (
    CROP_SEASON,
    CROPS,
    DISEASES,
    GEOGRAPHY,
    PESTS,
)


def build_knowledge_graph() -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(nid: str, ntype: str, label: str, props: dict[str, Any] | None = None) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": label, "props": props or {}}

    def add_edge(src: str, dst: str, etype: str, props: dict[str, Any] | None = None) -> None:
        edges.append({"source": src, "target": dst, "type": etype, "props": props or {}})

    # Crops
    for crop in CROPS:
        add_node(crop["crop_id"], "crop", crop["canonical_en"], {
            "scientific_name": crop["scientific_name"],
            "family": crop["family"],
            "type": crop["type"],
            "group": crop["group"],
        })

    # Geography (states)
    for state in GEOGRAPHY:
        add_node(state["state_code"], "state", state["name"], {
            "type": state["type"],
            "agroclimatic_zone": state["agroclimatic_zone"],
        })
        for dist in state.get("districts", []):
            add_node(dist["code"], "district", dist["name"], {"state": state["state_code"]})
            add_edge(dist["code"], state["state_code"], "inState")

    # Diseases + pathogens
    for disease in DISEASES:
        add_node(
            disease["disease_id"], "disease", disease["name"],
            {"pathogen_type": disease.get("pathogen_type"), "crop": disease.get("crop")},
        )
        if disease.get("crop_id") in nodes:
            add_edge(disease["crop_id"], disease["disease_id"], "hasDisease")
            add_edge(disease["disease_id"], disease["crop_id"], "affects")
        agent = disease.get("causal_agent")
        if agent:
            pid = f"PATHOGEN:{agent.lower()}"
            add_node(pid, "pathogen", agent, {"pathogen_type": disease.get("pathogen_type")})
            add_edge(disease["disease_id"], pid, "causedBy")

    # Pests
    for pest in PESTS:
        add_node(pest["pest_id"], "pest", pest["name"], {
            "scientific_name": pest.get("scientific_name"),
        })
        for host in str(pest.get("crop_hosts", "")).split("|"):
            host = host.strip()
            # match host common name against canonical crop name
            for crop_id, node in nodes.items():
                if node["type"] == "crop" and host.lower() in node["label"].lower():
                    add_edge(pest["pest_id"], crop_id, "pestOf")
                    add_edge(crop_id, pest["pest_id"], "hasPest")

    # Seasons
    for cs in CROP_SEASON:
        add_node(cs["season_id"], "season", cs["season_id"].replace("SEASON_", "").title())
        if cs["crop_id"] in nodes:
            add_edge(cs["crop_id"], cs["season_id"], "hasSeason")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": {t: sum(1 for n in nodes.values() if n["type"] == t) for t in sorted({n["type"] for n in nodes.values()})},
        },
    }
