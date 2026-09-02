# V5 — Retrieval & scale-out tracks

> Status: **in progress**. V5 upgrades the retrieval + product layers on top of
> the Phase 4 Krushi Mitra assistant. Tracks are independent; each lands and
> ships on its own. (V5-A shipped this slice.)

## Track V5-A — Hybrid semantic retrieval ✅ shipped

Upgrades the RAG evidence layer (Track 9) from pure BM25 to a **hybrid
retriever**:

- **Dense embeddings, dependency-free** — `reasoning/embeddings.py` implements
  the *hashing trick* (feature-hashed word + character n-gram features,
  sublinear TF weighting, collision-correct L2 normalization) with no
  numpy/scikit/ONNX — a deterministic stand-in for a real embedding model that
  already captures character-level overlap ("spot"/"spots", "leaf"/"leaves",
  and typos like "alternara" → Alternaria).
- **Ontology-driven query expansion** — `expand_query()` resolves crop aliases
  to canonical + scientific names and maps disease/deficiency names (e.g.
  "Khaira") to their symptom keywords, so retrieval matches the ontology, not
  just the query words.
- **Reciprocal Rank Fusion (RRF)** — `reasoning/rag.py::HybridIndex` fuses
  BM25 ranks with dense-similarity ranks (k=60), with a dense-similarity floor
  (0.12) to reject hash-noise and authority score as a deterministic tiebreak.
- Backward compatible: `search()` stays BM25; `hybrid_search()` is the new
  path, and `evidence_for_diagnosis()`, the assistant, and `/api/evidence`
  (default `mode=hybrid`) now use it.
- Verified: typo query "alternara" → BM25 empty, hybrid surfaces Early blight
  + Purple blotch chunks; 11 new tests (`tests/test_hybrid.py`).

## Track V5-B — Neo4j / Apache AGE graph export ✅ shipped

- `knowledge_graph/export.py` reads `gold.graph_nodes` / `gold.graph_edges`
  (or builds in-memory) and emits **idempotent** load scripts:
  - `data/gold/knowledge_graph.cypher` — Neo4j: per-type unique constraints,
    `MERGE` nodes on `id`, `MATCH … MERGE` edges; props (JSON) expanded; string
    literals escape `\` and `'`.
  - `data/gold/knowledge_graph_age.sql` — Apache AGE (PostgreSQL): `cypher()`
    calls with `$$…$$` dollar-quoting, one statement per node/edge.
- CLI `scripts/export_graph.py` + console script `agrilake-export-graph` +
  `make graph-export`.
- Verified: 1489 nodes / 1706 edges exported, all quotes balanced, all
  relationship types valid; 7 new tests (`tests/test_graph_export.py`).

## Track V5-F — Trained intent + NER ✅ shipped

Replaces the heuristic router inside `assistant.ask()` with a model fit on
data (`reasoning/nlu.py`), with no heavy dependencies (pure Python):

- **IntentClassifier** — multinomial Naive Bayes over Unicode word tokens +
  character n-grams (3–4), trained on a corpus generated from the seed
  ontologies (crop/alias lexicon, symptom lexicon, disease/pest lists, growth
  stages, geography) with per-intent templates in English + Hindi/Marathi/
  Tamil/Telugu. OOV tokens contribute no evidence; `general` is a
  confidence-threshold fallback (plus a small greeting blocklist), mirroring
  the heuristic's semantics. Character n-grams give typo robustness the
  keyword router lacks: `"blght on tomato"` → `diagnosis` (heuristic: general).
- **EntityTagger** — greedy first-order BIO sequence tagger (same NB scorer)
  over per-token features (token, prefix/suffix, char n-grams, gazetteer
  membership, previous label) + maximal-munch gazetteer pass for multi-word
  entities; symptom spans are validated against the closed symptom vocabulary.
  Extracts crop / district+state / growth-stage / symptom spans, tolerating
  Indic inflections (`टोमॅटोवर` → Tomato) and plurals (`tomatoes` → Tomato).
