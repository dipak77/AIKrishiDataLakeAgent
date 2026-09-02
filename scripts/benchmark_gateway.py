"""Golden-QA benchmark for the Dual-Engine Context Gateway (V6 2b).

Runs ``reasoning.gateway.gateway()`` over a labeled fixture
(``data/fixtures/golden_qa.json``) and measures the metrics that make DECG
accuracy a *measured number* instead of a claim:

  - routing accuracy    — expected routing path (canonical/exploratory/hybrid)
  - intent accuracy     — top predicted intent
  - crop recall         — expected crop extracted
  - graph coverage      — minimum deterministic segments returned
  - evidence coverage   — minimum RAG segments returned
  - evidence recall@k   — expected chunk/document appears in evidence citations
  - latency p50 / p95   — warm-path latency distribution

Exit code is non-zero when the pass rate is below ``--fail-under`` (CI gate).

Usage:
    python scripts/benchmark_gateway.py [--top-k 5] [--runs 3] [--json out.json]
                                        [--fail-under 0.90]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "golden_qa.json"

_INTENT_ALIASES = {
    "mandi": "mandi_price",
    "crop_plan": "crop_planning",
    "plan": "crop_planning",
}


def _top_intent(intents: dict[str, float]) -> str:
    if not intents:
        return ""
    label, _ = max(intents.items(), key=lambda kv: kv[1])
    return _INTENT_ALIASES.get(label, label)


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _crops(entities: dict[str, Any]) -> list[str]:
    crop = entities.get("crop")
    if isinstance(crop, dict):
        crop = crop.get("value")
    return crop if isinstance(crop, list) else ([crop] if crop else [])


def _evaluate_one(case: dict[str, Any], result: Any, top_k: int) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    notes: list[str] = []

    if case.get("expected_blocked"):
        checks["blocked"] = bool(result.guard.get("blocked"))
    else:
        checks["routing"] = result.routing_path == case.get("expected_path")
        checks["intent"] = _top_intent(result.intents) == case.get("expected_intent")

    if case.get("expected_crop"):
        want = case["expected_crop"].lower()
        checks["crop"] = any(c and c.lower() == want for c in _crops(result.entities))
        if not checks["crop"]:
            notes.append(f"crop got {_crops(result.entities)!r}")

    if "min_graph_segments" in case:
        ok = len(result.segments.graph) >= case["min_graph_segments"]
        checks["graph"] = ok
        if not ok:
            notes.append(f"graph={len(result.segments.graph)}")

    if "min_evidence_segments" in case:
        ok = len(result.segments.evidence) >= case["min_evidence_segments"]
        checks["evidence"] = ok
        if not ok:
            notes.append(f"evidence={len(result.segments.evidence)}")

    if case.get("must_hit_chunk"):
        hits = [s.title for s in result.segments.evidence]
        checks["evidence_recall"] = case["must_hit_chunk"] in hits
        if not checks["evidence_recall"]:
            notes.append(f"chunk {case['must_hit_chunk']!r} not in {hits[:5]!r}")

    if case.get("must_hit_document"):
        docs = [s.source for s in result.segments.evidence]
        checks["evidence_recall"] = any(case["must_hit_document"] in d for d in docs)
        if not checks["evidence_recall"]:
            notes.append(f"document {case['must_hit_document']!r} not in {docs[:5]!r}")

    passed = sum(checks.values())
    total = len(checks)
    return {
        "id": case["id"],
        "path": result.routing_path if not case.get("expected_blocked") else "blocked",
        "intent": _top_intent(result.intents),
        "checks": checks,
        "passed": passed,
        "total": total,
        "elapsed_ms": result.stats.get("elapsed_ms"),
        "notes": notes,
    }


def run_benchmark(cases: list[dict[str, Any]], top_k: int = 5, runs: int = 1) -> dict[str, Any]:
    from reasoning.gateway import gateway

    results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for _ in range(runs):
        for case in cases:
            t0 = time.perf_counter()
            res = gateway(case["query"], top_k=top_k)
            latencies.append((time.perf_counter() - t0) * 1000)
            if runs == 1 or _ == runs - 1:
                results.append(_evaluate_one(case, res, top_k))

    total_checks = sum(r["total"] for r in results)
    total_passed = sum(r["passed"] for r in results)
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    per_metric: dict[str, list[bool]] = {}
    for r in results:
        for name, ok in r["checks"].items():
            per_metric.setdefault(name, []).append(ok)

    return {
        "cases": len(results),
        "runs": runs,
        "checks_passed": total_passed,
        "checks_total": total_checks,
        "pass_rate": round(total_passed / total_checks, 4) if total_checks else 0.0,
        "metrics": {name: round(sum(v) / len(v), 4) for name, v in per_metric.items()},
        "latency": {"p50_ms": round(p50, 1), "p95_ms": round(p95, 1)},
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DECG golden-QA benchmark")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--runs", type=int, default=1, help="repeat for latency spread")
    parser.add_argument("--json", type=Path, default=None, help="write report JSON")
    parser.add_argument("--fail-under", type=float, default=0.0, help="min pass rate (CI gate)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    cases = _load_cases(args.fixture)
    report = run_benchmark(cases, top_k=args.top_k, runs=args.runs)

    if not args.quiet:
        print(f"DECG golden-QA benchmark - {report['cases']} cases, {args.runs} run(s)")
        print(f"pass rate: {report['pass_rate']:.1%}  "
              f"({report['checks_passed']}/{report['checks_total']} checks)")
        print(f"metrics:   " + "  ".join(f"{k}={v:.0%}" for k, v in report["metrics"].items()))
        print(f"latency:   p50={report['latency']['p50_ms']}ms  p95={report['latency']['p95_ms']}ms")
        print()
        for r in report["results"]:
            status = "PASS" if r["passed"] == r["total"] else "FAIL"
            detail = "; ".join(r["notes"]) if r["notes"] else ""
            print(f"  [{status}] {r['id']:24} path={r['path']:12} intent={r['intent']:14} {detail}")

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport written to {args.json}")

    if report["pass_rate"] < args.fail_under:
        print(f"FAIL: pass rate {report['pass_rate']:.1%} below threshold {args.fail_under:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
