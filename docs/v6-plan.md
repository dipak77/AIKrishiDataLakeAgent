# V6 — Dual-Engine Context Gateway (DECG)

> **Status:** Phase 1 shipped. This is the "next-level" upgrade that turns the
> Krushi Mitra assistant from *one-engine-per-query* into an **asynchronous
> orchestration layer** that routes every query to a deterministic knowledge
> engine, a probabilistic retrieval engine, or both — then fuses, de-duplicates
> and compacts the results into a single clean context payload.

---

## 1. Why this, and how it maps onto what we already ship

The DECG blueprint is a production orchestration pattern. We adopt its
topology wholesale, but every component lands **offline, deterministic, pure
Python** (our standing blueprint non-negotiable: no cloud LLM, no paid API, no
binary weights in the default path — each probabilistic upgrade is a
*pluggable, opt-in* backend, exactly like V5-C/V5-D).

| DECG concept | Our module | Status |
|---|---|---|
| Incoming Query | `apps/api/main.py` (FastAPI) | shipped |
| Guardrails & Intent Classification | `reasoning/guardrails.py` + `reasoning/nlu.py` (V5-F) | **this phase** + shipped |
| Multi-Query Planner | `gateway.plan_subqueries()` (NLU entity-driven) | **this phase** |
| OKF Registry Router / Graph Traversal / YAML metadata match | `reasoning/graph_query.py` + `reasoning/advisory.py` (seed ontology = the OKF, git-backed) | shipped |
| Advanced Hybrid RAG (sparse ⊕ dense) | `reasoning/rag.py::hybrid_search` (V5-A) | shipped |
| Cross-Encoder Rerank | `reasoning/gateway.py` deterministic reranker (dense cosine + authority); real cross-encoder = opt-in backend | **this phase** (stand-in) |
| RRF & Context De-duper | `reasoning/gateway.py::_fuse` | **this phase** |
| App Layer Response Engine | `assistant.ask()` + `/api/gateway` | shipped + **new endpoint** |

The core *new* capability is the middle: **async routing + fusion**, which we
did not have before — previously a query hit exactly one engine.

---

## 2. Adapted architecture

```
                 ┌─────────────────────────┐
                 │   Incoming Query (API)  │
                 └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │ guardrails.sanitize()   │   control chars, injection flags, cap
                 └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │ nlu.get_pipeline()      │   trained intent + NER (V5-F)
                 │  intent / entities      │
                 └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │ gateway.route()         │   CANONICAL | EXPLORATORY | HYBRID
                 │ gateway.plan_subqueries │   crop / symptoms / location → tasks
                 └───────┬─────────┬───────┘
          CANONICAL/HYBRID│         │EXPLORATORY/HYBRID
                         ▼         ▼
       ┌──────────────────────┐  ┌──────────────────────┐
       │ Graph engine         │  │ Hybrid RAG engine    │
       │ (deterministic OKF)  │  │ (probabilistic)      │
       │  • crop health map   │  │  • BM25 ⊕ dense      │
       │  • symptom candidates│  │  • ontology expansion│
       │  • advisory (fert/   │  │  • authority weight  │
       │    weather/plan/mandi│  └──────────┬───────────┘
       └──────────┬───────────┘             │
                  │        asyncio.gather() │  (to_thread — true concurrency)
                  └──────────┬──────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │ RRF fusion + de-dupe    │
                 │ deterministic rerank    │  dense cosine + authority/degree
                 │ context compaction      │  token budget + top-k
                 └───────────┬─────────────┘
                             ▼
                 ┌─────────────────────────┐
                 │ GatewayResult → API /   │
                 │ assistant / downstream  │
                 └─────────────────────────┘
```

---

## 3. Layer design

### Layer A — Guardrails + async classifier & decomposition

- `sanitize()`: strips control characters, normalizes whitespace, enforces a
  2000-char cap, and scans a prompt-injection pattern list (`ignore previous
  instructions`, `system prompt`, `act as …`, `<|im_start|>`, `os.system`, …).
  Blocked queries return a flagged empty payload — never a fabricated answer.
