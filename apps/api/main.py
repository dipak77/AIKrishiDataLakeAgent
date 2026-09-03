"""Krushi Mitra — REST API service (Track 14).

One FastAPI app exposing every lake engine + the assistant:

    POST /api/query          → assistant (multilingual farmer Q&A)
    POST /api/diagnose       → disease/pest/deficiency diagnosis
    POST /api/fertilizer     → fertilizer advisory (crop × stage × soil test)
    GET  /api/mandi          → mandi price snapshot + trend
    GET  /api/weather        → district agromet advisory
    GET  /api/plan           → crop calendar plan / what-to-sow
    GET  /api/evidence       → BM25 research evidence
    GET  /api/graph/*        → knowledge-graph queries
    POST /api/gateway        → dual-engine context gateway (DECG)
    GET  /health             → liveness + lake summary

Run:  agrilake-serve  (or `python apps/api/main.py`)

The web UI is served at `/` (single self-contained page; calls relative
`/api/…` URLs so it works behind the preview proxy).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

log = logging.getLogger("krushi-mitra")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Pre-warm NLU + RAG + graph + advisory caches so the first request is fast."""
    try:
        from reasoning.warmup import prewarm

        report = await asyncio.to_thread(prewarm)
        log.info("prewarm complete: %s", report)
    except Exception as exc:  # never block startup on warmup
        log.warning("prewarm skipped: %s", exc)
    yield


app = FastAPI(
    title="Krushi Mitra",
    description="India-first agriculture intelligence assistant (Agri Lake).",
    version="0.5.0",
    lifespan=lifespan,
)

# The preview proxy embeds this app under a generated origin; allow all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ops guards: optional API token + in-memory rate limit (config via env).
from apps.api.middleware import OpsMiddleware, RequestLoggingMiddleware  # noqa: E402

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(OpsMiddleware)

WEB_UI = ROOT / "apps" / "web" / "index.html"


# ── Request models ───────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class DiagnoseRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=100)
    symptoms: str = Field(..., min_length=1, max_length=1000)
    stage: str | None = Field(default=None, max_length=100)
    top: int = Field(default=5, ge=1, le=50)


class FertilizerRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=100)
    stage: str | None = Field(default=None, max_length=100)
    soil: dict[str, Any] | None = None


class GatewayRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    crop: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=5, ge=1, le=20)


class VisionRequest(BaseModel):
    image_base64: str | None = None
    image_path: str | None = None
    crop: str | None = Field(default=None, max_length=100)
    backend: str = Field(default="auto", max_length=50)
    top_k: int = Field(default=5, ge=1, le=20)


class NLURequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


# ── Liveness + docs ──────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    from reasoning.graph_query import graph_summary

    return {"status": "ok", "service": "krushi-mitra", "lake": graph_summary()}


@app.get("/", include_in_schema=False)
def web_ui() -> FileResponse:
    if WEB_UI.is_file():
        return FileResponse(WEB_UI)
    raise HTTPException(status_code=404, detail="web UI not found")


# ── Assistant ────────────────────────────────────────────────────────────────
@app.post("/api/query")
def query(req: QueryRequest) -> dict[str, Any]:
    from reasoning.assistant import ask

    return ask(req.query).as_dict()


# ── Diagnosis ────────────────────────────────────────────────────────────────
@app.post("/api/diagnose")
def diagnose(req: DiagnoseRequest) -> dict[str, Any]:
    from reasoning.diagnose import diagnose as run

    results = run(req.crop, req.symptoms, growth_stage=req.stage, top_n=req.top)
    return {"crop": req.crop, "results": [r.as_dict() for r in results]}


# ── Fertilizer ───────────────────────────────────────────────────────────────
@app.post("/api/fertilizer")
def fertilizer(req: FertilizerRequest) -> dict[str, Any]:
    from reasoning.advisory import recommend_fertilizer

    adv = recommend_fertilizer(req.crop, growth_stage=req.stage, soil_test=req.soil)
    if adv is None:
        raise HTTPException(status_code=404, detail=f"no nutrient recipe for '{req.crop}'")
    return adv.as_dict()


# ── Mandi ────────────────────────────────────────────────────────────────────
@app.get("/api/mandi")
def mandi(
    commodity: str = Query(..., min_length=1, max_length=100),
    market: str | None = Query(default=None, max_length=100),
) -> dict[str, Any]:
    from reasoning.mandi import market_advisory

    adv = market_advisory(commodity, market=market)
    if adv is None:
        raise HTTPException(status_code=404, detail=f"no price data for '{commodity}'")
    return adv.as_dict()


