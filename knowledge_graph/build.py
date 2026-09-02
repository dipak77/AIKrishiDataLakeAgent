"""Build a JSON knowledge graph from the seed ontologies.

Enables agronomic reasoning beyond RAG:

    Tomato ──hasDisease──→ Early Blight ──causedBy──→ Alternaria solani
      ├──hasPest──→ Fruit Borer
      ├──season──→ Kharif
    Urea ──contains──→ N (46%)
    Zinc deficiency ──deficiencyOf──→ NUT_ZN ──onCrop──→ Rice
    Early Blight ──hasSymptom──→ leaf spots / yellowing

Output: data/gold/knowledge_graph.json (nodes + edges). Migrates to Neo4j/AGE
in a later milestone.
"""

from __future__ import annotations

import re
from typing import Any

from domain.seed_data import (
    CROP_SEASON,
    CROPS,
    DISEASES,
    DISEASE_CLINICAL,
    FERTILIZERS,
    FERTILIZER_NUTRIENTS,
    GEOGRAPHY,
    NUTRIENTS,
    NUTRIENT_DEFICIENCIES,
    PESTS,
    PEST_IPM,
)

_SYMPTOM_TOKEN = re.compile(r"[^a-z0-9 ]+")


def _symptom_tokens(text: str | None) -> list[str]:
    """Crude but useful symptom tokenization (multi-word phrases via bigrams)."""
    if not text:
        return []
    cleaned = _SYMPTOM_TOKEN.sub(" ", text.lower())
    words = [w for w in cleaned.split() if len(w) > 2]
    stop = {"with", "and", "the", "are", "from", "that", "this", "for", "appears", "appear"}
    words = [w for w in words if w not in stop]
    tokens = list(words)
    tokens += [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    return tokens


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

    # Geography (states + districts)
    for state in GEOGRAPHY:
        add_node(state["state_code"], "state", state["name"], {
            "type": state["type"],
            "agroclimatic_zone": state["agroclimatic_zone"],
        })
        for dist in state.get("districts", []):
            add_node(dist["code"], "district", dist["name"], {"state": state["state_code"]})
            add_edge(dist["code"], state["state_code"], "inState")

    # Nutrients
    for nutrient in NUTRIENTS:
        add_node(nutrient["nutrient_id"], "nutrient", nutrient["name"], {
            "symbol": nutrient["symbol"],
            "role": nutrient.get("role"),
        })

    # Fertilizers + fertilizer → nutrient composition
    for fert in FERTILIZERS:
        add_node(fert["fertilizer_id"], "fertilizer", fert["name"], {
            "category": fert["category"],
        })
    for fn in FERTILIZER_NUTRIENTS:
        if fn["fertilizer_id"] in nodes and fn["nutrient_id"] in nodes:
            add_edge(fn["fertilizer_id"], fn["nutrient_id"], "contains", {
                "form": fn["form"],
                "percent": fn["percent"],
            })

    # Nutrient deficiencies
    for d in NUTRIENT_DEFICIENCIES:
        add_node(d["deficiency_id"], "deficiency", f"{d['nutrient_id'].replace('NUT_','')} deficiency", {
            "crop": d["crop"],
            "symptoms": d.get("symptoms"),
            "correction": d.get("correction"),
        })
        add_edge(d["deficiency_id"], d["nutrient_id"], "deficiencyOf")
        if d.get("crop_id") in nodes:
            add_edge(d["crop_id"], d["deficiency_id"], "hasDeficiency")
            add_edge(d["deficiency_id"], d["crop_id"], "onCrop")
        for token in _symptom_tokens(d.get("symptoms")):
            add_node(f"SYM:{token}", "symptom", token)
            add_edge(d["deficiency_id"], f"SYM:{token}", "hasSymptom")

    # Diseases + pathogens + symptoms
    for disease in DISEASES:
        add_node(
            disease["disease_id"], "disease", disease["name"],
            {
                "pathogen_type": disease.get("pathogen_type"),
                "crop": disease.get("crop"),
                "growth_stage": (DISEASE_CLINICAL.get(disease["disease_id"]) or {}).get("growth_stage"),
                "differential_diagnosis": (DISEASE_CLINICAL.get(disease["disease_id"]) or {}).get("differential_diagnosis"),
            },
        )
        if disease.get("crop_id") in nodes:
            add_edge(disease["crop_id"], disease["disease_id"], "hasDisease")
            add_edge(disease["disease_id"], disease["crop_id"], "affects")
        agent = disease.get("causal_agent")
        if agent:
            pid = f"PATHOGEN:{agent.lower()}"
            add_node(pid, "pathogen", agent, {"pathogen_type": disease.get("pathogen_type")})
            add_edge(disease["disease_id"], pid, "causedBy")
        for token in _symptom_tokens(disease.get("symptoms")):
            add_node(f"SYM:{token}", "symptom", token)
            add_edge(disease["disease_id"], f"SYM:{token}", "hasSymptom")

    # Pests
    for pest in PESTS:
        add_node(pest["pest_id"], "pest", pest["name"], {
            "scientific_name": pest.get("scientific_name"),
            "economic_threshold": (PEST_IPM.get(pest["pest_id"]) or {}).get("economic_threshold"),
        })
        for host in str(pest.get("crop_hosts", "")).split("|"):
            host = host.strip()
            for crop_id, node in nodes.items():
                if node["type"] == "crop" and host.lower() in node["label"].lower():
                    add_edge(pest["pest_id"], crop_id, "pestOf")
                    add_edge(crop_id, pest["pest_id"], "hasPest")
        for token in _symptom_tokens(pest.get("damage_symptoms")):
            add_node(f"SYM:{token}", "symptom", token)
            add_edge(pest["pest_id"], f"SYM:{token}", "hasSymptom")

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
