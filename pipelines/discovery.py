"""Source discovery: find datasets, read their real schema, detect drift.

Discovery is what turns "we scraped a URL once" into a governed supply chain
(`docs/v7-plan.md` §4.1). For the OGD Platform (data.gov.in) a single
``limit=1`` call to the resource endpoint returns everything needed:

* ``field`` — the real field ids, display names and types
* ``field_exposed`` — the subset that can actually be used in ``filters[...]``
* ``total`` — current row count
* ``updated_date`` — when the publisher last refreshed it

Those four facts drive the contract hash, the incremental strategy and the
volume band, and their change over time *is* the drift signal. Verified against
the live Agmarknet resource on 2026-09-02 (17,800 rows, ``updated_date``
2026-09-02T17:01:08Z).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from pipelines.contracts import SourceContract, contract_for
from pipelines.http import HttpClient, redact_url

logger = logging.getLogger("agrilake.discovery")

DATA_GOV_BASE = "https://api.data.gov.in"
DISCOVERED_DIR = Path(__file__).resolve().parents[1] / "metadata" / "discovered"


# ─────────────────────────── result shape ──────────────────────────────────


@dataclass
class DiscoveredResource:
    """One dataset as the publisher currently exposes it."""

    source_id: str
    resource_id: str
    title: str = ""
    org: list[str] = field(default_factory=list)
    sector: list[str] = field(default_factory=list)
    license_declared: str = ""
    license_decision: str = "REVIEW"
    field_schema: dict[str, dict[str, Any]] = field(default_factory=dict)
    field_exposed: list[str] = field(default_factory=list)
    total_records: int = 0
    upstream_updated_at: str = ""
    discovered_at: str = ""
    discovery_method: str = "resource_meta"
    contract_version: str = ""
    contract_hash: str = ""
    #: set when the live schema no longer matches the declared contract
    drift: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_drift(self) -> bool:
        return any(self.drift.values())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────── OGD discovery ─────────────────────────────────


class DataGovDiscovery:
    """Discover data.gov.in resources via their own metadata payload."""

    def __init__(self, http: HttpClient | None = None, *, base_url: str = DATA_GOV_BASE, api_key: str = "") -> None:
        self.http = http or HttpClient()
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key

    def api_key(self) -> str:
        if self._api_key:
            return self._api_key
        from connectors.government.data_gov import DataGovConnector

        return DataGovConnector().api_key()

    def discover_resource(self, source_id: str, resource_id: str) -> DiscoveredResource:
        """Read one resource's live schema + counters (``limit=1``)."""
        from pipelines.storage import utcnow_iso

        url = f"{self.base_url}/resource/{resource_id}"
        # same pagination shape as DataGovConnector.fetch_resource, so a single
        # cassette can serve both discovery and collection in replay mode
        payload = self.http.get_json(
            url,
            params={"api-key": self.api_key(), "format": "json", "offset": 0, "limit": 1},
        )
        if not isinstance(payload, dict):
            raise ValueError(f"{redact_url(url)}: unexpected payload type {type(payload).__name__}")
        if payload.get("status") == "error":
            raise LookupError(
                f"resource {resource_id} is not available: {payload.get('message')!r} "
                "(it may have been retired — re-discover and update the registry)"
            )

        schema: dict[str, dict[str, Any]] = {}
        exposed_names = {str(f.get("name")) for f in (payload.get("field_exposed") or [])}
        for spec in payload.get("field") or []:
            name = str(spec.get("id") or spec.get("name") or "")
            if not name:
                continue
            schema[name] = {
                "name": spec.get("name"),
                "type": spec.get("type"),
                "exposed": bool(spec.get("name") in exposed_names),
            }

        contract = contract_for(source_id)
        discovered = DiscoveredResource(
            source_id=source_id,
            resource_id=resource_id,
            title=str(payload.get("title") or payload.get("desc") or ""),
            org=list(payload.get("org") or []),
            sector=list(payload.get("sector") or []),
            field_schema=schema,
            field_exposed=sorted(n for n, meta in schema.items() if meta["exposed"]),
            total_records=int(payload.get("total") or 0),
            upstream_updated_at=str(payload.get("updated_date") or ""),
            discovered_at=utcnow_iso(),
            discovery_method="resource_meta",
            contract_version=contract.version if contract else "",
            contract_hash=contract.contract_hash() if contract else "",
        )
        discovered.license_declared, discovered.license_decision = self._license(source_id)
        if contract and contract.source_fields:
            discovered.drift = contract.drift_from(schema)
        return discovered

    @staticmethod
    def _license(source_id: str) -> tuple[str, str]:
        """Resolve the declared licence and its governance decision."""
        from connectors.base import registry
        from connectors.web.license_checker import LicenseChecker, LicenseClass

        if not registry._sources:  # noqa: SLF001 - lazy load
            registry.load()
        declared = ""
        try:
            declared = str((registry.get(source_id).license or {}).get("type") or "")
        except KeyError:
            pass
        decision = LicenseChecker().classify("", declared or None).decision
        names = {LicenseClass.ALLOW: "ALLOW", LicenseClass.REVIEW: "REVIEW", LicenseClass.BLOCK: "BLOCK"}
        return declared, names.get(decision, "REVIEW")


