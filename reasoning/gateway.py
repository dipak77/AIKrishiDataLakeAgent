"""Dual-Engine Context Gateway (DECG) — V6 orchestration layer.

Routes an incoming query through guardrails and the V5-F NLU classifier, then
runs the two engines **concurrently** with ``asyncio.to_thread``:

  * **CANONICAL / deterministic** — the OKF knowledge graph
    (``reasoning.graph_query``) + advisory engines: zero-hallucination lookup
    of crop health maps, symptom candidates, fertilizer / weather / crop-plan /
    mandi rules.
  * **PROBABILISTIC** — the hybrid sparse+dense RAG engine
    (``reasoning.rag.hybrid_search``) over the gold research corpus.

Results are merged with Reciprocal Rank Fusion, de-duplicated by
``(source, title)``, reranked by the configured reranker (deterministic dense
cosine + authority by default; opt-in cross-encoder via ``AGRI_RERANKER``) and
compacted to a token budget by the configured compactor (deterministic
truncation by default; opt-in LLM/IndicTrans2 via ``AGRI_COMPACTOR``). One
clean payload.

Both a sync one-shot ``gateway()`` and an async ``ContextGateway`` (matching the
DECG blueprint shape) are provided, plus ``run()`` for the synchronous CLI.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import nlu  # V5-F trained intent + entity pipeline (NEG imports)
from .advisory import recommend_fertilizer
from .compactor import CompactorUnavailable, get_compactor
from .crop_plan import crop_plan
from .graph_query import crop_health_map, symptom_candidates
from .guardrails import sanitize
from .mandi import market_advisory
from .rag import EvidenceHit, evidence_for_diagnosis, hybrid_search
from .reranker import RerankerUnavailable, get_reranker
from .weather import agromet_advisory

_WORD_RE = re.compile(r"[a-zA-Z0-9\u0900-\u097f]+")  # ASCII + Devanagari


@dataclass
class Segment:
    """One fused context segment (graph fact or research evidence)."""

    kind: str  # "graph" | "evidence"
    text: str
    score: float
    source: str = ""
    title: str = ""
    url: str = ""
    license: str = ""
    authority: float = 0.0

    def key(self) -> Tuple[str, str]:
        return (self.source, self.title)

    def citation(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "license": self.license,
            "authority": self.authority,
        }


@dataclass
class ContextSegments:
    graph: List[Segment] = field(default_factory=list)
    evidence: List[Segment] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class GatewayResult:
    query: str
    routing_path: str  # "canonical" | "exploratory" | "hybrid"
    intents: Dict[str, float]
    entities: Dict[str, Any]
    segments: ContextSegments
    guard: dict[str, Any]
    stats: Dict[str, Any]
    citations: List[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "routing_path": self.routing_path,
            "intents": self.intents,
            "entities": self.entities,
            "segments": {
                "graph": [s.text for s in self.segments.graph],
                "evidence": [s.text for s in self.segments.evidence],
                "notes": self.segments.notes,
            },
            "guard": self.guard,
            "stats": self.stats,
            "citations": self.citations,
        }


# ───────────────────────────── routing ────────────────────────────────────


def classify_path(intents: Dict[str, float], entities: Dict[str, Any]) -> str:
    """Map the V5-F intent to a DECG routing path.

    ``diagnosis`` needs both the canonical symptom→disease map *and* supporting
    evidence → HYBRID. ``evidence``/``general`` (no crop) → EXPLORATORY (RAG
    only). Everything else (fertilizer/weather/mandi/crop_plan/greeting) is
    fully determined by the OKF → CANONICAL.
    """
    crop = _crop_values(entities)
    symptoms = _list_value(entities.get("symptoms")) or _list_value(entities.get("symptom"))

    diagnosis = intents.get("diagnosis", 0.0)
    evidence = intents.get("evidence", 0.0)
    general = intents.get("general", 0.0)

    # symptom→disease needs the deterministic map *and* supporting evidence.
    if diagnosis >= 0.3 or (crop and symptoms):
        return "hybrid"
    if evidence >= 0.3 or general >= 0.3:
        return "exploratory"
    return "canonical"


def plan_subqueries(intents: Dict[str, float], entities: Dict[str, Any]) -> List[dict[str, Any]]:
    """Sub-query expansion (blueprint Multi-Query Planner, entity-driven)."""
    tasks: List[dict[str, Any]] = []
    crop = _crop_values(entities)
    symptoms = _list_value(entities.get("symptoms")) or _list_value(entities.get("symptom"))
    if intents.get("diagnosis", 0.0) >= 0.2 or symptoms or (crop and intents.get("general", 0.0) >= 0.2):
        tasks.append({"type": "health_map", "crop": crop})
        if symptoms:
            tasks.append({"type": "symptom_candidates", "symptoms": symptoms, "crop": crop})
        tasks.append({"type": "evidence", "crop": crop, "symptoms": symptoms})
    if intents.get("fertilizer", 0.0) >= 0.2 or (crop and intents.get("general", 0.0) >= 0.2):
        tasks.append({"type": "fertilizer", "crop": crop})
    if intents.get("crop_plan", 0.0) >= 0.2:
        tasks.append({"type": "crop_plan", "crop": crop})
    if intents.get("mandi", 0.0) >= 0.2:
        tasks.append({"type": "mandi", "crop": crop})
    if intents.get("weather", 0.0) >= 0.2:
        tasks.append({"type": "weather", "crop": crop})
    if not tasks:
        tasks.append({"type": "evidence", "crop": crop, "symptoms": symptoms})
    return tasks


def _crop_values(entities: Dict[str, Any]) -> List[str]:
    crop = entities.get("crop")
    if isinstance(crop, dict):
        crop = crop.get("value")
    return crop if isinstance(crop, list) else ([crop] if crop else [])


def adapt_nlu(result: Any) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Convert an ``nlu.NLUResult`` into (intent_scores, entities) for routing."""
    intents: Dict[str, float] = dict(getattr(result, "intent_scores", None) or {})
    top = getattr(result, "intent", None)
    conf = float(getattr(result, "intent_confidence", 0.0) or 0.0)
    if top:
        intents[top] = max(intents.get(top, 0.0), conf)
    # normalize NLU key aliases to the gateway's intent vocabulary
    intents["mandi"] = intents.get("mandi", intents.get("mandi_price", 0.0))
    intents["crop_plan"] = intents.get("crop_plan", intents.get("crop_planning", 0.0))

    entities: Dict[str, Any] = {}
    crop = getattr(result, "crop", None) or {}
    if crop.get("canonical_en") or crop.get("crop_id"):
        entities["crop"] = [crop.get("canonical_en") or crop.get("crop_id")]
    if getattr(result, "symptoms", None):
        entities["symptoms"] = list(result.symptoms)
    loc = getattr(result, "location", None) or {}
    if loc.get("district") or loc.get("state"):
        entities["location"] = [loc.get("district") or loc.get("state")]
    if getattr(result, "stage", None):
        entities["stage"] = result.stage
    return intents, entities


