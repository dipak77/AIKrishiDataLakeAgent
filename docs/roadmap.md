# Roadmap

> **Review & evaluation docs:** `system-overview.md` (architecture + flows),
> `decg-review.md` (dual-engine gateway review), `evaluation-report.md`
> (coverage %, gap register, next plan).

## V1 — Foundation (this repository) ✅

- 100+ canonical crops + Indian-language aliases
- All states/UTs (+ representative districts), agro-climatic/ecological zones
- Kharif/Rabi/Zaid crop mapping + phenological calendars
- Disease + pathogen, pest, weed, nutrient, fertilizer, pesticide, biocontrol,
  soil ontologies
- Source registry (governance)
- Bronze → Silver → Gold medallion pipeline + data-quality scoring
- Knowledge-graph builder + validation
- Live connector plugins (KCC, data.gov.in, Agmarknet, FAOSTAT, IMD, SHC, ICAR,
  PlantVillage, PlantDoc) with offline fixtures
- Unified agriculture record + evidence-separated recommendations + lineage
  fields

## V1.5 — Reasoning substrate (see `docs/phase-2-review.md`)

- **Track 1 — structured agronomy** ✅
  - `fertilizer_nutrient` numeric table + `fertilizer → contains → nutrient` edges
  - `nutrient_deficiency` table + graph links
  - symptom index + `symptom → disease/pest/deficiency` edges
  - deepened disease (growth_stage, differential_diagnosis) and pest (ETL, monitoring) fields
  - crop calendar for top 20 crops + state/district location overrides
- **Track 4 — first reasoning milestone** ✅
  - pure-DuckDB diagnosis retriever (`reasoning.diagnose`)
  - nutrient-math helpers (`reasoning.fertilizer`)
  - CLI `scripts/diagnose.py`
- **Track 2 — geography + language** ✅
  - full district coverage (36 states/UTs → 764 districts) + curated
    `DISTRICT_HQ` coordinates for major agri districts, rename aliases
    (Orissa/Odisha, Uttaranchal/Uttarakhand, Kadapa/YSR, Belgaum/Belagavi …)
  - `dim_subdistrict` representative tehsil/taluk/block + village rows
  - `pipelines.language`: script detection, Hindi/Marathi disambiguation,
    Devanagari → Latin transliteration, MT hook contract
  - Hindi + Marathi symptom lexicon so `diagnose()` accepts Indic symptom text
  - crop-compatibility is now a filter in `diagnose()` (`strict_crop`)

## V1.6 — Autonomous lake (platform hardening; see `docs/phase-3-plan.md`)

- **Robustness** — retry w/ exponential backoff + jitter (`pipelines/retry.py`),
  atomic writes (tmp + `os.replace`) across storage, idempotent seeding via
  ontology fingerprint (`seed_lake.py --force` to rebuild)
- **Auto-configuration** — `pipelines/config.py` (env `AGRILAKE_*` → `.env` →
  defaults), capability detection (keys/packages/network), connectors read
  keys/endpoints from config
- **Autonomous build** — `scripts/bootstrap.py` (`make bootstrap` / `make up` /
  `make doctor`): self-bootstraps venv, runs seed → gold → validate → test,
  writes `data/lake/_bootstrap_report.json`; isolated steps + exit codes
- **Tests** — 36 passing (added `tests/test_platform.py`)

### Feature tracks (see `docs/phase-3-plan.md`)

- **Track 5 — fertilizer advisory engine** ✅ shipped
  - `CROP_NUTRIENT_REQUIREMENT` (15 crops, stage-split N/P₂O₅/K₂O) +
    `SOIL_TEST_INTERPRETATION` (12 soil parameters)
  - `reasoning/advisory.py`: `recommend_fertilizer()` (soil-adjusted, DAP-first
    product mix, evidence-separated), `assess_soil()`, `persist_advisory()`
  - CLI `agrilake-fertilizer` / `scripts/fertilizer.py`; versioned
    `fertilizer_advisory@2026.08` records; gold tables
    `crop_nutrient_requirement` + `soil_test_interpretation`; 9 new tests
