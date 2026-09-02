"""Collection primitives: run identity, idempotency, watermarks and the run ledger.

These are the pieces that turn "a script that downloads something" into an
auditable ingestion pipeline (`docs/v7-plan.md` §4.3):

* **Run identity** — every row carries the ``run_id`` that produced it.
* **Idempotency** — ``record_hash`` is a sha256 over the record's *stable*
  fields, so re-running a partition writes nothing new.
* **Honest origin** — ``ingestion_method`` is a **column** (``live`` |
  ``replay`` | ``fixture``), not a log line: a fixture row can never be
  mistaken for a real one downstream (fixes F5).
* **Watermarks** — per (source, resource, partition) high-water marks so an
  incremental run has something to resume from (fixes F10).
* **Run ledger** — one row per run in ``gold.ingest_run`` with request/row
  counters, so "what happened last night?" is a query.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# Fields that change on every run and therefore must not affect identity.
VOLATILE_FIELDS = frozenset(
    {"ingested_at", "run_id", "record_hash", "quality", "_method", "ingestion_method"}
)

INGESTION_METHODS = ("live", "replay", "fixture")


# ─────────────────────────── identity ──────────────────────────────────────


def new_run_id(prefix: str = "run") -> str:
    from pipelines.storage import utcnow_iso

    stamp = utcnow_iso()[:19].replace(":", "").replace("-", "")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def canonical_json(record: dict[str, Any], *, exclude: Iterable[str] = ()) -> str:
    """Deterministic JSON for hashing: sorted keys, volatile fields removed."""
    drop = set(VOLATILE_FIELDS) | set(exclude)
    stable = {k: v for k, v in record.items() if k not in drop and not k.startswith("_")}
    return json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def record_hash(record: dict[str, Any], *, exclude: Iterable[str] = ()) -> str:
    """sha256 over the record's stable content (its idempotency identity)."""
    return hashlib.sha256(canonical_json(record, exclude=exclude).encode("utf-8")).hexdigest()


def attach_provenance(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    method: str,
    source_id: str = "",
) -> list[dict[str, Any]]:
    """Stamp ``run_id`` + ``ingestion_method`` + ``record_hash`` onto records.

    Returns **new** dicts; inputs are not mutated.
    """
    if method not in INGESTION_METHODS:
        raise ValueError(f"unknown ingestion_method {method!r}; expected one of {INGESTION_METHODS}")
    from pipelines.storage import utcnow_iso

    now = utcnow_iso()
    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        row["record_hash"] = record_hash(rec)
        row["run_id"] = run_id
        row["ingestion_method"] = method
        row.setdefault("ingested_at", now)
        if source_id:
            row.setdefault("source_id", source_id)
        out.append(row)
    return out