def _list_value(value: Any) -> List[str]:
    if isinstance(value, dict):
        value = value.get("value")
    return value if isinstance(value, list) else ([value] if value else [])


# ─────────────────────────── engines ──────────────────────────────────────


@lru_cache(maxsize=256)
def _health_lines(crop: str) -> Tuple[Tuple[str, str], ...]:
    """Cached, flattened OKF crop-health facts → ((node_id, text), …)."""
    _ensure_cache_fresh()
    data = crop_health_map(crop)
    if not data.get("found"):
        return ()
    lines: List[Tuple[str, str]] = []
    for kind in ("diseases", "deficiencies", "pests"):
        for d in data.get(kind, []):
            lines.append((d.get("id", ""), f"{d['label']}: {', '.join(d['symptoms'][:6])}"))
    return tuple(lines)


@lru_cache(maxsize=256)
def _candidate_lines(symptoms: Tuple[str, ...], crop: str) -> Tuple[Tuple[str, str], ...]:
    """Cached, flattened symptom→disease candidates → ((node_id, text), …)."""
    _ensure_cache_fresh()
    cands = symptom_candidates(" ".join(symptoms), crop=crop or None)
    return tuple((c.get("id", ""), f"{c['label']}: {', '.join(c['symptoms'][:6])}") for c in cands)


_CACHE_FINGERPRINT: str = ""


def _lake_fingerprint() -> str:
    try:
        from pipelines.storage import LAKE_DIR
        p = LAKE_DIR / "agrilake.duckdb"
        st = p.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "missing"


def _ensure_cache_fresh() -> None:
    """Drop OKF caches when the lake file changed under us (seed/gold rebuild)."""
    global _CACHE_FINGERPRINT
    fp = _lake_fingerprint()
    if _CACHE_FINGERPRINT != fp:
        _CACHE_FINGERPRINT = fp
        _health_lines.cache_clear()
        _candidate_lines.cache_clear()