- Model serialized to `data/gold/nlu_model.json` (deterministic, seeded);
  retrained automatically if missing/version-changed; `ask()` falls back to the
  keyword router on any failure. `AssistantResponse` now carries
  `intent_confidence` + `nlu_model`.
- Verified: 19/19 held-out intent eval (parity with heuristic on keyword
  queries, wins on typos); 14 new tests (`tests/test_nlu.py`); full suite 145.

## Track V5-C — Vision inference scaffold ✅ shipped

`vision/inference.py` is a **dependency-free** image-diagnosis scaffold:

- **Pure-Python PNG decoder** (stdlib `zlib`/`struct`) — RGB[A]/grayscale,
  8/16-bit, all scanline filters (Sub/Up/Average/Paeth); indexed + interlaced
  PNGs rejected with a clear message. No Pillow/numpy/OpenCV required.
- **Colour descriptor** — strided HSV sampling → green/yellow/brown/black/
  white/red fractions (O(max_pixels), independent of image size).
- **Pluggable backend interface** — `VisionBackend.predict(image, crop)`;
  `heuristic` (shipped: colour→symptom keywords→ranked ontology) plus
  `onnx` / `tflite` / `transformers` stubs that raise `BackendUnavailable`
  until weights are downloaded opt-in (PlantDoc / PlantVillage metadata
  fixtures already committed).
- **Ontology mapping** — candidates keyed by the same ids as
  `gold.dim_disease` / `gold.dim_pest` / `gold.nutrient_deficiency`, each with
  provenance; crop-scoping supported.
- `analyze_image()` orchestrator + `scripts/analyze_image.py` CLI + 19 tests
  (`tests/test_vision.py`): PNG round-trip, filter correctness, colour
  descriptors, healthy vs symptomatic verdicts, crop filter, backend registry.

## Track V5-D — MT behind `language.translate()` ✅ shipped

`pipelines/language.py::translate()` is now a **pluggable backend** with a real
offline fallback:

- **Lexicon backend (default)** — deterministic glossary translation to English
  built from `CROP_ALIASES` (12 languages) + `SYMPTOM_LEXICON` (hi/mr/ta/te) +
  a small function/agri-word glossary; unknown Devanagari tokens fall back to
  the existing ITRANS transliterator. Returns `status` (`ok`/`partial`/
  `pending_mt`), `coverage`, and `untranslated` so callers never mistrust a
  partial translation.
- **Pluggable MT backends** — `indictrans2` / `indicmt` / `api` (external)
  selected via `AGRI_MT_BACKEND` or the `backend` arg; each raises
  `MTBackendUnavailable` until its runtime/weights are installed (opt-in).
  `translate()` automatically falls back to the lexicon and records
  `fallback_reason`.
- 12 tests (`tests/test_translate.py`): en/mr/hi/ta/te translation, partial +
  transliteration, non-English target, registry, env selection, fallback.

## Track V5-E — Full LGD geography import ✅ shipped

- `scripts/import_lgd.py` parses Local Government Directory **blocks/tehsils +
  villages** CSVs (`LGD_DIR` / `--lgd-dir`, default `data/bronze/lgd`) into
  `gold.dim_subdistrict`, replacing the representative examples; documented CSV
  schema + real sample fixtures (`data/fixtures/lgd/`). **Offline baseline**
  (no CSVs): deterministic real-data coverage — every district with a known HQ
  town (174) plus the representative tehsil/village examples (no fabricated
  names), with a coverage report (174/764 ≈ 23% offline; full coverage via LGD
  CSVs).
- `resolve_subdistrict()` now reads the persisted `gold.dim_subdistrict` first
  and falls back to `SUBDISTRICT_EXAMPLES`; same (state, district) hint
  semantics, so free-text tehsil/village names resolve against the full table.
- 9 tests (`tests/test_lgd_import.py`): CSV parsing, baseline, lake round-trip,
  lake-backed + fallback resolution.

