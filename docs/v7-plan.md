# V7 — Real Ingestion, the Data-Quality Refinery, and Knowledge-Gap Closure

> **Status: plan.** Nothing in §4–§8 is implemented yet. Everything in §1–§3 was
> produced by running commands against this checkout (`93685b1`) on **2026-09-02**
> and by reading the live `api.data.gov.in` responses the same day. Where a
> number appears it came from a command; the command is named next to it.
>
> **Predecessors:** `v5-plan.md` (retrieval/scale-out), `v6-plan.md` (DECG
> gateway), `evaluation-report.md` (V1.9 coverage). V7 is the **data-depth +
> ingestion-governance** layer those documents deferred.

---

## 0. Scope and non-negotiables

V7 turns the lake from *"engine complete, data curated by hand"* into
*"data arrives by itself, is provably clean, and tells us what it is missing"*.

Three things it must deliver:

1. **Real ingestion** — source *discovery* (find datasets, read their schema,
   detect drift) and *collection* (throttled, incremental, resumable,
   provenance-stamped), verified against recorded live payloads rather than
   hand-written fixtures.
2. **A data-quality refinery** — a rule-based gate that classifies every record
   `pass | quarantine | reject`, never silently drops anything, and blocks
   promotion of a bad batch; then a canonicalization/conversion stage that
   produces one typed, versioned gold schema.
3. **Knowledge-gap closure** — the lake measures its own holes (unresolved
   entities, empty ontology slots, unanswered queries, thin domains) and runs a
   *targeted* collection loop that closes each gap with evidence **and** a
   regression test.

**Non-negotiables carried forward** (they are the reason this system is trusted):

| Invariant | How V7 protects it |
|---|---|
| Deterministic, zero-hallucination canonical path | LLMs may only *propose*; proposals land via DQ gate + tests (§5.4) |
| Bronze is immutable and honest about its origin | `ingestion_method` becomes a **column**, not a log line (§2 F4) |
| Every answer carries provenance + license | License gate moves into the ingestion path, not just the crawler (§2 F13) |
| Offline-first / no forced cloud dependency | Frontier-LLM stages are opt-in and **fail closed** (§5.3) |
| Original Indic text is never overwritten | Refinement writes `*_normalized` / `*_en` alongside originals (§4.6) |

---

## 1. Verified state of the repository

### 1.1 What is green today

| Check | Command | Result |
|---|---|---|
| Autonomous build | `python scripts/bootstrap.py` | `steps: 4/4 ok` (seed 0.49 s, gold 0.38 s, validate 0.16 s, test 22.43 s), `overall: OK` |
| Test suite | `python -m pytest -q` | **262 passed** (29 files) — but on a pristine tree this only passes because a test fixture rewrites committed seed CSVs first; the standalone drift gate exits **1** (F12, now fixed — §2.2) |
| Ontology + graph | `python scripts/validate.py` | all checks pass; **1,489 nodes / 1,706 edges** |
| Gold inventory | `information_schema.tables` on `data/lake/agrilake.duckdb` | **27 gold tables** on a fresh build |

The engine layer is genuinely solid: trained multilingual NLU, hybrid
BM25⊕dense retrieval, a dual-engine gateway, graph export, learned reranker,
six deterministic advisory engines. **The gap is not the engine. It is the
data supply chain in front of it.**

### 1.2 Measured inventory (fresh build)

```
gold.graph_edges 1706   gold.graph_nodes 1489   gold.dim_geography 800
gold.crop_alias 296     gold.dim_crop 116       gold.dim_subdistrict 69
gold.crop_calendar 60   gold.crop_season_map 58 gold.crop_nutrient_requirement 45
gold.dim_disease 30     gold.fertilizer_nutrient 29  gold.dim_pest 21
gold.dim_fertilizer 18  gold.dim_pesticide 18   gold.nutrient_deficiency 13
gold.dim_growth_stage 12  gold.dim_market 12    gold.dim_nutrient 12
gold.soil_test_interpretation 12  gold.biocontrol 9  gold.authority_levels 8
gold.dim_soil 8         gold.dim_weed 8         gold.biofertilizer 6
gold.dim_season 5       gold.crop_calendar_override 3  gold.meta 1
```

**Zero `fact_*` tables exist after `make bootstrap`.** `gold.research_chunk`
appears only after `python scripts/ingest_research.py`, which reports
`{"upserted": 26, "total": 26, "documents": 20, "methods": ["fixture"]}`.

---

## 2. Review findings (every one reproduced by a command)