def _graph_segments(tasks: Sequence[dict[str, Any]], location: str = "") -> List[Segment]:
    """Deterministic OKF segments — ontology lookup only, no generation."""
    segments: List[Segment] = []
    seen: set[Tuple[str, str]] = set()

    def add(kind: str, text: str, source: str, title: str, score: float, url: str = "", license_: str = "", authority: int = 0) -> None:
        if not text or (source, title) in seen:
            return
        seen.add((source, title))
        segments.append(Segment(kind, text, score, source, title, url, license_, authority))

    for task in tasks:
        ttype = task["type"]
        crops = task.get("crop") or []
        if ttype == "health_map":
            for c in crops:
                for node_id, text in _health_lines(c):
                    add("graph", text, "graph:health_map", node_id, 1.0)
        elif ttype == "symptom_candidates":
            key = tuple(sorted(task.get("symptoms") or []))
            for node_id, text in _candidate_lines(key, crops[0] if crops else ""):
                add("graph", text, "graph:symptom_candidates", node_id, 0.9)
        elif ttype == "fertilizer":
            for c in crops:
                rec = recommend_fertilizer(c)
                if rec is None:
                    continue
                for line in _as_lines(rec.as_dict()):
                    add("graph", line, "advisory:fertilizer", c, 0.9)
        elif ttype == "crop_plan":
            for c in crops:
                plan = crop_plan(c)
                if plan is None:
                    continue
                for line in _as_lines(plan.as_dict()):
                    add("graph", line, "advisory:crop_plan", c, 0.8)
        elif ttype == "weather":
            rec = agromet_advisory(location) if location else None
            if rec is not None:
                for line in _as_lines(rec.as_dict()):
                    add("graph", line, "advisory:weather", location, 0.8)
        elif ttype == "mandi":
            for c in crops:
                prices = market_advisory(c)
                if prices is None:
                    continue
                for line in _as_lines(prices.as_dict()):
                    add("graph", line, "advisory:mandi", c, 0.8)
    return segments


def _as_lines(value: Any) -> List[str]:
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items() if v not in (None, "", [], {})]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)] if value else []


def _evidence_segments(query: str, crops: List[str], top_k: int) -> List[Segment]:
    """Hybrid RAG segments (V5-A sparse+dense) over the research corpus."""
    hits: List[EvidenceHit]
    if crops:
        symptoms = _query_tokens(query)
        hits = evidence_for_diagnosis(crops[0], symptoms, top_k=top_k)
    else:
        hits = hybrid_search(query, top_k=top_k)
    out: List[Segment] = []
    for h in hits:
        lic = h.license.get("type", "") if isinstance(h.license, dict) else str(h.license or "")
        out.append(
            Segment(
                "evidence",
                h.text,
                h.score,
                h.document,
                h.chunk_id,
                h.source_url or "",
                lic,
                float(h.authority_score or 0.0),
            )
        )
    return out


def _query_tokens(query: str) -> List[str]:
    return _WORD_RE.findall(query)


# ─────────────────────────── fusion ───────────────────────────────────────

RRF_K = 60


