"""Evaluate reranker ranking quality (V6 4 — measured accuracy).

For each golden-QA case that must retrieve a specific chunk, retrieve a
candidate pool with the hybrid engine, then rerank with the deterministic and
learned backends and measure **top-1 recall** (did the correct chunk reach rank
1?) and **reciprocal rank** (mean 1/rank).

Usage:
    python scripts/eval_reranker.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.gateway import Segment  # noqa: E402
from reasoning.reranker import DeterministicReranker, LearnedReranker  # noqa: E402
from reasoning.rag import hybrid_search  # noqa: E402

GOLDEN = ROOT / "data" / "fixtures" / "golden_qa.json"


def _to_segments(hits) -> list[Segment]:
    out = []
    for h in hits:
        lic = h.license.get("type", "") if isinstance(h.license, dict) else str(h.license or "")
        out.append(
            Segment("evidence", h.text, h.score, h.document, h.chunk_id, h.source_url or "", lic, float(h.authority_score or 0.0))
        )
    return out


def evaluate() -> dict[str, object]:
    cases = [c for c in json.loads(GOLDEN.read_text(encoding="utf-8")) if c.get("must_hit_chunk")]
    det = DeterministicReranker()
    learned = LearnedReranker()

    det_rr: list[float] = []
    lrn_rr: list[float] = []
    det_top1 = lrn_top1 = 0

    for case in cases:
        q = case["query"]
        target = case["must_hit_chunk"]
        pool = _to_segments(hybrid_search(q, top_k=12, crop=case.get("expected_crop")))
        if not pool:
            continue

        det_ranked = det.rerank(q, [Segment(s.kind, s.text, s.score, s.source, s.title, s.url, s.license, s.authority) for s in pool])
        lrn_ranked = learned.rerank(q, [Segment(s.kind, s.text, s.score, s.source, s.title, s.url, s.license, s.authority) for s in pool])

        def _rr(ranked):
            for rank, seg in enumerate(ranked, start=1):
                if seg.title == target:
                    return 1.0 / rank
            return 0.0

        d = _rr(det_ranked)
        l = _rr(lrn_ranked)
        det_rr.append(d)
        lrn_rr.append(l)
        det_top1 += 1 if d == 1.0 else 0
        lrn_top1 += 1 if l == 1.0 else 0

    n = len(det_rr)
    return {
        "cases": n,
        "deterministic": {
            "top1_recall": round(det_top1 / n, 4) if n else 0.0,
            "mean_reciprocal_rank": round(sum(det_rr) / n, 4) if n else 0.0,
        },
        "learned": {
            "top1_recall": round(lrn_top1 / n, 4) if n else 0.0,
            "mean_reciprocal_rank": round(sum(lrn_rr) / n, 4) if n else 0.0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate reranker ranking quality")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("reranker evaluation (must-hit chunk ranking)")
    print(f"  deterministic : top-1 {report['deterministic']['top1_recall']:.0%}  "
          f"MRR {report['deterministic']['mean_reciprocal_rank']:.3f}")
    print(f"  learned       : top-1 {report['learned']['top1_recall']:.0%}  "
          f"MRR {report['learned']['mean_reciprocal_rank']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
