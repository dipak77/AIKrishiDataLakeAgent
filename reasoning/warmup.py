"""Startup pre-warm (V6 2a) — absorb cold-start cost before the first request.

The first live query pays a one-time cost to load the trained NLU model, build
the hybrid RAG index, ensure the knowledge-graph tables exist and prime the
advisory connection caches. Calling ``prewarm()`` during app startup moves that
cost out of the user's critical path (fixes the ~0.9 s first-call spike behind
the preview proxy). Idempotent and safe to call repeatedly.
"""

from __future__ import annotations

import time
from typing import Any


def prewarm() -> dict[str, Any]:
    """Warm all hot caches; returns a small timing report. Never raises."""
    t0 = time.perf_counter()
    steps: dict[str, Any] = {}
    try:
        s = time.perf_counter()
        from reasoning import nlu

        pipe = nlu.get_pipeline()
        pipe.predict("टोमॅटोवर काळे डाग")  # build/load trained intent + NER
        steps["nlu_ms"] = round((time.perf_counter() - s) * 1000, 1)
    except Exception as exc:  # pragma: no cover - defensive
        steps["nlu"] = f"error: {exc}"

    try:
        s = time.perf_counter()
        from reasoning.rag import _bm25_index, _hybrid_index

        _bm25_index("")
        _hybrid_index("")  # build BM25 + dense vectors once
        steps["rag_ms"] = round((time.perf_counter() - s) * 1000, 1)
    except Exception as exc:  # pragma: no cover - defensive
        steps["rag"] = f"error: {exc}"

    try:
        s = time.perf_counter()
        from reasoning.graph_query import ensure_graph_tables, graph_summary

        ensure_graph_tables()  # build graph tables if absent
        graph_summary()  # prime read-connection + graph scan
        steps["graph_ms"] = round((time.perf_counter() - s) * 1000, 1)
    except Exception as exc:  # pragma: no cover - defensive
        steps["graph"] = f"error: {exc}"

    try:
        s = time.perf_counter()
        # Prime advisory read-connections (market/weather/calendar/fertilizer).
        from reasoning.advisory import recommend_fertilizer
        from reasoning.crop_plan import crop_plan
        from reasoning.mandi import market_advisory

        market_advisory("onion")
        recommend_fertilizer("wheat")
        crop_plan("wheat")
        steps["advisory_ms"] = round((time.perf_counter() - s) * 1000, 1)
    except Exception as exc:  # pragma: no cover - defensive
        steps["advisory"] = f"error: {exc}"

    steps["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return steps


if __name__ == "__main__":  # pragma: no cover - CLI for diagnostics
    import json

    print(json.dumps(prewarm(), indent=2))
