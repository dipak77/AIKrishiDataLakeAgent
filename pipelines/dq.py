"""The data-quality refinery: rules, classification, quarantine and promotion gates.

`pipelines/quality.py` *scores* a record. This module *gates* it. Every record
leaves :func:`classify` in exactly one of three states:

``pass``        → may be promoted to silver/gold
``quarantine``  → retained (payload + violations) for review, never promoted
``reject``      → never persisted; only the violation is logged (e.g. a record
                  carrying a national identifier, or a BLOCK-licence source)

Nothing is ever dropped silently: every non-pass decision produces
:class:`Violation` rows, and :func:`evaluate` returns a scorecard a run must
pass before promotion (:func:`gate`). See `docs/v7-plan.md` §4.5 and §7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Optional

#: PII / encoding patterns live in `pipelines/refine.py` so the quality gate and
#: the redactor can never disagree about what counts as personal data.
from pipelines.refine import (
    AADHAAR_RE as _AADHAAR_RE,
    EMAIL_RE as _EMAIL_RE,
    MOJIBAKE_RE as _MOJIBAKE_RE,
    PAN_RE as _PAN_RE,
    PHONE_RE as _PHONE_RE,
)

# ─────────────────────────── vocabulary ────────────────────────────────────


class Severity(str, Enum):
    BLOCK = "block"     # prevents promotion of the whole run
    WARN = "warn"       # tolerated up to a threshold
    INFO = "info"       # recorded, never gates


class Outcome(str, Enum):
    QUARANTINE = "quarantine"   # keep the payload for review
    REJECT = "reject"           # never persist the payload


class Status(str, Enum):
    PASS = "pass"
    QUARANTINE = "quarantine"
    REJECT = "reject"


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: Severity
    message: str
    field: str = ""
    value: str = ""
    outcome: Outcome = Outcome.QUARANTINE

    def to_row(self, record_hash: str = "", run_id: str = "", source_id: str = "") -> dict[str, Any]:
        return {
            "run_id": run_id,
            "record_hash": record_hash,
            "source_id": source_id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
            "value": str(self.value)[:200],
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True)
class Decision:
    status: Status
    violations: tuple[Violation, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status is Status.PASS

    @property
    def blocks(self) -> bool:
        return any(v.severity is Severity.BLOCK for v in self.violations)

    @property
    def warnings(self) -> int:
        return sum(1 for v in self.violations if v.severity is Severity.WARN)


# ─────────────────────────── context ───────────────────────────────────────


@dataclass
class DQContext:
    """Everything a rule may need beyond the record itself."""

    source_id: str = ""
    domain: str = ""
    contract: Any = None                       # pipelines.contracts.SourceContract | None
    run_id: str = ""
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    #: licences that may be persisted without review (substring match, case-insensitive)
    allow_licenses: tuple[str, ...] = ("godl-india", "cc0", "cc-by", "public-domain", "open")
    review_licenses: tuple[str, ...] = ("institutional", "unknown")
    #: fixture rows may not be promoted to gold in a production run
    require_live: bool = True
    #: ``{(market, commodity): (median, mad)}`` for outlier detection
    price_stats: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    #: trailing row counts for the volume-band rule
    history_row_counts: list[int] = field(default_factory=list)
    #: declared freshness horizon in days for the table-scope rule
    max_age_days: int = 45
    #: per-domain extras
    extra: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── rule base ─────────────────────────────────────


class Rule:
    """A single quality assertion.

    Subclasses set ``id``/``severity``/``scope``/``domain`` and implement
    :meth:`check` (row scope) or :meth:`check_batch` (batch scope).
    """

    id: str = "DQ-UNNAMED"
    severity: Severity = Severity.WARN
    scope: str = "row"                    # row | batch
    domain: str = ""                      # "" = all domains
    outcome: Outcome = Outcome.QUARANTINE
    description: str = ""

    def applies(self, ctx: DQContext) -> bool:
        return not self.domain or self.domain == ctx.domain

    def check(self, record: dict[str, Any], ctx: DQContext) -> Violation | None:  # pragma: no cover
        return None

    def check_batch(
        self, records: list[dict[str, Any]], ctx: DQContext
    ) -> list[tuple[int, Violation]]:  # pragma: no cover
        return []

    def violation(self, message: str, *, field: str = "", value: Any = "") -> Violation:
        return Violation(
            rule_id=self.id,
            severity=self.severity,
            message=message,
            field=field,
            value=str(value),
            outcome=self.outcome,
        )


RULES: list[Rule] = []


def register(rule: Rule) -> Rule:
    RULES.append(rule)
    return rule


def rules_for(ctx: DQContext, scope: str = "row") -> list[Rule]:
    return [r for r in RULES if r.scope == scope and r.applies(ctx)]


# ─────────────────────────── shared helpers ────────────────────────────────

_DATE_FIELDS = ("price_date", "arrival_date", "valid_from", "valid_to", "published_date", "event_date")
_TEXT_FIELDS = ("query_original", "answer_original", "answer_normalized", "query_en", "text", "recommendation")

#: Plausible agronomic ranges for soil test values (kg/ha or ppm as published).
SOIL_RANGES: dict[str, tuple[float, float]] = {
    "N": (0, 2000), "P": (0, 500), "K": (0, 2000), "S": (0, 200),
    "Zn": (0, 50), "Fe": (0, 200), "Cu": (0, 50), "Mn": (0, 100), "B": (0, 20),
    "EC": (0, 10), "OC": (0, 5),
}


def _text_of(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in _TEXT_FIELDS:
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _parse_any_date(value: Any, ctx: DQContext, field_name: str = "") -> datetime | None:
    """Parse a date using the contract format when declared, else common formats."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    contract = ctx.contract
    if contract is not None and field_name:
        spec = contract.fields.get(field_name)
        if spec is not None and spec.type in ("date", "datetime"):
            parsed = spec.parse_date(value)
            if parsed is None:
                return None
            if isinstance(parsed, datetime):
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
    return _parse_common_date(str(value))


