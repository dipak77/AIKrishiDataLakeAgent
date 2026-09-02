"""Production ingestion orchestrator — the real discovery → collection → quality → gap flow.

This is the entry point that ties the Phase 0–F modules into one auditable run
(``docs/v7-plan.md`` §4). For each registered source it performs:

1. **discover** — read the upstream resource's own metadata payload, compare it
   with the declared contract, decide the licence, and upsert
   ``gold.source_catalog``. Drift is a first-class outcome, never a log line.
2. **collect** — run the connector under an explicit transport
   (``live`` | ``record`` | ``replay`` | ``offline``), stamp every record with
   ``run_id`` + ``ingestion_method``, persist bronze + silver, and write a
   ``gold.ingest_run`` ledger row per resource.
3. **quality** — dedupe on the declared business key, then run the 23-rule gate.
   Rows are promoted, quarantined (kept, never promoted) or rejected (never
   persisted); violations and the scorecard land in the lake.
4. **watermark** — advance the incremental high-water mark from the rows that
   actually passed, so the next run can skip them.
5. **gaps** — recompute the knowledge-gap register from what the lake still
   lacks, which is the input queue for the next collection cycle.

Nothing here is fixture-backed by default: ``--require-live`` (or
``AGRILAKE_REQUIRE_LIVE=1``) makes an unreachable source fail the run instead of
silently substituting bundled sample data.

Usage::

    python scripts/pipeline_run.py --source GOI_AGMARKNET --transport replay --limit 2
    python scripts/pipeline_run.py --source all --transport live --require-live --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.government import (  # noqa: E402
    AgmarknetConnector,
    ImdConnector,
    KccConnector,
    SoilHealthConnector,
)
from connectors.research import FaostatConnector, IcarConnector  # noqa: E402
from connectors.vision import PlantDocConnector, PlantVillageConnector  # noqa: E402
from pipelines.collect import (  # noqa: E402
    RunLedger,
    WatermarkStore,
    dedupe_records,
    new_run_id,
    partition_of,
)
from pipelines.contracts import contract_for  # noqa: E402
from pipelines.dq import DQContext, evaluate, gate, persist_report  # noqa: E402
from pipelines.discovery import DataGovDiscovery, save_discovered, upsert_catalog  # noqa: E402
from pipelines.gaps import detect_all, upsert_register  # noqa: E402
from pipelines.http import HttpClient  # noqa: E402

LOGGER = logging.getLogger("agrilake.pipeline")

#: source_id (registry key) → connector class
SOURCE_CONNECTORS: dict[str, Callable[[], Any]] = {
    "GOI_AGMARKNET": AgmarknetConnector,
    "GOI_KCC": KccConnector,
    "GOI_SHC": SoilHealthConnector,
    "IMD_AAS": ImdConnector,
    "FAO_FAOSTAT": FaostatConnector,
    "ICAR": IcarConnector,
    "PLANTVILLAGE": PlantVillageConnector,
    "PLANTDOC": PlantDocConnector,
}


# ─────────────────────────────── stage 1: discover ──────────────────────────


def declared_resources(source_id: str, contract: Any) -> list[str]:
    """Resource ids the registry declares for a source (contract id as fallback)."""
    from connectors.base import registry

    if not registry._sources:  # noqa: SLF001 - intentional lazy load
        registry.load()
    try:
        meta = registry.get(source_id)
    except KeyError:
        meta = None
    items = (getattr(meta, "acquisition", {}) or {}).get("resources") or [] if meta else []
    ids = [str(i.get("resource_id") or i.get("id")) for i in items if isinstance(i, dict)]
    if contract is not None and contract.resource_id and contract.resource_id not in ids:
        ids.append(str(contract.resource_id))
    return [i for i in ids if i and i != "None"]


def discover_stage(
    source_id: str,
    contract: Any,
    *,
    http: HttpClient | None = None,
    lake: Any = None,
    discovered_dir: Path | None = None,
    fail_on_drift: bool = False,
) -> dict[str, Any]:
    """Read upstream metadata for every declared resource and gate on drift."""
    outcome: dict[str, Any] = {"resources": [], "status": "ok", "error": ""}
    resources = declared_resources(source_id, contract)
    if not resources:
        outcome.update(status="skipped", error="no resources declared in the registry")
        return outcome

    finder = DataGovDiscovery(http)
    found = []
    for rid in resources:
        try:
            resource = finder.discover_resource(source_id, rid)
        except Exception as exc:  # noqa: BLE001 - one dead resource must not kill the run
            LOGGER.warning("discovery failed for %s/%s: %s", source_id, rid, exc)
            outcome["resources"].append({"resource_id": rid, "status": "error", "error": str(exc)})
            outcome["status"] = "degraded"
            continue
        found.append(resource)
        outcome["resources"].append(
            {
                "resource_id": rid,
                "status": "drift" if resource.has_drift else "ok",
                "title": resource.title,
                "total_records": resource.total_records,
                "license": resource.license_declared,
                "license_decision": resource.license_decision,
                "updated_at": resource.upstream_updated_at,
                "has_drift": resource.has_drift,
                "drift": resource.drift,
                "filterable": resource.field_exposed,
            }
        )
        if resource.license_decision == "BLOCK":
            outcome["status"] = "blocked"
        if resource.has_drift and fail_on_drift:
            outcome["status"] = "drift"

    if found:
        try:
            save_discovered(found, discovered_dir)
            upsert_catalog(found, lake)
        except Exception:  # noqa: BLE001 - catalog write must not break ingestion
            LOGGER.exception("could not persist discovery results for %s", source_id)
            outcome["status"] = "degraded"
    return outcome


# ─────────────────────────────── stage 3: quality ───────────────────────────


def price_stats(records: Iterable[dict[str, Any]]) -> dict[tuple[str, str], tuple[float, float]]:
    """``{(market, commodity): (median, MAD)}`` for the outlier rule."""
    buckets: dict[tuple[str, str], list[float]] = {}
    for rec in records:
        try:
            value = float(rec.get("modal_price") or 0.0)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        buckets.setdefault((str(rec.get("market") or ""), str(rec.get("commodity_raw") or "")), []).append(value)

    stats: dict[tuple[str, str], tuple[float, float]] = {}
    for key, values in buckets.items():
        if len(values) < 3:            # MAD is meaningless below this
            continue
        median = statistics.median(values)
        mad = statistics.median([abs(v - median) for v in values])
        stats[key] = (median, mad)
    return stats


def quality_stage(
    records: list[dict[str, Any]],
    *,
    source_id: str,
    domain: str,
    run_id: str,
    contract: Any,
    lake: Any,
    require_live: bool,
) -> dict[str, Any]:
    """Dedupe, gate, persist — the quality filter and the refine path in one."""
    key_fields = list(contract.business_key) if contract and getattr(contract, "business_key", None) else None
    unique, duplicates, conflicts = dedupe_records(records, key_fields=key_fields)

    ledger = RunLedger(lake)
    history = [int(r.get("rows_pass") or 0) for r in ledger.recent(20, source_id=source_id)]

    ctx = DQContext(
        source_id=source_id,
        domain=domain,
        contract=contract,
        run_id=run_id,
        require_live=require_live,
        price_stats=price_stats(unique),
        history_row_counts=history,
    )
    report = evaluate(unique, ctx)
    scorecard = report.scorecard()
    scorecard["duplicates"] = len(duplicates)
    scorecard["conflicts"] = len(conflicts)
    scorecard["promoted"] = bool(gate(scorecard))

    try:
        persist_report(report, lake)
    except Exception:  # noqa: BLE001 - a lake write failure must not lose the report
        LOGGER.exception("could not persist DQ report for %s", run_id)

    return {
        "scorecard": scorecard,
        "rule_counts": report.rule_counts,
        "promoted": scorecard["promoted"],
        "quarantined": len(report.quarantined),
        "rejected": len(report.rejected),
        "passed": len(report.passed),
        "violations": report.violations[:20],
        "records_passed": report.passed,
    }


# ─────────────────────────────── stage 4: watermark ─────────────────────────


def watermark_stage(
    passed: list[dict[str, Any]],
    *,
    source_id: str,
    resource_id: str,
    contract: Any,
    lake: Any,
) -> dict[str, Any]:
    if contract is None:
        return {"advanced": False, "reason": "no contract — no incremental key declared"}
    values = [v for v in (contract.incremental_key_of(r) for r in passed) if v]
    if not values:
        return {"advanced": False, "reason": "no incremental key values in the passed batch"}
    store = WatermarkStore(lake)
    incremental = contract.incremental
    partition = (
        partition_of(max(values))
        if incremental.strategy == "partition_by_field" and incremental.partition_field
        else "*"
    )
    high = store.advance(source_id, resource_id, values, partition=partition, rows_seen=len(passed))
    return {"advanced": high is not None, "watermark": high, "partition": partition, "rows_seen": len(passed)}


# ─────────────────────────────── orchestration ──────────────────────────────


def _read_jsonl(paths: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        file = Path(path)
        if not file.is_file():
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_source(
    source_id: str,
    *,
    transport: str = "replay",
    require_live: bool = False,
    limit: int = 10,
    lake: Any = None,
    http: HttpClient | None = None,
    discovered_dir: Path | None = None,
    cassette_dir: Path | None = None,
    fail_on_drift: bool = False,
    include_gaps: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the full pipeline for one registered source and return an audit dict."""
    factory = SOURCE_CONNECTORS.get(source_id)
    if factory is None:
        return {"source_id": source_id, "status": "unknown_source", "error": f"no connector for {source_id!r}"}

    contract = contract_for(source_id)
    run_id = run_id or new_run_id(source_id.lower())
    if http is None:
        # discovery must obey the same transport as collection: a `replay` run
        # reads metadata from the cassette, it does not phone the publisher
        http = HttpClient(mode=transport, cassette_dir=cassette_dir)
    outcome: dict[str, Any] = {
        "source_id": source_id,
        "run_id": run_id,
        "transport": transport,
        "contract_version": contract.version if contract else "",
        "contract_hash": contract.contract_hash() if contract else "",
        "require_live": require_live,
    }

    # 1. discovery + drift gate
    outcome["discovery"] = discover_stage(
        source_id, contract, http=http, lake=lake,
        discovered_dir=discovered_dir, fail_on_drift=fail_on_drift,
    )
    if fail_on_drift and outcome["discovery"]["status"] in ("drift", "blocked"):
        outcome["status"] = outcome["discovery"]["status"]
        return outcome

    # 2. collection
    connector = factory()
    connector.limit = limit
    try:
        summary = connector.run(
            transport=transport, require_live=require_live, lake=lake, run_id=run_id,
            cassette_dir=cassette_dir,
        )
    except Exception as exc:  # noqa: BLE001 - report, never crash the orchestrator
        LOGGER.exception("collection failed for %s", source_id)
        outcome.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        return outcome

    outcome["collection"] = {
        "discovered": summary.get("discovered", 0),
        "status": summary.get("status"),
        "resources": [
            {k: v for k, v in entry.items() if k in ("status", "records", "method", "bronze", "paths", "error")}
            for entry in summary.get("resources", [])
        ],
    }
    if not summary.get("resources"):
        outcome["status"] = "empty"          # nothing upstream to collect (e.g. retired resource)
        return outcome
    if summary.get("status") != "ok":
        outcome["status"] = "failed"
        outcome["error"] = "; ".join(
            str(e.get("error", "")) for e in summary.get("resources", []) if e.get("status") == "error"
        )
        return outcome

    # 3. quality gate over what was actually persisted
    records = _read_jsonl(
        p for entry in summary.get("resources", []) for p in entry.get("paths") or []
    )
    outcome["quality"] = quality_stage(
        records, source_id=source_id, domain=connector.domain, run_id=run_id,
        contract=contract, lake=lake, require_live=require_live,
    )

    # 4. watermark (only rows that passed may move it forward)
    resource_ids = [
        str(e.get("resource", {}).get("resource_id") or e.get("resource", {}).get("id") or "default")
        for e in summary.get("resources", [])
    ]
    outcome["watermark"] = watermark_stage(
        outcome["quality"]["records_passed"], source_id=source_id,
        resource_id=resource_ids[0] if resource_ids else "default",
        contract=contract, lake=lake,
    )
    outcome["quality"].pop("records_passed", None)   # keep the audit dict small

    outcome["status"] = "promoted" if outcome["quality"]["promoted"] else "parked"

    # 5. knowledge gaps (queue for the next collection cycle)
    if include_gaps:
        try:
            gaps = detect_all(lake)
            result = upsert_register(gaps, lake)
            outcome["gaps"] = {
                "detected": len(gaps),
                "new": result["added"],
                "refreshed": result["refreshed"],
                "top": [
                    {"gap_id": g.gap_id, "type": g.type, "key": g.key, "severity": g.severity}
                    for g in gaps[:10]
                ],
            }
        except Exception:  # noqa: BLE001 - gap detection is advisory
            LOGGER.exception("gap detection failed for %s", source_id)
            outcome["gaps"] = {"error": "gap detection failed"}
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the production ingestion pipeline")
    parser.add_argument("--source", default="GOI_AGMARKNET",
                        help=f"registry source_id, or 'all' ({', '.join(sorted(SOURCE_CONNECTORS))})")
    parser.add_argument("--transport", default=os.environ.get("AGRILAKE_TRANSPORT", "live"),
                        choices=("live", "record", "replay", "offline"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--lake", default=None, help="DuckDB path (default: data/lake/agrilake.duckdb)")
    parser.add_argument("--require-live", action="store_true",
                        help="fail the run when a source is unreachable (default: on)")
    parser.add_argument("--allow-fixtures", action="store_true",
                        help="OPT OUT of the production default: let bundled fixture rows "
                             "through the quality gate (never use this for a real run)")
    parser.add_argument("--fail-on-drift", action="store_true",
                        help="abort a source whose upstream schema no longer matches its contract")
    parser.add_argument("--no-gaps", action="store_true", help="skip knowledge-gap detection")
    parser.add_argument("--cassette-dir", default=None, help="cassette directory for replay/record")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    # Production default: a run promotes only live/replay rows. Fixture rows may
    # still be produced by a connector, but DQ-INGEST-METHOD rejects them unless
    # the operator explicitly opts out (docs/v7-plan.md F4/F5).
    require_live = not args.allow_fixtures and os.environ.get("AGRILAKE_REQUIRE_LIVE", "1") != "0"
    http = HttpClient(
        mode=args.transport,
        cassette_dir=Path(args.cassette_dir) if args.cassette_dir else None,
    )
    lake = Path(args.lake) if args.lake else None
    sources = sorted(SOURCE_CONNECTORS) if args.source == "all" else [args.source]

    outcomes = [
        run_source(
            source_id, transport=args.transport, require_live=require_live, limit=args.limit,
            lake=lake, http=http, cassette_dir=http.cassette_dir,
            fail_on_drift=args.fail_on_drift, include_gaps=not args.no_gaps,
        )
        for source_id in sources
    ]

    if args.json:
        print(json.dumps(outcomes, indent=2, ensure_ascii=False, default=str))
    else:
        for out in outcomes:
            print(f"\n=== {out['source_id']} [{out.get('status', '?')}] run={out['run_id']} "
                  f"transport={out['transport']} contract={out.get('contract_version') or '—'} ===")
            discovery = out.get("discovery") or {}
            for res in discovery.get("resources", []):
                status = res.get("status", "ok")
                detail = (
                    f"rows={res.get('total_records')} licence={res.get('license_decision')} "
                    f"updated={res.get('updated_at')}"
                    if status in ("ok", "drift") else f"error={res.get('error', '')[:90]}"
                )
                print(f"  discover  {res['resource_id'][:12]}… [{status}] {detail}")
            if discovery.get("status") == "skipped":
                print(f"  discover  skipped — {discovery.get('error')}")
            collection = out.get("collection") or {}
            for res in collection.get("resources", []):
                print(f"  collect   [{res.get('status')}] records={res.get('records', 0)} "
                      f"method={res.get('method') or '—'} bronze={bool(res.get('bronze'))}")
            quality = out.get("quality") or {}
            card = quality.get("scorecard") or {}
            if card:
                print(f"  quality   pass={card.get('rows_pass')} quarantine={card.get('rows_quarantine')} "
                      f"reject={card.get('rows_reject')} warn_rate={card.get('warn_rate')} "
                      f"blocks={card.get('block_count')} promoted={quality.get('promoted')}")
                if quality.get("rule_counts"):
                    print(f"            rules={quality['rule_counts']}")
            if out.get("watermark"):
                wm = out["watermark"]
                print(f"  watermark {wm.get('watermark') or wm.get('reason')} "
                      f"(partition={wm.get('partition', '—')})")
            gaps = out.get("gaps") or {}
            if gaps:
                print(f"  gaps      detected={gaps.get('detected')} new={gaps.get('new')} "
                      f"refreshed={gaps.get('refreshed')}")
                for g in (gaps.get("top") or [])[:5]:
                    print(f"            [{g['severity']}] {g['type']} {g['key']}")
            if out.get("error"):
                print(f"  error     {out['error']}")

    failed = [o["source_id"] for o in outcomes if o.get("status") in ("failed", "drift", "blocked", "unknown_source")]
    parked = [o["source_id"] for o in outcomes if o.get("status") == "parked"]
    if failed:
        print(f"\nFAILED sources: {', '.join(failed)}", file=sys.stderr)
        return 1
    if parked:
        print(f"\nPARKED (quality gate did not promote): {', '.join(parked)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
