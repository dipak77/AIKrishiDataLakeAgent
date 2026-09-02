"""DECG load test (V6 Phase 4) — concurrency, throughput, latency percentiles.

Two modes:

  * in-process (default) — hammer ``reasoning.gateway.gateway()`` across a
    thread pool; no server needed.
  * HTTP — pass ``--url http://host:8000`` to hit a live ``/api/gateway``.

Reports total requests, errors, throughput (req/s) and p50/p90/p95/p99 latency
so the gateway's production envelope is a measured number.

Usage:
    python scripts/load_test.py [--n 100] [--concurrency 8] [--url URL]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUERIES = [
    "Tomato has leaf spots",
    "टोमॅटोवर काळे डाग आहेत",
    "what is the price of onion in Nagpur",
    "wheat fertilizer recommendation",
    "zinc deficiency in rice",
    "research on pink bollworm in cotton",
]


def _in_process_runner() -> Callable[[str], float]:
    from reasoning.gateway import gateway

    def run(query: str) -> float:
        t0 = time.perf_counter()
        gateway(query, top_k=5)
        return (time.perf_counter() - t0) * 1000

    return run


def _http_runner(url: str) -> Callable[[str], float]:
    endpoint = url.rstrip("/") + "/api/gateway"

    def run(query: str) -> float:
        payload = json.dumps({"query": query, "top_k": 5}).encode("utf-8")
        req = urllib.request.Request(
            endpoint, data=payload, headers={"Content-Type": "application/json"}
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except urllib.error.HTTPError:
            raise
        return (time.perf_counter() - t0) * 1000

    return run


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * p))
    return sorted_vals[idx]


def run_load(runner: Callable[[str], float], n: int, concurrency: int) -> dict[str, Any]:
    queries = [QUERIES[i % len(QUERIES)] for i in range(n)]
    latencies: list[float] = []
    errors: list[str] = []
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(runner, q): q for q in queries}
        for fut in as_completed(futures):
            q = futures[fut]
            try:
                latencies.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{q!r}: {exc}")

    wall = time.perf_counter() - t0
    latencies.sort()
    return {
        "requests": n,
        "errors": len(errors),
        "error_rate": round(len(errors) / n, 4) if n else 0.0,
        "throughput_rps": round((n - len(errors)) / wall, 1) if wall else 0.0,
        "wall_s": round(wall, 2),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 1),
            "p90": round(_percentile(latencies, 0.90), 1),
            "p95": round(_percentile(latencies, 0.95), 1),
            "p99": round(_percentile(latencies, 0.99), 1),
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        },
        "sample_errors": errors[:5],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DECG load test")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--url", type=str, default=None, help="live server base URL")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    runner = _http_runner(args.url) if args.url else _in_process_runner()
    report = run_load(runner, args.n, args.concurrency)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