def _parse_common_date(text: str) -> datetime | None:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt)) + 4], fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _license_text(record: dict[str, Any]) -> str:
    value = record.get("license")
    if isinstance(value, dict):
        value = value.get("type") or value.get("name") or ""
    return str(value or "").strip().lower()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ─────────────────────────── row rules ─────────────────────────────────────


class SchemaConformRule(Rule):
    id = "DQ-SCHEMA-CONFORM"
    severity = Severity.BLOCK
    description = "Row conforms to the declared source contract (types, formats, domains)."

    def check(self, record, ctx):
        if ctx.contract is None:
            return None
        problems = ctx.contract.check_row(record)
        if problems:
            return self.violation("; ".join(problems[:5]), field=problems[0].split()[0] if problems else "")
        return None


class SchemaDriftRule(Rule):
    id = "DQ-SCHEMA-DRIFT"
    severity = Severity.WARN
    description = "No fields outside the contract (upstream drift signal)."

    def check(self, record, ctx):
        if ctx.contract is None:
            return None
        unexpected = ctx.contract.unexpected_fields(record)
        # provenance/enrichment fields are ours, not the source's
        ours = {"source", "source_id", "source_url", "authority", "authority_level", "license",
                "ingested_at", "quality", "run_id", "record_hash", "ingestion_method", "country",
                "crop", "crop_canonical", "crop_scientific_name", "state_code", "district_code",
                "agroclimatic_zone", "agroecological_region", "record_id", "query_id", "chunk_id",
                "farmer_language", "season", "month", "growth_stage", "expert_verified", "unit",
                "commodity_raw", "category", "subcategory", "answer_normalized",
                "query_id", "record_id", "unit", "crop_canonical", "farmer_language"}
        unexpected = [
            f for f in unexpected
            if f not in ours and not f.endswith("_raw") and not f.startswith("pii_")
        ]
        if unexpected:
            return self.violation(f"unexpected fields vs contract: {unexpected}", field=",".join(unexpected))
        return None


