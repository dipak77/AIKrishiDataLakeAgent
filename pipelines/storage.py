"""Filesystem layout for the lake (mirrors an S3/MinIO object layout).

The `data/` tree mirrors the keys an object store would use, so the same code
path works against local disk now and S3/MinIO later without rewriting the
pipeline logic.

    data/
      bronze/<source_id>/<resource>/       immutable raw + _manifest.json
      silver/<domain>/                     normalized records (jsonl)
      gold/<application>/                  domain-ready tables/parquet
      lake/agrilake.duckdb                 DuckDB lakehouse
      seeds/                               committed seed ontologies (csv)
      fixtures/                            committed sample records (offline fallback)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
LAKE_DIR = DATA_DIR / "lake"
SEEDS_DIR = DATA_DIR / "seeds"
FIXTURES_DIR = DATA_DIR / "fixtures"


def repo_root() -> Path:
    return REPO_ROOT


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_").lower()
    return value or "resource"


def write_json(path: Path, data: Any, indent: int | None = 2) -> Path:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent, default=str),
        encoding="utf-8",
    )
    return path


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Append-independent JSONL writer (one JSON object per line)."""
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return path


def write_bronze(
    source_id: str,
    resource_id: str,
    payload: bytes | str,
    filename: str,
    meta: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Persist an immutable raw artifact plus its provenance manifest.

    Returns (artifact_path, manifest_path).
    """
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    digest = content_hash(raw)
    resource_dir = ensure_dir(BRONZE_DIR / slugify(source_id) / slugify(resource_id))
    artifact = resource_dir / filename
    artifact.write_bytes(raw)

    manifest = {
        "source_id": source_id,
        "resource_id": resource_id,
        "filename": filename,
        "sha256": digest,
        "bytes": len(raw),
        "retrieved_at": utcnow_iso(),
        "ingestion_method": (meta or {}).get("ingestion_method", "live"),
        "meta": meta or {},
    }
    manifest_path = write_json(resource_dir / "_manifest.json", manifest)
    return artifact, manifest_path
