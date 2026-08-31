# Architecture

Krushiverse / Agri Intelligence Lake is an **India-first agriculture data lake**.
This document describes the target architecture; the code in this repository
implements the foundation layers marked `[V1]`.

## 1. Design principle

We do **not** build "10 TB of documents + a vector database = AI platform".
Instead:

```
         AGRI DATA
             ↓
       NORMALIZATION          (pipelines/silver.py)
             ↓
        ONTOLOGIES            (domain/, ontology/)
             ↓
      KNOWLEDGE GRAPH         (knowledge_graph/)
             ↓
      EVIDENCE LAYER          (provenance + authority + versioning)
             ↓
 ┌────────────┼────────────────┐
 ↓            ↓                ↓
Structured  Vector RAG       Vision
analytics   knowledge        models
(DuckDB)    (Qdrant)         (PlantDoc/PlantVillage)
 │            │                │
 └────────────┴────────────────┘
             ↓
      REASONING ENGINE        (future: Krushi Mitra)
             ↓
       FARMER ANSWER
```

Recommendations are **evidence-linked** (retrieved fact → document → page →
publication date), never silently overwritten, and always separated from
observations/diagnoses (see "Evidence vs recommendation" in `data-model.md`).

## 2. Medallion layers

### Bronze — immutable raw
`data/bronze/<source>/...` — the byte-for-byte original artifact plus an
ingestion manifest (sha256 content hash, retrieved date, license, source id).
Never mutated. One directory per registered source.

### Silver — normalized
`data/silver/<domain>/...` — cleaning, dedup, language detection, entity
extraction, geocoding, schema alignment to canonical record models
(`schemas/`).

### Gold — domain-ready
`data/gold/<application>/...` — joined dimension/fact tables, derived metrics
(yield = production / area), quality scores, versioned advisory tables, the
RAG corpus and the knowledge graph.

## 3. Storage (V1)

| Layer | Technology | Notes |
| --- | --- | --- |
| Object / files | Local filesystem (MinIO/S3 compatible layout) | `data/` mirrors `s3://agrilake/` keys |
| Lakehouse query | DuckDB | SQL over Parquet; identical layout migrates to Trino/Spark |
| Files | Parquet (columnar, partitioned by domain/date) | DuckDB native read/write |
| Graph | JSON knowledge graph (`data/gold/knowledge_graph.json`) | migrates to Neo4j/AGE |
| Metadata | YAML source registry + JSON Schemas | versioned in git |

### Scale-out path (documented, scaffolded in `infrastructure/docker-compose.yml`)

```
                    MinIO / S3
                        │
                 Apache Iceberg
                        │
            ┌───────────┼────────────┐
            │           │            │
         DuckDB       Spark        Trino
                        │
                    PostgreSQL + PostGIS
                        │
              ├────────── Qdrant (vector)
              └────────── Neo4j/AGE (knowledge graph)

Kafka → Airflow/Dagster → Spark/Trino → Iceberg → MinIO → Postgres/PostGIS → Qdrant → Neo4j
```

## 4. Ingestion layer — plugin architecture

Every source implements one interface (`connectors/base.py`):

```python
class AgricultureSourceConnector:
    def discover(self): ...   # enumerate available resources
    def fetch(self): ...      # download / call API
    def validate(self): ...   # schema + integrity checks
    def normalize(self): ...  # to canonical silver record
    def enrich(self): ...     # ontology links, geocoding, entities
    def persist(self): ...    # bronze + silver + gold
```

A source must be **registered** in `metadata/sources/*.yaml` before it can be
crawled (see `docs/source-registry.md`).

## 5. Ontologies

Canonical, hand-curated dimensions (never trust raw dataset names):

- `dim_crop` + `crop_alias` (100+ crops, 12 languages)
- `dim_geography` (state/UT → district → subdistrict → block → village → lat/lon
  → agro-climatic zone → agro-ecological zone)
- `dim_season`, `dim_growth_stage`, `crop_calendar`
- `dim_disease` + `dim_pathogen`, `dim_pest`, `dim_weed`
- `dim_nutrient`, `dim_fertilizer`, `dim_pesticide`, `dim_biocontrol`, `dim_soil`
- `authority_levels`

Relationships (e.g. crop → season, fertilizer → nutrients, disease → causal
agent → crop host → favourable conditions) are materialized in the knowledge
graph and validated by `scripts/validate.py`.

## 6. Knowledge graph

Enables agronomic reasoning beyond RAG:

```
Tomato ──hasDisease──→ Early Blight ──causedBy──→ Alternaria solani
  │                          └────── symptom ────→ concentric leaf spots
  ├──nutrientDeficiency──→ Nitrogen Deficiency
  ├──pest──→ Fruit Borer
  ├──cultivatedIn──→ Maharashtra
  └──season──→ Kharif
```

## 7. Quality & provenance

Every record carries `authority_score`, `freshness_score`,
`completeness_score`, `location_specificity`, `crop_specificity`,
`evidence_score`, `expert_verified`, `license_score`, `source`, `license`,
`ingested_at`, `version`. The authority hierarchy is defined in
`data/seeds/authority_levels.csv` (1.00 government/ICAR/SAU → 0.20 anonymous
social media).

## 8. Future applications (`apps/`)

- **AI Krushi Mitra** — conversational farmer assistant over evidence-linked RAG
- **Disease detection** — vision service over the image lake
- **Fertilizer advisory** — crop × variety × stage × soil test × target yield →
  nutrient requirement → fertilizer recommendation
- **Crop plan / market engine** — calendar + mandi intelligence
