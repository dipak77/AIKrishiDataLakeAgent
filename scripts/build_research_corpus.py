"""Build `gold.research_chunk` from the committed ICAR fixture (V6 Phase 3).

The hybrid RAG layer reads `gold.research_chunk` (see ``reasoning.rag.load_chunks``)
and falls back to ``data/fixtures/icar_research_chunk.json`` when the table is
absent. This script materializes the table so retrieval runs against the lake —
the same source of truth as every other gold table — and is the seam where live
ICAR/FAO/PlantVillage ingestion will land without changing the RAG code.

Usage:
    python scripts/build_research_corpus.py [--fixture data/fixtures/icar_research_chunk.json]
                                             [--lake data/lake/agrilake.duckdb]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "icar_research_chunk.json"
DEFAULT_LAKE = ROOT / "data" / "lake" / "agrilake.duckdb"

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


def build(fixture: Path, lake: Path) -> dict[str, object]:
    from pipelines.storage import get_read_connection, read_write_connection

    chunks = json.loads(fixture.read_text(encoding="utf-8"))
    con = read_write_connection(lake)  # read-write (creates if absent)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.execute("CREATE TABLE IF NOT EXISTS gold.research_chunk ("
                    "chunk_id VARCHAR, document VARCHAR, institution VARCHAR, year INTEGER, "
                    "crop VARCHAR[], topics VARCHAR[], section VARCHAR, page INTEGER, "
                    "text VARCHAR, authority VARCHAR, authority_score DOUBLE, source_url VARCHAR)")
        for c in chunks:
            cid = c.get("chunk_id")
            con.execute("DELETE FROM gold.research_chunk WHERE chunk_id = ?", [cid])
            con.execute(
                """INSERT INTO gold.research_chunk
                (chunk_id, document, institution, year, crop, topics, section, page, text, authority, authority_score, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    cid,
                    c.get("document"),
                    c.get("institution"),
                    c.get("year"),
                    c.get("crop") or [],
                    c.get("topics") or [],
                    c.get("section"),
                    c.get("page"),
                    c.get("text"),
                    c.get("authority", "research"),
                    float(c.get("authority_score") or 0.0),
                    c.get("source_url"),
                ],
            )
    finally:
        con.close()

    rcon = get_read_connection(lake)
    n = rcon.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
    docs = rcon.execute("SELECT count(DISTINCT document) FROM gold.research_chunk").fetchone()[0]
    return {"chunks": n, "documents": docs, "source": str(fixture.name)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build gold.research_chunk from the ICAR fixture")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.fixture.is_file():
        print(f"fixture not found: {args.fixture}", file=sys.stderr)
        return 1

    report = build(args.fixture, args.lake)
    if not args.quiet:
        print(f"gold.research_chunk: {report['chunks']} chunks / {report['documents']} documents "
              f"<- {report['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
