"""Train the learned gateway reranker (V6 4 — real, measured ranking weights).

Trains a pairwise logistic-regression reranker over the golden-QA set + research
corpus (pure Python, no numpy/torch) and persists the weights to
``data/gold/reranker_model.json``. The gateway's ``AGRI_RERANKER=learned``
backend loads the same file.

Usage:
    python scripts/train_reranker.py [--epochs 120] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.reranker import (  # noqa: E402
    N_FEATURES,
    LEARNED_MODEL_PATH,
    LEARNED_MODEL_VERSION,
    build_training_pairs,
    train_weights,
)
from pipelines.storage import ensure_dir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the learned gateway reranker")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--lr", type=float, default=0.2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    pairs = build_training_pairs()
    weights = train_weights(pairs, epochs=args.epochs, lr=args.lr)
    ensure_dir(LEARNED_MODEL_PATH.parent)
    LEARNED_MODEL_PATH.write_text(
        json.dumps({"version": LEARNED_MODEL_VERSION, "weights": weights}),
        encoding="utf-8",
    )

    report = {"pairs": len(pairs), "weights": weights, "model": str(LEARNED_MODEL_PATH)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"trained reranker on {len(pairs)} pairs -> {LEARNED_MODEL_PATH}")
    print("weights (dense, overlap, authority, title_overlap, bias):",
          "  ".join(f"{w:+.4f}" for w in weights))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
