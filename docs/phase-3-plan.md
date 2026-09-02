# Phase 3 — Autonomous lake: hardening, self-configuration & new advisory features

> Status: **platform foundation shipped** (this phase's "robustness + autonomy"
> work is implemented and tested below); new *features* are scoped as tracks to
> build on top of it.

## 1. Goals

1. Make the lake **robust** — never silently corrupt, never half-write, never
   die on a transient network error, never rebuild what hasn't changed.
2. Make the lake **self-configuring** — one command to bring the whole thing up
   from a clean checkout, with environment/capability auto-detection and
   graceful degradation (fixtures when keys/network are absent).
3. Make the lake **autonomous** — a reproducible, idempotent build pipeline
   with a machine-readable health report, so CI, cron, and a human operator see
   the same picture.
4. Add the **next batch of advisory features** on top of the hardened
   substrate (fertilizer advisory, mandi intelligence, weather advisory, crop
   planning, RAG evidence retrieval).

## 2. What is already shipped in this phase ✅

Implemented, tested (36/36 passing), and committed in this slice:

### 2.1 Robustness
- **Retry with exponential backoff + jitter** — `pipelines/retry.py`;
  wired into `connectors/base.py::run()` so a transient API 5xx/timeout no
  longer kills an ingestion run. Retry count/timeout are config-driven.
- **Atomic writes** — `pipelines/storage.py` now writes JSON/JSONL/bronze
  artifacts via tmp-file + `os.replace()`, so a crash can never leave a
  half-written CSV/JSONL/manifest behind.
- **Idempotent seeding** — `scripts/seed_lake.py` fingerprints the ontology
  source (`seed_fingerprint()`, sha256 of `seed_data.py` + schema version) and
  skips the rebuild when unchanged; `--force` overrides.

### 2.2 Auto-configuration
- **`pipelines/config.py`** — three-layer resolution (environment `AGRILAKE_*`
  → `.env` → defaults), a dependency-free `.env` parser, and
  `detect_capabilities()` (API keys present, optional packages, network probe).
- Connectors now read keys/endpoints from config: `data_gov.py` (OGD API key),
  `fao.py` (FAOSTAT base URL) with environment fallbacks intact.
- `.env.example` documents every `AGRILAKE_*` variable.

### 2.3 Autonomous build
- **`scripts/bootstrap.py`** — one-shot build that self-bootstraps its own
  virtualenv, installs the package, then runs `seed → gold → validate → test`
  as isolated subprocesses and writes `data/lake/_bootstrap_report.json`.
- `--check` ("doctor") mode: environment + capability report with no build.
- Makefile targets: `make bootstrap`, `make up`, `make doctor`, `make check`.

## 3. New features (scoped tracks)

These build on the hardened substrate. Each track is independent and lands in
the order listed.

### Track 5 — Fertilizer advisory engine ✅ shipped
The blueprint's `fertilizer_advisory@<version>` table. We already had the math
(`reasoning/fertilizer.py`); this adds the full engine.
- `CROP_NUTRIENT_REQUIREMENT` (15 crops × N/P₂O₅/K₂O seasonal kg/ha with
  basal/vegetative/reproductive stage splits) + `SOIL_TEST_INTERPRETATION`
  (12 parameters: NPK/OC/pH/EC + 6 micronutrients).
- `reasoning/advisory.py`: `recommend_fertilizer(crop, stage, soil_test)` →
  soil assessment → adjusted requirement → DAP-first product mix (correct N
  credit) → per-timing plan; `assess_soil` → `SoilFlag`s; `persist_advisory`
  → `fertilizer_advisory@2026.08.csv`.
- Evidence-separated result (observation / recommendation / evidence),
  versioned records via `FertilizerAdvisoryRecord` (Pydantic).
- CLI `agrilake-fertilizer` / `scripts/fertilizer.py` (JSON soil file or
  `--soil-*` flags; Marathi/Hindi crop aliases work).
- Gold tables: `crop_nutrient_requirement` (45 rows), `soil_test_interpretation`
  (12 rows); `tests/test_advisory.py` (9 tests).

