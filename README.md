# AIKrishiDataLakeAgent

**Krushiverse / Agri Intelligence Lake** — an India-first, continuously expanding
agriculture data lake that powers farmer Q&A + RAG, crop recommendation,
disease/pest diagnosis, soil intelligence, fertilizer advisory, weather advisory,
crop planning, mandi intelligence, computer vision, research retrieval, and
(eventually) model fine-tuning.

This repository ships the **foundation through the assistant**: project
scaffold, canonical schemas, seed ontologies, a governed source registry, the
Bronze → Silver → Gold medallion pipeline, data-quality scoring, a
graph-native lakehouse, seven reasoning engines (diagnosis, fertilizer, mandi,
weather, crop planning, RAG evidence, nutrient math), and the **Krushi Mitra**
multilingual assistant — exposed as a REST API + web UI (`make serve`).

> **The key architectural decision.** We do *not* build "dump 10 TB of documents
> + a vector DB = AI platform". We build: `data → normalization → ontologies →
> knowledge graph → evidence layer → {structured analytics, vector RAG, vision}`.
> Every record carries source + license + geography + crop + season + growth stage
> + authority + ingestion date + version, so web extraction becomes a defensible
> production data foundation rather than an ungoverned scraper.

---

## Architecture

```
        Government          Research        Farmer Data        Vision
        ──────────          ────────        ───────────        ──────
        data.gov.in         ICAR/IARI       KCC queries        PlantDoc
        Agmarknet           SAUs/ICRISAT    KVK FAQs           PlantVillage
        IMD                 FAO             Public forums      Own uploads
        Soil Health Card    Journals        Blogs/Articles     Pest/disease images
             │                   │                │                 │
             └───────────────────┴────────────────┴─────────────────┘
                                     │
                             INGESTION LAYER          connectors/  (plugin base)
                  API / CSV / JSON / PDF / HTML / Images
                                     │
                                     ▼
                              BRONZE / RAW            pipelines/bronze.py  (immutable)
                                     │
                        Validation · OCR · Parsing · Cleaning ·
                        Dedup · Language detection · Entity extraction ·
                        Geocoding
                                     │
                                     ▼
                              SILVER / CLEAN          pipelines/silver.py
                                     │
                   Crop / Disease / Pest / Soil / Season /
                   State / District / Variety / Growth stage
                                     │
                                     ▼
                              GOLD / DOMAIN           pipelines/gold.py
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
      Lakehouse (DuckDB       Vector DB (Qdrant)       Knowledge Graph
      + Parquet/Iceberg)       (rag/ - future)         (knowledge_graph/)
            │                        │                        │
            └────────────────────────┼────────────────────────┘
                                     ▼
                           AGRI INTELLIGENCE APIs  (apps/ - future)
```

**Stack for V1 (deliberately light):** Python + Pydantic (schemas) + YAML
(source registry) + DuckDB/Parquet (lakehouse) + a JSON knowledge graph. The
blueprint's Postgres/PostGIS/Qdrant/MinIO/Iceberg/Kafka scale-out layer is
documented in `docs/architecture.md` and scaffolded in
`infrastructure/docker-compose.yml`.

---

## Repository layout

```
├── apps/                  # (future) ingestion-api / search-api / admin-api
├── connectors/            # source connector plugins (see base.AgricultureSourceConnector)
│   ├── government/        #   data_gov, kcc, agmarknet, imd, soil_health
│   ├── research/          #   fao (FAOSTAT), icar, research_pdf
│   ├── web/               #   crawler, article_parser, license_checker
│   └── vision/            #   plantdoc, plantvillage
├── pipelines/             # bronze / silver / gold + quality scoring
├── domain/                # canonical ontologies: crops, pests, diseases, soils,
│                          #   nutrients, fertilizers, pesticides, weather, geography
├── ontology/              # ontology loaders + cross-entity validators
├── knowledge_graph/       # nodes/edges builder + consistency checks
├── rag/                   # (future) vector retrieval
├── vision/                # (future) image pipeline
├── schemas/               # Pydantic record models + generated JSON Schema
├── metadata/sources/      # SOURCE REGISTRY (one YAML per registered source)
├── data/
│   ├── seeds/             # committed seed ontologies (CSV) — dim_crop, dim_geography, ...
│   └── fixtures/          # committed sample records for offline ingestion
├── scripts/               # seed_lake, ingest_live, build_gold, validate, gen_json_schema, build_graph
├── infrastructure/        # docker-compose for the scale-out stack (optional)
├── docs/                  # architecture, data model, source registry, roadmap, provenance
└── tests/
```

---

## Quickstart

```bash
make bootstrap             # ONE command: venv → seed → gold → validate → test
                           # (self-bootstraps .venv; idempotent; writes a health report)