class DateParseRule(Rule):
    id = "DQ-DATE-PARSE"
    severity = Severity.BLOCK
    description = "Every declared date field parses under its contract format."

    def check(self, record, ctx):
        fields = list(ctx.contract.date_fields) if ctx.contract and ctx.contract.date_fields else list(_DATE_FIELDS)
        for name in fields:
            value = record.get(name)
            if value in (None, ""):
                continue
            if _parse_any_date(value, ctx, name) is None:
                return self.violation(f"{name}={value!r} is not a parseable date", field=name, value=value)
        return None


class DateNotFutureRule(Rule):
    id = "DQ-DATE-NOT-FUTURE"
    severity = Severity.BLOCK
    description = "Event dates are not in the future (beyond a 1-day clock tolerance)."

    def check(self, record, ctx):
        for name in _DATE_FIELDS:
            parsed = _parse_any_date(record.get(name), ctx, name)
            if parsed is None:
                continue
            if parsed > ctx.now + timedelta(days=1):
                return self.violation(
                    f"{name}={parsed.date().isoformat()} is in the future", field=name, value=parsed.date()
                )
        return None


class PriceTriangleRule(Rule):
    id = "DQ-PRICE-TRIANGLE"
    severity = Severity.BLOCK
    domain = "market"
    description = "0 < min ≤ modal ≤ max for a mandi price observation."

    def check(self, record, ctx):
        lo, modal, hi = (_num(record.get(k)) for k in ("min_price", "modal_price", "max_price"))
        present = [v for v in (lo, modal, hi) if v is not None]
        if not present:
            return None
        if any(v is not None and v <= 0 for v in present):
            return self.violation(f"non-positive price in {record.get('record_id')}", field="min_price", value=present)
        if lo is not None and modal is not None and lo > modal:
            return self.violation(f"min_price {lo} > modal_price {modal}", field="min_price", value=lo)
        if modal is not None and hi is not None and modal > hi:
            return self.violation(f"modal_price {modal} > max_price {hi}", field="max_price", value=hi)
        return None


class PriceOutlierRule(Rule):
    id = "DQ-PRICE-OUTLIER-MAD"
    severity = Severity.WARN
    domain = "market"
    description = "Modal price within 5 MAD of the market×commodity baseline."

    def check(self, record, ctx):
        modal = _num(record.get("modal_price"))
        if modal is None or not ctx.price_stats:
            return None
        key = (str(record.get("market") or ""), str(record.get("commodity_raw") or record.get("crop") or ""))
        stat = ctx.price_stats.get(key)
        if not stat:
            return None
        median, mad = stat
        if mad <= 0:
            return None
        z = abs(modal - median) / mad
        if z > 5:
            return self.violation(
                f"modal_price {modal} is {z:.1f} MAD from the {median} baseline for {key}",
                field="modal_price", value=modal,
            )
        return None


class CropResolvedRule(Rule):
    id = "DQ-CROP-RESOLVED"
    severity = Severity.INFO
    description = (
        "The raw commodity/crop string resolved to a canonical crop. INFO by "
        "design: an unresolved mention is a *gap signal* (it feeds "
        "gold.unresolved_mention / the gap register), not a data defect — a new "
        "mandi vocabulary string is expected on the first day of live ingestion."
    )

    def check(self, record, ctx):
        raw = record.get("commodity_raw") or record.get("crop_canonical")
        if raw and not record.get("crop"):
            return self.violation(
                f"crop mention {raw!r} did not resolve to dim_crop", field="crop", value=raw
            )
        return None