Severity: **P0** blocks real ingestion · **P1** corrupts or silently degrades
data · **P2** hardening/hygiene.

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| **F1** | **P0** | **The KCC connector cannot ever fetch live.** `KccConnector.discover()` yields the *dict key* (`"transcripts"`) as `resource_id` instead of the value (`kisan-call-centre-kcc-transcripts-…`), so the request URL is `/resource/transcripts`. | `connectors/government/kcc.py:31-46`; run output shows `resource_id: transcripts` |
| **F2** | **P0** | **The documented KCC resource id is dead.** `5f039cdb2e054ab5b74bfc2a6e1a860b` (cited in `docs/live-ingestion.md` and in the connector comment) returns `{"message": "Meta not found", "status": "error"}`. | `GET api.data.gov.in/resource/5f039cdb…` on 2026-09-02 |
| **F3** | **P0** | **No discovery path exists at all.** `discover()` is a hard-coded 1-element list in all 8 connectors; the catalog search API used to be assumed available but `GET /catalog/search?query=kisan` → `{"message": "Meta not found"}` and `data.gov.in/api/3/action/package_search` → 404. | `grep -c "def discover" connectors/**`; both live calls on 2026-09-02 |
| **F4** | **P1** | **No live record has ever landed.** `ingest_live.py --source all` → **8/8 sources `method=fixture`, `bronze=None`**; `data/bronze/` contains only `seed_ontology/*` (+ a `dummy/` dir from tests). | `python scripts/ingest_live.py --source all --limit 3 --json` |
| **F5** | **P1** | **Fixture-sourced rows are indistinguishable from live rows in the data.** Silver records carry no `ingestion_method` field (only the run summary does), and a fixture mandi row still scores `quality_score: 0.875`. | key list of `data/silver/market/goi_agmarknet_*.jsonl` line 1 |
| **F6** | **P1** | **No schema validation anywhere in ingestion.** `AgricultureSourceConnector.validate()` is a no-op with **zero overrides**; `schemas/records.py` (Pydantic) is used only by `gen_json_schema.py` and one smoke test. | `grep -rn "def validate" connectors/` → 1 hit (base); `grep -rn "schemas.records"` → generator + test only |
| **F7** | **P1** | **The DQ layer is a single weighted score, not a gate.** `pipelines/quality.py` computes 8 signals → one number. There is no rule engine, no `pass/quarantine/reject` classification, no dedupe, no outlier/volume anomaly check, no PII handling, no rejection ledger, no promotion threshold. | `pipelines/quality.py` (118 lines, one function) |
| **F8** | **P1** | **Fixtures flatter the entity resolver.** On the 13 curated fixture rows `resolve_crop` hits **13/13 (100 %)**; on a *live-verified* commodity string from today's feed, `"Ridgeguard(Tori)"`, it returns **`None`**. The alias layer has never seen real mandi vocabulary. | `resolve_crop("Ridgeguard(Tori)") -> None` vs fixture 13/13 |
| **F9** | **P1** | **Live dates are `dd/mm/yyyy`; everything downstream assumes ISO.** Verified live value `arrival_date: "02/09/2026"`. `reasoning/mandi.py::season_signal` swallows the parse failure and returns `('unknown', 'No crop-calendar entry…')` — a *silent* degradation; `gold.mandi_price_trend` does `ORDER BY price_date DESC` / `max(price_date)` on a string, so lexicographic ≠ chronological. | `season_signal('CROP_TOMATO','02/09/2026')` → `unknown`; `season_signal('CROP_TOMATO','2026-08-26')` → `transition`; `scripts/build_gold.py` trend SQL |
| **F10** | **P1** | **Incremental ingestion is impossible as designed.** The live resource exposes only 6 filterable fields (`state, district, market, commodity, variety, grade`); `arrival_date` is *not* in `field_exposed`, and `filters[arrival_date]=01/09/2026` was **silently ignored** (`total` stayed 17,800, same record returned). There is no watermark/checkpoint table, so "fetch what's new" cannot be expressed. | `field_exposed` in the live payload; filtered call on 2026-09-02 |
| **F11** | **P1** | **Retry logic is status-blind.** `pipelines/retry.py::retry_call` retries on *any* `Exception` (including 401/403/404), has no `Retry-After` handling, no 429 awareness, no circuit breaker, no per-run request budget. The shared demo key returns `{"error": "Rate limit exceeded"}` after ~4 calls. | `pipelines/retry.py`; 5th live call on 2026-09-02 |
| **F12** | **P1** | **The seed-drift gate contradicts itself, and the test suite hides it.** 17 committed seed CSVs are CRLF, 7 are LF, while `_write_csv` used `csv.DictWriter`'s default `\r\n` terminator. So on a pristine tree `verify_seeds.py` exits **1** (7 files flagged) — but a full `pytest` run *passes*, because `tests/test_reasoning.py`'s fixture calls `emit_seed_csvs()` into the **real** `data/seeds/` when the lake is missing, rewriting those 7 files to CRLF *before* `test_verify_seeds_passes_on_clean_tree` runs. The suite therefore leaves committed files modified and its verdict depends on test order. ✅ **Fixed while writing this plan** (see §2.2) | `pytest tests/test_observability.py::test_verify_seeds_passes_on_clean_tree` → **1 failed** on pristine seeds; after `rm -rf data/lake && pytest -q` → 262 passed **and** `git status` shows 7 modified seed CSVs |
| **F13** | **P2** | **License governance is not enforced at ingest time.** `LicenseChecker` is used only by `connectors/web/crawler.py`; no dataset connector consults it, and `SourceMetadata.license` is never checked against an ALLOW/BLOCK policy before a record is persisted. | `grep -rn LicenseChecker --include=*.py` → crawler + smoke test only |
| **F14** | **P2** | **Silver → gold is order-dependent and schema-anarchic.** `build_gold.py` uses `read_json_auto(..., union_by_name=true)` + `CREATE OR REPLACE`, so gold columns are whatever the newest JSONL happens to contain, and nothing runs gold after ingest unless someone remembers to. | `scripts/build_gold.py::_load_silver` |
| **F15** | **P2** | **No CI exists.** `.github/` is absent, although `docs/roadmap.md` Track 10 claims `.github/workflows/ci.yml` shipped. The drift gate, tests and validate never run automatically — which is exactly how F12 survived. | `ls .github` → *No such file or directory* |
| **F16** | **P2** | **Tests write into the real lake tree.** `tests/test_medallion.py::Dummy` persists to `data/bronze/dummy/r1/` (manifest on disk, `source_id: DUMMY`). Harmless only because `data/bronze/` is gitignored. | `data/bronze/dummy/r1/_manifest.json` |
| **F17** | **P2** | **No knowledge-gap instrumentation.** Nothing in the code measures unresolved mentions, empty ontology slots, zero-evidence queries, or the 55-domain coverage matrix. The gap register exists only as prose in `evaluation-report.md`. | no `gap` module; `grep -ri "gap" --include=*.py` → docstrings only |
| **F18** | **P2** | **No LLM/model-selection policy.** `LLMCompactor` is a stub that raises `CompactorUnavailable`; there is no model registry, no tiering, no cost budget, no call audit, no eval gate for model changes. | `reasoning/compactor.py` |

### 2.1 What the live source actually looks like (verified 2026-09-02)

`GET https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070`
(Agmarknet daily mandi prices, Ministry of Agriculture & Farmers Welfare):

```jsonc
{
  "status": "ok", "total": 17800, "count": 2,
  "updated_date": "2026-09-02T17:01:08Z",          // daily refresh, same-day
  "field": [ {"name":"State","id":"state","type":"keyword"}, …,
             {"name":"Min_x0020_Price","id":"min_price","type":"double"} ],
  "field_exposed": [ state, district, market, commodity, variety, grade ],  // 6 only
  "records": [ {"state":"Odisha","district":"Mayurbhanja","market":"Baripada APMC",
                "commodity":"Brinjal","variety":"Brinjal","grade":"Medium",
                "arrival_date":"02/09/2026","min_price":4000,"max_price":5000,
                "modal_price":4500} ]
}
```

Four facts this establishes, all of which the plan is built around:

1. **The resource-meta payload *is* a discovery API.** One `limit=1` call
   returns field ids, types, filterable fields, `total`, and `updated_date` —
   enough to build a schema contract and detect drift without any extra
   endpoint.
2. **Field names moved** (`Min_x0020_Price`, lowercase ids). The connector
   survives only because `_price()` has a `min_price` fallback. Nothing would
   tell us if a fallback silently stopped matching.
3. **~17,800 rows/day ⇒ ≈ 6.5 M rows/year** for one resource. Volume planning,
   partitioning and incremental strategy are not optional.
4. **Dates are `dd/mm/yyyy`** (F9) and **not filterable** (F10).

### 2.2 Fixed while writing this plan (Phase 0.1, already landed)

Two edits, because leaving a self-contradicting drift gate in the tree would
have invalidated every reproducibility claim in this document:

| Change | File | Verified result |
|---|---|---|
| Pin the CSV line terminator to LF | `scripts/seed_lake.py::_write_csv` (`lineterminator="\n"`) | all 24 seed CSVs now LF (`24 LF`, `0 CRLF`) |
| Normalize the 17 CRLF seed CSVs to LF | `data/seeds/*.csv` (regenerated via `emit_seed_csvs()`) | `git status` → 17 modified; `verify_seeds.py` → `OK: 24 committed seed CSVs match seed_data.py`, **exit 0** |
| Pin eol in git so a Windows checkout cannot re-break it | new `.gitattributes` | `data/seeds/*.csv text eol=lf` |

Before/after on the fresh-clone condition (`rm -rf data/lake`, pristine seeds,
then `pytest -q`):

```
before fix:  262 passed  +  git status: 7 modified seed CSVs   (test run mutated committed data)
             pytest …::test_verify_seeds_passes_on_clean_tree  → 1 failed
after fix:   262 passed  +  seeds sha256 identical before/after the run
             6aa07125d030e08e8bfaffef88c5026d4a154ae2e1bd2af5272bd1d7f9a73c90
             verify_seeds.py → exit 0 ; make check → 262 passed ; bootstrap → 4/4 ok
```

Remaining Phase 0 items (F1, F2, F11, F16, F15) are **not** done — they are
scheduled in §8.

---

## 3. Root causes (why the gaps cluster)

1. **Fixtures were written to fit the ontology**, so every measurement taken
   against them (100 % crop resolution, 100 % geo resolution, green tests)
   measures the fixture, not the world. *Fix: recorded real payloads
   (cassettes) become the test substrate (§4.2).*
2. **"Graceful degradation" degraded all the way to fake data.** Fixture
   fallback is right for a demo, wrong for a lake: it produced a green run with
   zero live records and no data-level marker (F4, F5). *Fix: fail-closed runs +
   `ingestion_method` as a column + run ledger.*
3. **Quality was modelled as a score, not a contract.** A score can be reported
   and ignored; a gate cannot (F7). *Fix: rule engine + quarantine + promotion
   thresholds.*