- `classify_path()` maps the V5-F intent to a routing path:
  - `diagnosis` → **HYBRID** (graph candidates + supporting evidence)
  - `evidence` / `general` (no crop) → **EXPLORATORY** (RAG only)
  - everything else → **CANONICAL** (deterministic graph/advisory only)
  - multi-aspect queries (crop **and** location, or symptoms + location) → HYBRID
- `plan_subqueries()` decomposes into a task matrix (crop health map, symptom
  candidates, advisory, expanded evidence) — the blueprint's "sub-query
  expansion", driven by the trained NER rather than an LLM.

### Layer B — Deterministic OKF engine (0-hallucination path)

The git-backed seed CSVs + the persisted DuckDB knowledge graph *are* the OKF.
`_graph_segments()` answers with only ontology-backed facts:
`crop_health_map`, `symptom_candidates`, and the deterministic advisory
engines (fertilizer / weather / crop plan / mandi). No generation — only
retrieval of stored knowledge, so critical rules can't hallucinate.

### Layer C — Sparse-dense hybrid RAG + reranker

`_rag_segments()` runs `hybrid_search` (BM25 ⊕ feature-hashed dense, RRF-fused,
authority-weighted — V5-A) over the expanded query. The **cross-encoder
stand-in** is a deterministic reranker: `score = rrf + 0.5·dense_cosine + 0.001·authority`.
A real cross-encoder (opt-in ONNX) plugs into the same interface later without
changing callers.

### Layer D — RRF & compaction

`_fuse()` merges the graph and RAG ranked lists with Reciprocal Rank Fusion
(k=60), de-duplicates by `(source, title)`, re-scores with the reranker, and
compacts to a token budget (top-k segments, per-segment truncation).

---

## 4. Integration interface (shipped)

```python
from reasoning.gateway import gateway            # sync one-shot
from reasoning.gateway import ContextGateway      # async class (DECG shape)

gw = ContextGateway()
res = await gw.route_and_retrieve("टोमॅटोवर काळे डाग आहेत")
res.routing_path   # "hybrid"
res.segments       # fused, deduped, compacted ContextSegments
res.citations      # provenance (source/url/license/authority)
```

REST: `POST /api/gateway` `{query, crop?, top_k?}` → same payload.

---

## 5. KPIs & how we measure them (offline benchmarks = tests)

| KPI | Target | Measurement |
|---|---|---|
| Deterministic absorption | ≥75% of routine queries route CANONICAL (no vector scan) | routing test matrix |
| Latency | CANONICAL <15 ms; HYBRID <180 ms | `elapsed_ms` in `stats` (perf_counter around `asyncio.gather`) |
| Context precision | no injection fragments; deduped; budget-capped | guardrail + fusion tests assert flags, uniqueness, and ≤ budget |
| Dual-engine coverage | HYBRID queries return segments from **both** engines | `stats.engine_contrib` = {"graph": n, "rag": n} |
| Provenance | every segment carries `source` + citations | result schema test |

---

## 6. Phased rollout

- **Phase 1 (this commit):** guardrails, routing, sub-query planner, async
  dual-engine orchestration, deterministic rerank, RRF fusion + compaction,
  `/api/gateway`, tests.
- **Phase 2:** real cross-encoder (opt-in ONNX) + LLM/IndicTrans2 context
  compactor behind the same backends (mirror V5-C/V5-D opt-in pattern).
- **Phase 3:** learned sub-query planner (upgrade the V5-F NER into a
  decomposition model) + streaming response over the preview proxy.

## 7. Success criteria (Phase 1)

- `tests/test_gateway.py` green: guardrails block injections; routing matrix
  correct; HYBRID queries produce graph **and** rag segments; fusion dedupes
  and caps the budget; async + sync paths agree; `/api/gateway` returns the
  full payload.
- No new heavy dependencies; deterministic (same query → same payload).
- Existing 185 tests stay green (the gateway is additive; `ask()` unchanged).
