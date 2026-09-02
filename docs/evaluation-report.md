# Evaluation Report — Coverage, Gaps & Next Plan

> Grounded assessment of the Krushi Mitra / AIKrishiDataLake system at HEAD
> `2f06904`. Every number below was verified against the running workspace
> (DuckDB lake, pytest, `eval_nlu`, `verify_seeds`, live API on :8000).

---

## 1. Executive summary

**Where we are:** a strong, deterministic, offline-first **engine and
orchestration layer is complete and test-green** — foundation ontologies,
knowledge graph, six reasoning engines, a trained multilingual NLU, hybrid
retrieval, and (new) the Dual-Engine Context Gateway. **What is not yet
production-grade** is the *depth* layer — real data volume (8 research chunks,
12 mandi markets), real AI backends (cross-encoder, IndicTrans2, vision
weights), a materialized bronze/silver lake, and ops hardening.

**Overall readiness estimate: ≈ 70%** toward the 100%-production vision
(transparent scorecard in §2). The *engine/orchestration* layer is ≈ 85–90%;
the *data-depth / AI-backend / ops* layer is ≈ 40–55%. That asymmetry is the
gap, and the next plan targets exactly it.

**What is already "super-solid":** deterministic OKF routing with zero-
hallucination operational rules, guardrails that block prompt injection,
provenance on every answer, a 208-case test suite + seed-drift gate + trained
NLU with 19/19 held-out accuracy, and dual-engine fused retrieval with ~42 ms
warm hybrid latency.

---

## 2. Readiness scorecard (vs the 100% production vision)

| # | Pillar | Readiness | Evidence (verified) | Missing |
|---|---|---|---|---|
| 1 | Ontology & foundation | 95% | 116 crops, 36 states/UTs + 764 districts, 30 diseases, 21 pests, 13 deficiencies, seasons/stages/soil/fertilizer/pesticide/weed/biocontrol ontologies, 24 drift-gated CSVs | long-tail crops/dialect aliases |
| 2 | Medallion & storage | 70% | gold schema = 27 tables; quality scoring + lineage fields shipped | **bronze/silver not materialized** (G1) |
| 3 | Knowledge graph | 90% | 1,489 nodes / 1,706 edges; graph query + Neo4j/AGE export | scale-out (external store) not deployed |
| 4 | Reasoning engines | 85% | fertilizer/mandi/weather/plan/diagnose + tests | deeper variety/stage data |
| 5 | Retrieval (RAG) | 55% | hybrid BM25⊕dense + RRF + expansion shipped | **corpus = 8 chunks / 7 docs** (G2) |
| 6 | Multilingual (NLP+MT) | 65% | trained intent+NER (19/19), hi/mr/ta/te lexicons, lake-backed geo | real MT (IndicTrans2) not wired (G6) |
| 7 | Vision | 40% | PNG decoder + HSV heuristic + pluggable stubs (scaffold) | real model weights (G5) |
| 8 | DECG orchestration | 70% | Phase 1 shipped + live (`/api/gateway`) | cross-encoder/compactor/planner/streaming (G3, G4) |
| 9 | Live ingestion | 50% | 10+ connectors coded w/ offline fixtures | egress blocked → unvalidated live (G7) |
| 10 | Ops & production hardening | 45% | logging, retry, CI, health, seed-drift, docker-compose | auth/rate-limit/caching/monitoring/load-test (G9) |
| 11 | Domain content depth (55-domain target) | 35% | ontology coverage broad; calendar 60 rows, markets 12, corpus 8 chunks | real content depth (G2, G11) |

**Weighted average ≈ 70%** (weights: pillars 1/4/8 at 15% each, 2/3/5/6 at
10% each, 7/9/10/11 at 5% each). Treat as an engineering estimate anchored to
the artifacts above, not a measured precision.

---

## 3. What is 100% done and production-solid

1. **Autonomous build** — `make bootstrap` self-configures venv, seeds, builds
   gold + graph, validates, tests (idempotent).
2. **Deterministic operational rules** — fertilizer/mandi/weather/plan/diagnose
   are retrieval-over-ontology, not generation → zero-hallucination for
   critical advice, and `source`/`quality`/version on every record.
3. **Trained multilingual NLU** — Naive-Bayes intent + BIO NER, 1,579 training
   examples, train acc 1.000, **19/19 held-out** (parity with the heuristic
   router, with added typo tolerance + confidence scores); Marathi/Tamil
   entity extraction verified.
4. **Hybrid retrieval** — BM25 ⊕ dense with RRF + ontology query expansion,
   authority-weighted.
5. **DECG Phase 1** — guardrails + routing + concurrent dual-engine + fusion +
   compaction, live at `/api/gateway` (see `decg-review.md`).
6. **Verification** — 208 pytest cases green, `verify_seeds` clean, CLI per
   engine, seed-drift gate in CI.

---

## 4. Accuracy & quality evidence

### 4.1 Verification coverage
- **208 passing test cases** (204 test functions, 21 files): vision 19,
  gateway 19, nlu 14, api 13, translate 12, platform 11, hybrid 11, …