4. **Nothing observes the pipeline.** No CI (F15), no run ledger, no watermark
   (F10), no gap instrumentation (F17) — so drift and silent degradation
   accumulate invisibly (F9, F12). *Fix: `ingest_run`, `dq_scorecard`,
   `gap_register` tables + CI + alerts.*

---

## 4. Target architecture — the V7 refinery

```
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │S0 DISCOVER│──▶│S1 CONTRACT│──▶│S2 COLLECT │──▶│S3 LAND    │  bronze (immutable)
   │catalog/   │   │schema +   │   │throttled, │   │raw+hdrs+  │  + manifest
   │robots/    │   │DQ rules + │   │incremental│   │sha256     │
   │sitemap    │   │cassettes  │   │resumable  │   │run ledger │
   └────▲─────┘   └──────────┘   └──────────┘   └────┬─────┘
        │                                            ▼
        │                                     ┌────────────┐  BLOCK>0 → park run
        │                                     │S4 DQ FILTER │──────────┐
        │                                     │rules, dedupe│          ▼
        │                                     │PII, license │   ┌────────────┐
        │                                     │outliers     │   │ QUARANTINE │
        │                                     └─────┬──────┘   │ (queryable,│
        │                                           │ pass     │  never     │
        │                                           ▼          │  dropped)  │
   ┌────┴─────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐ └────────────┘
   │S9 GAP-   │◀──│S8 GAP     │◀──│S7 SERVE   │◀──│S6 CONVERT  │
   │TARGETED  │   │DETECT     │   │API/UI/RAG │   │typed gold, │   S5 REFINE
   │COLLECTION│   │unresolved │   │gateway    │   │SCD2, snap- │◀── canonicalize
   └──────────┘   │holes, thin│   │           │   │shots,      │    dates/units/geo/
                  │domains    │   │           │   │lineage     │    entities/PII/lang
                  └───────────┘   └──────────┘   └────────────┘
```

