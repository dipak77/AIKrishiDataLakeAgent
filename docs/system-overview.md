# System Overview & Flows (Krushi Mitra / AIKrishiDataLake)

> In-depth companion to `architecture.md` (design principles), `data-model.md`
> (table semantics), `live-ingestion.md` (connectors) and `source-registry.md`
> (governance). This document describes **what actually exists today**, the
> component catalog, and the end-to-end request/data flows, and is anchored to
> the shipped code at HEAD `2f06904`.

---

## 1. Reading map

| Concern | Document |
|---|---|
| Design principles, medallion, storage, ingestion | `architecture.md` |
| Table semantics, evidence-vs-recommendation, lineage | `data-model.md` |
| Live connectors + egress notes | `live-ingestion.md` |
| Source governance | `source-registry.md` |
| Provenance / licensing / authority | `provenance-and-licensing.md` |
| Retrieval & scale-out tracks (V5-A…V5-E) | `v5-plan.md` |
| Dual-Engine Context Gateway blueprint | `v6-plan.md` |
| DECG implementation review | `decg-review.md` |
| Full evaluation, coverage & gap analysis | `evaluation-report.md` |

---

## 2. High-level architecture

```
                    ┌────────────────────────────────────────────────┐
                    │   Ingest (connectors/)                         │
                    │   government/ research/ web/ vision/           │
                    │   agmarknet, data.gov, imd, kcc, soil_health,  │
                    │   fao, icar, research_pdf, crawler, ...        │
                    └──────────────────────┬─────────────────────────┘
                                           │ (offline → fixtures)
                                           ▼
                    ┌────────────────────────────────────────────────┐
                    │   Medallion lake  data/lake/agrilake.duckdb    │
                    │   bronze (immutable) → silver → gold (27 tbls) │
                    └──────────────────────┬─────────────────────────┘
                                           │
        ┌──────────────────────────────────┼───────────────────────────────┐
        ▼                                  ▼                                ▼
 knowledge_graph/                 domain/ (catalog, models,         pipelines/
 build.py → graph_nodes(1489)     seed_data = the OKF source        entities, language,
 export.py → Cypher/AGE SQL       of truth; 24 seed CSVs            geocode, quality, logging
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
           reasoning/  (the "reasoning substrate")
           ├─ nlu.py            trained intent + NER (V5-F)
           ├─ graph_query.py    deterministic OKF graph engine
           ├─ rag.py            hybrid BM25 ⊕ dense retrieval (V5-A)
           ├─ advisory/fertilizer/mandi/weather/crop_plan/diagnose
           ├─ guardrails.py     sanitize + injection block (V6)
           └─ gateway.py        Dual-Engine Context Gateway (V6)
                       │
                       ▼
           assistant.py  (orchestrates engines behind one `ask()`)
                       │
                       ▼
           apps/api/main.py  (FastAPI)  →  apps/web/index.html  (UI)
```

**Design invariants** (unchanged from the blueprint): every record carries
`source` + `quality`; bronze is immutable; silver normalizes; gold is
app-ready; evidence is stored separately from recommendations; original
Indian-language text is preserved alongside English; deterministic retrieval
for critical operational rules (zero-hallucination path).

---

## 3. Component catalog (shipped state)

### 3.1 Data & ontology — `domain/`, `data/seeds/`
- `domain/seed_data.py` — single source of truth for 24 committed seed CSVs
  (drift-gated by `scripts/verify_seeds.py`).
- `domain/catalog.py` — lookup structures (crops by canonical/alias, geography).
- `domain/models.py` — Pydantic record models (schema source).

### 3.2 Lake — `data/lake/agrilake.duckdb`
- **gold** schema, 27 tables (verified): crops(116), geography(800 rows =
  36 states/UTs + 764 districts), diseases(30), pests(21), nutrients(12),
  deficiencies(13), fertilizers(18), pesticides(18), weeds(8), biocontrol(9),
  biofertilizer(6), seasons(5), growth stages(12), soil(8), markets(12),
  calendar(60 + 3 overrides), crop×season(58), nutrient requirement(45),
  fertilizer×nutrient(29), subdistrict(242), graph_nodes(1489),
  graph_edges(1706), authority_levels(8), soil_test_interpretation(12), meta.