# ─────────────────────────── persistence ───────────────────────────────────


def save_discovered(resources: list[DiscoveredResource], directory: Path | None = None) -> list[Path]:
    """Write one JSON file per source under ``metadata/discovered/``."""
    directory = Path(directory or DISCOVERED_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    from pipelines.storage import write_json

    by_source: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        by_source.setdefault(resource.source_id, []).append(resource.to_dict())
    return [
        write_json(directory / f"{source_id.lower()}.json", {"resources": rows})
        for source_id, rows in sorted(by_source.items())
    ]


def load_discovered(source_id: str, directory: Path | None = None) -> list[dict[str, Any]]:
    """Read the last discovery snapshot for a source ([] if never discovered)."""
    path = Path(directory or DISCOVERED_DIR) / f"{source_id.lower()}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("resources") or [])


# ─────────────────────────── lake table ────────────────────────────────────

CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS gold.source_catalog (
    source_id VARCHAR, resource_id VARCHAR, title VARCHAR, org VARCHAR,
    sector VARCHAR, license_declared VARCHAR, license_decision VARCHAR,
    field_schema VARCHAR, field_exposed VARCHAR, total_records BIGINT,
    upstream_updated_at VARCHAR, discovered_at VARCHAR, discovery_method VARCHAR,
    contract_version VARCHAR, contract_hash VARCHAR, has_drift BOOLEAN,
    drift VARCHAR,
    PRIMARY KEY (source_id, resource_id)
)
"""


def upsert_catalog(resources: list[DiscoveredResource], lake: Any = None) -> int:
    """Upsert discovery results into ``gold.source_catalog``; returns row count."""
    from pipelines.collect import _connect

    if not resources:
        return 0
    con = _connect(lake)
    try:
        con.execute(CATALOG_DDL)
        for resource in resources:
            con.execute(
                "DELETE FROM gold.source_catalog WHERE source_id = ? AND resource_id = ?",
                [resource.source_id, resource.resource_id],
            )
            con.execute(
                "INSERT INTO gold.source_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    resource.source_id, resource.resource_id, resource.title,
                    json.dumps(resource.org, ensure_ascii=False),
                    json.dumps(resource.sector, ensure_ascii=False),
                    resource.license_declared, resource.license_decision,
                    json.dumps(resource.field_schema, ensure_ascii=False, sort_keys=True),
                    json.dumps(resource.field_exposed, ensure_ascii=False),
                    resource.total_records, resource.upstream_updated_at,
                    resource.discovered_at, resource.discovery_method,
                    resource.contract_version, resource.contract_hash,
                    resource.has_drift,
                    json.dumps(resource.drift, ensure_ascii=False, sort_keys=True),
                ],
            )
        return len(resources)
    finally:
        con.close()


def catalog_rows(lake: Any = None) -> list[dict[str, Any]]:
    """Read ``gold.source_catalog`` ([] when the table does not exist yet)."""
    from pipelines.storage import LAKE_DIR, ensure_dir, get_read_connection

    path = Path(lake) if lake else (ensure_dir(LAKE_DIR) / "agrilake.duckdb")
    if not path.is_file():
        return []
    con = get_read_connection(path)
    has = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='gold' AND table_name='source_catalog'"
    ).fetchone()[0]
    if not has:
        return []
    cur = con.execute("SELECT * FROM gold.source_catalog ORDER BY source_id")
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
