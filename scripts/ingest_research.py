"""Ingest research evidence → `gold.research_chunk` (V6 Phase 3).

Runs the research-domain connectors (ICAR now; the PDF pipeline joins the same
domain), which attempt a **live** fetch and fall back to the committed fixture
offline. Each run:

  1. persists the immutable raw payload to **bronze** (when live),
  2. writes normalized, provenance-enriched records to **silver**
     (`silver/research/*.jsonl`),
  3. upserts every chunk into **gold.research_chunk** (by chunk_id) so the
     hybrid RAG engine reads a single source of truth.

The fixture is the offline baseline; live data augments it. Idempotent.

Usage:
    python scripts/ingest_research.py [--lake data/lake/agrilake.duckdb] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_LAKE = ROOT / "data" / "lake" / "agrilake.duckdb"

REQUIRED = (
    "chunk_id",
    "document",
    "institution",
    "text",
    "authority",
    "authority_score",
    "source_url",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS gold.research_chunk (
    chunk_id        VARCHAR PRIMARY KEY,
    document        VARCHAR,
    institution     VARCHAR,
    year            INTEGER,
    crop            VARCHAR[],
    topics          VARCHAR[],
    section         VARCHAR,
    page            INTEGER,
    text            VARCHAR,
    authority       VARCHAR,
    authority_score DOUBLE,
    source_url      VARCHAR
)
"""

INSERT = """
INSERT OR REPLACE INTO gold.research_chunk
(chunk_id, document, institution, year, crop, topics, section, page, text, authority, authority_score, source_url)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _run_connector() -> tuple[list[dict], list[dict]]:
    """Run research connectors; return (records, summaries)."""
    from connectors.research import IcarConnector

    records: list[dict] = []
    summaries: list[dict] = []
    for connector_cls in (IcarConnector,):
        conn = connector_cls()
        summary = conn.run()
        summaries.append(summary)
        for res in summary.get("resources", []):
            for path in res.get("paths", []):
                p = Path(path)
                if p.is_file():
                    records.extend(
                        json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
                    )
    return records, summaries


def _upsert(lake: Path, records: list[dict]) -> dict[str, Any]:
    """Insert or replace records into gold.research_chunk; return count."""
    from pipelines.storage import get_read_connection, read_write_connection

    con = read_write_connection(lake)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute("CREATE TABLE IF NOT EXISTS gold.research_chunk ("
                    "chunk_id VARCHAR, document VARCHAR, institution VARCHAR, year INTEGER, "
                    "crop VARCHAR[], topics VARCHAR[], section VARCHAR, page INTEGER, "
                    "text VARCHAR, authority VARCHAR, authority_score DOUBLE, source_url VARCHAR)")
        n = 0
        for rec in records:
            # enriched records nest license/quality; flatten authority_score.
            if "authority_score" not in rec:
                rec = dict(rec)
                rec["authority_score"] = float(rec.get("authority_level", 0.95) or 0.95)
            cid = rec.get("chunk_id") or rec.get("record_id", "")
            con.execute("DELETE FROM gold.research_chunk WHERE chunk_id = ?", [cid])
            con.execute(
                """INSERT INTO gold.research_chunk
                (chunk_id, document, institution, year, crop, topics, section, page, text, authority, authority_score, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    cid,
                    rec.get("document") or "",
                    rec.get("institution") or "",
                    rec.get("year"),
                    rec.get("crop") or [],
                    rec.get("topics") or [],
                    rec.get("section"),
                    rec.get("page"),
                    rec.get("text") or "",
                    rec.get("authority", "research"),
                    float(rec.get("authority_score") or 0.0),
                    rec.get("source_url"),
                ],
            )
            n += 1
    finally:
        con.close()

    rcon = get_read_connection(lake)
    total = rcon.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
    docs = rcon.execute("SELECT count(DISTINCT document) FROM gold.research_chunk").fetchone()[0]
    return {"upserted": n, "total": total, "documents": docs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest research evidence into gold.research_chunk")
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    records, summaries = _run_connector()
    methods = [
        r.get("method")
        for s in summaries
        for r in s.get("resources", [])
        if r.get("status") == "ok"
    ]
    report = _upsert(args.lake, records)

    if args.json:
        print(json.dumps({"report": report, "methods": methods}, ensure_ascii=False, indent=2))
        return 0

    print(
        f"gold.research_chunk: {report['total']} chunks / {report['documents']} documents "
        f"(upserted {report['upserted']}, method={set(methods) or 'fixture'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