- Note: **bronze/silver are pipeline concepts only** — the shipped DB
  materializes gold directly (see gap G1 in `evaluation-report.md`).

### 3.3 Ingestion — `connectors/`
`base.py` (plugin contract) + `government/` (agmarknet, data_gov, imd, kcc,
soil_health), `research/` (fao, icar, research_pdf), `web/` (crawler,
article_parser, license_checker), `vision/` (scaffold). Each falls back to
bundled fixtures when offline; orchestrated by `scripts/ingest_live.py`.

### 3.4 Pipelines — `pipelines/`
`entities.py` (crop/geo resolution), `language.py` (script detection,
Devanagari disambiguation, ITRANS-lite, pluggable MT), `geocode.py`
(lake-backed subdistrict resolution), `quality.py`, `logging.py`, `retry.py`,
`storage.py`, `config.py`.

### 3.5 Knowledge graph — `knowledge_graph/`
`build.py` builds `gold.graph_nodes/edges` from seeded ontologies;
`export.py` emits Neo4j Cypher + Apache AGE SQL. Query API in
`reasoning/graph_query.py`.

### 3.6 Reasoning — `reasoning/`
| Module | Role | Status |
|---|---|---|
| `nlu.py` | Naive-Bayes intent + BIO NER, trained offline, cached model | ✅ shipped |
| `graph_query.py` | deterministic OKF traversal (neighbors, health map, symptom candidates, path, summary) | ✅ shipped |
| `rag.py` | hybrid BM25 ⊕ dense, RRF, authority weighting, `evidence_for_diagnosis` | ✅ shipped |
| `embeddings.py` | dependency-free dense embeddings (hashing trick) + query expansion | ✅ shipped |
| `guardrails.py` | input sanitize + injection block | ✅ shipped (V6) |
| `gateway.py` | Dual-Engine Context Gateway orchestrator | ✅ shipped (V6) |
| `assistant.py` | single `ask()` entry point used by the API/CLI | ✅ shipped |
| `diagnose.py` | symptom → candidate differential | ✅ shipped |
| `advisory.py` | fertilizer (crop × stage × soil) | ✅ shipped |
| `mandi.py` / `weather.py` / `crop_plan.py` | price, agromet, calendar engines | ✅ shipped |
| `symptoms.py` | Indic-aware symptom tokenizer + match scoring | ✅ shipped |

### 3.7 Vision — `vision/`
`inference.py` — dependency-free PNG decoder + HSV colour descriptor +
pluggable backend interface (heuristic shipped; ONNX/TFLite/transformers
opt-in stubs). `scripts/analyze_image.py` CLI.

### 3.8 API & UI — `apps/`
FastAPI service `apps/api/main.py` (v0.5.0) + single-page web UI
`apps/web/index.html` (relative `/api/…` URLs, preview-proxy safe).

| Method | Route | Backs onto |
|---|---|---|
| POST | `/api/query` | `assistant.ask()` |
| POST | `/api/diagnose` | `reasoning.diagnose` |
| POST | `/api/fertilizer` | `reasoning.advisory` |
| GET | `/api/mandi`, `/api/markets` | `reasoning.mandi` |
| GET | `/api/weather` | `reasoning.weather` |
| GET | `/api/plan`, `/api/plan/sow` | `reasoning.crop_plan` |
| GET | `/api/evidence` | `reasoning.rag` |
| GET | `/api/graph/summary\|neighbors\|health\|candidates` | `reasoning.graph_query` |
| POST | `/api/gateway` | `reasoning.gateway` (DECG) |
| GET | `/health` | liveness + graph summary |
| GET | `/` | web UI |

### 3.9 Ops — `scripts/`, `infrastructure/`, `Makefile`
`bootstrap.py` (autonomous build), `seed_lake.py`, `build_gold.py`,
`build_graph.py`, `validate.py`, `verify_seeds.py`, `export_graph.py`,
`eval_nlu.py`, `import_lgd.py`, `ingest_live.py`, plus CLI runners per engine.
`Makefile` aggregates (`bootstrap`, `check`, `verify-seeds`, `serve`,
`gateway`, …). `infrastructure/docker-compose.yml` documents the scale-out
path.

