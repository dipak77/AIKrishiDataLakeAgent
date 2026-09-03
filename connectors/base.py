"""Plugin architecture + source registry.

Every source must be registered in ``metadata/sources/*.yaml`` before it can be
crawled (no untraceable dumps). Connectors subclass :class:`AgricultureSourceConnector`
and implement the six lifecycle methods.
"""

from __future__ import annotations

import abc
import json
import logging
from pathlib import Path
from typing import Any, ClassVar, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("agrilake.connectors")

METADATA_DIR = Path(__file__).resolve().parents[1] / "metadata" / "sources"


class SourceMetadata(BaseModel):
    source_id: str
    name: str
    country: str = "IN"
    source_type: list[str] = Field(default_factory=list)
    authority: str = "community"
    acquisition: dict[str, Any] = Field(default_factory=dict)
    domains: list[str] = Field(default_factory=list)
    license: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    #: Machine-checkable contract (schema/business key/pagination/rate limit/
    #: volume/cassettes). Validated lazily by ``pipelines.contracts.contract_for``
    #: so an invalid block fails loudly at use time, not at registry load time.
    contract: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class SourceRegistry:
    """Loads + validates every registered source from metadata/sources/."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or METADATA_DIR
        self._sources: dict[str, SourceMetadata] = {}

    def load(self) -> dict[str, SourceMetadata]:
        self._sources = {}
        if not self.directory.is_dir():
            logger.warning("No source registry directory at %s", self.directory)
            return self._sources
        for path in sorted(self.directory.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            try:
                meta = SourceMetadata.model_validate(raw)
            except ValidationError as exc:
                raise ValueError(f"Invalid source registry file {path.name}: {exc}") from exc
            if meta.source_id in self._sources:
                raise ValueError(f"Duplicate source_id {meta.source_id!r} in {path.name}")
            self._sources[meta.source_id] = meta
        return self._sources

    def get(self, source_id: str) -> SourceMetadata:
        if source_id not in self._sources:
            raise KeyError(
                f"Source {source_id!r} is not registered. Register it in "
                f"metadata/sources/{source_id}.yaml before crawling."
            )
        return self._sources[source_id]

    def all(self) -> list[SourceMetadata]:
        return list(self._sources.values())


# Module-level registry instance (populated lazily on first use).
registry = SourceRegistry()


class AgricultureSourceConnector(abc.ABC):
    """Base class for all source connectors.

    Lifecycle: discover → fetch → validate → normalize → enrich → persist.
    Subclasses may implement the methods with source-specific logic; ``run``
    orchestrates them and always returns a structured summary.
    """

    source_id: ClassVar[str] = ""
    domain: ClassVar[str] = "misc"  # silver/ domain folder

    def __init__(self) -> None:
        if not self.source_id:
            raise TypeError(f"{type(self).__name__} must set `source_id`.")
        self.limit: int = 10

    @property
    def metadata(self) -> SourceMetadata:
        if not registry._sources:  # noqa: SLF001 - intentional lazy load
            registry.load()
        return registry.get(self.source_id)

    # ── transport ──────────────────────────────────────────────────────────
    def set_transport(self, mode: str | None, cassette_dir: Path | None = None) -> None:
        """Point this connector's HTTP client at ``mode``.

        Connectors that talk HTTP expose an ``http()`` accessor returning a
        :class:`pipelines.http.HttpClient`; the orchestrator calls this so the
        ``--transport`` flag (not just the environment) decides whether a run is
        live, recorded or replayed.
        """
        factory = getattr(self, "http", None)
        if not callable(factory):
            return
        client = factory()
        if mode and getattr(client, "mode", None) != mode:
            client.mode = mode
        if cassette_dir is not None:
            client.cassette_dir = Path(cassette_dir)

    # ── lifecycle ──────────────────────────────────────────────────────────
    @abc.abstractmethod
    def discover(self) -> list[dict[str, Any]]:
        """Return a list of resource descriptors available from the source."""

    @abc.abstractmethod
    def fetch(self, resource: dict[str, Any]) -> Any:
        """Download / call the API for one resource. Returns raw payload."""

    def validate(self, raw: Any) -> None:
        """Schema/integrity checks; raise ValueError on failure."""

    @abc.abstractmethod
    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        """Map raw payload → list of canonical silver records (dicts)."""

    def enrich(
        self,
        records: list[dict[str, Any]],
        *,
        run_id: str | None = None,
        method: str | None = None,
    ) -> list[dict[str, Any]]:
        """Attach ontology links, geocoding, language, quality + run provenance."""
        from pipelines.collect import attach_provenance
        from pipelines.quality import score_record

        enriched: list[dict[str, Any]] = []
        for rec in records:
            rec.setdefault("source_id", self.source_id)
            rec.setdefault("source", self.metadata.name)
            rec.setdefault("license", self.metadata.license)
            rec.setdefault("authority", self.metadata.authority)
            # authority_level is a *level name* ("government"|"research"|…),
            # never the numeric authority_score — the old fallback leaked a
            # float into a string column and broke downstream grouping.
            rec.setdefault("authority_level", self.metadata.authority)
            rec.setdefault("ingested_at", self._now())
            rec["quality"] = score_record(rec, authority=self.metadata.authority)
            enriched.append(rec)
        if run_id and method:
            # record_hash / run_id / ingestion_method become first-class columns,
            # so a fixture row can never be mistaken for a live one downstream.
            enriched = attach_provenance(
                enriched, run_id=run_id, method=method, source_id=self.source_id
            )
        return enriched

    def persist_bronze(self, raw: Any, resource: dict[str, Any], *, method: str = "live") -> str | None:
        """Write the immutable raw payload (bronze) + manifest; return path.

        Fixture fallbacks (``raw is None``) carry no raw payload, so no bronze
        artifact is written — the silver records still record their method.
        ``method`` is the per-record ingestion method (live|replay|fixture) so
        the manifest never mislabels a replayed cassette as a live call.
        """
        from pipelines.storage import write_bronze

        if raw is None:
            return None
        try:
            payload = json.dumps(raw, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = str(raw)
        rid = resource.get("resource_id") or resource.get("id") or "default"
        artifact, _manifest = write_bronze(
            self.source_id,
            rid,
            payload,
            f"{rid}.json",
            meta={"ingestion_method": method},
        )
        return str(artifact)

    def persist(self, records: list[dict[str, Any]], resource: dict[str, Any]) -> list[str]:
        """Write silver records (jsonl) and return paths."""
        from pipelines.storage import write_jsonl, SILVER_DIR

        paths: list[str] = []
        if records:
            rid = resource.get("resource_id") or resource.get("id") or "default"
            out = write_jsonl(
                SILVER_DIR / self.domain / f"{self.source_id.lower()}_{rid}.jsonl",
                records,
            )
            paths.append(str(out))
        return paths

    # ── orchestration ──────────────────────────────────────────────────────
    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Run the full lifecycle for every discovered resource.

        Production semantics (docs/v7-plan.md §4.3):

        * one ``run_id`` per invocation, stamped onto every record;
        * ``ingestion_method`` recorded **per record** (live | replay | fixture);
        * ``require_live=True`` (or ``AGRILAKE_REQUIRE_LIVE=1``) makes an
          unreachable source **fail the run** instead of silently substituting
          bundled fixtures — fixture data must never masquerade as real data;
        * every resource produces a ``gold.ingest_run`` ledger row.
        """
        import os

        from pipelines.collect import RunLedger, RunSummary, attach_provenance, git_sha, new_run_id
        from pipelines.config import load_settings
        from pipelines.retry import retry_call
        from pipelines.storage import utcnow_iso

        settings = load_settings()
        require_live = bool(kwargs.pop("require_live", os.environ.get("AGRILAKE_REQUIRE_LIVE", "") == "1"))
        transport = kwargs.pop("transport", os.environ.get("AGRILAKE_TRANSPORT", "live"))
        cassette_dir = kwargs.pop("cassette_dir", None)
        lake = kwargs.pop("lake", None)
        self.set_transport(transport, cassette_dir)
        run_id = str(kwargs.pop("run_id", "") or new_run_id(self.source_id.lower()))
        sha = git_sha()

        resources = self.discover()
        summary: dict[str, Any] = {
            "source_id": self.source_id,
            "run_id": run_id,
            "transport": transport,
            "discovered": len(resources),
            "resources": [],
        }
        ledger = RunLedger(lake) if kwargs.pop("ledger", True) else None

        for resource in resources:
            rid = str(resource.get("resource_id") or resource.get("id") or "default")
            started = utcnow_iso()
            row = RunSummary(
                run_id=f"{run_id}:{rid}", source_id=self.source_id, resource_id=rid,
                transport=transport, git_sha=sha, started_at=started,
            )
            entry: dict[str, Any] = {"resource": resource, "status": "ok", "run_id": row.run_id}
            try:
                raw = retry_call(
                    self.fetch,
                    resource,
                    retries=settings.http_retries,
                    logger=logger,
                    on_retry=lambda info: setattr(row, "retries", row.retries + 1),
                )
                # a connector that reports how it got the data wins over the
                # requested transport (replay rows are not live rows)
                reported = resource.get("_method") or (
                    raw.get("_method") if isinstance(raw, dict) else None
                )
                method = str(reported or ("fixture" if raw is None else transport))
                if raw is None and method != "fixture":
                    method = "fixture"

                if raw is None and require_live:
                    # Fail closed: no silent fixture substitution.
                    raise RuntimeError(
                        f"source unreachable and require_live=1 — refusing to emit fixtures "
                        f"(transport={transport})"
                    )

                bronze_path = self.persist_bronze(raw, resource, method=method)
                self.validate(raw)
                records = self.normalize(raw, resource)
                row.rows_raw = len(records)
                records = self.enrich(records, run_id=row.run_id, method=method)
                paths = self.persist(records, resource)
                row.rows_pass = len(records)
                row.status = "ok"
                row.finished_at = utcnow_iso()
                entry.update(
                    {
                        "records": len(records),
                        "paths": paths,
                        "bronze": bronze_path,
                        "method": method,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - connectors must be resilient
                row.status = "failed"
                row.error = f"{type(exc).__name__}: {exc}"
                row.finished_at = utcnow_iso()
                entry.update({"status": "error", "method": "", "error": row.error})
                logger.exception("Connector %s failed on %s", self.source_id, resource)

            summary["resources"].append(entry)
            if ledger is not None:
                try:
                    ledger.record(row)
                except Exception:  # noqa: BLE001 - ledger must never break ingestion
                    logger.exception("could not write run ledger for %s", row.run_id)

        summary["status"] = (
            "empty" if not summary["resources"]
            else "ok" if all(r.get("status") == "ok" for r in summary["resources"])
            else "failed"
        )
        return summary

    @staticmethod
    def _now() -> str:
        from pipelines.storage import utcnow_iso

        return utcnow_iso()

    def fixture_records(self) -> list[dict[str, Any]]:
        """Offline fallback: return fixture records for this source."""
        return []
