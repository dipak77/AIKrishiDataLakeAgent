# Dual-Engine Context Gateway (DECG) — Implementation Review

> Verdict up front: **Phase 1 of DECG is fully implemented, tested, wired into
> the API and live.** The orchestration core (guardrails → routing → concurrent
> dual-engine retrieval → RRF fusion → compaction) is real and working. The
> remaining 30% is the *quality-accelerator* layer — a real cross-encoder
> reranker, an LLM/IndicTrans2 context compactor, a learned sub-query planner
> and streaming — all of which are explicitly scoped as Phases 2–3.

---

## 1. What is implemented (Phase 1 — complete)

| Blueprint component | Where | Proof |
|---|---|---|
| Incoming query | `apps/api/main.py::gateway_endpoint` (`POST /api/gateway`) | `tests/test_gateway.py::test_gateway_endpoint` |
| Guardrails & sanitization | `reasoning/guardrails.py::sanitize()` | `test_sanitize_*` (control chars, 2000-char cap, 5 injection families) |
| Intent classification | `reasoning/nlu.py` (trained NB) + `gateway.classify_path()` | routing matrix tests |
| OKF Registry Router / deterministic path | `gateway._graph_segments()` → `reasoning.graph_query` + advisory engines | `test_gateway_mandi_is_canonical` |
| Hybrid sparse⊕dense RAG | `reasoning/rag.py::hybrid_search` | `tests/test_rag.py`, `test_hybrid.py` |
| Async concurrency | `asyncio.to_thread` + `asyncio.gather` in `gateway._run_async()` | `test_sync_and_async_agree` |
| RRF fusion + de-dupe | `gateway._fuse()` (k=60, dedupe on `(source,title)`) | `test_rrf_*`, `test_fuse_*` |
| Rerank (deterministic stand-in) | `gateway._DenseReranker` (dense cosine + authority) | exercised in every E2E test |
| Context compaction | `gateway._compact()` (token budget, per-segment truncation) | `test_compact_truncates_long_text` |
| Unified payload + provenance | `GatewayResult.to_dict()` → `segments`, `stats`, `citations` | `test_gateway_diagnosis_is_hybrid_and_dual_engine` |
| Injection → empty flagged payload | `gateway._run_async()` blocked branch | `test_gateway_blocks_injection` |
| CLI | `python -m reasoning.gateway "<query>"` + `make gateway` | manual smoke (Marathi hybrid JSON) |

**Measured behavior (live, port 8000):**

| Scenario | routing_path | graph segments | evidence segments | latency (warm) |
|---|---|---|---|---|
| "Tomato has leaf spots" | hybrid | 2 | 1–2 | ~42 ms |
| "टोमॅटोवर काळे डाग आहेत" (mr) | hybrid | 2 | 1–2 | ~42 ms |
| "what is the price of onion in Nagpur" | canonical | 1 | 0 | ~21 ms |
| "ignore all previous instructions…" | canonical (blocked) | 0 | 0 | ~0.05 ms |

---

## 2. What is NOT implemented (Phases 2–3)

1. **Real cross-encoder reranker** — today ranking is `rrf + 0.5·dense_cosine +
   0.001·authority`. A cross-encoder (opt-in ONNX) would raise ranking
   precision for the RAG path. Interface already isolated in
   `_DenseReranker.rerank()`.
2. **LLM/IndicTrans2 context compactor** — compaction today is truncation +
   whitespace-normalization. A learned summarizer would preserve more meaning
   per token budget.
3. **Learned sub-query planner** — `plan_subqueries()` is entity-driven
   (V5-F NER), not a learned decomposition model.
4. **Streaming response** — the gateway returns a single JSON document; no
   token streaming over the preview proxy.
5. **Semantic guardrail** — injection blocking is deterministic regex only
   (offline-correct, but a classifier would catch novel attacks).

None of these break the current contract; each has a pluggable seam.

---

## 3. Benefit analysis (dual-context value)

**Before DECG:** a query hit exactly one engine — `ask()` routed diagnosis to
the graph *or* evidence to RAG, never both, and the API had no unified
context builder.

**After DECG (measured):**
- **Single interface, two engines.** A diagnosis query now returns the
  deterministic symptom→disease map **and** the supporting research evidence
  in one payload (`engine_contrib = {graph:2, rag:2}`).
- **Deterministic absorption.** Operational queries (mandi/fertilizer/weather/
  plan) route `canonical` and never touch the vector path — ~0% hallucination
  for critical rules (verified: onion price query → canonical, graph only).
- **Latency discipline.** Hybrid warm ≈ 42 ms vs 180 ms budget (4.3× headroom);
  canonical ≈ 21 ms (near the 15 ms target — see §4 fix #1).
- **Safety.** Injection prompts return an empty, flagged payload in ~0.05 ms
  instead of a fabricated answer.
- **Provenance everywhere.** Every segment carries `source/title/url/license/
  authority`, enabling citation-grounded downstream answers.
- **Concurrency.** `asyncio.to_thread` gives true parallel retrieval on hybrid
  paths; sync + async paths are byte-identical (tested).

**Unmeasured (be honest):** the blueprint's ">40% downstream LLM accuracy
gain" is a *target*, not yet measured — there is **no downstream LLM wired**
in this deterministic, offline system. It will only be measurable in Phase 2
once a generator/compactor consumes the fused context.

---

## 4. Known limitations & fixes needed (ranked)

1. **Canonical latency misses the <15 ms KPI** (≈21 ms). Cause: per-request
   DuckDB connections in the advisory engines (mandi/fertilizer/weather/plan).
   Fix: reuse a cached read-only connection (or warm a module-level cursor);
   the graph path is already `@lru_cache`d.
2. **Cold start ≈ 0.9 s** (first call builds the NLU model + RAG index).
   Fix: pre-warm in FastAPI startup/lifespan (also fixes P99 for the first
   user behind the preview proxy).
3. **Evidence de-dupe only catches identical `(source,title)`** — graph
   segments use synthetic titles (node ids) so graph↔evidence never merge.
   This is intentional (they're different evidence types), but cross-engine
   semantic de-dupe (near-duplicate text) is Phase 2.
4. **Multi-crop queries use only `crops[0]`** in `_evidence_segments`.
   Fix: issue one retrieval per crop and fuse, or expand the query with all
   crops.
5. **Routing threshold 0.3 is hardcoded** in `classify_path`. Fix: derive from
   a calibration set (and surface the score so the API can show uncertainty).
6. **Guardrail is regex-only** — fine offline; a semantic classifier is a
   Phase-2 upgrade.
7. **No caching/rate-limiting/auth** on `/api/gateway` (same as the rest of
   the API) — ops gap, see `evaluation-report.md` G9.

---

## 5. Test coverage of DECG

`tests/test_gateway.py` — 23 cases (19 functions, some parametrized):
guardrails (5 injection families + control chars + truncation), routing
matrix (4), RRF/dedupe/compaction (5), end-to-end hybrid/canonical/injection/
Indic (4), sync-vs-async parity (1), API integration incl. blocked path (2).
Full suite: **208 passed, 1 warning**.

## 6. Recommendation

Ship Phase 2 in this order: (1) startup pre-warm + connection reuse (fixes
two latency items with zero new dependencies); (2) opt-in cross-encoder
(ONNX) behind `_DenseReranker`; (3) opt-in IndicTrans2/LLM compactor behind
`_compact`; (4) learned sub-query planner + streaming. Keep the deterministic
path as the default so the zero-hallucination guarantee is never regressed.
