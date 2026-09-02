# apps/

Application services.

- `api/` — **Krushi Mitra REST API** (FastAPI). One service exposing every
  engine + the assistant. Run with `agrilake-serve` / `make serve`.
- `web/` — **Krushi Mitra web UI** (single self-contained `index.html`),
  served by the API at `/`. Calls relative `/api/…` URLs only, so it works
  behind the preview proxy.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | liveness + lake summary |
| POST | `/api/query` | Krushi Mitra assistant (multilingual farmer Q&A) |
| POST | `/api/diagnose` | disease/pest/deficiency diagnosis |
| POST | `/api/fertilizer` | fertilizer advisory (crop × stage × soil test) |
| GET | `/api/mandi` | mandi price snapshot + trend |
| GET | `/api/markets` | list known APMC mandis |
| GET | `/api/weather` | district agromet advisory |
| GET | `/api/plan` | crop calendar plan |
| GET | `/api/plan/sow` | crops to sow in a month |
| GET | `/api/evidence` | BM25 research evidence |
| GET | `/api/graph/summary` | knowledge-graph stats |
| GET | `/api/graph/neighbors` | node neighbors |
| GET | `/api/graph/health` | crop disease/pest/deficiency map |
| GET | `/api/graph/candidates` | symptom → candidates via graph |

OpenAPI docs are auto-served at `/docs`.

## Planned (V5+)

- `ingestion-api/` — schedule + trigger connectors over HTTP (Kafka/Airflow)
- `search-api/` — vector/hybrid retrieval (Qdrant)
- `admin-api/` — source registry + lineage + quality dashboards