- **Track 6 — mandi intelligence** ✅ shipped
  - `reasoning/mandi.py`: price stats (trend/volatility/spread) + crop-calendar
    season signal + `market_advisory()`; `dim_market` (12 APMC mandis,
    geo-resolved); `mandi_price_trend` gold aggregate; multi-day price fixtures
  - CLI `agrilake-mandi` / `scripts/mandi.py`; 8 new tests
- **Track 7 — weather advisory** ✅ shipped
  - `reasoning/weather.py`: risk flags (heat/frost/humidity/wind/waterlogging/
    dry spell) + rainfall-text proxy + crop water-need comparison
  - CLI `agrilake-weather` / `scripts/weather.py`; 8 new tests
- **Track 8 — crop planning** ✅ shipped
  - `reasoning/crop_plan.py`: crop plan (seasons/timeline/sow-harvest windows),
    `crops_to_sow(month)`, `sow_risk()`, location overrides; CLI `agrilake-plan`
  - 6 new tests
- **Track 9 — RAG evidence retrieval** ✅ shipped
  - `reasoning/rag.py`: dependency-free Okapi BM25 `SearchIndex` over
    provenance-only research chunks; `search()` + `evidence_for_diagnosis()`;
    ICAR fixture 2 → 8 chunks; CLI `agrilake-retrieve`
  - 8 new tests
- **Track 10 — CI/CD + observability** ⚠ partially shipped
  - `pipelines/logging.py` (JSON logs + correlation ids);
    `scripts/verify_seeds.py` + `make verify-seeds`
  - **`.github/workflows/ci.yml` is not present at HEAD** (verified
    2026-09-02: `.github/` does not exist), so tests/validate/drift-gate never
    run automatically. Restoring CI is Phase 0.5 of `v7-plan.md`.
  - 4 new tests
- **Track 11 — multilingual + geography** ✅ (partial: Tamil + Telugu symptom
  lexicons + script-aware tokenizer + `resolve_subdistrict()`; LGD full import
  and MT hook remain later)
  - 7 new tests

## V1.7 — Krushi Mitra assistant (see `docs/phase-4-plan.md`)

- **Track 12 — graph-native lakehouse** ✅ — `gold.graph_nodes`/`graph_edges`
  + `reasoning/graph_query.py` (neighbors, paths, crop health map, symptom
  reverse-index) via recursive CTE
- **Track 13 — assistant router** ✅ — `reasoning/assistant.py`: multilingual
  intent classification + entity extraction + engine routing + evidence-cited
  composition (diagnosis / fertilizer / mandi / weather / planning / RAG)
- **Track 14 — REST API** ✅ — `apps/api/main.py` (FastAPI, `/api/*` +
  OpenAPI), `agrilake-serve`
- **Track 15 — web UI** ✅ — `apps/web/index.html` single-page chat (live preview)

## V1.8 — Retrieval & scale-out (see `docs/v5-plan.md`)

- **Track V5-A — hybrid semantic retrieval** ✅
  - `reasoning/embeddings.py`: dependency-free dense embeddings (hashing trick,
    char n-grams, L2-normalized) + `expand_query()` ontology query expansion
  - `reasoning/rag.py::HybridIndex`: BM25 ⊕ dense fused via Reciprocal Rank
    Fusion; assistant + `/api/evidence` now default to hybrid
- **Track V5-B — Neo4j/AGE graph export** ✅
  - `knowledge_graph/export.py` → idempotent `knowledge_graph.cypher` (Neo4j)
    + `knowledge_graph_age.sql` (Apache AGE) from the graph-native lakehouse;
    `agrilake-export-graph` / `make graph-export`; 7 new tests
- **Track V5-F — trained intent + NER** ✅
  - `reasoning/nlu.py`: Naive Bayes intent classifier + BIO sequence tagger,
    trained offline on seed ontologies (char n-grams, typo-robust, confidence
    scores); `assistant.ask()` now routes via the trained pipeline with
    heuristic fallback; model cached at `data/gold/nlu_model.json`; 14 tests