class GeoResolvedRule(Rule):
    id = "DQ-GEO-RESOLVED"
    severity = Severity.WARN
    description = "State/district resolved to canonical geography codes."

    def check(self, record, ctx):
        if record.get("district") and not record.get("district_code") and not record.get("agroclimatic_zone"):
            from pipelines.geocode import resolve_geography

            geo = resolve_geography(record.get("state"), record.get("district"))
            if geo and not geo.get("district_code"):
                return self.violation(
                    f"district {record.get('district')!r} unresolved in {record.get('state')!r}",
                    field="district", value=record.get("district"),
                )
        return None


class GeoExistsRule(Rule):
    id = "DQ-GEO-EXISTS"
    severity = Severity.BLOCK
    description = "A named state must exist in dim_geography."

    def check(self, record, ctx):
        state = record.get("state")
        if not state:
            return None
        from pipelines.geocode import resolve_geography

        if resolve_geography(state, record.get("district")) is None:
            return self.violation(f"state {state!r} not in dim_geography", field="state", value=state)
        return None


class MarketKnownRule(Rule):
    id = "DQ-MARKET-KNOWN"
    severity = Severity.INFO
    domain = "market"
    description = (
        "Market appears in dim_market, else it is a registration candidate. "
        "INFO: discovering new markets is how dim_market grows (12 rows today "
        "vs ~1,800 in the live feed)."
    )

    def check(self, record, ctx):
        market = record.get("market")
        if not market:
            return None
        known = ctx.extra.get("known_markets")
        if known is None:
            from domain.seed_data import MARKETS

            known = {str(m["name"]).strip().lower() for m in MARKETS}
            ctx.extra["known_markets"] = known
        if str(market).strip().lower() not in known:
            return self.violation(f"market {market!r} not in dim_market", field="market", value=market)
        return None


class SourceUrlRule(Rule):
    id = "DQ-SOURCE-URL"
    severity = Severity.BLOCK
    description = "Every record carries a resolvable source URL."

    def check(self, record, ctx):
        url = record.get("source_url")
        if not url or not str(url).startswith(("http://", "https://")):
            return self.violation("missing or non-HTTP source_url", field="source_url", value=url or "")
        return None


class LicenseAllowRule(Rule):
    id = "DQ-LICENSE-ALLOW"
    severity = Severity.BLOCK
    description = "Licence is in the ALLOW set; REVIEW licences quarantine; BLOCK rejects."

    def check(self, record, ctx):
        text = _license_text(record)
        if not text:
            return self.violation("no licence declared", field="license", value="")
        if any(tok in text for tok in ctx.allow_licenses):
            return None
        if any(tok in text for tok in ctx.review_licenses):
            return self.violation(f"licence {text!r} needs review before promotion", field="license", value=text)
        return Violation(
            rule_id=self.id, severity=Severity.BLOCK, outcome=Outcome.REJECT,
            message=f"licence {text!r} is not permitted for ingestion", field="license", value=text,
        )


class IngestionMethodRule(Rule):
    id = "DQ-INGEST-METHOD"
    severity = Severity.BLOCK
    description = "A production run promotes only live/replay rows, never fixtures."

    def check(self, record, ctx):
        if not ctx.require_live:
            return None
        method = record.get("ingestion_method")
        if method == "fixture":
            return Violation(
                rule_id=self.id, severity=Severity.BLOCK, outcome=Outcome.REJECT,
                message="fixture-sourced record may not be promoted in a production run",
                field="ingestion_method", value="fixture",
            )
        return None


class PiiRedactRule(Rule):
    id = "DQ-PII-REDACT"
    severity = Severity.WARN
    description = "No raw phone number or e-mail address survives in free text."

    def check(self, record, ctx):
        text = _text_of(record)
        if not text:
            return None
        found = []
        if _PHONE_RE.search(text):
            found.append("phone")
        if _EMAIL_RE.search(text):
            found.append("email")
        if found:
            return self.violation(f"unredacted PII ({', '.join(found)})", field="text", value=",".join(found))
        return None


