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

    def enrich(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach ontology links, geocoding, language, quality."""
        from pipelines.quality import score_record

        enriched: list[dict[str, Any]] = []
        for rec in records:
            rec.setdefault("source_id", self.source_id)
            rec.setdefault("source", self.metadata.name)
            rec.setdefault("license", self.metadata.license)
            rec.setdefault("authority", self.metadata.authority)
            rec.setdefault(
                "authority_level",
                self.metadata.quality.get("authority_score", self.metadata.authority),
            )
            rec.setdefault("ingested_at", self._now())
            rec["quality"] = score_record(rec, authority=self.metadata.authority)
            enriched.append(rec)
        return enriched

    def persist_bronze(self, raw: Any, resource: dict[str, Any]) -> str | None:
        """Write the immutable raw payload (bronze) + manifest; return path.

        Fixture fallbacks (``raw is None``) carry no raw payload, so no bronze
        artifact is written — the silver records still record their method.
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
            meta={"ingestion_method": "live"},
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
        from pipelines.config import load_settings
        from pipelines.retry import retry_call

        settings = load_settings()
        resources = self.discover()
        summary: dict[str, Any] = {
            "source_id": self.source_id,
            "discovered": len(resources),
            "resources": [],
        }
        for resource in resources:
            entry: dict[str, Any] = {"resource": resource, "status": "ok"}
            try:
                raw = retry_call(
                    self.fetch,
                    resource,
                    retries=settings.http_retries,
                    logger=logger,
                )
                method = resource.get("_method") or ("fixture" if raw is None else "live")
                bronze_path = self.persist_bronze(raw, resource)
                self.validate(raw)
                records = self.normalize(raw, resource)
                records = self.enrich(records)
                paths = self.persist(records, resource)
                entry.update(
                    {
                        "records": len(records),
                        "paths": paths,
                        "bronze": bronze_path,
                        "method": method,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - connectors must be resilient
                entry.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
                logger.exception("Connector %s failed on %s", self.source_id, resource)
            summary["resources"].append(entry)
        return summary

    @staticmethod
    def _now() -> str:
        from pipelines.storage import utcnow_iso

        return utcnow_iso()

    def fixture_records(self) -> list[dict[str, Any]]:
        """Offline fallback: return fixture records for this source."""
        return []