---

## 4. Data flow (ingestion → gold)

```
connectors (live, else fixture) ──► bronze (raw, immutable; not materialized
   in shipped DB) ──► silver (normalized; not materialized) ──► gold tables
   (27) ──► knowledge_graph.build ──► graph_nodes/edges ──► reasoning engines
   ──► assistant / API ──► farmer answer + citations + provenance
```

Seed drift is gated: `scripts/verify_seeds.py` asserts the 24 CSVs match
`seed_data.py`; CI runs the full pytest suite.

---

## 5. Request flow — assistant (single engine) vs gateway (dual engine)

### 5.1 `POST /api/query` (classic assistant)
```
query ─► language detect (mr/hi/ta/te/en)
      ─► nlu.get_pipeline().predict  → intent + entities (crop/symptoms/location/stage)
      ─► route:
           diagnosis  → reasoning.diagnose (graph/OKF)
           fertilizer → reasoning.advisory
           mandi      → reasoning.mandi
           weather    → reasoning.weather
           crop_plan  → reasoning.crop_plan
           evidence   → reasoning.rag.hybrid_search
           general    → deterministic general answer
      ─► as_dict() → {language, intent, intent_confidence, entities, answers, citations}
```

### 5.2 `POST /api/gateway` (DECG — the V6 flow)

```
query ─► guardrails.sanitize()          (control chars, 2000-char cap,
                                           10 injection patterns)
      ── blocked? ──► empty payload {guard.blocked=True, citations=[]}
      ─► nlu.predict() → intents + entities
      ─► classify_path():  diagnosis ≥0.3 or (crop+symptoms) → hybrid
                            evidence/general ≥0.3              → exploratory
                            else                                → canonical
      ─► plan_subqueries(): health_map / symptom_candidates / advisory / evidence tasks
      ─► engines run CONCURRENTLY (asyncio.to_thread):
            canonical   → _graph_segments()  (OKF: graph_query + advisory)
            exploratory → _evidence_segments() (rag.hybrid_search)
            hybrid      → BOTH via asyncio.gather
      ─► RRF fusion (k=60) → de-dupe by (source,title) → deterministic
         rerank (dense cosine + authority) → token-budget compaction
      ─► GatewayResult.to_dict() → {routing_path, segments{graph,evidence},
         guard, stats{engine_contrib, elapsed_ms, dedupe_removed}, citations}
```

**Latency budget (measured, warm path):** canonical ≈ 21 ms · hybrid ≈ 42 ms ·
injection block ≈ 0.05 ms. Cold first call ≈ 0.9 s (NLU model load + index
build) — see `decg-review.md` for the warm-up recommendation.

---

## 6. Multilingual flow

```
input ─► pipelines.language detect_script ─► Devanagari (hi/mr disambiguation)
      ─► symptom lexicon lookup (hi/mr/ta/te → English) in reasoning.symptoms
      ─► entities: Indic crop aliases (domain.seed_data.CROP_ALIASES) +
          Indic geography via pipelines.entities/geocode
      ─► output: English reasoning + Indic-preserved evidence; translation
          only via pipelines.language.translate() (lexicon default, IndicTrans2
          opt-in — NOT wired with real weights yet → gap G6)
```

## 7. Vision flow (scaffold)

```
image (PNG bytes) ─► vision.inference.decode_image (stdlib PNG decoder)
                  ─► HSV colour descriptor ─► heuristic backend
                  ─► candidates → dim_disease/dim_pest ids
        (real ONNX/TFLite/transformers backends are opt-in stubs — gap G5)
```

## 8. Scale-out & production path

Single-node DuckDB + Parquet today; `infrastructure/docker-compose.yml` and
`architecture.md` document the documented (not yet deployed) path to
object-storage bronze, Arrow/Parquet silver, and an external graph store
(Neo4j/AGE — already exportable via `scripts/export_graph.py`).
