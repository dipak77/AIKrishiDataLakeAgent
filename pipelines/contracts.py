"""Source contracts: the machine-checkable promise a source makes about its data.

A contract is declared in ``metadata/sources/<source_id>.yaml`` under a
``contract:`` block and is the single source of truth for:

* **schema** — field types, required-ness, date formats, numeric domains
* **identity** — the business key that makes a record uniquely addressable
* **access** — which fields are filterable, how to paginate, how to go
  incremental, how fast we may call the endpoint
* **expectations** — the row-count band a healthy run lands in
* **test substrate** — which recorded cassettes prove the contract still holds

Contracts are versioned and hashed (``contract_hash``); discovery compares
hashes to detect upstream schema drift (`docs/v7-plan.md` §4.1).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ── date formats ────────────────────────────────────────────────────────────
# Declared per field, because upstream feeds disagree: Agmarknet publishes
# ``arrival_date`` as ``DD/MM/YYYY`` while every fixture in this repo used ISO
# (docs/v7-plan.md F9). Contracts make that explicit instead of accidental.
DATE_FORMATS: dict[str, str] = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "DD/MM/YYYY HH:MM:SS": "%d/%m/%Y %H:%M:%S",
    "ISO8601": "iso",
}

TYPE_CHECKS: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list": list,
    "dict": dict,
}

#: Upstream publishers use their own type vocabulary. The OGD Platform returns
#: ``keyword``/``text``/``double``/``long`` (verified in the live Agmarknet
#: metadata), so drift detection must compare *normalised* types — otherwise
#: every field looks like it changed.
UPSTREAM_TYPE_ALIASES: dict[str, str] = {
    "keyword": "str", "text": "str", "string": "str", "varchar": "str",
    "date": "date", "datetime": "datetime", "timestamp": "datetime",
    "double": "float", "float": "float", "decimal": "float", "number": "float",
    "long": "int", "integer": "int", "int": "int",
    "boolean": "bool", "bool": "bool",
}


def normalize_type(value: Any) -> str:
    """Map a publisher type name onto the contract type vocabulary."""
    key = str(value or "").strip().lower()
    return UPSTREAM_TYPE_ALIASES.get(key, key)



class FieldSpec(BaseModel):
    """One contracted field."""

    model_config = ConfigDict(extra="forbid")

    type: str = "str"
    required: bool = False
    format: Optional[str] = None          # for type=date/datetime
    min: Optional[float] = None
    max: Optional[float] = None
    enum: Optional[list[Any]] = None
    non_empty: bool = False

    def parse_date(self, value: Any) -> date | datetime | None:
        """Parse ``value`` under this field's declared format (None if absent)."""
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        key = (self.format or "ISO8601").upper()
        if key not in DATE_FORMATS:
            # A format we do not know is a contract authoring error, not a data
            # problem: fail loudly instead of silently returning None.
            raise ValueError(f"unknown date format {self.format!r}; known: {sorted(DATE_FORMATS)}")
        fmt = DATE_FORMATS[key]
        text = str(value).strip()
        if fmt == "iso":
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            return None
        return parsed.date() if self.type == "date" else parsed


class PaginationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "offset_limit"            # offset_limit | cursor | page | none
    page_size: int = 1000
    max_pages: Optional[int] = None
    offset_param: str = "offset"
    limit_param: str = "limit"


class RateLimitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rps: float = 1.0
    burst: int = 5
    honor_retry_after: bool = True


class IncrementalSpec(BaseModel):
    """How a run fetches *only what is new*.

    ``full_scan_client_filter`` is the honest default when the upstream does
    not expose a filterable incremental key — verified for Agmarknet, where
    ``arrival_date`` is absent from ``field_exposed`` and a server-side date
    filter is silently ignored (docs/v7-plan.md F10).
    """

    model_config = ConfigDict(extra="forbid")

    strategy: str = "full_scan_client_filter"   # | partition_by_field | updated_date | none
    key: Optional[str] = None
    partition_field: Optional[str] = None


class VolumeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_rows_per_run: Optional[list[int]] = None     # [min, max]
    expected_rows_per_day: Optional[list[int]] = None     # [min, max]


