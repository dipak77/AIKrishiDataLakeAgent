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
import os
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


# ── Thread-local read-only DuckDB connections (V6 2a: connection reuse) ────
#
# ``duckdb.connect(read_only=True)`` costs ~10–15 ms per call. Reasoning hot
# paths opened a fresh connection on every query, which pushed the canonical
# gateway path to ~21 ms. DuckDB connections are NOT thread-safe, so we cache
# one connection *per thread*, keyed by the resolved lake path. Callers MUST
# NOT ``.close()`` a connection obtained here — it is shared and reused.
import threading  # noqa: E402

_READ_CONNS: dict[tuple[int, str], Any] = {}
_CONNS_LOCK = threading.Lock()


def get_read_connection(lake: Path | None = None):
    """Return a cached read-only DuckDB connection for this thread + lake file.

    Never close the returned handle; it is reused across calls. Use
    ``clear_connection_cache()`` to reset (e.g. after rebuilding the lake).
    """
    import duckdb

    path = Path(lake or (LAKE_DIR / "agrilake.duckdb")).resolve()
    key = (threading.get_ident(), str(path))
    with _CONNS_LOCK:
        con = _READ_CONNS.get(key)
        if con is None:
            con = duckdb.connect(str(path), read_only=True)
            _READ_CONNS[key] = con
        return con


def clear_connection_cache() -> None:
    """Close and forget all cached read-only connections."""
    with _CONNS_LOCK:
        for con in _READ_CONNS.values():
            try:
                con.close()
            except Exception:
                pass
        _READ_CONNS.clear()


def read_write_connection(lake: Path | None = None):
    """Open a read-write connection, first closing cached read-only handles.

    DuckDB refuses to open the same file with mixed configurations, so any
    write path (seed / graph build / corpus build) must drop the read cache
    first. The cached read connections are re-established lazily afterwards.
    """
    import duckdb

    clear_connection_cache()
    path = Path(lake or (LAKE_DIR / "agrilake.duckdb")).resolve()
    return duckdb.connect(str(path))


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_").lower()
    return value or "resource"


def write_json(path: Path, data: Any, indent: int | None = 2) -> Path:
    payload = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    return _atomic_write_text(path, payload)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Append-independent JSONL writer (one JSON object per line)."""
    payload = "".join(
        json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows
    )
    return _atomic_write_text(path, payload)


def _atomic_write_text(path: Path, text: str) -> Path:
    _atomic_write_bytes(path, text.encode("utf-8"))
    return path


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes to ``path`` atomically (tmp file + ``os.replace``).

    A crash mid-write can never leave a half-written CSV/JSONL/manifest behind.
    """
    ensure_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)  # atomic on POSIX and Windows (same volume)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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
    _atomic_write_bytes(artifact, raw)

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
