"""Analyze a crop-leaf image with the vision pipeline (V5-C).

Usage:
    python scripts/analyze_image.py leaf.png [--crop tomato] [--backend auto]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vision import analyze_image  # noqa: E402
from vision.inference import BackendUnavailable  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a crop-leaf image (PNG).")
    parser.add_argument("image", help="path to a PNG image")
    parser.add_argument("--crop", default=None, help="optional crop to scope candidates")
    parser.add_argument("--backend", default="auto", help="backend name (default: heuristic)")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    try:
        res = analyze_image(
            args.image, crop=args.crop, backend=args.backend, top_k=args.top_k
        )
    except BackendUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - user-facing CLI
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{args.image}: {res.width}x{res.height} · backend={res.backend} · verdict={res.verdict}")
    print("descriptor:", ", ".join(f"{k}={v:.2f}" for k, v in res.descriptor.items()))
    for i, c in enumerate(res.candidates, 1):
        print(f"  {i}. {c.entity_id:26} {c.entity_type:10} {c.name:30} "
              f"score={c.score} matched={c.matched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
