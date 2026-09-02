# Phase 4 — Krushi Mitra: the integrated assistant (top-class upgrade)

> Status: **planned + in progress**. This phase turns the lake + the
> per-domain engines (diagnosis, fertilizer, mandi, weather, planning, RAG)
> into a single *product surface*: a multilingual farmer assistant with a
> graph-native lakehouse, a REST API, and a browser UI.

## 1. Vision

Phases 1–3 built a robust, self-configuring lake and seven independent
reasoning engines. Phase 4 makes them **talk to each other** behind one
interface:

```
                    ┌──────────────────────────────────────────────┐
   farmer query ──▶ │  Krushi Mitra assistant (reasoning/assistant) │
  ("टोमॅटोवर काळे   │   detect language → intent → entities         │
    डाग, Pune")     │   (crop / district / stage / symptoms)        │
                    │   → route to the right engine(s)              │
                    └───────────────┬──────────────────────────────┘
                                    │
        ┌──────────────┬────────────┼───────────────┬──────────────┐
        ▼              ▼            ▼               ▼              ▼
   diagnose()     fertilizer()   mandi()        weather()      evidence()
        └──────────────┴────────────┴───────────────┴──────────────┘
                                    │
                    ┌───────────────▼──────────────────────────────┐
                    │  graph-native lakehouse (gold.graph_*)        │
                    │  recursive CTE traversal + evidence citations │
                    └──────────────────────────────────────────────┘
```

## 2. What's new in this phase

### Track 12 — Graph-native lakehouse + graph query API
Today the knowledge graph is a JSON file (1489 nodes / 1706 edges). This
upgrades it to **queryable DuckDB tables** (`gold.graph_nodes`,
`gold.graph_edges`) with a traversal API — recursive CTE, no Neo4j dependency
(yet):

- `graph_neighbors(id)` · `graph_path(from, to)` ·
  `crop_health_map(crop)` (diseases/pests/deficiencies + symptoms) ·
  `symptom_candidates(symptoms)` (reverse index symptom → disease/pest/deficiency).
- Lets the assistant answer "what's wrong with my tomato" and "what does Khaira
  look like" from the graph, not just the retriever.

### Track 13 — Krushi Mitra assistant (intent routing + composition)
`reasoning/assistant.py` — the product brain. A farmer query in English, Hindi,
Marathi, Tamil or Telugu is classified into an intent, entities are extracted,
the right engine(s) run, and a single **structured, evidence-cited** answer is
composed (observation ≠ recommendation ≠ evidence, per the blueprint).

- Intents: `diagnosis`, `fertilizer`, `mandi_price`, `weather`, `crop_planning`,
  `evidence` (RAG), `general` (graph + RAG fallback).
- Routing is keyword + lexicon based (the existing `SYMPTOM_LEXICON` and
  crop/geography lookups), so it works offline and in Indic scripts.
- Multi-engine: e.g. "tomato black spots in Pune" → diagnosis **+** weather
  environment **+** evidence citations in one response.

### Track 14 — REST API service (FastAPI)
`apps/api/main.py` — a single service exposing every engine + the assistant:

- `GET  /health` · `POST /query` (assistant) · `POST /diagnose` ·
  `POST /fertilizer` · `GET  /mandi` · `GET  /weather` · `GET  /plan` ·
  `GET  /evidence` · `GET  /graph/*`
- Serves the web UI + OpenAPI docs; CORS permissive for the preview origin;
  started with `agrilake-serve` / `make serve`.

### Track 15 — Krushi Mitra web UI
`apps/web/index.html` — a single-page chat that calls the relative `/api/…`
endpoints (no localhost hardcoding), renders the structured answer with
evidence citations, and degrades gracefully if the backend is cold.

## 3. Milestones

| # | Milestone | Deliverable | Depends |
|---|---|---|---|
| M8 | Graph-native lakehouse | `gold.graph_nodes/edges` + `reasoning/graph_query.py` | — |
| M9 | Assistant router | `reasoning/assistant.py` + intent/entity extraction | M8 |
| M10 | REST API | `apps/api/main.py` + `agrilake-serve` | M9 |
| M11 | Web UI | `apps/web/index.html` (live preview) | M10 |

## 4. Acceptance criteria

- `agrilake-serve` boots the API on `0.0.0.0`; `/health` returns ok; the web UI
  loads under the live-preview origin.
- A single `POST /query` with Indic text ("टोमॅटोवर काळे डाग") returns a
  structured answer with the right intent and evidence citations.
- `gold.graph_nodes` / `gold.graph_edges` exist in the lake and
  `symptom_candidates("black spots")` returns ranked diseases via graph traversal.
- All existing 86 tests remain green; new tests cover graph queries, the
  assistant, and the API.

## 5. Risks

- **FastAPI adds a dependency** — it's a pure-python web layer; the offline
  engine code paths remain untouched (the assistant imports engines directly).
- **Preview origin** — the UI must call relative URLs only (no `localhost`);
  CORS + a wildcard origin allow the proxy to embed it.
- **Intent classification is heuristic** — acceptable for V1 of the assistant;
  a trained classifier / LLM re-rank lands in V5.

## 6. Later (V5+)

Trained intent/NER, embeddings + hybrid retrieval (Qdrant), Neo4j/AGE graph,
vision model inference, IndicTrans2 MT behind `language.translate()`, full LGD
geography import.