### Track 6 — Mandi intelligence ✅ shipped
We have live Agmarknet ingestion + `fact_mandi_price`.
- `reasoning/mandi.py`: `price_stats()` (per market × commodity: latest/mean/
  min/max, spread, volatility, trend), `season_signal()` (crop-calendar →
  harvest/lean/transition), `market_advisory()`, `list_markets()`.
- `dim_market` gold table — 12 major APMC mandis (Lasalgaon, Azadpur, Vashi,
  Guntur, …) geo-resolved to state/district codes with curated lat/lon and
  headline commodities.
- `mandi_price_trend` derived gold aggregate in `build_gold.py`.
- Agmarknet fixture extended to a 7-day tomato (Pune) + 5-day onion (Lasalgaon)
  series so trend/volatility are exercised.
- CLI `agrilake-mandi` / `scripts/mandi.py` (snapshot, trend, season signal,
  `--markets` listing); `tests/test_mandi.py` (8 tests).

### Track 7 — Weather advisory ✅ shipped
- `WEATHER_RISK_THRESHOLDS` (7 flags: heat stress, frost, cold night, high
  humidity, strong wind, waterlogging, dry spell) + `CROP_WATER_NEED_MM_WEEK`
  (10 crops) + `RAINFALL_TEXT_PROXY` (IMD text → mm) in `domain/seed_data.py`.
- `reasoning/weather.py`: `weather_flags()`, `rainfall_mm()`,
  `crop_water_flag()` (rainfall vs peak crop need → deficit/excess note),
  `agromet_advisory(district, crop)`, `load_bulletins()`.
- CLI `agrilake-weather` / `scripts/weather.py`; `tests/test_weather.py`
  (8 tests). Risk flags are structured so the diagnosis chain can consume
  them as the `environment` input later.

### Track 8 — Crop planning ✅ shipped
- `reasoning/crop_plan.py`: `crop_plan(crop, state, district)` → seasons,
  ordered stage timeline with months, sow/harvest windows, duration;
  `crops_to_sow(month, location)` reverse lookup; `sow_risk()` on/near/off
  window; location overrides applied district → state → India base.
- CLI `agrilake-plan` / `scripts/crop_plan.py` (plan or "what to sow in month X").
- `tests/test_crop_plan.py` (6 tests).

### Track 9 — RAG evidence retrieval ✅ shipped
- Bronze research chunks (ICAR/KVK/FAOSTAT) → short, provenance-only silver
  chunks (no whole-article reproduction) → dependency-free **Okapi BM25**
  retriever (`reasoning/rag.py::SearchIndex`, no vector DB per V1 scope).
- `search(query, crop, top_k)` + `evidence_for_diagnosis(crop, symptoms)`;
  hits carry source (institution/url/license/authority) + score.
- ICAR fixture grown 2 → 8 chunks (cotton PBW, soybean rust, tomato early/late
  blight, rice Khaira, wheat rust, maize FAW, onion purple blotch).
- CLI `agrilake-retrieve` / `scripts/retrieve.py`; `tests/test_rag.py` (8 tests).

### Track 10 — CI/CD + observability ✅ shipped
- `.github/workflows/ci.yml`: test job (3.10/3.11/3.12, pytest + drift gate +
  validate) on push/PR + a nightly autonomous `bootstrap` job that uploads
  `_bootstrap_report.json` as an artifact.
- `pipelines/logging.py`: JSON-line formatter + `correlation_id` contextvar +
  `log_event()` (structured events) — no regex parsing needed downstream.
- `scripts/verify_seeds.py` + `make verify-seeds`: drift gate proving committed
  `data/seeds/*.csv` match `seed_data.py`.
- `tests/test_observability.py` (4 tests).

### Track 11 — Multilingual + geography expansion ✅ partially shipped
- **Done**: Tamil (`ta`, 64 terms) + Telugu (`te`, 59 terms) symptom lexicons;
  `reasoning/symptoms.py` is now script-aware (Devanagari→hi/mr, Tamil→ta,
  Telugu→te, + script ranges for kn/ml/bn-as/gu/od/pa) so `diagnose()` accepts
  Dravidian-script symptom text; `resolve_subdistrict()` added to
  `pipelines/geocode.py` (representative tehsil/taluk/block/village coverage).
  Tests: `tests/test_multilingual_geo.py` (7 tests).