class PiiIdentifierRule(Rule):
    id = "DQ-PII-IDENTIFIER"
    severity = Severity.BLOCK
    outcome = Outcome.REJECT
    description = "National identifiers (Aadhaar/PAN) are never persisted."

    def check(self, record, ctx):
        text = _text_of(record)
        if not text:
            return None
        if _AADHAAR_RE.search(text):
            return self.violation("Aadhaar-like 12-digit identifier present", field="text", value="aadhaar")
        if _PAN_RE.search(text):
            return self.violation("PAN-like identifier present", field="text", value="pan")
        return None


class SoilPhRule(Rule):
    id = "DQ-SOIL-PH"
    severity = Severity.BLOCK
    domain = "soil"
    description = "Soil pH is within 0–14."

    def check(self, record, ctx):
        ph = _num((record.get("soil_test") or {}).get("pH"))
        if ph is not None and not 0 <= ph <= 14:
            return self.violation(f"pH {ph} outside 0–14", field="soil_test.pH", value=ph)
        return None


class SoilRangeRule(Rule):
    id = "DQ-SOIL-RANGE"
    severity = Severity.WARN
    domain = "soil"
    description = "Soil test values inside agronomic ranges."

    def check(self, record, ctx):
        test = record.get("soil_test") or {}
        for param, (lo, hi) in SOIL_RANGES.items():
            value = _num(test.get(param))
            if value is not None and not lo <= value <= hi:
                return self.violation(
                    f"{param}={value} outside plausible range {lo}–{hi}", field=f"soil_test.{param}", value=value
                )
        return None


class MojibakeRule(Rule):
    id = "DQ-MOJIBAKE"
    severity = Severity.BLOCK
    description = "No encoding damage (replacement chars / double-encoded UTF-8)."

    def check(self, record, ctx):
        text = _text_of(record)
        if text and _MOJIBAKE_RE.search(text):
            return self.violation("encoding damage detected in text", field="text", value="mojibake")
        return None


class LanguageConsistentRule(Rule):
    id = "DQ-LANG-CONSISTENT"
    severity = Severity.WARN
    description = "Declared language agrees with the detected script/language."

    def check(self, record, ctx):
        declared = record.get("farmer_language")
        text = record.get("query_original") or record.get("answer_original")
        if not declared or not isinstance(text, str) or not text.strip():
            return None
        from pipelines.language import detect_language

        detected = detect_language(text).get("language")
        # hi/mr share Devanagari and are routinely interchangeable at detection time
        equivalent = {"hi", "mr"}
        if detected != declared and not {detected, declared} <= equivalent:
            return self.violation(
                f"declared {declared!r} but detected {detected!r}", field="farmer_language", value=declared
            )
        return None


class CalendarConsistentRule(Rule):
    id = "DQ-CALENDAR-CONSISTENT"
    severity = Severity.WARN
    description = "A dated observation's month is plausible for the crop's calendar."

    def check(self, record, ctx):
        crop, season = record.get("crop"), record.get("season")
        if not crop or not season:
            return None
        parsed = _parse_any_date(record.get("price_date") or record.get("valid_from"), ctx, "price_date")
        if parsed is None:
            return None
        from domain.seed_data import CROP_CALENDAR, CROP_CALENDAR_TOP20, SEASONS

        season_id = next(
            (s["season_id"] for s in SEASONS if s["season_id"].endswith(str(season).upper())), None
        )
        if not season_id:
            return None
        rows = [c for c in CROP_CALENDAR + CROP_CALENDAR_TOP20 if c["crop_id"] == crop and c["season_id"] == season_id]
        if not rows:
            return None
        months: set[int] = set()
        for row in rows:
            m = int(row["month_start"])
            while True:
                months.add(m)
                if m == int(row["month_end"]):
                    break
                m = m % 12 + 1
        if parsed.month not in months:
            return self.violation(
                f"month {parsed.month} outside the {crop}/{season} calendar window {sorted(months)}",
                field="season", value=season,
            )
        return None