Stages S0–S6 replace today's `discover → fetch → validate(no-op) → normalize →
enrich(score) → persist`. S7 is the existing assistant/API/gateway. S8–S9 are
new.

### 4.1 S0 — Source discovery (new: `pipelines/discovery/`)

| Component | Responsibility |
|---|---|
| `catalog.py::DataGovCatalog` | Enumerate + read resource metadata via `GET /resource/{id}?limit=1`; harvest `field`, `field_exposed`, `total`, `updated_date`, `org`, `sector`, `catalog_uuid`. Verified working 2026-09-02. |
| `catalog.py::CatalogSearch` | Dataset *search* over the OGD portal. `/catalog/search?query=` is **not** usable (verified `Meta not found`); implement against the portal's own search API and pin the response shape in a cassette. Fallback: a curated, versioned `metadata/sources/*.yaml` seed list + human-approved additions. |
| `sitemap.py` | robots.txt-aware discovery for IMD/ICAR/KVK/SAU portals (reuse `connectors/web/crawler.py::robots_allowed`). |
| `repository.py` | OAI-PMH / sitemap / RSS discovery for research corpora (ICAR, IARI, SAUs, ICRISAT, FAO). |
| `licenses.py` | Run every discovered URL through `LicenseChecker` **at discovery time** and stamp `license_decision ∈ {ALLOW, REVIEW, BLOCK}` (fixes F13). |
| `registry.py` | Write `metadata/discovered/<source_id>.json` + upsert `gold.source_catalog`; emit a `schema_drift` event when the field-set hash or `total` band changes. |

Outputs a **`source_catalog`** row per dataset: `source_id, dataset_uuid,
resource_id, title, org, sector, license_declared, license_decision,
field_schema (JSON), field_exposed[], total_records, updated_date,
discovered_at, discovery_method, contract_hash`.

**Drift detection** is a hash over `(field ids, types, exposed set)`. A changed
hash ⇒ new contract version ⇒ connector contract test must be re-recorded ⇒
alert. This is what would have caught `Min_x0020_Price` and the KCC resource
going dark.

### 4.2 S1 — Source contracts + recorded-payload tests (new: `pipelines/http.py`, `tests/contracts/`)

```yaml
# metadata/sources/goi_agmarknet.yaml  (new `contract:` block)
contract:
  resource_id: 9ef84268-d588-465a-a308-a864a43d0070
  version: 2026-09-02            # bumped by S0 on drift
  fields:
    state:        {type: str,  required: true}
    arrival_date: {type: date, format: "DD/MM/YYYY", required: true}   # F9
    min_price:    {type: float, min: 0}
    modal_price:  {type: float, min: 0}
    max_price:    {type: float, min: 0}
  business_key: [market, commodity, variety, grade, arrival_date]
  filterable: [state, district, market, commodity, variety, grade]      # F10
  incremental: {strategy: full_scan_client_filter, key: arrival_date}   # F10
  pagination: {mode: offset_limit, page_size: 1000}
  rate_limit: {rps: 1, burst: 5, honor_retry_after: true}               # F11
  volume: {expected_rows_per_day: [8000, 40000]}
  cassettes: [tests/fixtures/cassettes/agmarknet_2026-09-02.json.gz]
```

**`pipelines/http.py::Transport`** with four modes — `live | record | replay |
offline` — selected by `AGRILAKE_TRANSPORT`. Cassettes are gzip'd JSON
`(request_url_without_key, status, headers, body, recorded_at)`, sha256-checked
into the repo. Contract tests then run **deterministically with no egress**,
which is the only way to verify connectors in a sandbox where every non-PyPI
TLS handshake is closed (verified: `pypi.org → 200`; `api.data.gov.in`,
`fenixservices.fao.org`, `icar.gov.in`, `mausam.imd.gov.in`, `api.github.com`,
`example.com` → `SSLError`).

Contract tests assert: field set matches the cassette; dtype/format coercion
works; `business_key` is unique; row counts land inside `volume.expected_*`;
every `filters[...]` the connector relies on actually narrows the result (this
test fails today for `arrival_date`).

### 4.3 S2 — Collection engine (new: `pipelines/collect/`)

| Piece | Fixes | Behaviour |
|---|---|---|
| `throttle.py::ThrottledSession` | F11 | Per-host token bucket (`AGRILAKE_RPS`, default 1/s), honours `Retry-After`, retries **only** on 429/5xx/timeouts, raises on 4xx, per-host circuit breaker (open after 5 consecutive failures, half-open probe after 60 s), per-run request budget. |
| `cursor.py::Watermark` | F10 | `gold.ingest_watermark(source_id, resource_id, partition, high_watermark, rows_seen, updated_at)`. Strategies: `full_scan_client_filter` (Agmarknet — `arrival_date` not filterable), `partition_by_field` (state/commodity — both exposed), `updated_date_shortcircuit` (skip the run if `updated_date` is unchanged). |
| `paginate.py` | F10 | offset/limit with page-size cap, resume from cursor, checksum de-dupe across pages. |
| `idempotency.py` | F5 | `record_hash = sha256(canonical_json(record))`; every row carries `run_id` + `ingestion_method ∈ {live, replay, fixture}` **as a column**; `fixture` rows can never be promoted past silver (configurable, default hard-block). |
| `runner.py` | F4 | One run = one `gold.ingest_run` row: source, resource, transport mode, started/finished, requests, retries, bytes, rows raw/pass/quarantine/reject, watermark before/after, contract version, git sha, status. **Fail closed**: if `transport=live` was requested and the source is unreachable, the run is `failed` — it does not quietly emit fixture rows. |

Discovery → collection is now data-driven: `runner.py --source all` reads
`gold.source_catalog`, so adding a dataset is a YAML + contract change, not a
code change.

### 4.4 S3 — Bronze landing

Layout stays S3-compatible (`pipelines/storage.py` already mirrors object keys):

```
data/bronze/<source_id>/dt=<YYYY-MM-DD>/run=<run_id>/<resource_id>/<part>.json.gz
                                            └── _manifest.json
```

`_manifest.json` gains: `contract_version`, `request_url` (key redacted),
`response_status`, `etag`/`last_modified`, `row_count`, `transport`,
`upstream_updated_date`. Bronze is append-only; re-ingesting identical content
is a no-op keyed on sha256 (this behaviour already exists in `write_bronze` and
`build_medallion.py` and is kept).

### 4.5 S4 — Data-quality filter (new: `pipelines/dq/`)

The heart of V7. A record leaves S4 in exactly one state.

```python
@dataclass(frozen=True)
class Rule:
    id: str                 # "DQ-PRICE-TRIANGLE"
    severity: Severity      # BLOCK | WARN | INFO
    scope: str              # "field" | "row" | "table" | "cross_source"
    domain: str             # "market" | "farmer_qa" | "soil" | ...
    def check(self, rec, ctx) -> Violation | None: ...
```

`classify(record) -> Decision(pass | quarantine, violations=[…])`
`gate(run) -> Promote | Park` — promote only if `BLOCK == 0` **and**
`WARN rate < AGRILAKE_DQ_WARN_MAX` (default 2 %).

Ten rule families (concrete instances in §7):

1. **Schema/type conformance** — validate against `schemas/records.py` Pydantic
   models, which today are *generated to JSON Schema but never used to
   validate* (F6). Unknown fields ⇒ `WARN` + `schema_drift` metric, not silent
   absorption.
2. **Referential integrity** — `crop ∈ dim_crop`, `district ∈ dim_geography`,
   `market ∈ dim_market` (auto-register unknown markets as candidates rather
   than dropping rows), `growth_stage ∈ dim_growth_stage`.
3. **Value domain** — `0 < min ≤ modal ≤ max`; pH 0–14; EC/NPK/plausible ppm
   ranges; `year ∈ [1950, current+1]`; parsed date ≤ now + 1 d.
4. **Uniqueness/dedupe** — `record_hash` dedupe; business-key collision with
   *different* values ⇒ `quarantine` (conflict, not duplicate).
5. **Volume/freshness anomaly** — per-run row count vs trailing 28 runs
   (median ± 3·MAD ⇒ `WARN`, ± 6·MAD ⇒ `BLOCK`); missing expected partition
   ⇒ `BLOCK`; `updated_date` older than the source's declared schedule ⇒ `WARN`.
6. **Encoding/language** — mojibake and mixed-script detection; declared
   language vs detected language mismatch ⇒ `WARN`.
7. **PII** — phone/email/PAN/Aadhaar patterns. Phone/email ⇒ redact +
   `pii_redacted=true`; Aadhaar/PAN ⇒ `BLOCK` (never persisted to silver).
8. **License/provenance** — `license_decision == ALLOW` required;
   `REVIEW ⇒ quarantine`; `BLOCK ⇒ reject`; missing `source_url` ⇒ `BLOCK`.
9. **Statistical outlier** — modal price vs 28-day `market × commodity` median
   (MAD z > 5 ⇒ `quarantine`, retained for review, never deleted).
10. **Cross-source consistency** — mandi modal vs MSP band; `season` vs
    `crop_calendar`; advisory `valid_from ≤ valid_to`.

Every violation is written to **`gold.dq_violation`** and the offending record
to **`gold.quarantine`** with the full violation list — so "why did this row
not make it?" is always a query, never a mystery. A per-run
**`gold.dq_scorecard`** records counts by rule, pass rate, warn rate, block
rate, and the promotion decision.

### 4.6 S5 — Refinement (silver)

`pipelines/refine/` — pure functions, unit-tested, one concern each:

| Transform | Fixes | Detail |
|---|---|---|
| `dates.py` | F9 | Per-source format registry from the contract; everything emitted ISO-8601. Unparseable ⇒ `BLOCK`. Adds `*_raw` preservation. |
| `units.py` | — | INR/quintal ⇄ INR/tonne, ha ⇄ acre, hg/ha ⇄ kg/ha, %⇄ppm. Unit always stored explicitly (already partly true: `unit: "INR/quintal"`). |
| `geo.py` | F8 | `resolve_geography` + `resolve_subdistrict` with `geo_confidence ∈ {exact, alias, fuzzy, none}`; unresolved names captured to `gold.unresolved_mention`. |
| `entities.py` | F8 | Crop/disease/pest resolution returns `(entity_id, method, confidence)`; the risky substring fallback in `pipelines/entities.py::resolve_crop` becomes **opt-in** and always tagged `method=substring`; unresolved strings accumulate with counts → gap input (S8). |
| `language.py` | — | Existing `detect_language` + `translate()` seam; adds `mt_model_id` + `mt_confidence` when a real backend runs. Originals never overwritten (invariant). |
| `text.py` | — | Unicode NFC, whitespace, boilerplate strip, chunking for RAG with `content_hash`. |
| `dedupe.py` | F7 | Near-duplicate detection (normalized text + shingle Jaccard ≥ 0.95) with `canonical_of` back-link. |

### 4.7 S6 — Conversion to gold (typed, versioned)

Replaces `read_json_auto(union_by_name=true)` + `CREATE OR REPLACE` (F14) with:

- **Explicit DDL per gold table** (checked into `pipelines/ddl/*.sql`), typed
  columns, `DATE`/`TIMESTAMP`/`DECIMAL` where they belong, primary keys and
  `NOT NULL` on the contract's required fields. Ingest loads into
  `<table>__staging` then swaps in one transaction.
- **SCD2 for dimensions** (`valid_from`, `valid_to`, `is_current`) so a market
  rename or district reorganisation never rewrites history.
- **Dataset snapshots**: `gold.dataset_version(table, version, git_sha,
  row_count, dq_pass_rate, built_at, contract_versions[])` — every gold build
  is addressable and diffable; `gold.lineage_edge(from, to, transform,
  run_id)` records how each table was produced.
- **Aggregates fixed**: `mandi_price_trend` recomputed over real `DATE` columns
  with proper `arg_max`, plus 7/28-day rolling stats and MAD used by DQ rule 9.

### 4.8 S7 — Serving

Unchanged engine (`reasoning/gateway.py`, `apps/api/main.py`) plus new
operational endpoints:

```
GET  /api/ops/runs?source=&status=      → ingest_run ledger
GET  /api/ops/runs/{run_id}             → rows, DQ scorecard, watermark, errors
GET  /api/ops/dq/scorecard?window=7d    → pass/warn/block rates per source
GET  /api/ops/quarantine?rule=&source=  → paged rejected records + violations
GET  /api/ops/gaps?type=&severity=      → open knowledge gaps + demand signal
POST /api/ops/runs                      → trigger a collection run (token-gated)
```

The web UI (`apps/web/index.html`) gains an **Ops** tab rendering the same
four tables — "is the lake healthy today?" becomes a glance, not an
investigation.

### 4.9 S8 — Knowledge-gap detection (new: `pipelines/gaps.py`)

Gaps are *computed from the lake*, not asserted in prose. Each gap carries a
`demand_signal` so collection is prioritized by need.

| Gap type | Query over the lake | Example measured today |
|---|---|---|
| `UNRESOLVED_ENTITY` | `gold.unresolved_mention` grouped by count | `"Ridgeguard(Tori)"` → 1 (verified unresolvable) |
| `ONTOLOGY_HOLE` | `dim_crop` LEFT JOIN `dim_disease` / `dim_pest` / `crop_calendar` / `crop_nutrient_requirement` WHERE NULL | 116 crops vs **60** calendar rows, **45** nutrient-requirement rows, **30** diseases |
| `GEO_HOLE` | districts without subdistricts; markets without coordinates | `dim_subdistrict` = **69** rows; `dim_market` = **12** |
| `EVIDENCE_HOLE` | crops/domains with 0 `research_chunk` | 26 chunks / 20 docs / 12 crops total |
| `TEMPORAL_HOLE` | months/districts with no advisory or weather rows | weather = 2 fixture rows |
| `DOMAIN_COVERAGE` | the 55-domain matrix from `docs/roadmap.md` scored per domain | most domains have 0 evidence rows |
| `QUERY_FAILURE` | gateway/assistant runs routing `exploratory` with 0 segments; golden-QA misses | measurable from `/api/gateway` stats |

Output: **`gold.gap_register`** (`gap_id, type, dimension, key, severity,
demand_signal, evidence_count, first_seen, last_seen, status, owner,
resolution_test`).

### 4.10 S9 — Gap-targeted collection loop

```
gap → evidence_request(gap_id, source_types[], query_templates[], license_class, priority)
    → dispatcher:
        • registered source has it      → S2 collection run (automatic)
        • web-only                      → crawler (robots + license gate)
        • document-only                 → research_pdf → chunk → S4
        • needs a human                 → KVK/expert review queue
    → S4 DQ gate → S5/S6 → gold
    → VERIFY: gap assertion + new regression test must pass
    → gap.status = closed   (only with a passing test — no self-certified closure)
```

Two anti-patterns this design forbids explicitly:

- **Fake closure.** A gap closes only when a *test* that encodes the gap
  assertion passes (`tests/gaps/test_gap_<id>.py`, generated with the gap).
- **Hallucinated evidence.** Where a frontier model is used to draft an alias,
  a disease description or an extraction schema, its output is a *proposal*
  that enters S4 like any other record — it must cite a real source URL with an
  ALLOW licence, and ontology edits additionally require the two-model quorum
  in §5.4.

---

## 5. Model-selection policy — upper-boundary only

This is a hard policy, encoded in `pipelines/models.py`, applying to every
stage of this process (planning, authoring, extraction, gap analysis,
evaluation) and to the runtime.

### 5.1 Verified frontier tier (public leaderboards, 2026-09-02)

| Model | Vendor | Position (verified) | Pricing (in/out per 1 M tok) | Context |
|---|---|---|---|---|
| `grok-4.6` | xAI | A.1 tier, 92 (akitaonrails 2026-08-15); "coding and agents" pick, intelligence #2 (designforonline 2026-08) | $2 / $6 | 500 K |
| `qwen3.8-max` | Alibaba (open-weight) | A.1 tier, 92; benchlm frontier #7 (78) | $2 / $6 | 1 M |
| `claude-opus-5` | Anthropic | benchlm **frontier #1** (84); DFO 87.1 (#1) | $5 / $25 | 1 M |
| `kimi-k3` | Moonshot | benchlm frontier #2 (82); A.1 tier, 95 (akitaonrails) | — / $15 out | — |
| `gpt-5.6-sol` | OpenAI | benchlm frontier #3 (80); A.1 tier, 93 | $5 / $30 | 1.1 M |
| `gemini-3.7-flash` | Google | A.1 tier, 93 at ~$4.12/task | — | — |
| `glm-5.3` | Zhipu | A.1 tier, 94 (akitaonrails) | ≈$2.59 equiv | — |

Sources: benchlm.ai/frontier-ai-models (2026-09-01),
akitaonrails.com/en/2026-08-15/llm-benchmarks-qwen-3-8-glm-5-3-gemini-3-7,
designforonline.com/the-best-ai-models-so-far-in-2026,
iternal.ai/llm-selection-guide.

### 5.2 Tiering

| Tier | Use | Allowed models |
|---|---|---|
| **T1 — Authoring** (gap analysis, extraction-schema design, source triage, ontology *proposals*, doc/plan authoring, eval design) | Highest-stakes reasoning | **frontier allowlist only.** Default primary `grok-4.6`; default secondary `qwen3.8-max` (cross-vendor quorum); `claude-opus-5` / `kimi-k3` / `gpt-5.6-sol` accepted as higher-scoring substitutes. |
| **T2 — Runtime generation** (context compaction, answer drafting, translation QA) | Latency + cost sensitive, still user-facing | Frontier allowlist only; may use the *flash*-class frontier variant (e.g. `gemini-3.7-flash`) when the eval gate passes. |
| **T3 — Bulk/mechanical** (regex extraction, dedupe, classification already covered by the trained NLU) | Deterministic | **No LLM.** Use the existing deterministic engines — cheaper and reproducible. |

### 5.3 Rules

1. **Upper boundary only for T1/T2.** No mid-tier or small model may be
   selected for authoring, extraction design, or gap analysis. `ModelPolicy`
   raises `ModelTierViolation` if a non-allowlisted id is requested.
2. **Fail closed, never silently degrade.** If no frontier model is reachable
   and a T1/T2 stage is required, the stage **stops** and the run is marked
   `failed`. It does not quietly fall back to a weaker model and it does not
   fabricate output. (This mirrors the fixture lesson, F4.)
3. **Deterministic-first invariant.** The canonical serving path stays
   LLM-free. LLM usage is opt-in via env and always recorded.
4. **Two-model quorum for ontology writes.** Any T1-authored ontology
   addition (crop alias, disease/pest claim, calendar override) must be
   independently produced by two *different-vendor* frontier models and must
   agree; disagreement ⇒ human review queue. Single-model output may only
   create a `gap_register` entry, never a `dim_*` row.
5. **Cost + budget governance.** Per-run and per-day USD caps
   (`AGRI_MODEL_BUDGET_RUN_USD`, default $5; `..._DAY_USD`, default $50);
   exceeding ⇒ run parks.
6. **Full audit.** Every call appends to `gold.model_call_audit(run_id, stage,
   task, model_id, tier, policy_version, prompt_hash, tokens_in, tokens_out,
   cost_usd, latency_ms, status)`.
7. **Eval gate before promotion.** Changing a model id requires the golden-QA
   benchmark (`scripts/benchmark_gateway.py`, currently 43/43) and the DQ eval
   suite to be non-regressing; results are persisted next to the policy
   version. A model is *promoted*, never hot-swapped.

### 5.4 Configuration surface (to be added to `.env.example` in Phase F)

```bash
AGRI_MODEL_POLICY=frontier-only        # only accepted value in T1/T2
AGRI_MODEL_PRIMARY=grok-4.6
AGRI_MODEL_SECONDARY=qwen3.8-max
AGRI_MODEL_ALLOWLIST=grok-4.6,qwen3.8-max,claude-opus-5,kimi-k3,gpt-5.6-sol,gemini-3.7-flash
AGRI_MODEL_QUORUM=2                    # cross-vendor agreement for ontology writes
AGRI_MODEL_BUDGET_RUN_USD=5
AGRI_MODEL_BUDGET_DAY_USD=50
AGRI_MODEL_AUDIT=1
```

---

## 6. Data-model additions

```sql
-- discovery
CREATE TABLE gold.source_catalog(
  source_id VARCHAR, resource_id VARCHAR, dataset_uuid VARCHAR, title VARCHAR,
  org VARCHAR[], sector VARCHAR[], license_declared VARCHAR,
  license_decision VARCHAR, field_schema JSON, field_exposed VARCHAR[],
  total_records BIGINT, upstream_updated_at TIMESTAMP, discovered_at TIMESTAMP,
  discovery_method VARCHAR, contract_version VARCHAR, contract_hash VARCHAR,
  PRIMARY KEY (source_id, resource_id));

-- collection
CREATE TABLE gold.ingest_run(
  run_id VARCHAR PRIMARY KEY, source_id VARCHAR, resource_id VARCHAR,
  transport VARCHAR, contract_version VARCHAR, git_sha VARCHAR,
  started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR,
  requests INT, retries INT, bytes BIGINT,
  rows_raw INT, rows_pass INT, rows_quarantine INT, rows_reject INT,
  watermark_before VARCHAR, watermark_after VARCHAR, error VARCHAR);

CREATE TABLE gold.ingest_watermark(
  source_id VARCHAR, resource_id VARCHAR, partition VARCHAR,
  high_watermark VARCHAR, rows_seen BIGINT, updated_at TIMESTAMP,
  PRIMARY KEY (source_id, resource_id, partition));

-- quality
CREATE TABLE gold.dq_violation(
  run_id VARCHAR, record_hash VARCHAR, rule_id VARCHAR, severity VARCHAR,
  field VARCHAR, message VARCHAR, value VARCHAR, detected_at TIMESTAMP);
CREATE TABLE gold.quarantine(
  record_hash VARCHAR, run_id VARCHAR, source_id VARCHAR, domain VARCHAR,
  payload JSON, violations JSON, quarantined_at TIMESTAMP,
  status VARCHAR,          -- open | fixed | rejected | expired
  resolved_by VARCHAR, resolved_at TIMESTAMP);
CREATE TABLE gold.dq_scorecard(
  run_id VARCHAR, source_id VARCHAR, rows_total INT, rows_pass INT,
  rows_quarantine INT, rows_reject INT, warn_rate DOUBLE, block_rate DOUBLE,
  rule_counts JSON, promoted BOOLEAN, built_at TIMESTAMP);

-- refinement / gaps
CREATE TABLE gold.unresolved_mention(
  mention VARCHAR, kind VARCHAR, source_id VARCHAR, occurrences INT,
  first_seen TIMESTAMP, last_seen TIMESTAMP, sample_context VARCHAR);
CREATE TABLE gold.gap_register(
  gap_id VARCHAR PRIMARY KEY, type VARCHAR, dimension VARCHAR, key VARCHAR,
  severity VARCHAR, demand_signal DOUBLE, evidence_count INT,
  first_seen TIMESTAMP, last_seen TIMESTAMP, status VARCHAR,
  owner VARCHAR, resolution_test VARCHAR);
CREATE TABLE gold.evidence_request(
  request_id VARCHAR PRIMARY KEY, gap_id VARCHAR, source_types VARCHAR[],
  query_templates VARCHAR[], license_class VARCHAR, priority DOUBLE,
  status VARCHAR, created_at TIMESTAMP, closed_at TIMESTAMP);

-- governance
CREATE TABLE gold.dataset_version(
  table_name VARCHAR, version VARCHAR, git_sha VARCHAR, row_count BIGINT,
  dq_pass_rate DOUBLE, contract_versions VARCHAR[], built_at TIMESTAMP,
  PRIMARY KEY (table_name, version));
CREATE TABLE gold.lineage_edge(
  from_ref VARCHAR, to_ref VARCHAR, transform VARCHAR, run_id VARCHAR,
  created_at TIMESTAMP);
CREATE TABLE gold.model_call_audit(
  call_id VARCHAR PRIMARY KEY, run_id VARCHAR, stage VARCHAR, task VARCHAR,
  model_id VARCHAR, tier VARCHAR, policy_version VARCHAR, prompt_hash VARCHAR,
  tokens_in INT, tokens_out INT, cost_usd DOUBLE, latency_ms INT,
  status VARCHAR, called_at TIMESTAMP);
```

`docs/data-model.md` and `docs/architecture.md` get matching sections in the
phase that introduces each table.

---

## 7. DQ rule catalogue (first 24 rules, seeded from verified data)

| Rule id | Sev | Domain | Assertion | Origin |
|---|---|---|---|---|
| DQ-DATE-PARSE | BLOCK | all | date fields parse under the contract format → ISO | F9 (`02/09/2026`) |
| DQ-DATE-NOT-FUTURE | BLOCK | all | `event_date <= now + 1d` | F9 |
| DQ-PRICE-TRIANGLE | BLOCK | market | `0 < min ≤ modal ≤ max` | live row 4000/4500/5000 |
| DQ-PRICE-OUTLIER-MAD | QUAR | market | `|z_MAD| ≤ 5` vs 28-day market×commodity | new |
| DQ-CROP-RESOLVED | WARN | market, farmer_qa | `crop IS NOT NULL` | F8 (`Ridgeguard(Tori)`) |
| DQ-GEO-RESOLVED | WARN | all | `district_code IS NOT NULL` | F8 |
| DQ-GEO-EXISTS | BLOCK | all | `(state, district) ∈ dim_geography` | referential |
| DQ-MARKET-KNOWN | WARN | market | `market ∈ dim_market` (else candidate) | `dim_market` = 12 |
| DQ-SCHEMA-CONFORM | BLOCK | all | Pydantic model validates | F6 |
| DQ-SCHEMA-DRIFT | WARN | all | no unexpected fields vs contract | F2/F10 |
| DQ-BUSINESS-KEY-UNIQUE | BLOCK | all | unique on contract `business_key` | F7 |
| DQ-CONFLICT-VERSION | QUAR | all | same key, different values | F7 |
| DQ-SOURCE-URL | BLOCK | all | non-empty `source_url` | provenance |
| DQ-LICENSE-ALLOW | BLOCK/QUAR | all | `license_decision == ALLOW` (`REVIEW`→quarantine) | F13 |
| DQ-INGEST-METHOD | BLOCK | all | `ingestion_method ∈ {live,replay}` for promotion | F5 |
| DQ-PII-REDACT | WARN | farmer_qa | no raw phone/email after redaction | new |
| DQ-PII-IDENTIFIER | BLOCK | all | no Aadhaar/PAN pattern | new |
| DQ-SOIL-PH | BLOCK | soil | `0 ≤ pH ≤ 14` | new |
| DQ-SOIL-RANGE | WARN | soil | N/P/K/Zn within agronomic ranges | new |
| DQ-VOLUME-BAND | WARN/BLOCK | table | run rows within `volume.expected_*` (±3/±6 MAD) | F10 |
| DQ-FRESHNESS | WARN | table | `upstream_updated_at` within source schedule | 17 800 rows/day |
| DQ-LANG-CONSISTENT | WARN | farmer_qa | declared vs detected script/language agree | multilingual |
| DQ-MOJIBAKE | QUAR | all | no replacement-char / encoding damage | new |
| DQ-CALENDAR-CONSISTENT | WARN | advisory | `season` matches `crop_calendar` window | cross-source |

Rules are plain data + predicates, so adding one is a 5-line change plus a
test. Every rule ships with at least one positive and one negative test case.

---

## 8. Phased delivery plan

Estimates assume one engineer; phases are ordered by dependency, and each ends
green (`make check`).

### Phase 0 — Stop the bleeding (≈ 1 day)

| # | Fix | File | Acceptance |
|---|---|---|---|
| 0.1 | ✅ **Done** — seed CSV line endings → LF everywhere (`lineterminator="\n"`), re-emit, `.gitattributes` pin | `scripts/seed_lake.py::_write_csv`, `data/seeds/*.csv`, `.gitattributes` | `verify_seeds.py` exits **0** on a pristine clone (was: exit 1, 7 files); a test run no longer mutates committed seeds (§2.2) |
| 0.2 | KCC `discover()` yields the real resource id; dead id removed and re-discovered via S0-lite | `connectors/government/kcc.py` | resource id in the request URL is not `"transcripts"`; contract test recorded |
| 0.3 | `retry_call` gains `retry_on=(429,5xx,timeouts)` + `Retry-After` | `pipelines/retry.py` | unit tests: no retry on 404; sleeps `Retry-After` |
| 0.4 | Tests use `tmp_path` for bronze writes | `tests/test_medallion.py` | `data/bronze/dummy/` never created |
| 0.5 | `.github/workflows/ci.yml` restored (tests + validate + drift gate) | new | CI green on push; would have caught 0.1 |

### Phase A — Discovery + contracts (≈ 5 days)
Deliverables: `pipelines/discovery/*`, `pipelines/http.py` (Transport +
cassettes), `metadata/sources/*.yaml` contract blocks, `tests/contracts/*`,
`gold.source_catalog`, `scripts/discover.py` (`agrilake-discover`).
**Acceptance:** `agrilake-discover --source all` writes a catalog row per
registered source with a real field schema; contract tests pass in `replay`
mode with zero network; a mutated cassette fails the drift assertion.

### Phase B — Real collection (≈ 6 days)
Deliverables: `pipelines/collect/*` (throttle, cursor, paginate, idempotency,
runner), `gold.ingest_run`, `gold.ingest_watermark`, `ingestion_method`
column, `scripts/ingest_live.py` rewritten on the runner, fail-closed mode.
**Acceptance:** a live (or replay) Agmarknet run lands ≥ 8 000 rows/day
partition in bronze with a manifest and a run row; re-running the same
partition writes 0 new rows (idempotent); killing the run mid-way and resuming
completes it; `transport=live` + no network ⇒ run `failed`, **zero** fixture
rows in silver.

### Phase C — DQ refinery (≈ 7 days)
Deliverables: `pipelines/dq/*` (rules, classifier, gate, quarantine),
`gold.dq_violation` / `gold.quarantine` / `gold.dq_scorecard`, PII redaction,
license gate at ingest, ≥ 24 rules from §7 with unit tests,
`/api/ops/dq/scorecard` + `/api/ops/quarantine`.
**Acceptance:** a synthetic bad batch (one violation per rule) is classified
correctly 24/24; a run with ≥ 1 BLOCK is parked, not promoted; every
quarantined row is retrievable with its violations; no record is ever dropped
without a `dq_violation` row.

### Phase D — Refinement + typed gold (≈ 6 days)
Deliverables: `pipelines/refine/*`, `pipelines/ddl/*.sql`, staging-swap loader,
SCD2 dims, `gold.dataset_version`, `gold.lineage_edge`, fixed
`mandi_price_trend` on real DATEs, `gold.unresolved_mention`.
**Acceptance:** 100 % of silver dates ISO-8601 (asserted over the full table);
gold DDL matches the contract field set; `dataset_version` written on every
build; `season_signal` returns a real signal for live-format dates (today:
`unknown`); unresolved-mention counts populated from a replay run.

### Phase E — Gap detection + closure loop (≈ 6 days)
Deliverables: `pipelines/gaps.py`, `gold.gap_register`,
`gold.evidence_request`, dispatcher (S2 / crawler / research_pdf / expert
queue), gap regression-test generator, `/api/ops/gaps`, Ops tab in the web UI.
**Acceptance:** the gap register auto-populates ≥ 5 gap types from the current
lake (measurable today: `Ridgeguard(Tori)`, 116-vs-60 calendar holes, 69
subdistricts, 12 markets, 26 chunks); one full loop — gap → collect → DQ →
gold → test passes → `status=closed` — demonstrated end-to-end for at least
one alias gap and one evidence gap.

### Phase F — Ops, model policy, evals (≈ 5 days)
Deliverables: `pipelines/models.py` (`ModelPolicy`, tier enforcement, budget,
audit) + `gold.model_call_audit`; `.env.example` model block; frontier LLM
compactor wired to the T2 policy; scheduler (cron/Dagster) for `discover →
ingest → dq → gold → gaps`; Prometheus `/metrics` + alerts on run failure,
block rate, volume anomaly, staleness; model-change eval gate.
**Acceptance:** `ModelPolicy` raises `ModelTierViolation` for a non-allowlisted
id (unit-tested); audit row written per call; a run over budget parks; alerts
fire on an injected failure; model promotion blocked on a regressing golden-QA
score.

**Total ≈ 36 engineer-days**, each phase independently shippable.

---

## 9. KPIs

| KPI | Today (measured) | V7 target | Measured by |
|---|---|---|---|
| Sources with a live/replay-verified collection run | 0 of 8 (`method=fixture`) | ≥ 6 of 8 | `gold.ingest_run` |
| Connector contract-test coverage | 0 % (no contract tests) | 100 % of connectors | `tests/contracts/` |
| Crop resolution on real mandi vocabulary | unresolvable strings present (`Ridgeguard(Tori)`) | ≥ 98 % of rows | `gold.unresolved_mention` ÷ rows |
| ISO-8601 date conformance in silver | partial (fixtures ISO, live `dd/mm/yyyy`) | 100 % | DQ-DATE-PARSE block rate = 0 |
| Records dropped without a violation row | unbounded (no ledger) | 0 | `dq_violation` ⟕ quarantine join |
| Promoted runs with BLOCK violations | n/a (no gate) | 0 | `dq_scorecard.promoted` |
| Fresh build has fact tables | 0 `fact_*` | all contracted facts | `information_schema` |
| RAG corpus | 26 chunks / 20 docs / 12 crops | ≥ 5 000 chunks / ≥ 40 crops | `gold.research_chunk` |
| Subdistrict coverage | 69 rows | ≥ 764 districts covered | `gold.dim_subdistrict` |
| Registered markets | 12 | ≥ 200 (from live mandi markets) | `gold.dim_market` |
| Open gaps with a demand signal | not measured | measured, ranked, ≥ 1 closed/week | `gold.gap_register` |
| Non-frontier model used in T1/T2 | n/a | 0 (enforced) | `ModelPolicy` + `model_call_audit` |
| CI present | absent (`.github/` missing) | green on every push | Actions |

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Dev sandbox has no egress (verified: only `pypi.org` reachable) | Cassette record/replay is the primary CI substrate; `record` mode runs once in a networked environment; contract hash detects when a cassette goes stale |
| Rate limits / shared demo key (verified `Rate limit exceeded` after ~4 calls) | Per-host token bucket, `Retry-After`, real API keys from env, per-run request budget, circuit breaker |
| Schema drift upstream (verified field renames) | `contract_hash` + drift event ⇒ alert + contract re-record; unknown fields never absorbed silently |
| Non-filterable incremental keys (verified for `arrival_date`) | Strategy is declared per source in the contract; `full_scan_client_filter` is the honest default |
| Fixture data masquerading as real (F4/F5) | `ingestion_method` column + fail-closed runs + DQ-INGEST-METHOD block |
| Quarantine becomes a landfill | Weekly triage report from `/api/ops/quarantine`; `status` + `resolved_by`; auto-expiry after 90 d with a count in the scorecard |
| LLM hallucination entering the ontology | Propose-only + ALLOW-licence citation + two-model cross-vendor quorum + DQ + generated regression test |
| Cost blowout on frontier models | Per-run/day USD caps, T3 stays deterministic, audit table, promotion gated on evals |
| Line-ending / reproducibility drift (F12) | ✅ Landed: LF pinned in the writer + `.gitattributes`; still needs the drift gate running in CI (Phase 0.5) so a regression cannot hide behind test order again |

---

## 11. Definition of done (V7)

1. `agrilake-discover` + `agrilake-ingest --source all` run unattended on a
   schedule and populate bronze → silver → gold with **live** data, recorded in
   `gold.ingest_run`.
2. No record reaches silver without passing the DQ gate; nothing is ever
   dropped without a `dq_violation` row; every run has a scorecard.
3. Gold is typed, versioned and lineage-tracked; a fresh clone reproduces it
   byte-for-byte (`verify_seeds` exit 0 — ✅ already true after §2.2; keep it
   true by running the gate in CI).
4. The gap register is live, ranked by demand, and at least one gap has been
   closed end-to-end with a passing regression test.
5. Model selection is frontier-only by policy and enforced by a test; every
   call is audited with cost.
6. CI runs tests + validate + drift gate on every push; the ops endpoints and
   UI tab answer "is the lake healthy?" without shell access.
7. `make check` green, and the numbers in §9 re-measured and written back into
   `docs/evaluation-report.md`.

---

## 12. Implementation status — plan vs. landed code (2026-09-02)

Everything below was produced by running the code, not by reading it. Test count
is `make check` → **403 passed** (baseline before this work: 262, so 141 new tests: 30 DQ + 19 model policy + 16 contracts + 16 transport + 14 collect + 14 gaps + 13 pipeline + 10 connector-contract + 9 discovery).

### 12.1 Stage → module → proof

| Plan stage | Landed module | Executed proof |
|---|---|---|
| S0 discovery | `pipelines/discovery.py` | `tests/test_discovery.py` (9): reads the recorded `limit=1` payload → `total_records=17800`, `license_decision=ALLOW`, `has_drift=False`; a mutated contract flips `has_drift=True`; a retired resource raises `LookupError` |
| S1 contracts + cassettes | `pipelines/contracts.py`, `pipelines/http.py`, `tests/contracts/test_agmarknet_contract.py` | `tests/test_contracts.py` (16) + `tests/test_http_transport.py` (16); the contract test replays the **real** captured payload and asserts `arrival_date == "02/09/2026"` → `price_date == "2026-09-02"` |
| S2 collection engine | `pipelines/collect.py`, `connectors/base.py::run` | `tests/test_collect.py` (14): run ledger rows, per-record `ingestion_method`, watermark monotonicity, `require_live` fail-closed |
| S4 DQ filter | `pipelines/dq.py` | `tests/test_dq_refinery.py` (30): 23 rules, reject/quarantine/pass, `gate()` semantics, scorecard persistence |
| S8 gap detection | `pipelines/gaps.py` | `tests/test_gaps.py` (14) against the built lake; idempotent register upsert that never auto-closes |
| S9 gap→collection loop | `scripts/pipeline_run.py` | `tests/test_pipeline_run.py` (13) + `tests/contracts/test_agmarknet_contract.py` (10): one call runs discover → collect → gate → watermark → gaps on the recorded payload and promotes it |
| F model policy | `pipelines/models.py` | `tests/test_model_policy.py` (19): frontier-only selection, cross-vendor quorum, fail-closed unavailability, run/day budget, audited cost |
| Ops: CI | `ci/ci.yml` (**parked** — the branch's automation token lacks the GitHub `workflows` permission, so it cannot be written to `.github/workflows/`; the file header carries the one-line activation command) | bootstrap → verify-seeds → pipeline replay smoke run, py3.10/3.11/3.12, `AGRILAKE_TRANSPORT=replay` so CI never dials out |

### 12.2 Deviations from the plan (deliberate, with reasons)

1. **Flat modules, not sub-packages.** §4 names `pipelines/discovery/`,
   `pipelines/collect/`, `pipelines/dq/`; the implementation is
   `pipelines/discovery.py`, `collect.py`, `dq.py`, `contracts.py`, `refine.py`,
   `gaps.py`, `models.py`, `http.py`, `retry.py`. Each is under ~1k lines and has
   one responsibility; splitting now would add import churn without adding
   structure. Revisit only when a module needs internal layering.
2. **23 DQ rules, not 24.** `DQ-CONFLICT-VERSION` (§7) is implemented inside
   `DQ-BUSINESS-KEY-UNIQUE`: same business key with different content is a
   *conflict*, surfaced by `collect.dedupe_records` and quarantined, not a
   separate rule id. Severity mix: **12 BLOCK / 9 WARN / 2 INFO**.
3. **Severity recalibration (measured, not stylistic).** `DQ-CROP-RESOLVED` and
   `DQ-MARKET-KNOWN` are **INFO**, not WARN. A clean batch of real live rows
   scored `warn_rate = 1.0` under the planned severities — an unknown market and
   an unresolvable crop name are *novelty*, which is exactly what the gap
   register is for — so the gate parked every run. After the change the same
   batch scores `warn_rate 0.0` and promotes, while the novelty still lands in
   `gold.gap_register` as `UNRESOLVED_ENTITY Ridgeguard(Tori)`.
4. **The watermark key is the silver field.** `incremental.key` is `price_date`
   (canonical), not `arrival_date` (upstream alias). The alias remains declared
   in `source_date_fields` and `source_fields`; `incremental_key_of` resolves
   either view, and a date-typed key yields `2026-09-02`, not
   `2026-09-02T00:00:00`.
5. **An orchestrator the plan did not name.** `scripts/pipeline_run.py` is the
   single entry point that chains S0→S9 and returns an audit dict / JSON. The
   plan described the stages but not the runner; without it the stages were
   only reachable from tests.
6. **Transport is now inherited by every OGD connector.**
   `DataGovConnector.fetch_resource` goes through `pipelines/http.py`, so
   `live|record|replay|offline`, throttling and redaction apply to collection as
   well as discovery. `connectors/base.py::run(transport=…)` calls
   `set_transport()` so a flag — not just the environment — decides the mode,
   and a connector that reports `_method` overrides the requested transport.
7. **Production default is fail-closed.** `pipeline_run.py` requires live/replay
   rows unless `--allow-fixtures` is passed (`AGRILAKE_REQUIRE_LIVE=0`); fixture
   rows are then rejected by `DQ-INGEST-METHOD`, not silently promoted.
8. **Subdistrict coverage is 5/764 districts, not 22.77%.** `dim_subdistrict`
   has 69 rows covering 5 distinct `district_code` values out of 764 in
   `dim_geography`. The older percentage in `docs/evaluation-report.md` is
   stale and must be re-measured (Definition of done #7).

### 12.3 Bugs the tests caught during implementation

Each of these was a real defect found by an executed test, not a review comment:

| Defect | Found by | Fix |
|---|---|---|
| `incremental_key_of` returned the raw `02/09/2026` instead of ISO | `tests/test_contracts.py` | resolve `source_fields` before `fields`, emit ISO |
| `FieldSpec.parse_date` silently returned `None` for an unknown declared format | `tests/test_contracts.py` | raise `ValueError` (a contract that cannot be honoured must fail loudly) |
| Watermark/ledger reads crashed on a lake that does not exist yet (first run) | `tests/test_collect.py` | guard on `path.is_file()` in `collect`, `discovery`, `gaps` |
| `detect_all` closed the **thread-cached** read connection, so the next call failed with `Connection already closed!` | `tests/test_gaps.py` | never close a `get_read_connection()` handle; invariant documented in `pipelines/storage.py` |
| `geo_hole_gaps` queried `dim_geography.level`, a column that does not exist | `tests/test_gaps.py` | districts are `district_code IS NOT NULL`; pest coverage matches free-text `crop_hosts` (`dim_pest` has no `crop_id`) |
| Replay never matched the recording because the connector sends `offset=0` and the probe did not | `scripts/pipeline_run.py` smoke run | `url_key` treats `offset=0` and a missing `offset` as the same request |
| Discovery kept dialling the publisher in a `replay` run | `tests/test_pipeline_run.py` | `run_source` builds the discovery client from the requested transport |
| The suite rewrote 24 committed CSVs, 24 bronze manifests and 25 silver JSONL files on every run | md5 snapshot before/after `pytest` | seeds/bronze/silver redirected to tmp in `test_smoke`, `test_medallion`, `test_reasoning`, `test_research_ingest`, `test_collect`; **verified**: `pytest` now leaves `data/seeds|bronze|silver` byte-identical |

### 12.4 Still open

* `goi_faostat.yaml` has no `contract:` block, so FAOSTAT is collected without
  schema-drift protection (Phase A remainder).
* Discovery is single-resource per source; the multi-resource OGD crawl
  (`catalog/search`, CKAN `package_search`) is confirmed dead upstream, so the
  curated resource-id manifest in `metadata/sources/*.yaml` is the discovery
  input until a working catalogue endpoint is verified.
* `pipelines/models.py` is policy + audit only: no caller invokes a model yet,
  and the frontier seam stays opt-in per §5.3.
* Gold conversion (S6) is unchanged; `fact_*` tables are still absent, which is
  why `DOMAIN_COVERAGE` gaps dominate the register.