@app.get("/api/markets")
def markets() -> list[dict[str, Any]]:
    from reasoning.mandi import list_markets

    return list_markets()


# ── Mandi district view (Agmarknet dashboard: district avg + MSP) ────────────
@app.get("/api/mandi/districts")
def mandi_districts() -> dict[str, Any]:
    """Districts covered by the dashboard feed (location picker for the UI)."""
    from reasoning.mandi_dashboard import covered_districts, dashboard_source

    return {"districts": covered_districts(), "data_source": dashboard_source()}


@app.get("/api/mandi/district")
def mandi_district(
    district: str = Query(..., min_length=1, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    commodity: str | None = Query(default=None, max_length=100),
) -> dict[str, Any]:
    """Today's district-wise rates + MSP comparison for the user's location."""
    from reasoning.mandi_dashboard import district_view

    view = district_view(district, state=state, commodity=commodity)
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=f"no dashboard coverage for district '{district}'"
            + (f" in '{state}'" if state else "")
            + " (see /api/mandi/districts for covered districts)",
        )
    return view.as_dict()


# ── Weather ──────────────────────────────────────────────────────────────────
@app.get("/api/weather")
def weather(
    district: str = Query(..., min_length=1, max_length=100),
    crop: str | None = Query(default=None, max_length=100),
) -> dict[str, Any]:
    from reasoning.weather import agromet_advisory

    adv = agromet_advisory(district, crop=crop)
    if adv is None:
        raise HTTPException(status_code=404, detail=f"no advisory could be resolved for '{district}'")
    return adv.as_dict()


# ── Crop planning ────────────────────────────────────────────────────────────
@app.get("/api/plan")
def plan(
    crop: str = Query(..., min_length=1, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None, max_length=100),
) -> dict[str, Any]:
    from reasoning.crop_plan import crop_plan

    p = crop_plan(crop, state=state, district=district)
    if p is None:
        raise HTTPException(status_code=404, detail=f"no calendar for '{crop}'")
    return p.as_dict()


@app.get("/api/plan/sow")
def plan_sow(month: int = Query(..., ge=1, le=12), state: str | None = None) -> list[dict[str, Any]]:
    from reasoning.crop_plan import crops_to_sow

    return crops_to_sow(month, state=state)


# ── Evidence (RAG) ───────────────────────────────────────────────────────────
@app.get("/api/evidence")
def evidence(
    query: str = Query(..., min_length=1, max_length=2000),
    crop: str | None = Query(default=None, max_length=100),
    top: int = Query(default=5, ge=1, le=20),
    mode: str = Query(default="hybrid", max_length=20),
) -> dict[str, Any]:
    from reasoning.rag import hybrid_search, search

    if mode not in ("hybrid", "bm25"):
        raise HTTPException(status_code=400, detail="mode must be 'hybrid' or 'bm25'")
    hits = hybrid_search(query, top_k=top, crop=crop) if mode == "hybrid" else search(query, top_k=top, crop=crop)
    return {"query": query, "mode": mode, "hits": [h.as_dict() for h in hits]}


# ── Knowledge graph ──────────────────────────────────────────────────────────
@app.get("/api/graph/summary")
def graph_summary() -> dict[str, Any]:
    from reasoning.graph_query import graph_summary

    return graph_summary()


@app.get("/api/graph/neighbors")
def graph_neighbors(
    node_id: str = Query(..., min_length=1, max_length=200),
    direction: str = Query(default="out", max_length=10),
) -> list[dict[str, Any]]:
    from reasoning.graph_query import graph_neighbors

    if direction not in ("in", "out", "both"):
        raise HTTPException(status_code=400, detail="direction must be 'in', 'out' or 'both'")
    return graph_neighbors(node_id, direction=direction)


@app.get("/api/graph/health")
def graph_health(crop: str = Query(..., min_length=1, max_length=100)) -> dict[str, Any]:
    from reasoning.graph_query import crop_health_map

    return crop_health_map(crop)


@app.get("/api/graph/candidates")
def graph_candidates(
    symptoms: str = Query(..., min_length=1, max_length=1000),
    crop: str | None = Query(default=None, max_length=100),
    top: int = Query(default=8, ge=1, le=50),
) -> list[dict[str, Any]]:
    from reasoning.graph_query import symptom_candidates

    return symptom_candidates(symptoms, crop=crop, top_n=top)