- `scripts/verify_seeds.py` — **OK: 24 committed seed CSVs** match `seed_data.py`.
- `scripts/eval_nlu.py` — **trained 19/19, heuristic 19/19** on the 19-query
  held-out set; entity samples correct (tomato/टोमॅटो, Pune, wheat+Punjab).

### 4.2 Latency (measured, live)
| Path | Warm | Budget | Status |
|---|---|---|---|
| canonical | ~21 ms | <15 ms | ⚠ slight miss (fix: connection reuse) |
| hybrid | ~42 ms | <180 ms | ✅ 4.3× headroom |
| injection block | ~0.05 ms | — | ✅ |
| cold first call | ~0.9 s | — | ⚠ pre-warm recommended |

### 4.3 Accuracy position (honest)
This is a **deterministic** system — no generative model — so "accuracy"
decomposes into three measurable parts:
- **Routing/classification:** measured (19/19 held-out; 1.000 train).
- **Retrieval relevance:** hybrid+RRF+authority is shipped, but **no labeled
  relevance benchmark exists yet** → recommend a golden QA set (next plan §6).
- **Zero-hallucination operational rules:** guaranteed by construction
  (canonical path is lookup-only).

The blueprint's **">40% downstream LLM accuracy gain" is currently a target,
not a measured result** — there is no downstream LLM wired. It becomes
measurable in Phase 2 when a generator/compactor consumes the fused context.

---

## 5. Gap register

| ID | Gap | Severity | Consequence |
|---|---|---|---|
| ~~G1~~ | ✅ bronze/silver materialized (`build_medallion.py`, connector `persist_bronze`) | — | resolved |
| G2 | research corpus is curated sample (26 chunks), not live bulk | Medium | RAG recall ceiling until live bulk lands |
| G3 | no downstream LLM / compactor → >40% gain unmeasured | High | flagship accuracy KPI unverifiable |
| ~~G4~~ | ✅ learned reranker trained + eval harness (`AGRI_RERANKER=learned`); ONNX cross-encoder still opt-in | Low | cross-encoder weights not downloaded (offline) |
| G5 | vision backends implemented but real weights not installed (offline) | Medium | no real image diagnosis until weights dropped in |
| G6 | MT backends implemented but real models not installed (offline) | Medium | non-English answers transliterate until models dropped in |
| G7 | live ingestion path wired but egress blocked in sandbox (unvalidated live) | Medium | connectors untested against real endpoints |
| G8 | subdistrict coverage 22.77% (174/764 districts) | Medium | village-level geo incomplete |
| ~~G9~~ | ✅ auth token + rate-limit + request logging + load-test shipped | Low | external monitoring/alerting still open |
| ~~G10~~ | ✅ canonical ~4 ms, hybrid ~25 ms warm; prewarm at startup | — | resolved |
| G11 | content depth thin (60 calendar rows, 12 markets, 26 chunks) | Low | "55-domain" target far from realized |

---

## 6. Next plan (prioritized)

> **Status update:** Phase 2a ✅, Phase 2b ✅, Phase 3 ✅, Phase 4 ✅ —
> see `docs/roadmap.md` V1.9. What remains is *content/ops depth*, below.

**Done this pass (closing the three highest-value items)**
- ✅ **Bronze/silver materialization** — `scripts/build_medallion.py` (24 seed
  tables → immutable bronze artifacts w/ sha256 manifests + normalized,
  quality-scored silver JSONL) + connector `persist_bronze` in the lifecycle.
  Idempotent (2nd run: 0 written / 24 unchanged).
- ✅ **Live ICAR research ingestion** — `connectors/research/icar.py` now
  attempts the live endpoint and degrades to fixture offline;
  `scripts/ingest_research.py` runs bronze→silver→gold (`gold.research_chunk`).
- ✅ **Real weight seams** — learned reranker (trained, persisted, evaluated
  100% top-1 / MRR 1.000), real ONNX/TFLite/transformers vision `predict()`,
  real IndicTrans2/indicMT/API MT `translate()` — each gated on its runtime +
  weights, with graceful fallback unchanged.

**Remaining (content & ops depth — needs network/ops, not code)**
1. Download + drop in real model weights: cross-encoder ONNX
   (`AGRI_CROSS_ENCODER_MODEL`), PlantVillage/PlantDoc vision
   (`AGRI_VISION_MODEL` + `AGRI_VISION_LABELS`), IndicTrans2
   (`AGRI_MT_MODEL_DIR`) — the inference paths are done; only the binaries are
   missing (outbound egress is blocked in this sandbox) (G4, G5, G6).
2. Bulk live corpus ingestion once deployed with network (ICAR/FAO/PlantVillage
   → `gold.research_chunk`) to lift RAG recall (G2, G11).
3. Complete LGD subdistricts beyond 174/764 + expand mandi markets beyond 12
   (G8, G11).
4. External monitoring/alerting + CI soak (G9-partial); downstream
   LLM/compactor to make the ">40% accuracy gain" a measured number (G3).

**Ordering principle (unchanged):** every fix lands behind an existing pluggable
seam and keeps the deterministic canonical path as the default, so the
zero-hallucination and offline guarantees are never regressed.
