"""Drift gate: verify committed ``data/seeds/*.csv`` still match ``seed_data.py``.

Re-emits every seed CSV into a temp directory and compares content hashes
against the committed files. Exits non-zero if any CSV drifted (i.e. the
ontology source changed but the CSVs were not regenerated) — the exact class
of silent drift the CI gate is meant to catch.

Usage: python scripts/verify_seeds.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.storage import SEEDS_DIR  # noqa: E402
from scripts.seed_lake import emit_seed_csvs  # noqa: E402

IGNORED = {"_seed_sha.txt"}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    committed = {p.name for p in SEEDS_DIR.glob("*.csv")}
    with tempfile.TemporaryDirectory() as tmp:
        # `emit_seed_csvs` writes via the module-level SEEDS_DIR imported into
        # scripts.seed_lake, so patch that binding for the duration.
        import scripts.seed_lake as seed_lake

        original = seed_lake.SEEDS_DIR
        seed_lake.SEEDS_DIR = Path(tmp)
        try:
            emitted_paths = emit_seed_csvs()
        finally:
            seed_lake.SEEDS_DIR = original

        emitted_names = {p.name for p in emitted_paths}
        drift: list[tuple[str, str]] = []
        missing = sorted(committed - emitted_names)
        extra = sorted(emitted_names - committed)
        for name in sorted(committed & emitted_names):
            if _hash(SEEDS_DIR / name) != _hash(Path(tmp) / name):
                drift.append(name)

    if not drift and not missing and not extra:
        print(f"OK: {len(committed)} committed seed CSVs match seed_data.py")
        return 0

    print("SEED DRIFT DETECTED — regenerate with `make seed` / `python scripts/seed_lake.py --force`")
    for name in drift:
        print(f"  [changed] {name}")
    for name in missing:
        print(f"  [missing from committed] {name}")
    for name in extra:
        print(f"  [extra, not committed] {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