@app.get("/api/graph/path")
def graph_path_endpoint(
    src: str = Query(..., min_length=1, max_length=200),
    dst: str = Query(..., min_length=1, max_length=200),
    max_depth: int = Query(default=5, ge=1, le=10),
) -> list[dict[str, Any]]:
    from reasoning.graph_query import graph_path

    return graph_path(src, dst, max_depth=max_depth)


# ── Vision Crop Doctor (Image Diagnosis) ──────────────────────────────────
# 8 MiB base64 ≈ 6 MiB raw — matches vision.inference.MAX_IMAGE_BYTES.
MAX_VISION_B64_CHARS = 11_000_000

@app.post("/api/vision")
def vision_endpoint(req: VisionRequest) -> dict[str, Any]:
    import base64
    import logging
    from vision.inference import VisionError, analyze_image

    _log = logging.getLogger("krushi-mitra.vision")
    if req.image_path:
        # Server-side paths are a local-file-read primitive: sandbox them to
        # the repo's data/uploads tree and refuse everything else.
        raw = (req.image_path or "").strip().replace("\\", "/")
        base = (ROOT / "data" / "uploads").resolve()
        candidate = (base / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            raise HTTPException(status_code=400, detail="image_path must live under data/uploads")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="image file not found")
        source: Any = candidate
    elif req.image_base64:
        raw_b64 = req.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        if len(raw_b64) > MAX_VISION_B64_CHARS:
            raise HTTPException(status_code=413, detail="image too large (max ~6 MB raw)")
        try:
            source = base64.b64decode(raw_b64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid base64 image data")
    else:
        raise HTTPException(status_code=400, detail="either image_base64 or image_path must be provided")

    if req.backend not in ("auto", "heuristic", "onnx", "tflite", "transformers"):
        raise HTTPException(status_code=400, detail="unknown vision backend")
    try:
        res = analyze_image(source, crop=req.crop, backend=req.backend, top_k=req.top_k)
        return res.as_dict()
    except VisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to clients
        _log.exception("vision inference failed")
        raise HTTPException(status_code=500, detail="vision inference failed") from exc


# ── NLU Diagnostic & Parsing ──────────────────────────────────────────────
@app.post("/api/nlu")
def nlu_endpoint(req: NLURequest) -> dict[str, Any]:
    from pipelines.language import detect_language
    from reasoning.nlu import get_pipeline

    pipe = get_pipeline()
    res = pipe.predict(req.query)
    lang = detect_language(req.query)
    return {
        "query": req.query,
        "language": lang["language"],
        "language_confidence": lang["confidence"],
        "intent": res.intent,
        "intent_confidence": res.intent_confidence,
        "intent_scores": res.intent_scores,
        "model": res.model,
        "crop": res.crop,
        "location": res.location,
        "stage": res.stage,
        "symptoms": res.symptoms,
    }


# ── Medallion Lakehouse Observability & Metrics ──────────────────────────
@app.get("/api/metrics")
def metrics_endpoint() -> dict[str, Any]:
    from pipelines.storage import LAKE_DIR, get_read_connection
    from reasoning.graph_query import graph_summary

    lake = LAKE_DIR / "agrilake.duckdb"
    tables: dict[str, int] = {}
    if lake.exists():
        try:
            con = get_read_connection(lake)
            t_rows = con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='gold' ORDER BY table_name"
            ).fetchall()
            allowed = {str(t[0]) for t in t_rows if str(t[0]).replace("_", "").isalnum()}
            for tname in sorted(allowed):
                try:
                    # Quoted identifier from the allow-list above — never raw input.
                    cnt = con.execute(f'SELECT count(*) FROM gold."{tname}"').fetchone()[0]
                    tables[tname] = int(cnt)
                except Exception:
                    continue
        except Exception:
            tables = {}

    return {
        "status": "healthy",
        "lake_path": str(lake),
        "lake_exists": lake.exists(),
        "graph": graph_summary(),
        "gold_tables": tables,
        "total_gold_records": sum(tables.values()),
    }


# ── Dual-Engine Context Gateway (DECG) ──────────────────────────────────────
@app.post("/api/gateway")
def gateway_endpoint(req: GatewayRequest) -> dict[str, Any]:
    from reasoning.gateway import gateway

    return gateway(req.query, crop=req.crop, top_k=req.top_k).to_dict()


def main() -> None:
    import uvicorn

    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