class SourceContract(BaseModel):
    """The full contract for one source resource."""

    model_config = ConfigDict(extra="forbid")

    version: str
    resource_id: Optional[str] = None
    #: The **canonical silver record** contract — what the lake stores, and what
    #: the data-quality refinery validates (`pipelines/dq.py`).
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    #: The **upstream payload** contract — what the source actually returns.
    #: Discovery/contract tests validate this; drift here is an upstream event.
    source_fields: dict[str, FieldSpec] = Field(default_factory=dict)
    source_date_fields: list[str] = Field(default_factory=list)
    business_key: list[str] = Field(default_factory=list)
    filterable: list[str] = Field(default_factory=list)
    pagination: PaginationSpec = Field(default_factory=PaginationSpec)
    rate_limit: RateLimitSpec = Field(default_factory=RateLimitSpec)
    incremental: IncrementalSpec = Field(default_factory=IncrementalSpec)
    volume: VolumeSpec = Field(default_factory=VolumeSpec)
    cassettes: list[str] = Field(default_factory=list)
    date_fields: list[str] = Field(default_factory=list)

    # ── identity / drift ───────────────────────────────────────────────────
    def contract_hash(self) -> str:
        """Stable hash over the schema-affecting parts of the contract."""
        canonical = {
            "source_fields": {
                name: {"type": spec.type, "format": spec.format, "required": spec.required}
                for name, spec in sorted(self.source_fields.items())
            },
            "fields": {
                name: {"type": spec.type, "format": spec.format, "required": spec.required}
                for name, spec in sorted(self.fields.items())
            },
            "filterable": sorted(self.filterable),
            "business_key": self.business_key,
        }
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def required_fields(self) -> list[str]:
        return sorted(name for name, spec in self.fields.items() if spec.required)

    def source_field_names(self) -> list[str]:
        return sorted(self.source_fields.keys())

    def check_source_row(self, row: dict[str, Any]) -> list[str]:
        """Validate one **upstream** payload row against ``source_fields``."""
        return self._check_against(row, self.source_fields, self.source_date_fields)

    def drift_from(self, discovered: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        """Diff a discovered upstream schema against ``source_fields``.

        ``discovered`` maps field name → ``{"type": ..., "exposed": bool}``.
        """
        declared = set(self.source_fields)
        found = set(discovered)
        type_changed = [
            name
            for name in sorted(declared & found)
            if discovered[name].get("type")
            and normalize_type(discovered[name]["type"]) != normalize_type(self.source_fields[name].type)
        ]
        exposed_changed = sorted(
            name for name in self.filterable if name in found and discovered[name].get("exposed") is False
        )
        return {
            "added": sorted(found - declared),
            "removed": sorted(declared - found),
            "type_changed": type_changed,
            "no_longer_filterable": exposed_changed,
        }

    def unexpected_fields(self, row: dict[str, Any]) -> list[str]:
        """Fields present in a row but absent from the contract (drift signal)."""
        return sorted(k for k in row.keys() if k not in self.fields)

    def missing_required(self, row: dict[str, Any]) -> list[str]:
        out = []
        for name in self.required_fields():
            value = row.get(name)
            if value in (None, "", [], {}):
                out.append(name)
        return out

    # ── row-level conformance ──────────────────────────────────────────────
    def check_row(self, row: dict[str, Any]) -> list[str]:
        """Return a list of human-readable conformance problems (empty = clean)."""
        return self._check_against(row, self.fields, self.date_fields)

    def _check_against(
        self,
        row: dict[str, Any],
        fields: dict[str, FieldSpec],
        date_fields: list[str],
    ) -> list[str]:
        problems: list[str] = []
        required = sorted(name for name, spec in fields.items() if spec.required)
        for name in required:
            if row.get(name) in (None, "", [], {}):
                problems.append(f"missing required field {name!r}")

        for name, spec in fields.items():
            value = row.get(name)
            if value in (None, ""):
                if spec.non_empty:
                    problems.append(f"{name} must not be empty")
                continue

            if spec.type in TYPE_CHECKS and not isinstance(value, TYPE_CHECKS[spec.type]):
                if not (spec.type == "float" and isinstance(value, (int, float)) and not isinstance(value, bool)):
                    problems.append(f"{name} expected {spec.type}, got {type(value).__name__}")
                    continue

            if spec.type in ("date", "datetime") and spec.parse_date(value) is None:
                problems.append(f"{name}={value!r} does not parse as {spec.format or 'ISO8601'}")

            if spec.type in ("int", "float") and isinstance(value, (int, float)) and not isinstance(value, bool):
                if spec.min is not None and value < spec.min:
                    problems.append(f"{name}={value} below min {spec.min}")
                if spec.max is not None and value > spec.max:
                    problems.append(f"{name}={value} above max {spec.max}")

            if spec.enum is not None and value not in spec.enum:
                problems.append(f"{name}={value!r} not in enum {spec.enum}")

        return problems

    def business_key_of(self, row: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(row.get(k) for k in self.business_key)

    def incremental_key_of(self, row: dict[str, Any]) -> str | None:
        """Normalised high-watermark value for a row (ISO dates sort correctly)."""
        key = self.incremental.key
        if not key:
            return None
        value = row.get(key)
        if value in (None, ""):
            return None
        # the incremental key usually lives on the *upstream* payload, so check
        # both schema views
        spec = self.source_fields.get(key) or self.fields.get(key)
        parsed = spec.parse_date(value) if spec and spec.type in ("date", "datetime") else None
        if parsed is None:
            return str(value)
        text = parsed.isoformat()
        # a date-typed watermark is a date: 2026-09-02, not 2026-09-02T00:00:00.
        # `parse_date` may hand back either a date or a datetime, so slice rather
        # than call .date() (which a bare date does not have).
        return text[:10] if spec.type == "date" else text


# ── loading ─────────────────────────────────────────────────────────────────


def contract_from_dict(raw: dict[str, Any]) -> SourceContract:
    """Validate a ``contract:`` block; raises ``ValueError`` with field detail."""
    try:
        return SourceContract.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid source contract: {exc}") from exc


def contract_for(source_id: str) -> SourceContract | None:
    """Load the declared contract for a registered source (None if undeclared)."""
    from connectors.base import registry

    if not registry._sources:  # noqa: SLF001 - intentional lazy load
        registry.load()
    try:
        meta = registry.get(source_id)
    except KeyError:
        return None
    raw = getattr(meta, "contract", None) or {}
    if not raw:
        return None
    return contract_from_dict(raw)


def all_contracts() -> dict[str, SourceContract]:
    """Every declared contract, keyed by source id."""
    from connectors.base import registry

    if not registry._sources:  # noqa: SLF001
        registry.load()
    out: dict[str, SourceContract] = {}
    for meta in registry.all():
        raw = getattr(meta, "contract", None) or {}
        if raw:
            out[meta.source_id] = contract_from_dict(raw)
    return out