- **Later**: Kannada/Malayalam/Bengali/Odia/Gujarati/Punjabi lexicons (script
  ranges wired, terms TBD), the full LGD block/zilla/village import, and real
  MT behind `language.translate()` (IndicTrans2/IndicMT).

## 4. Robustness backlog (further hardening)

Already shipped this phase: retry/backoff, atomic writes, idempotent seed,
auto-config, capability detection, bootstrap report. Remaining:

- **Bronze dedup** — content-hash keying so re-ingesting the same payload is a
  no-op (immutability by construction).
- **Schema enforcement at persist** — validate silver records against the
  Pydantic models (currently `validate()` is advisory); reject/route bad rows
  to a quarantine directory.
- **Drift detection** — verify `data/seeds/*.csv` still matches
  `domain/seed_data.py` (the fingerprint exists; add a `make verify-seeds`
  gate).
- **Self-healing** — if a gold table is missing/stale, bootstrap rebuilds it;
  partial-failure resume so a failed step doesn't force a full rebuild.

## 5. Autonomous flow (architecture)

```
                    ┌─────────────────────────────────────────────┐
   one command ───▶ │ scripts/bootstrap.py  (stdlib-only)          │
                    │  1. collect_environment()  → python, venv,   │
                    │     config (env > .env > defaults),          │
                    │     capabilities (keys, packages, network)   │
                    │  2. ensure_venv()  → create .venv + install  │
                    │  3. run_steps()    → subprocess per step:    │
                    │        seed → gold → validate → test         │
                    │  4. report → data/lake/_bootstrap_report.json│
                    └─────────────────────────────────────────────┘
      exit code 0/1  ←  CI, cron, Makefile (`make up|bootstrap|doctor|check`)
```

- **Idempotent**: `seed` fingerprints the ontology and no-ops when unchanged.
- **Isolated**: every step is a subprocess; one failure doesn't cascade, and the
  report + exit code reflect exactly which step failed.
- **Degrading**: connectors fall back to committed fixtures when keys/network
  are absent (already the behaviour in `connectors/*`).

## 6. Milestones

| # | Milestone | Rough scope | Depends on |
|---|---|---|---|
| M0 | Robust + autonomous foundation | retry, atomic IO, idempotent seed, config, bootstrap, doctor | ✅ shipped |
| M1 | CI + drift/self-heal gates | GitHub Actions, verify-seeds, quarantine | ✅ shipped |
| M2 | Fertilizer advisory (Track 5) | nutrient-requirement tables + soil-test input + versioned advisory | ✅ shipped |
| M3 | Mandi intelligence (Track 6) | price trend/seasonality + dim_market | ✅ shipped |
| M4 | Weather advisory (Track 7) | IMD risk flags feeding env-input chain | ✅ shipped |
| M5 | RAG evidence (Track 9) | semantic chunks + BM25 retriever + citations | ✅ shipped |
| M6 | Crop planning (Track 8) | sow/harvest windows + risk notes | ✅ shipped |
| M7 | Multilingual + LGD geography (Track 11) | remaining-script lexicons, MT, subdistrict resolution | ✅ partial (ta/te + subdistrict done; LGD/MT later) |

## 7. Acceptance criteria

- `python scripts/bootstrap.py` from a clean checkout (no `.venv`) exits 0 and
  leaves a green lake + `_bootstrap_report.json`. ✅ (verified this slice)
- `make doctor` prints environment/capabilities without mutating data.
- Re-running `seed_lake.py` with unchanged ontologies is a no-op; `--force`
  rebuilds. ✅
- A connector hit by a transient failure retries with backoff, then falls back
  to fixtures; a crash mid-write never leaves a `.tmp`/partial file. ✅
- All prior tests remain green (36/36) and new platform tests cover config,
  retry, atomic IO, and seed fingerprinting. ✅

## 8. Risks

- **Live endpoints are rate-limited/blocked** (data.gov.in demo key, FAOSTAT
  egress) — the fixture fallback is the safety net; `probe_network()` reports
  reachability without hard-failing.
- **Translating/MT quality** — kept behind the `language.translate()` hook so a
  swap to IndicTrans2 is non-breaking.
- **Geo granularity** — representative subdistricts are placeholders until the
  LGD import (Track 11); code paths already key on `district_code`.