def _rrf(ranked: List[Segment]) -> Dict[Tuple[str, str], float]:
    scores: Dict[Tuple[str, str], float] = {}
    for rank, seg in enumerate(ranked, start=1):
        scores[seg.key()] = scores.get(seg.key(), 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _fuse(graph: List[Segment], rag: List[Segment], top_k: int = 5) -> List[Segment]:
    """RRF-fused, de-duplicated, reranked segment list.

    Scores are computed on copies: the cached `_health_lines` /
    `_candidate_lines` segments are shared across requests and must never be
    mutated in place (the old code did `merged[key].score += val`, leaking one
    query's RRF scores into the next).
    """
    from dataclasses import replace

    graph_by_key: Dict[Tuple[str, str], Segment] = {}
    for seg in graph:
        graph_by_key.setdefault(seg.key(), seg)
    rag_by_key: Dict[Tuple[str, str], Segment] = {}
    for seg in rag:
        rag_by_key.setdefault(seg.key(), seg)
    fused: Dict[Tuple[str, str], Segment] = {}
    for key, val in _rrf(graph).items():
        base = graph_by_key.get(key)
        if base is not None:
            fused[key] = replace(base, score=val)
    for key, val in _rrf(rag).items():
        if key in fused:
            fused[key] = replace(fused[key], score=fused[key].score + val)
        else:
            base = rag_by_key.get(key)
            if base is not None:
                fused[key] = replace(base, score=val)
    return sorted(fused.values(), key=lambda s: s.score, reverse=True)[:top_k]


# ─────────────────── rerank + compaction (pluggable) ──────────────────────


def _rerank(query: str, segments: List[Segment]) -> List[Segment]:
    """Rerank via the configured backend; fall back to deterministic on failure."""
    try:
        return get_reranker().rerank(query, segments)
    except RerankerUnavailable:
        from .reranker import DeterministicReranker

        return DeterministicReranker().rerank(query, segments)


def _compact(segments: List[Segment], top_k: int, max_chars_per: int = 480) -> List[Segment]:
    """Compact via the configured backend; fall back to truncation on failure."""
    try:
        return get_compactor().compact("", segments, top_k, max_chars_per)
    except CompactorUnavailable:
        from .compactor import TruncationCompactor

        return TruncationCompactor().compact("", segments, top_k, max_chars_per)


# ─────────────────────────── orchestrator ─────────────────────────────────


def _finalize(query: str, path: str, intents: Dict[str, float], entities: Dict[str, Any], guard: dict[str, Any], graph: List[Segment], rag: List[Segment], top_k: int, t0: float) -> GatewayResult:
    dedupe_removed = max(0, len(graph) + len(rag) - len(set(s.key() for s in graph + rag)))
    fused = _fuse(graph, rag, top_k=top_k)
    fused = _rerank(query, fused)
    fused = _compact(fused, top_k)

    final_graph = [s for s in fused if s.kind == "graph"]
    final_ev = [s for s in fused if s.kind == "evidence"]

    stats = {
        "engine_contrib": {"graph": len(final_graph), "rag": len(final_ev)},
        "total_segments": len(fused),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "dedupe_removed": dedupe_removed,
    }
    return GatewayResult(
        query=query,
        routing_path=path,
        intents=intents,
        entities=entities,
        segments=ContextSegments(graph=final_graph, evidence=final_ev),
        guard=guard,
        stats=stats,
        citations=[s.citation() for s in fused],
    )


class ContextGateway:
    """Async DECG orchestrator (blueprint shape)."""

    def __init__(self, top_k: int = 5, lake: Optional[Any] = None) -> None:
        self.top_k = top_k
        self.lake = lake

    async def route_and_retrieve(self, query: str, crop: Optional[str] = None) -> GatewayResult:
        return await _run_async(query, self.top_k, self.lake, crop)


async def _run_async(query: str, top_k: int, lake: Optional[Any], crop: Optional[str]) -> GatewayResult:
    t0 = time.perf_counter()
    guard = sanitize(query)
    if guard["blocked"]:
        empty = ContextSegments(notes=["blocked by guardrails"])
        return GatewayResult(query, "canonical", {}, {}, empty, guard, {"elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)})
    pipe = await asyncio.to_thread(nlu.get_pipeline)
    result = await asyncio.to_thread(pipe.predict, guard["query"])
    intents, entities = adapt_nlu(result)
    if crop:
        entities.setdefault("crop", crop)
    path = classify_path(intents, entities)
    tasks = plan_subqueries(intents, entities)

    crops = _crop_values(entities)
    location = _list_value(entities.get("location"))
    location = location[0] if location else ""
    if path == "canonical":
        graph = await asyncio.to_thread(_graph_segments, tasks, location)
        rag: List[Segment] = []
    elif path == "exploratory":
        graph = []
        rag = await asyncio.to_thread(_evidence_segments, guard["query"], crops, top_k)
    else:
        graph, rag = await asyncio.gather(
            asyncio.to_thread(_graph_segments, tasks, location),
            asyncio.to_thread(_evidence_segments, guard["query"], crops, top_k),
        )
    return _finalize(guard["query"], path, intents, entities, guard, graph, rag, top_k, t0)


def gateway(query: str, crop: Optional[str] = None, top_k: int = 5, lake: Optional[Any] = None) -> GatewayResult:
    """Sync one-shot orchestration.

    Works both outside and inside a running event loop (e.g. Jupyter /
    FastAPI tests): when a loop is already running the coroutine is executed
    on a dedicated thread instead of raising `RuntimeError: asyncio.run()
    cannot be called from a running event loop`.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run_async(query, top_k, lake, crop))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run_async(query, top_k, lake, crop)).result()


def clear_gateway_cache() -> None:
    """Drop cached OKF lookups after a lake rebuild (seed/gold/graph)."""
    global _CACHE_FINGERPRINT
    _CACHE_FINGERPRINT = ""
    _health_lines.cache_clear()
    _candidate_lines.cache_clear()


# ─────────────────────────── CLI ──────────────────────────────────────────


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dual-Engine Context Gateway")
    parser.add_argument("query", nargs="+", help="query text")
    parser.add_argument("--crop", help="optional crop hint")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    result = gateway(" ".join(args.query), crop=args.crop, top_k=args.top_k)
    import json

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