- **Track V5-C — vision inference scaffold** ✅
  - `vision/inference.py`: dependency-free PNG decoder + HSV colour descriptor
    + pluggable backends (heuristic shipped; ONNX/TFLite/transformers stubs for
    opt-in weights) → `dim_disease`/`dim_pest` candidates; 19 tests
- **Track V5-D — MT behind `language.translate()`** ✅
  - pluggable backends (lexicon default, IndicTrans2/IndicMT/API opt-in via
    `AGRI_MT_BACKEND`) with offline glossary + transliteration fallback; 12 tests
- **Track V5-E — full LGD geography import** ✅
  - `scripts/import_lgd.py`: LGD block/village CSV parser + deterministic
    real-data offline baseline → `gold.dim_subdistrict`; `resolve_subdistrict()`
    now lake-backed; 9 tests

## V1.9 — Dual-Engine Context Gateway (see `docs/v6-plan.md`)

- **Phase 1** ✅
  - `reasoning/guardrails.py`: sanitize + injection-block (deterministic)
  - `reasoning/gateway.py`: async orchestrator routing every query to the
    deterministic OKF graph engine, the hybrid sparse⊕dense RAG engine, or
    both (`asyncio.to_thread` concurrency), fused with RRF + de-dupe +
    deterministic rerank + token-budget compaction
  - `POST /api/gateway` → clean unified context payload (routing path, fused
    segments, engine-contribution stats, citations)
- **Phase 2a — ops/perf** ✅
  - thread-local read-only DuckDB connection cache (`pipelines.storage`) —
    canonical path ~21 ms → **~4 ms**, hybrid warm ~42 ms → **~25 ms**
  - `@lru_cache` RAG index build + `reasoning/warmup.py` pre-warm wired into
    the FastAPI lifespan (cold first call absorbed at startup, ~91 ms)
  - `apps/api/middleware.py`: optional `AGRILAKE_API_TOKEN` auth + in-memory
    sliding-window rate limit (`AGRILAKE_RATE_LIMIT`/`AGRILAKE_RATE_WINDOW`)
- **Phase 2b — quality + measured accuracy** ✅
  - `reasoning/reranker.py`: pluggable reranker (deterministic default;
    opt-in `cross_encoder` via `AGRI_RERANKER`)
  - `reasoning/compactor.py`: pluggable compactor (truncation default;
    opt-in `llm`/`indic_trans` via `AGRI_COMPACTOR`)
  - NLU: deficiency-intent training (+ out-of-vocabulary → `general`
    short-circuit); "zinc deficiency in rice" now routes diagnosis/hybrid
  - golden-QA benchmark `scripts/benchmark_gateway.py` +
    `data/fixtures/golden_qa.json`: **100% (43/43 checks)** — routing, intent,
    crop, graph/evidence coverage, evidence recall@k, injection block
- **Phase 3 — data depth** ✅
  - research corpus expanded 8 → **26 chunks / 20 documents / 12 crops**
  - `scripts/ingest_research.py`: live-capable ICAR ingestion
    (**bronze → silver → gold.research_chunk**) with offline fixture fallback;
    `connectors/research/icar.py::fetch` now attempts the live endpoint and
    degrades gracefully. FAOSTAT stays the production/yield source (its
    domain is `production`, by design).
- **Phase 4 — hardening** ✅
  - `RequestLoggingMiddleware` (structured JSON request logs) +
    `scripts/load_test.py` (concurrency/throughput/latency percentiles)
  - **bronze/silver materialization** (`scripts/build_medallion.py` +
    connector `persist_bronze`): 24 seed tables → immutable bronze artifacts
    with sha256 manifests + normalized, quality-scored silver JSONL
  - **real model-weight seams**:
    - `reasoning/reranker.py` learned reranker — pure-Python logistic
      regression trained on golden-QA + corpus, persisted at
      `data/gold/reranker_model.json` (`AGRI_RERANKER=learned`,
      `scripts/train_reranker.py`); `scripts/eval_reranker.py` reports
      top-1 recall / MRR (100% / 1.000 on current corpus)
    - `vision/inference.py`: real ONNX / TFLite / transformers `predict()`
      inference paths (gated on `onnxruntime`/`tflite-runtime`/`transformers`
      + `AGRI_VISION_MODEL`), with label-map + ontology-index mapping
    - `pipelines/language.py`: real IndicTrans2 / indicMT / API `translate()`
      paths (gated on toolkit + `AGRI_MT_MODEL_DIR` / `AGRI_MT_API_URL`),
      graceful lexicon fallback unchanged

