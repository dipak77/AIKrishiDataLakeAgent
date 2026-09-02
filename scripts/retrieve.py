"""Research evidence retrieval CLI (Track 9, BM25).

Usage:
    python scripts/retrieve.py --query "pink bollworm control"
    python scripts/retrieve.py --query "rust control" --crop soybean --top 3
    python scripts/retrieve.py --query "early blight" --crop tomato --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning.rag import search  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve research evidence (BM25)")
    parser.add_argument("query_pos", nargs="?", default=None, help="search query")
    parser.add_argument("--query", "-q", default=None, help="search query")
    parser.add_argument("--crop", default=None, help="optional crop filter (name/id)")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    query_str = args.query or args.query_pos
    if not query_str:
        parser.error("provide query (as positional argument or with --query)")

    hits = search(query_str, top_k=args.top, crop=args.crop)

    if args.json:
        print(json.dumps([h.as_dict() for h in hits], indent=2, ensure_ascii=False))
        return 0

    print(f"\nEvidence for '{query_str}'"
          + (f" (crop={args.crop})" if args.crop else "") + f" - {len(hits)} hit(s)\n")
    if not hits:
        print("  No chunks matched. Broaden the query.")
        return 0
    for h in hits:
        print(f"  [{h.score:.3f}] {h.document} - {h.institution} ({h.year})")
        print(f"      section={h.section or '-'} page={h.page or '-'} | crops={','.join(h.crop)}")
        print(f"      {h.text}")
        print(f"      authority={h.authority} ({h.authority_score}) | {h.source_url}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
