# Phase 1 review & Phase 2 proposal

Status: **Phase 1 merged** (`main` @ `a25721a`). This document records an honest
review of the merged foundation and the agreed next phase (the user selected
**Track 1 + 4 — reasoning substrate** as the Phase 2 starting point).

---

## 1. Verified baseline

Re-verified on a clean install: `pip install -e ".[dev]"` + `pytest` → **9/9 pass**;
`seed_lake` loads 17 gold dimension tables into DuckDB; the knowledge graph builds
(360 nodes / 322 edges); referential-integrity validation passes.

Shipped and working:

- Medallion pipeline + quality scoring (authority hierarchy wired into `enrich`).
- Ontologies: 116 crops, 296 aliases (Unicode-safe resolution), 36 states/UTs,
  124 districts, 30 diseases, 21 pests, 12 nutrients, 18 fertilizers, 18 pesticides,
  8 soils, 8 weeds, seasons + 12 growth stages + crop calendars.
- Connector plugin base + source registry (11 governed sources) + license gate +
  crawler skeleton + offline fixture fallback with honest provenance tagging.
- Pydantic record models + JSON Schema (incl. unified agriculture record).

## 2. Strengths

- Right architecture (blueprint §30): medallion → ontologies → graph → evidence,
  not a document dump.
- Governance is real, not cosmetic: registry, ALLOW/REVIEW/BLOCK, authority
  hierarchy, evidence/lineage fields on every record.
- Everything runs offline end-to-end, so CI and demos are cheap.

## 3. Gaps (verified, not inferred)

1. **Fertilizer → nutrient is not structured.** `urea.composition` is the string
   `"N 46%"`; there is no `fertilizer_nutrient` table and no
   `fertilizer → contains → nutrient` graph edges, so the nutrient math required
   by §9 and the fertilizer-advisory engine is impossible today.
2. **Knowledge graph is entity-only.** Edge types are only
   `hasDisease/affects/causedBy/pestOf/hasPest/hasSeason/inState`. Missing:
   `fertilizer→nutrient`, `crop→growth_stage`, `symptom→disease`,
   `disease→favourable_conditions`, `nutrient→deficiency→crop`.
3. **Diagnosis path not wired.** `dim_disease` is all free-text VARCHAR (no
   `growth_stage`, `differential_diagnosis`); there is no symptom→disease index,
   so `query → crop → problem → recommendation` cannot be routed yet.
4. **Agronomic depth is skeletal** — 30 diseases / 21 pests, uneven crop coverage,
   one-line entries.
5. **Crop calendar is 5 crops / 21 rows**, no location overrides (§5 model absent).
6. **Geography is 2 of 8 levels** (124/~750 districts; no subdistrict/block/tehsil/
   village/lat-lon; `agroecological_region` NULL everywhere).
7. **Multilingual not yet true.** Devanagari input is always tagged `hi` (Marathi
   mislabeled; both return `{language: hi, confidence: 0.5}`). No hi/mr
   disambiguation, transliteration, or translation step.
8. **Engineering gaps.** Bronze never written by connectors end-to-end; no silver
   dedup; Pydantic models not enforced at persist (`validate()` no-op); live
   connectors unverified against real payloads; IMD/ICAR/SHC are fixture stubs;
   no CI/lint/types; seeds-CSV ↔ `seed_data.py` can drift silently.

## 4. Phase 2 plan (agreed starting point: Track 1 + 4)

| # | Track | Delivers | Status |
|---|---|---|---|
| 1 | Structured agronomy | `fertilizer_nutrient` (numeric), `nutrient_deficiency`, symptom index, deepened disease/pest (growth_stage, differential, ETL), top-20 calendars + location overrides | ✅ shipped |
| 2 | Geography + language | 764 districts + hierarchy + lat/lon + AER; hi/mr disambiguation + transliteration + Indic symptom lexicon | ✅ shipped |
| 3 | Real ingestion + hardening | bronze persistence + dedup, schema enforcement, verified FAOSTAT/data.gov.in pipeline, retry/backoff, CI | queued |
| 4 | First reasoning milestone | pure-DuckDB diagnosis retriever: crop+symptom → candidates → stage/env filter → management + source | ✅ shipped |

Track 1 + 4 convert the entity catalog into something that can **answer** — the
"most important architectural decision" in the blueprint — using only data + SQL
(no new infra, no vector DB, no LLM).

### Shipped in this slice

- `gold.fertilizer_nutrient` (29 rows, numeric) + graph `fertilizer → contains → nutrient`
- `gold.nutrient_deficiency` (13 rows) + graph `deficiency → deficiencyOf/onCrop`
- symptom graph: 446 symptom nodes + `hasSymptom` edges
- deepened `dim_disease` (growth_stage, differential_diagnosis) and `dim_pest`
  (economic_threshold, monitoring, growth_stage)
- `crop_calendar` 21 → 60 rows + `crop_calendar_override` (India → state/district → crop)
- `reasoning.diagnose` (ranked, evidence-cited candidates), `reasoning.fertilizer`
  (nutrient math), `scripts/diagnose.py` CLI
- knowledge graph 360 → 849 nodes / 1066 edges; tests 9 → 16 (all passing)

### Track 2 shipped (follow-up)

- `GEOGRAPHY` expanded 130-representative → **764 districts** across all 36
  states/UTs; `DISTRICT_HQ` curated lat/lon for ~174 major agri districts;
  rename aliases (Orissa/Odisha, Uttaranchal/Uttarakhand, Kadapa/YSR,
  Belgaum/Belagavi, Prayagraj/Allahabad …); ISO-suffix + abbreviation
  resolution (`MH`, `UP`, `CG`) in `catalog.GEOGRAPHY_LOOKUP`.
- `dim_subdistrict` representative tehsil/taluk/block + village rows (69);
  `dim_geography` now carries latitude/longitude + agroecological_region.
- `pipelines.language`: script detection, Hindi/Marathi disambiguation
  (distinctive-word lexicon + geographic prior), Devanagari → Latin
  transliteration, and a `translate()` MT-hook contract (real IndicMT lands in
  a later milestone).
- Hindi + Marathi symptom lexicons (`SYMPTOM_LEXICON`) so `reasoning.symptoms`
  maps `पानावर काळे डाग` → `leaf + black + spots`; `diagnose()` now returns
  candidates for Marathi/Hindi-only symptom text.
- `diagnose(strict_crop=…)`: crop compatibility is now a hard filter (the
  blueprint's chain) instead of a score bonus; the old English-only limitation
  regression test was replaced by positive Hindi/Marathi assertions.

### Remaining limitation (accepted)

Devanagari is the only Indic script with a symptom lexicon; Tamil/Telugu/
Kannada/… and full block/zilla/village geography (LGD import) remain later
milestones, and real machine translation is a stub behind `language.translate`.

## 5. Acceptance criteria for this slice

- `gold.fertilizer_nutrient` numeric table + graph `fertilizer → contains → nutrient`.
- `gold.nutrient_deficiency` table + graph links.
- `gold.symptom_index` built from seed data (+ synonyms), with symptom→entity edges.
- Deepened disease (growth_stage, differential) and pest (ETL, monitoring) fields.
- Crop calendar for top 20 crops + state/district location overrides.
- `reasoning.diagnose(crop, symptoms, …)` returns ranked, evidence-cited candidates.
- `reasoning.fertilizer` nutrient-math helpers (supply computation).
- CLI `scripts/diagnose.py` + tests; all prior tests still green.