## V2 — Real ingestion, data-quality refinery & knowledge-gap closure

> **Full plan: [`v7-plan.md`](v7-plan.md)** (evidence-backed review + phased
> delivery). Verified state at HEAD on 2026-09-02: 262 tests green, but **0 of
> 8 connectors have ever landed a live record** (`ingest_live --source all` →
> 8/8 `method=fixture`, `bronze=None`), there are **no `fact_*` tables** after
> `make bootstrap`, and the seed-drift gate exits **1** on a pristine clone.

- **Phase 0** — line-ending/reproducibility fix ✅ (landed 2026-09-02: LF pinned in
  `scripts/seed_lake.py::_write_csv` + `.gitattributes`; `verify_seeds` now exits 0
  on a pristine tree), then KCC resource-id fix, status-aware retry, test
  isolation, CI restored
- **Phase A** — source **discovery** (`pipelines/discovery/`, `gold.source_catalog`,
  contract hashes + drift detection) and recorded-payload **contract tests**
- **Phase B** — real **collection** (throttled/incremental/resumable transport,
  watermarks, run ledger, `ingestion_method` as a column, fail-closed runs)
- **Phase C** — **data-quality filter** (rule engine, `pass|quarantine|reject`,
  promotion gate, PII + license gates, scorecards)
- **Phase D** — **quality conversion** (canonical dates/units/geo/entities,
  typed DDL gold, SCD2, dataset versions, lineage)
- **Phase E** — **knowledge-gap discovery + targeted collection loop**
  (gap register ranked by demand; gaps close only with a passing regression test)
- **Phase F** — ops (scheduler, metrics, alerts), **frontier-only model policy**
  (`grok-4.6` / `qwen3.8-max` and higher, audited + budget-capped), eval gates
- Scale-out substrate when volume demands it: MinIO + Iceberg + Trino,
  Postgres/PostGIS, Qdrant (see `infrastructure/docker-compose.yml`); full
  district/subdistrict/block/village geography import

## V3 — Reasoning & assistants

- Knowledge graph to Neo4j/AGE
- Krushi Mitra RAG with evidence citations
- Disease/pest diagnosis engine (symptom → candidate → environment → stage →
  visual → differential)
- Fertilizer advisory engine (crop × variety × stage × soil test → nutrient
  requirement → recommendation)
- Crop plan + mandi intelligence engines

## V4 — Vision & fine-tuning

- Vision training over Tier-A datasets + first-party farmer uploads
  (crop + district + month + stage + description + image + AI hypothesis +
  expert confirmation + outcome)
- Model fine-tuning on farmer Q&A and research chunks

## Domain coverage target (55 domains)

1–10 identification/varieties/planning/calendars/nursery/land-prep/sowing/seed
treatment/germination/transplantation; 11–14 soil science/testing/fertility/
nutrient deficiency; 15–17 fertilizers/organic/biofertilizers; 18–19 irrigation/
water; 20 weed management; 21–25 diseases/pests/nematodes/biocontrol/IPM;
26–27 growth stages/physiology; 28–30 weather/agrometeorology/climate risks;
31–35 harvest/post-harvest/storage/grading/processing; 36–38 prices/MSP/commodity
markets; 39–40 machinery/precision; 41–43 horticulture/floriculture/plantation;
44–48 livestock/dairy/poultry/fisheries/beekeeping; 49–50 schemes/insurance;
51 research; 52 farmer Q&A; 53–55 computer vision/remote sensing/satellite
agriculture.