def dedupe_records(
    records: list[dict[str, Any]],
    *,
    key_fields: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a batch into ``(unique, duplicates, conflicts)``.

    * ``duplicates`` — identical stable content (same ``record_hash``).
    * ``conflicts`` — same business key, different content. Conflicts are a
      data problem, not a duplicate, and must be quarantined (never silently
      first-wins).
    """
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_hash: set[str] = set()
    seen_key: dict[tuple[Any, ...], str] = {}

    for rec in records:
        digest = rec.get("record_hash") or record_hash(rec)
        if digest in seen_hash:
            duplicates.append(rec)
            continue
        if key_fields:
            key = tuple(rec.get(k) for k in key_fields)
            if key in seen_key and seen_key[key] != digest:
                conflicts.append(rec)
                continue
            seen_key[key] = digest
        seen_hash.add(digest)
        unique.append(rec)
    return unique, duplicates, conflicts


# ─────────────────────────── run summary ───────────────────────────────────


@dataclass
class RunSummary:
    """One ingestion run's counters (persisted to ``gold.ingest_run``)."""

    run_id: str
    source_id: str
    resource_id: str = ""
    transport: str = "live"
    contract_version: str = ""
    git_sha: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"        # running | ok | failed | parked
    requests: int = 0
    retries: int = 0
    bytes: int = 0
    rows_raw: int = 0
    rows_pass: int = 0
    rows_quarantine: int = 0
    rows_reject: int = 0
    watermark_before: str = ""
    watermark_after: str = ""
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["extra"] = json.dumps(self.extra, ensure_ascii=False, default=str, sort_keys=True)
        return row


def git_sha(root: Path | None = None) -> str:
    """Current commit sha, or "" when unavailable (never raises)."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root or Path(__file__).resolve().parents[1]),
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 - git is optional at runtime
        return ""


# ─────────────────────────── lake-backed stores ────────────────────────────

RUN_DDL = """
CREATE TABLE IF NOT EXISTS gold.ingest_run (
    run_id VARCHAR PRIMARY KEY,
    source_id VARCHAR,
    resource_id VARCHAR,
    transport VARCHAR,
    contract_version VARCHAR,
    git_sha VARCHAR,
    started_at VARCHAR,
    finished_at VARCHAR,
    status VARCHAR,
    requests INTEGER,
    retries INTEGER,
    bytes BIGINT,
    rows_raw INTEGER,
    rows_pass INTEGER,
    rows_quarantine INTEGER,
    rows_reject INTEGER,
    watermark_before VARCHAR,
    watermark_after VARCHAR,
    error VARCHAR,
    extra VARCHAR
)
"""

WATERMARK_DDL = """
CREATE TABLE IF NOT EXISTS gold.ingest_watermark (
    source_id VARCHAR,
    resource_id VARCHAR,
    partition VARCHAR,
    high_watermark VARCHAR,
    rows_seen BIGINT,
    updated_at VARCHAR,
    PRIMARY KEY (source_id, resource_id, partition)
)
"""


def _connect(lake: Path | None):
    from pipelines.storage import LAKE_DIR, ensure_dir, read_write_connection

    path = Path(lake) if lake else (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
    con = read_write_connection(path)
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    return con


class RunLedger:
    """Append/upsert run rows in ``gold.ingest_run``."""

    def __init__(self, lake: Path | None = None) -> None:
        self.lake = Path(lake) if lake else None

    def record(self, summary: RunSummary) -> None:
        row = summary.to_row()
        cols = list(row.keys())
        con = _connect(self.lake)
        try:
            con.execute(RUN_DDL)
            con.execute(f"DELETE FROM gold.ingest_run WHERE run_id = ?", [row["run_id"]])
            con.execute(
                f"INSERT INTO gold.ingest_run ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
        finally:
            con.close()

    def recent(self, limit: int = 20, source_id: str | None = None) -> list[dict[str, Any]]:
        from pipelines.storage import LAKE_DIR, ensure_dir, get_read_connection

        path = self.lake or (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
        if not Path(path).is_file():
            return []          # no lake yet — a first run has no history to read
        con = get_read_connection(path)
        has = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='gold' AND table_name='ingest_run'"
        ).fetchone()[0]
        if not has:
            return []
        sql = "SELECT * FROM gold.ingest_run"
        params: list[Any] = []
        if source_id:
            sql += " WHERE source_id = ?"
            params.append(source_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(int(limit))
        cur = con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


class WatermarkStore:
    """High-water marks per (source, resource, partition)."""

    def __init__(self, lake: Path | None = None) -> None:
        self.lake = Path(lake) if lake else None

    def get(self, source_id: str, resource_id: str, partition: str = "*") -> Optional[str]:
        from pipelines.storage import LAKE_DIR, ensure_dir, get_read_connection

        path = self.lake or (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
        if not Path(path).is_file():
            return None        # first run for this source: no watermark exists
        con = get_read_connection(path)
        has = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='gold' AND table_name='ingest_watermark'"
        ).fetchone()[0]
        if not has:
            return None
        row = con.execute(
            "SELECT high_watermark FROM gold.ingest_watermark "
            "WHERE source_id = ? AND resource_id = ? AND partition = ?",
            [source_id, resource_id, partition],
        ).fetchone()
        return row[0] if row else None

    def set(
        self,
        source_id: str,
        resource_id: str,
        high_watermark: str,
        *,
        partition: str = "*",
        rows_seen: int = 0,
    ) -> None:
        from pipelines.storage import utcnow_iso

        con = _connect(self.lake)
        try:
            con.execute(WATERMARK_DDL)
            con.execute(
                "DELETE FROM gold.ingest_watermark "
                "WHERE source_id = ? AND resource_id = ? AND partition = ?",
                [source_id, resource_id, partition],
            )
            con.execute(
                "INSERT INTO gold.ingest_watermark VALUES (?, ?, ?, ?, ?, ?)",
                [source_id, resource_id, partition, high_watermark, int(rows_seen), utcnow_iso()],
            )
        finally:
            con.close()

    def advance(
        self,
        source_id: str,
        resource_id: str,
        values: Iterable[str],
        *,
        partition: str = "*",
        rows_seen: int = 0,
    ) -> str | None:
        """Move the watermark to the max observed value (ISO dates sort correctly)."""
        candidates = [v for v in values if v]
        if not candidates:
            return None
        high = max(candidates)
        current = self.get(source_id, resource_id, partition)
        if current is not None and current >= high:
            return current
        self.set(source_id, resource_id, high, partition=partition, rows_seen=rows_seen)
        return high


def partition_of(value: str | None) -> str:
    """``dt=YYYY-MM-DD`` partition key for a date-like value (``dt=unknown``)."""
    if not value:
        return "dt=unknown"
    text = str(value)[:10]
    return f"dt={text}" if len(text) == 10 and text[4] == "-" else "dt=unknown"
