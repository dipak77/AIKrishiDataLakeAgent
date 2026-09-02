"""Knowledge-gap detection: the lake measures its own holes.

A gap is a *computed* fact about missing knowledge, not an assertion in a
document (`docs/v7-plan.md` §4.9). Each :class:`Gap` carries the evidence that
produced it and a ``demand_signal`` so the targeted-collection loop (S9) can
work the highest-value hole first.

Detectors, all read-only over the built lake + committed seeds:

``ONTOLOGY_HOLE``   a canonical crop with no disease / pest / calendar /
                    nutrient-requirement knowledge attached
``GEO_HOLE``        districts with no subdistrict rows; thin market coverage
``EVIDENCE_HOLE``   crops/domains with no research evidence
``UNRESOLVED_ENTITY`` raw source strings (e.g. a live mandi commodity) that no
                    ontology entry resolves — with occurrence counts
``DOMAIN_COVERAGE`` the 55-domain target scored against what actually exists

A gap closes only when a test encoding its assertion passes; this module never
marks anything closed on its own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

GAP_TYPES = (
    "ONTOLOGY_HOLE", "GEO_HOLE", "EVIDENCE_HOLE", "UNRESOLVED_ENTITY",
    "DOMAIN_COVERAGE", "TEMPORAL_HOLE", "QUERY_FAILURE",
)

SEVERITIES = ("critical", "high", "medium", "low")


@dataclass
class Gap:
    type: str
    key: str
    dimension: str = ""
    severity: str = "medium"
    demand_signal: float = 0.0
    evidence_count: int = 0
    detail: str = ""
    suggested_sources: list[str] = field(default_factory=list)
    resolution_test: str = ""

    @property
    def gap_id(self) -> str:
        import hashlib

        raw = f"{self.type}:{self.dimension}:{self.key}".encode("utf-8")
        return f"GAP-{hashlib.sha256(raw).hexdigest()[:12].upper()}"

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["gap_id"] = self.gap_id
        return row


# ─────────────────────────── helpers ───────────────────────────────────────


def _table(con: Any, name: str) -> bool:
    return bool(
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='gold' AND table_name=?",
            [name],
        ).fetchone()[0]
    )


def _connect_read(lake: Optional[Path] = None):
    from pipelines.storage import LAKE_DIR, ensure_dir, get_read_connection

    path = Path(lake) if lake else (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
    if not path.is_file():
        return None
    return get_read_connection(path)


# ─────────────────────────── detectors ─────────────────────────────────────


def ontology_hole_gaps(con: Any, *, limit: int = 40) -> list[Gap]:
    """Crops with no disease, pest, calendar or nutrient-requirement knowledge.

    Pest coverage is matched against the free-text ``crop_hosts`` column
    (``dim_pest`` has no ``crop_id``), so it is approximate by construction and
    labelled as such in the gap detail.
    """
    if not _table(con, "dim_crop"):
        return []
    has_nutrient = _table(con, "crop_nutrient_requirement")
    has_pest = _table(con, "dim_pest")
    nutrient_expr = (
        "(SELECT count(*) FROM gold.crop_nutrient_requirement n WHERE n.crop_id = c.crop_id)"
        if has_nutrient else "0"
    )
    pest_expr = (
        "(SELECT count(*) FROM gold.dim_pest p "
        " WHERE lower(coalesce(p.crop_hosts,'')) LIKE '%' || lower(c.canonical_en) || '%')"
        if has_pest else "0"
    )
    rows = con.execute(
        f"""
        SELECT c.crop_id, c.canonical_en,
               (SELECT count(*) FROM gold.dim_disease d WHERE d.crop_id = c.crop_id) AS diseases,
               {pest_expr} AS pests,
               (SELECT count(*) FROM gold.crop_calendar cc WHERE cc.crop_id = c.crop_id) AS calendar_rows,
               {nutrient_expr} AS nutrient_rows
        FROM gold.dim_crop c
        ORDER BY c.crop_id
        """
    ).fetchall()

    gaps: list[Gap] = []
    for crop_id, name, diseases, pests, calendar_rows, nutrient_rows in rows:
        missing = [
            label
            for label, count in (
                ("disease", diseases), ("pest", pests),
                ("calendar", calendar_rows), ("nutrient_requirement", nutrient_rows),
            )
            if not count
        ]
        if not missing:
            continue
        gaps.append(
            Gap(
                type="ONTOLOGY_HOLE",
                key=crop_id,
                dimension="crop_protection" if "disease" in missing else "agronomy",
                severity="high" if len(missing) >= 3 else "medium",
                demand_signal=round(len(missing) * 1.0, 2),
                evidence_count=0,
                detail=f"{name} has no {'/'.join(missing)} knowledge",
                suggested_sources=["ICAR", "KVK", "GOI_DATAGOV", "research_pdf"],
                resolution_test=f"tests/gaps/test_gap_{crop_id.lower()}.py",
            )
        )
    gaps.sort(key=lambda g: (-g.demand_signal, g.key))
    return gaps[:limit]


def geo_hole_gaps(con: Any) -> list[Gap]:
    """Districts without subdistricts, and thin mandi-market coverage."""
    gaps: list[Gap] = []
    if _table(con, "dim_geography"):
        districts = con.execute(
            "SELECT count(DISTINCT district_code) FROM gold.dim_geography "
            "WHERE district_code IS NOT NULL"
        ).fetchone()[0]
        covered = (
            con.execute("SELECT count(DISTINCT district_code) FROM gold.dim_subdistrict").fetchone()[0]
            if _table(con, "dim_subdistrict") else 0
        )
        missing = max(0, int(districts) - int(covered))
        if missing:
            gaps.append(
                Gap(
                    type="GEO_HOLE", key="subdistrict_coverage", dimension="geography",
                    severity="high", demand_signal=round(missing / max(districts, 1), 3),
                    evidence_count=int(covered),
                    detail=f"{covered}/{districts} districts have subdistrict rows ({missing} missing)",
                    suggested_sources=["LGD", "GOI_DATAGOV"],
                    resolution_test="tests/gaps/test_gap_subdistrict_coverage.py",
                )
            )
    if _table(con, "dim_market"):
        markets = con.execute("SELECT count(*) FROM gold.dim_market").fetchone()[0]
        if int(markets) < 200:
            gaps.append(
                Gap(
                    type="GEO_HOLE", key="market_coverage", dimension="market",
                    severity="medium", demand_signal=round(1.0 - int(markets) / 200.0, 3),
                    evidence_count=int(markets),
                    detail=f"only {markets} APMC markets registered (live mandi feed carries ~1,800)",
                    suggested_sources=["GOI_AGMARKNET"],
                    resolution_test="tests/gaps/test_gap_market_coverage.py",
                )
            )
    return gaps


def evidence_hole_gaps(con: Any) -> list[Gap]:
    """Crops with no research evidence behind them."""
    if not _table(con, "research_chunk") or not _table(con, "dim_crop"):
        return [
            Gap(
                type="EVIDENCE_HOLE", key="research_corpus_absent", dimension="research",
                severity="critical", demand_signal=1.0, evidence_count=0,
                detail="gold.research_chunk is empty or missing — the RAG engine has nothing to cite",
                suggested_sources=["ICAR", "research_pdf", "FAO_FAOSTAT"],
                resolution_test="tests/gaps/test_gap_research_corpus.py",
            )
        ]
    total = con.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
    rows = con.execute(
        "SELECT c.crop_id, c.canonical_en FROM gold.dim_crop c "
        "WHERE NOT EXISTS (SELECT 1 FROM gold.research_chunk r "
        "                  WHERE list_contains(r.crop, c.crop_id))"
    ).fetchall()
    gaps = [
        Gap(
            type="EVIDENCE_HOLE", key=crop_id, dimension="research",
            severity="medium", demand_signal=1.0, evidence_count=0,
            detail=f"no research evidence mentions {name}",
            suggested_sources=["ICAR", "research_pdf"],
            resolution_test=f"tests/gaps/test_gap_evidence_{crop_id.lower()}.py",
        )
        for crop_id, name in rows
    ]
    if int(total) < 1000:
        gaps.insert(
            0,
            Gap(
                type="EVIDENCE_HOLE", key="corpus_depth", dimension="research",
                severity="high", demand_signal=round(1.0 - int(total) / 1000.0, 3),
                evidence_count=int(total),
                detail=f"research corpus holds only {total} chunks (target ≥ 5,000)",
                suggested_sources=["ICAR", "research_pdf", "KVK"],
                resolution_test="tests/gaps/test_gap_corpus_depth.py",
            ),
        )
    return gaps


def unresolved_mention_gaps(
    silver_dir: Path | None = None, *, limit: int = 50
) -> list[Gap]:
    """Raw source strings that no ontology entry resolved, ranked by frequency.

    Scans silver JSONL for records carrying a raw mention (``commodity_raw``,
    ``crop_canonical``, ``subcategory``) with a null canonical link. This is how
    the live mandi vocabulary (e.g. ``Ridgeguard(Tori)``) becomes actionable.
    """
    from pipelines.storage import SILVER_DIR

    base = Path(silver_dir or SILVER_DIR)
    if not base.is_dir():
        return []
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(base.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            pairs = (
                ("crop", row.get("commodity_raw"), row.get("crop")),
                ("category", row.get("subcategory"), None if not row.get("category") else row.get("category")),
            )
            for kind, mention, resolved in pairs:
                if mention and not resolved:
                    key = (kind, str(mention).strip())
                    entry = counts.setdefault(
                        key, {"occurrences": 0, "sources": set(), "sample": row.get("source_id", "")}
                    )
                    entry["occurrences"] += 1
                    if row.get("source_id"):
                        entry["sources"].add(str(row["source_id"]))

    gaps = [
        Gap(
            type="UNRESOLVED_ENTITY",
            key=mention,
            dimension=kind,
            severity="high" if info["occurrences"] >= 10 else "medium",
            demand_signal=float(info["occurrences"]),
            evidence_count=int(info["occurrences"]),
            detail=f"{info['occurrences']} record(s) mention {mention!r} with no canonical {kind}",
            suggested_sources=sorted(info["sources"]),
            resolution_test=f"tests/gaps/test_gap_alias_{kind}.py",
        )
        for (kind, mention), info in counts.items()
    ]
    gaps.sort(key=lambda g: (-g.demand_signal, g.key))
    return gaps[:limit]


DOMAIN_TARGETS: dict[str, str] = {
    "crop_protection": "diseases/pests/IPM",
    "soil_fertility": "soil testing + fertilizer advisory",
    "market": "prices/MSP/commodity markets",
    "weather": "agrometeorology + climate risk",
    "farmer_qa": "farmer questions + expert answers",
    "research": "research evidence corpus",
    "vision": "computer vision / pest-disease imagery",
    "irrigation": "irrigation + water management",
    "postharvest": "harvest/post-harvest/storage",
    "schemes": "government schemes + insurance",
}


def domain_coverage_gaps(con: Any) -> list[Gap]:
    """Score the 55-domain target against tables that actually hold rows."""
    present: dict[str, int] = {}
    if _table(con, "dim_disease"):
        present["crop_protection"] = con.execute(
            "SELECT (SELECT count(*) FROM gold.dim_disease) + (SELECT count(*) FROM gold.dim_pest)"
        ).fetchone()[0]
    if _table(con, "soil_test_interpretation"):
        present["soil_fertility"] = con.execute(
            "SELECT (SELECT count(*) FROM gold.soil_test_interpretation) "
            "+ (SELECT count(*) FROM gold.crop_nutrient_requirement)"
        ).fetchone()[0]
    if _table(con, "fact_mandi_price"):
        present["market"] = con.execute("SELECT count(*) FROM gold.fact_mandi_price").fetchone()[0]
    elif _table(con, "dim_market"):
        present["market"] = con.execute("SELECT count(*) FROM gold.dim_market").fetchone()[0]
    if _table(con, "fact_agromet_advisory"):
        present["weather"] = con.execute("SELECT count(*) FROM gold.fact_agromet_advisory").fetchone()[0]
    if _table(con, "farmer_query"):
        present["farmer_qa"] = con.execute("SELECT count(*) FROM gold.farmer_query").fetchone()[0]
    if _table(con, "research_chunk"):
        present["research"] = con.execute("SELECT count(*) FROM gold.research_chunk").fetchone()[0]
    if _table(con, "agri_image"):
        present["vision"] = con.execute("SELECT count(*) FROM gold.agri_image").fetchone()[0]

    gaps = []
    for domain, label in DOMAIN_TARGETS.items():
        rows = int(present.get(domain, 0))
        if rows > 0:
            continue
        gaps.append(
            Gap(
                type="DOMAIN_COVERAGE", key=domain, dimension=domain,
                severity="high" if domain in ("farmer_qa", "research", "crop_protection") else "medium",
                demand_signal=1.0, evidence_count=0,
                detail=f"no rows for domain '{label}' — nothing to answer {domain} questions from",
                suggested_sources=["GOI_KCC", "ICAR", "GOI_DATAGOV", "IMD_AAS"],
                resolution_test=f"tests/gaps/test_gap_domain_{domain}.py",
            )
        )
    return gaps


def query_failure_gaps(failures: Iterable[dict[str, Any]], *, limit: int = 25) -> list[Gap]:
    """Turn gateway/assistant misses (0-segment answers) into gaps.

    ``failures`` is supplied by the caller from ``/api/gateway`` stats — this
    module never invents demand it did not observe.
    """
    counts: dict[str, int] = {}
    for item in failures:
        query = str(item.get("query") or "").strip()
        if query and int(item.get("segments", 0) or 0) == 0:
            counts[query] = counts.get(query, 0) + 1
    gaps = [
        Gap(
            type="QUERY_FAILURE", key=query, dimension="assistant",
            severity="high" if n >= 3 else "medium", demand_signal=float(n), evidence_count=0,
            detail=f"query returned zero context segments {n} time(s)",
            suggested_sources=["ICAR", "KVK", "GOI_KCC"],
            resolution_test="tests/gaps/test_gap_query_failure.py",
        )
        for query, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return gaps[:limit]


# ─────────────────────────── orchestration ─────────────────────────────────


def detect_all(
    lake: Path | None = None,
    *,
    failures: Iterable[dict[str, Any]] = (),
    include: Iterable[str] = GAP_TYPES,
) -> list[Gap]:
    """Run every applicable detector and return the merged, ranked gap list."""
    wanted = set(include)
    gaps: list[Gap] = []
    con = _connect_read(lake)
    try:
        if con is not None:
            if "ONTOLOGY_HOLE" in wanted:
                gaps += ontology_hole_gaps(con)
            if "GEO_HOLE" in wanted:
                gaps += geo_hole_gaps(con)
            if "EVIDENCE_HOLE" in wanted:
                gaps += evidence_hole_gaps(con)
            if "DOMAIN_COVERAGE" in wanted:
                gaps += domain_coverage_gaps(con)
        else:
            if "EVIDENCE_HOLE" in wanted:
                gaps.append(
                    Gap(
                        type="EVIDENCE_HOLE", key="lake_not_built", dimension="platform",
                        severity="critical", demand_signal=1.0,
                        detail="no lakehouse found — run `make bootstrap` before gap detection",
                        resolution_test="tests/gaps/test_gap_lake_present.py",
                    )
                )
    finally:
        # `con` is the thread-cached read handle from get_read_connection(); its
        # contract is "never close the returned handle". Closing it here left a
        # dead connection in the cache, so the next detect_all() call failed with
        # "Connection already closed!" (caught by tests/test_gaps.py).
        pass
    if "UNRESOLVED_ENTITY" in wanted:
        gaps += unresolved_mention_gaps()
    if "QUERY_FAILURE" in wanted:
        gaps += query_failure_gaps(failures)

    order = {sev: i for i, sev in enumerate(SEVERITIES)}
    gaps.sort(key=lambda g: (order.get(g.severity, 9), -g.demand_signal, g.key))
    return gaps


# ─────────────────────────── persistence ───────────────────────────────────

GAP_DDL = """
CREATE TABLE IF NOT EXISTS gold.gap_register (
    gap_id VARCHAR PRIMARY KEY, type VARCHAR, dimension VARCHAR, key VARCHAR,
    severity VARCHAR, demand_signal DOUBLE, evidence_count INTEGER, detail VARCHAR,
    suggested_sources VARCHAR, resolution_test VARCHAR,
    first_seen VARCHAR, last_seen VARCHAR, status VARCHAR, owner VARCHAR
)
"""

REQUEST_DDL = """
CREATE TABLE IF NOT EXISTS gold.evidence_request (
    request_id VARCHAR PRIMARY KEY, gap_id VARCHAR, source_types VARCHAR,
    query_templates VARCHAR, license_class VARCHAR, priority DOUBLE,
    status VARCHAR, created_at VARCHAR, closed_at VARCHAR
)
"""


def upsert_register(gaps: Iterable[Gap], lake: Any = None) -> dict[str, int]:
    """Insert new gaps, refresh ``last_seen`` on known ones. Never auto-closes."""
    from pipelines.collect import _connect
    from pipelines.storage import utcnow_iso

    gaps = list(gaps)
    now = utcnow_iso()
    con = _connect(lake)
    try:
        con.execute(GAP_DDL)
        con.execute(REQUEST_DDL)
        added = refreshed = 0
        for gap in gaps:
            row = gap.to_dict()
            exists = con.execute(
                "SELECT first_seen FROM gold.gap_register WHERE gap_id = ?", [row["gap_id"]]
            ).fetchone()
            if exists:
                con.execute(
                    "UPDATE gold.gap_register SET last_seen = ?, demand_signal = ?, "
                    "evidence_count = ?, detail = ?, severity = ? WHERE gap_id = ?",
                    [now, gap.demand_signal, gap.evidence_count, gap.detail, gap.severity, row["gap_id"]],
                )
                refreshed += 1
            else:
                con.execute(
                    "INSERT INTO gold.gap_register VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        row["gap_id"], gap.type, gap.dimension, gap.key, gap.severity,
                        gap.demand_signal, gap.evidence_count, gap.detail,
                        json.dumps(gap.suggested_sources, ensure_ascii=False),
                        gap.resolution_test, now, now, "open", None,
                    ],
                )
                added += 1
        return {"added": added, "refreshed": refreshed, "total": len(gaps)}
    finally:
        con.close()


def register_rows(lake: Any = None, *, status: str | None = None) -> list[dict[str, Any]]:
    """Read the gap register ([] when it does not exist yet)."""
    from pipelines.storage import LAKE_DIR, ensure_dir, get_read_connection

    path = Path(lake) if lake else (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
    if not path.is_file():
        return []
    con = get_read_connection(path)
    if not _table(con, "gap_register"):
        return []
    sql = "SELECT * FROM gold.gap_register"
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY demand_signal DESC, gap_id"
    cur = con.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