for rule in (
    SchemaConformRule(), SchemaDriftRule(), DateParseRule(), DateNotFutureRule(),
    PriceTriangleRule(), PriceOutlierRule(), CropResolvedRule(), GeoResolvedRule(),
    GeoExistsRule(), MarketKnownRule(), SourceUrlRule(), LicenseAllowRule(),
    IngestionMethodRule(), PiiRedactRule(), PiiIdentifierRule(), SoilPhRule(),
    SoilRangeRule(), MojibakeRule(), LanguageConsistentRule(), CalendarConsistentRule(),
):
    register(rule)


# ─────────────────────────── batch rules ───────────────────────────────────


class BusinessKeyUniqueRule(Rule):
    id = "DQ-BUSINESS-KEY-UNIQUE"
    severity = Severity.BLOCK
    scope = "batch"
    description = "Business key is unique; identical rows are duplicates, differing rows are conflicts."

    def check_batch(self, records, ctx):
        key_fields = list(ctx.contract.business_key) if ctx.contract and ctx.contract.business_key else []
        if not key_fields:
            return []
        seen: dict[tuple[Any, ...], str] = {}
        out: list[tuple[int, Violation]] = []
        for idx, rec in enumerate(records):
            key = tuple(rec.get(k) for k in key_fields)
            if any(v is None for v in key):
                continue
            digest = rec.get("record_hash") or ""
            if key in seen and seen[key] != digest:
                out.append((idx, self.violation(
                    f"conflicting record for business key {key}", field=",".join(key_fields), value=key
                )))
            else:
                seen.setdefault(key, digest)
        return out


