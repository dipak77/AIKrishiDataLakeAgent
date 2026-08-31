PY ?= python3
VENV ?= .venv
BIN ?= $(VENV)/bin

.PHONY: setup seed ingest validate schema graph gold test clean

## Create virtualenv and install dependencies
setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

## Load seed ontologies (crops, geography, diseases, pests, nutrients, ...) into the lakehouse
seed:
	$(BIN)/python scripts/seed_lake.py

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
