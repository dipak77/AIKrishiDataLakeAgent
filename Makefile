PY ?= python3
VENV ?= .venv
BIN ?= $(VENV)/bin

.PHONY: bootstrap up doctor check verify-seeds serve graph-export eval-nlu import-lgd gateway research-corpus ingest-research benchmark load-test medallion train-reranker eval-reranker setup seed ingest validate schema graph gold test clean

## One-shot autonomous build: configure → venv → seed → gold → validate → test.
## Self-bootstraps its own virtualenv; idempotent (skips unchanged steps).
bootstrap:
	$(PY) scripts/bootstrap.py

## Alias for `bootstrap` (bring the whole lake up in one command).
up: bootstrap

## Environment + health report only (no build steps).
doctor:
	$(PY) scripts/bootstrap.py --check

## Validate + test (fast pre-commit gate).
check: validate test

## Verify committed data/seeds/*.csv still match seed_data.py (drift gate).
verify-seeds:
	$(BIN)/python scripts/verify_seeds.py

## Run the Krushi Mitra API + web UI (http://0.0.0.0:8000).
serve:
	$(BIN)/agrilake-serve

## Export the knowledge graph → Neo4j Cypher + Apache AGE SQL (data/gold/).
graph-export:
	$(BIN)/python scripts/export_graph.py

## Train + evaluate the NLU intent/NER models against the heuristic router.
eval-nlu:
	$(BIN)/python scripts/eval_nlu.py

## Import LGD subdistricts (block/village CSVs, or offline HQ baseline).
import-lgd:
	$(BIN)/python scripts/import_lgd.py

## Run the dual-engine context gateway. e.g. make gateway Q="Tomato has leaf spots"
gateway:
	$(BIN)/python -m reasoning.gateway $(Q)

## Build gold.research_chunk from the ICAR fixture (RAG corpus).
research-corpus:
	$(BIN)/python scripts/build_research_corpus.py

## Ingest research evidence (live ICAR fetch + offline fixture) → gold.research_chunk.
ingest-research:
	$(BIN)/python scripts/ingest_research.py

## Run the DECG golden-QA benchmark (accuracy + latency report).
benchmark:
	$(BIN)/python scripts/benchmark_gateway.py

## Load test the gateway (throughput + latency percentiles).
load-test:
	$(BIN)/python scripts/load_test.py

## Create virtualenv and install dependencies
setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

## Load seed ontologies (crops, geography, diseases, pests, nutrients, ...) into the lakehouse
seed:
	$(BIN)/python scripts/seed_lake.py

## Materialize bronze (immutable) + silver (normalized) from seed ontologies.
medallion:
	$(BIN)/python scripts/build_medallion.py

## Train the learned gateway reranker (→ data/gold/reranker_model.json).
train-reranker:
	$(BIN)/python scripts/train_reranker.py

## Evaluate reranker ranking quality (top-1 recall / MRR).
eval-reranker:
	$(BIN)/python scripts/eval_reranker.py

## Run live connectors (falls back to fixtures offline). e.g. make ingest SOURCE=agmarknet LIMIT=5
ingest:
	$(BIN)/python scripts/ingest_live.py --source $(SOURCE) --limit $(LIMIT)

## Validate ontologies + knowledge-graph consistency + data-quality scoring
validate:
	$(BIN)/python scripts/validate.py

## Emit JSON Schema files from the Pydantic record models
schema:
	$(BIN)/python scripts/gen_json_schema.py

## Build the knowledge graph from seeded ontologies
graph:
	$(BIN)/python scripts/build_graph.py

## Build gold/ application-ready tables from silver/ (incl. derived yield, quality scores)
gold:
	$(BIN)/python scripts/build_gold.py

test:
	$(BIN)/python -m pytest -q

clean:
	rm -rf data/bronze data/silver data/gold data/lake
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