class VolumeBandRule(Rule):
    id = "DQ-VOLUME-BAND"
    severity = Severity.WARN
    scope = "batch"
    description = "Run row count inside the contracted band (or the trailing-run MAD envelope)."

    def check_batch(self, records, ctx):
        n = len(records)
        band = ctx.contract.volume.expected_rows_per_run if ctx.contract else None
        if band and len(band) == 2:
            lo, hi = int(band[0]), int(band[1])
            if not lo <= n <= hi:
                severity = Severity.BLOCK if (n < lo * 0.5 or n > hi * 2) else self.severity
                return [(0, Violation(
                    rule_id=self.id, severity=severity, outcome=Outcome.QUARANTINE,
                    message=f"row count {n} outside contracted band [{lo}, {hi}]",
                    field="_batch", value=n,
                ))]
            return []
        history = [h for h in (ctx.history_row_counts or []) if h > 0]
        if len(history) < 5:
            return []
        median = sorted(history)[len(history) // 2]
        mad = sorted(abs(h - median) for h in history)[len(history) // 2] or 1
        if abs(n - median) > 6 * mad:
            return [(0, Violation(
                rule_id=self.id, severity=Severity.BLOCK, outcome=Outcome.QUARANTINE,
                message=f"row count {n} is >6 MAD from the trailing median {median}", field="_batch", value=n,
            ))]
        return []


class FreshnessRule(Rule):
    id = "DQ-FRESHNESS"
    severity = Severity.WARN
    scope = "batch"
    description = "The newest event in the batch is within the source's freshness horizon."

    def check_batch(self, records, ctx):
        newest = None
        for rec in records:
            for name in ("price_date", "arrival_date", "valid_from", "published_date", "event_date"):
                parsed = _parse_any_date(rec.get(name), ctx, name)
                if parsed and (newest is None or parsed > newest):
                    newest = parsed
        if newest is None:
            return []
        age_days = (ctx.now - newest).days
        if age_days > ctx.max_age_days:
            return [(0, self.violation(
                f"newest event is {age_days} days old (> {ctx.max_age_days})",
                field="_batch", value=newest.date(),
            ))]
        return []


for rule in (BusinessKeyUniqueRule(), VolumeBandRule(), FreshnessRule()):
    register(rule)


# ─────────────────────────── engine ────────────────────────────────────────


def classify(record: dict[str, Any], ctx: DQContext) -> Decision:
    """Classify one record: ``pass`` | ``quarantine`` | ``reject``."""
    violations: list[Violation] = []
    for rule in rules_for(ctx, scope="row"):
        try:
            found = rule.check(record, ctx)
        except Exception as exc:  # noqa: BLE001 - a broken rule must not sink a run
            found = Violation(
                rule_id=rule.id, severity=Severity.WARN,
                message=f"rule raised {type(exc).__name__}: {exc}", field="_rule",
            )
        if found is not None:
            violations.append(found)

    if any(v.outcome is Outcome.REJECT for v in violations):
        return Decision(Status.REJECT, tuple(violations))
    if any(v.outcome is Outcome.QUARANTINE and v.severity is Severity.BLOCK for v in violations):
        return Decision(Status.QUARANTINE, tuple(violations))
    return Decision(Status.PASS, tuple(violations))


@dataclass
class DQReport:
    """Result of gating one batch, with everything needed to persist + audit."""

    run_id: str
    source_id: str
    domain: str
    total: int
    passed: list[dict[str, Any]] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    rule_counts: dict[str, int] = field(default_factory=dict)
    promoted: bool = False
    batch_violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def warn_rate(self) -> float:
        if not self.total:
            return 0.0
        warned = sum(1 for r in self.passed if r.get("_dq_warnings"))
        return round(warned / self.total, 4)

    def scorecard(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "domain": self.domain,
            "rows_total": self.total,
            "rows_pass": len(self.passed),
            "rows_quarantine": len(self.quarantined),
            "rows_reject": len(self.rejected),
            "block_count": sum(1 for v in self.violations if v["severity"] == Severity.BLOCK.value),
            "warn_rate": self.warn_rate,
            "rule_counts": dict(sorted(self.rule_counts.items())),
            "promoted": self.promoted,
        }


def evaluate(
    records: list[dict[str, Any]],
    ctx: DQContext,
    *,
    warn_max: float = 0.02,
) -> DQReport:
    """Classify a batch, apply batch-scope rules, and decide promotion."""
    report = DQReport(run_id=ctx.run_id, source_id=ctx.source_id, domain=ctx.domain, total=len(records))

    for record in records:
        decision = classify(record, ctx)
        row = dict(record)
        row["_dq_status"] = decision.status.value
        row["_dq_warnings"] = decision.warnings
        if decision.violations:
            row["_dq_violations"] = [
                {"rule_id": v.rule_id, "severity": v.severity.value, "message": v.message, "field": v.field}
                for v in decision.violations
            ]
            for v in decision.violations:
                report.violations.append(v.to_row(record.get("record_hash", ""), ctx.run_id, ctx.source_id))
                report.rule_counts[v.rule_id] = report.rule_counts.get(v.rule_id, 0) + 1
        if decision.status is Status.PASS:
            report.passed.append(row)
        elif decision.status is Status.QUARANTINE:
            report.quarantined.append(row)
        else:
            # never persist a rejected payload — only its violation rows
            report.rejected.append({"record_hash": record.get("record_hash", ""), "_dq_status": "reject"})

    for rule in rules_for(ctx, scope="batch"):
        try:
            findings = rule.check_batch(records, ctx)
        except Exception as exc:  # noqa: BLE001
            findings = [(0, Violation(rule.id, Severity.WARN, f"rule raised {type(exc).__name__}: {exc}"))]
        for idx, violation in findings:
            target_hash = records[idx].get("record_hash", "") if 0 <= idx < len(records) else ""
            entry = violation.to_row(target_hash, ctx.run_id, ctx.source_id)
            report.batch_violations.append(entry)
            report.violations.append(entry)
            report.rule_counts[violation.rule_id] = report.rule_counts.get(violation.rule_id, 0) + 1
            if violation.severity is Severity.BLOCK and target_hash:
                # A row-level conflict demotes that specific row out of the
                # promote set. A batch-wide block (volume/freshness) has no
                # target_hash and instead fails the gate via block_count.
                demote = next(
                    (r for r in report.passed if r.get("record_hash") == target_hash), None
                )
                if demote is not None:
                    report.passed.remove(demote)
                    demote["_dq_status"] = Status.QUARANTINE.value
                    demote.setdefault("_dq_violations", []).append(
                        {"rule_id": violation.rule_id, "severity": violation.severity.value,
                         "message": violation.message, "field": violation.field}
                    )
                    report.quarantined.append(demote)

    scorecard = report.scorecard()
    report.promoted = gate(scorecard, warn_max=warn_max)
    return report


def gate(scorecard: dict[str, Any], *, warn_max: float = 0.02) -> bool:
    """Promote a run only with zero blocking violations and a warn rate under budget."""
    return int(scorecard.get("block_count", 0)) == 0 and float(scorecard.get("warn_rate", 1.0)) <= warn_max


# ─────────────────────────── persistence ───────────────────────────────────

VIOLATION_DDL = """
CREATE TABLE IF NOT EXISTS gold.dq_violation (
    run_id VARCHAR, record_hash VARCHAR, source_id VARCHAR, rule_id VARCHAR,
    severity VARCHAR, field VARCHAR, message VARCHAR, value VARCHAR,
    outcome VARCHAR, detected_at VARCHAR
)
"""

QUARANTINE_DDL = """
CREATE TABLE IF NOT EXISTS gold.quarantine (
    record_hash VARCHAR, run_id VARCHAR, source_id VARCHAR, domain VARCHAR,
    payload VARCHAR, violations VARCHAR, quarantined_at VARCHAR,
    status VARCHAR, resolved_by VARCHAR, resolved_at VARCHAR
)
"""

SCORECARD_DDL = """
CREATE TABLE IF NOT EXISTS gold.dq_scorecard (
    run_id VARCHAR, source_id VARCHAR, rows_total INTEGER, rows_pass INTEGER,
    rows_quarantine INTEGER, rows_reject INTEGER, block_count INTEGER,
    warn_rate DOUBLE, rule_counts VARCHAR, promoted BOOLEAN, built_at VARCHAR
)
"""


def persist_report(report: DQReport, lake: Any = None) -> dict[str, int]:
    """Write violations, quarantined payloads and the scorecard into the lake."""
    import json as _json

    from pipelines.collect import _connect
    from pipelines.storage import utcnow_iso

    now = utcnow_iso()
    con = _connect(lake)
    try:
        con.execute(VIOLATION_DDL)
        con.execute(QUARANTINE_DDL)
        con.execute(SCORECARD_DDL)

        for row in report.violations:
            con.execute(
                "INSERT INTO gold.dq_violation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [row["run_id"], row["record_hash"], row["source_id"], row["rule_id"],
                 row["severity"], row["field"], row["message"], row["value"],
                 row["outcome"], now],
            )
        for row in report.quarantined:
            payload = {k: v for k, v in row.items() if not k.startswith("_dq")}
            con.execute(
                "INSERT INTO gold.quarantine VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [row.get("record_hash", ""), report.run_id, report.source_id, report.domain,
                 _json.dumps(payload, ensure_ascii=False, default=str),
                 _json.dumps(row.get("_dq_violations", []), ensure_ascii=False, default=str),
                 now, "open", None, None],
            )
        card = report.scorecard()
        con.execute(
            "DELETE FROM gold.dq_scorecard WHERE run_id = ?", [report.run_id]
        )
        con.execute(
            "INSERT INTO gold.dq_scorecard VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [card["run_id"], card["source_id"], card["rows_total"], card["rows_pass"],
             card["rows_quarantine"], card["rows_reject"], card["block_count"],
             card["warn_rate"], _json.dumps(card["rule_counts"], sort_keys=True),
             card["promoted"], now],
        )
        return {
            "violations": len(report.violations),
            "quarantined": len(report.quarantined),
            "scorecards": 1,
        }
    finally:
        con.close()
