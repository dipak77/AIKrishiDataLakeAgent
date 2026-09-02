"""Tests for knowledge-gap detection (Phase E: pipelines/gaps.py).

Gaps are computed from the built lake, so these tests assert on the *shape and
behaviour* of the detectors plus a couple of facts that hold for any build of
this repository (116 crops vs 60 calendar rows, 12 markets, thin corpus).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.gaps import (  # noqa: E402
    Gap,
    detect_all,
    detect_all as _detect_all,
    domain_coverage_gaps,
    evidence_hole_gaps,
    geo_hole_gaps,
    ontology_hole_gaps,
    query_failure_gaps,
    register_rows,
    unresolved_mention_gaps,
    upsert_register,
)

LAKE = ROOT / "data" / "lake" / "agrilake.duckdb"

pytestmark = pytest.mark.skipif(not LAKE.is_file(), reason="lake not built (run `make seed`)")


def _con():
    from pipelines.storage import clear_connection_cache, get_read_connection

    clear_connection_cache()
    return get_read_connection(LAKE)


# ─────────────────────────── detectors ─────────────────────────────────────


def test_ontology_holes_are_computed_from_the_lake():
    gaps = ontology_hole_gaps(_con())
    assert gaps, "116 crops vs 60 calendar rows must leave holes"
    for gap in gaps:
        assert gap.type == "ONTOLOGY_HOLE"
        assert gap.key.startswith("CROP_")
        assert gap.detail and gap.suggested_sources
        assert gap.resolution_test.startswith("tests/gaps/")


def test_ontology_holes_are_ranked_by_severity():
    gaps = ontology_hole_gaps(_con())
    demand = [g.demand_signal for g in gaps]
    assert demand == sorted(demand, reverse=True)


def test_geo_holes_cover_subdistricts_and_markets():
    keys = {g.key for g in geo_hole_gaps(_con())}
    assert "market_coverage" in keys           # 12 registered markets < 200 target
    gap = next(g for g in geo_hole_gaps(_con()) if g.key == "market_coverage")
    assert gap.evidence_count == 12


def test_evidence_holes_flag_a_thin_corpus():
    gaps = evidence_hole_gaps(_con())
    assert gaps
    assert any(g.key == "corpus_depth" for g in gaps) or any(
        g.key == "research_corpus_absent" for g in gaps
    )


def test_domain_coverage_reports_empty_domains():
    gaps = domain_coverage_gaps(_con())
    domains = {g.key for g in gaps}
    # These three have no ingestion path at all yet, so they are gaps in every
    # build of this repository (unlike farmer_qa/market, which appear as soon as
    # their silver domain has rows).
    assert {"irrigation", "postharvest", "schemes"} <= domains
    for gap in gaps:
        assert gap.type == "DOMAIN_COVERAGE" and gap.evidence_count == 0
        assert gap.detail.startswith("no rows for domain")


def test_domain_coverage_stays_silent_for_domains_that_have_rows():
    gaps = domain_coverage_gaps(_con())
    # the lake always has market rows (dim_market), so it must not be a gap
    assert "market" not in {g.key for g in gaps}


def test_unresolved_mentions_are_counted_from_silver(tmp_path):
    silver = tmp_path / "silver" / "market"
    silver.mkdir(parents=True)
    rows = [
        {"source_id": "GOI_AGMARKNET", "commodity_raw": "Ridgeguard(Tori)", "crop": None},
        {"source_id": "GOI_AGMARKNET", "commodity_raw": "Ridgeguard(Tori)", "crop": None},
        {"source_id": "GOI_AGMARKNET", "commodity_raw": "Brinjal", "crop": "CROP_BRINJAL"},
    ]
    (silver / "mandi.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    gaps = unresolved_mention_gaps(tmp_path / "silver")
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.key == "Ridgeguard(Tori)" and gap.type == "UNRESOLVED_ENTITY"
    assert gap.evidence_count == 2 and gap.demand_signal == 2.0
    assert gap.suggested_sources == ["GOI_AGMARKNET"]


def test_query_failures_become_gaps_only_when_observed():
    gaps = query_failure_gaps([
        {"query": "zinc deficiency in ridge gourd", "segments": 0},
        {"query": "zinc deficiency in ridge gourd", "segments": 0},
        {"query": "tomato early blight", "segments": 4},
    ])
    assert len(gaps) == 1
    assert gaps[0].key == "zinc deficiency in ridge gourd"
    assert gaps[0].demand_signal == 2.0


def test_gap_ids_are_stable_and_namespaced():
    a = Gap(type="GEO_HOLE", key="market_coverage", dimension="market")
    b = Gap(type="GEO_HOLE", key="market_coverage", dimension="market")
    assert a.gap_id == b.gap_id and a.gap_id.startswith("GAP-")
    assert Gap(type="GEO_HOLE", key="other").gap_id != a.gap_id


# ─────────────────────────── orchestration + register ──────────────────────


def test_detect_all_merges_and_ranks_every_family():
    gaps = _detect_all(LAKE)
    types = {g.type for g in gaps}
    assert {"ONTOLOGY_HOLE", "GEO_HOLE", "EVIDENCE_HOLE", "DOMAIN_COVERAGE"} <= types
    severities = [g.severity for g in gaps]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert [order[s] for s in severities] == sorted(order[s] for s in severities)


def test_detect_all_can_be_scoped():
    gaps = _detect_all(LAKE, include=("GEO_HOLE",))
    assert gaps and {g.type for g in gaps} == {"GEO_HOLE"}


def test_detect_all_without_a_lake_reports_the_platform_gap(tmp_path):
    gaps = _detect_all(tmp_path / "missing.duckdb", include=("EVIDENCE_HOLE",))
    assert gaps[0].key == "lake_not_built"
    assert gaps[0].severity == "critical"


def test_register_upsert_is_idempotent_and_never_auto_closes(tmp_path):
    import duckdb

    lake = tmp_path / "lake.duckdb"
    gaps = [
        Gap(type="GEO_HOLE", key="market_coverage", dimension="market", demand_signal=0.9),
        Gap(type="ONTOLOGY_HOLE", key="CROP_X", dimension="agronomy", demand_signal=3.0),
    ]
    first = upsert_register(gaps, lake)
    assert first == {"added": 2, "refreshed": 0, "total": 2}
    second = upsert_register(gaps, lake)
    assert second == {"added": 0, "refreshed": 2, "total": 2}

    rows = register_rows(lake)
    assert len(rows) == 2
    assert all(r["status"] == "open" for r in rows)
    # demand ranking drives the collection order
    assert rows[0]["demand_signal"] >= rows[1]["demand_signal"]

    con = duckdb.connect(str(lake), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM gold.gap_register").fetchone()[0] == 2
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='gold' AND table_name='evidence_request'"
        ).fetchone()[0] == 1
    finally:
        con.close()


def test_register_rows_returns_empty_when_absent(tmp_path):
    import duckdb

    lake = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(lake))
    con.execute("CREATE SCHEMA gold")
    con.close()
    from pipelines.storage import clear_connection_cache

    clear_connection_cache()
    assert register_rows(lake) == []