make up                    # alias for `bootstrap`
make doctor                # environment + capability report (no build)

# … or the explicit steps (bootstrap runs these):
make setup                 # python3 -m venv .venv && pip install -e ".[dev]"
make seed                  # load seed ontologies into data/lake (DuckDB) + Parquet
make validate              # ontology + knowledge-graph + quality checks
make schema                # emit schemas/json/*.json from Pydantic models
make graph                 # emit data/gold/knowledge_graph.json
make gold                  # build application-ready gold tables
make test                  # smoke tests
make check                 # validate + test (fast pre-commit gate)

# Reasoning substrate (pure DuckDB — no LLM / vector DB):
python scripts/diagnose.py --crop tomato --symptoms "black spots, lower leaves yellowing"
python scripts/diagnose.py --crop "टोमॅटो" --symptoms "पानावर काळे डाग"   # Marathi symptoms
python scripts/diagnose.py --crop "धान" --symptoms "भूरे धब्बे, सफेद कली, बौना"  # Hindi

# Live ingestion (needs internet + optionally a data.gov.in API key; falls back
# to bundled fixtures when the source is unreachable):
make ingest SOURCE=agmarknet LIMIT=5
make ingest SOURCE=kcc LIMIT=5
make ingest SOURCE=faostat LIMIT=20

# Krushi Mitra — the assistant (REST API + web UI on http://0.0.0.0:8000):
make serve
```

See `docs/live-ingestion.md` for endpoint details and API-key setup.

Configuration is automatic (env `AGRILAKE_*` → `.env` → defaults); see
`.env.example`. The build report lands at `data/lake/_bootstrap_report.json`.
The Phase 4 product plan is in `docs/phase-4-plan.md`.

---

## What's seeded in V1

- **100+ canonical crops** with scientific names, families, types/groups, and
  Indian-language aliases (hi/mr/gu/pa/bn/od/ta/te/kn/ml/as).
- **All 36 Indian states/UTs → 764 districts** with ISO codes, curated
  headquarters coordinates for major agri districts, rename aliases, and
  representative tehsil/taluk/block/village rows — plus agro-climatic zones and
  agro-ecological regions.
- **Seasons** (kharif/rabi/zaid/summer/whole-year) and the full **phenological
  growth-stage timeline** per crop, with location overrides.
- **Disease + pathogen**, **pest**, **weed**, **nutrient**, **fertilizer**,
  **pesticide**, **biocontrol** and **soil** ontologies, with IPM-aligned control
  ladders and the authority/quality hierarchy.
- **Source registry** (one governed YAML per source: authority, license, schedule,
  domains, acquisition method) — no untraceable crawls.
- **Medallion pipeline** + **data-quality scoring** + **unified agriculture record**
  schema + **evidence-separated recommendations** (observation → diagnosis →
  evidence → management option → source → legal/label validity → location → date).
- **Reasoning substrate (V1.5)** — `fertilizer → contains → nutrient` (numeric),
  nutrient-deficiency disorders, symptom graph, IPM thresholds, crop calendars
  with location overrides, and a pure-DuckDB **diagnosis retriever**
  (`reasoning/`, `scripts/diagnose.py`) that accepts English **or** Hindi/Marathi
  crop + symptom text (Devanagari lexicon + hi/mr disambiguation in
  `pipelines/language.py`).

---

## Docs

| Document | Contents |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Full architecture, medallion, storage, scale-out plan |
| [`docs/data-model.md`](docs/data-model.md) | Gold lakehouse tables + unified record + field glossary |
| [`docs/source-registry.md`](docs/source-registry.md) | Source governance model and registered sources |
| [`docs/roadmap.md`](docs/roadmap.md) | V1 → Vn milestones and the 55-domain coverage target |
| [`docs/provenance-and-licensing.md`](docs/provenance-and-licensing.md) | ALLOW/REVIEW/BLOCK policy, GODL, authority hierarchy, lineage |
| [`docs/live-ingestion.md`](docs/live-ingestion.md) | Running live connectors, endpoints, keys, egress notes |
| [`docs/v7-plan.md`](docs/v7-plan.md) | **Next:** real ingestion (discovery + collection), the data-quality refinery, knowledge-gap closure, frontier-only model policy |

## License

Code: MIT. All ingested data retains its own provenance/license metadata
(see `docs/provenance-and-licensing.md`).
