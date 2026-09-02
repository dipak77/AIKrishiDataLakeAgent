"""Refinement: canonicalize raw source values into lake-standard form.

Pure, dependency-light transforms that run between the data-quality gate and
gold (`docs/v7-plan.md` §4.6). Each function is total (never raises on bad
input) and returns enough information to *report* what it could not convert —
silently coercing a bad date into ``None`` is how `dd/mm/yyyy` mandi data ended
up with a broken season signal.

Conventions enforced here:

* **Dates** — ISO-8601 (``YYYY-MM-DD``) in every silver/gold field; the raw
  value is preserved in a ``*_raw`` sibling so nothing is lost.
* **Units** — always stored explicitly, with helpers to convert between the
  units Indian sources actually publish (INR/quintal, hg/ha, acres).
* **PII** — redacted before a record can be promoted; national identifiers are
  detected so the caller can reject rather than store them.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Iterable

# ─────────────────────────── dates ─────────────────────────────────────────

DATE_FORMATS: dict[str, str] = {
    "ISO8601": "%Y-%m-%d",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "DD/MM/YYYY HH:MM:SS": "%d/%m/%Y %H:%M:%S",
    "YYYY-MM-DDTHH:MM:SS": "%Y-%m-%dT%H:%M:%S",
}

#: Tried in order when a source declares no format. Deliberately conservative:
#: ambiguous numeric forms are *not* guessed.
_FALLBACK_FORMATS = ("ISO8601", "DD/MM/YYYY", "YYYY/MM/DD", "DD-MM-YYYY")


def parse_date(value: Any, fmt: str | None = None) -> date | datetime | None:
    """Parse ``value`` under ``fmt`` (or the fallback list). ``None`` if unparseable."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None

    candidates: list[str] = []
    if fmt:
        key = fmt.upper()
        if key not in DATE_FORMATS:
            raise ValueError(f"unknown date format {fmt!r}; known: {sorted(DATE_FORMATS)}")
        candidates.append(key)
    else:
        candidates.extend(_FALLBACK_FORMATS)

    for key in candidates:
        if key == "ISO8601":
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                continue
        try:
            return datetime.strptime(text, DATE_FORMATS[key])
        except ValueError:
            continue
    return None


def to_iso(value: Any, fmt: str | None = None) -> str | None:
    """Canonical ``YYYY-MM-DD`` (or full ISO timestamp for datetimes)."""
    parsed = parse_date(value, fmt)
    if parsed is None:
        return None
    if isinstance(parsed, datetime):
        # keep the timestamp only when it carries a time component
        if (parsed.hour, parsed.minute, parsed.second) == (0, 0, 0):
            return parsed.date().isoformat()
        return parsed.isoformat()
    return parsed.isoformat()


def canonicalize_dates(
    record: dict[str, Any],
    mapping: dict[str, str],
    *,
    keep_raw: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """Rewrite the mapped fields to ISO, preserving originals in ``<field>_raw``.

    Returns ``(record, problems)`` where ``problems`` lists fields that could
    not be parsed — the caller decides whether that blocks promotion.
    """
    out = dict(record)
    problems: list[str] = []
    for field_name, fmt in mapping.items():
        value = out.get(field_name)
        if value in (None, ""):
            continue
        iso = to_iso(value, fmt)
        if iso is None:
            problems.append(f"{field_name}={value!r} does not parse as {fmt or 'a known date format'}")
            continue
        if keep_raw and str(value) != iso:
            out[f"{field_name}_raw"] = value
        out[field_name] = iso
    return out, problems


# ─────────────────────────── units ─────────────────────────────────────────

QUINTAL_PER_TONNE = 10.0
ACRE_PER_HECTARE = 2.471053814671653
HG_PER_KG = 10.0


def price_quintal_to_tonne(value: float | None) -> float | None:
    """INR/quintal → INR/tonne."""
    return None if value is None else round(float(value) * QUINTAL_PER_TONNE, 2)


def price_tonne_to_quintal(value: float | None) -> float | None:
    return None if value is None else round(float(value) / QUINTAL_PER_TONNE, 2)


def yield_hg_ha_to_kg_ha(value: float | None) -> float | None:
    """FAOSTAT publishes yield in hg/ha; the lake standard is kg/ha."""
    return None if value is None else round(float(value) / HG_PER_KG, 3)


def acres_to_hectares(value: float | None) -> float | None:
    return None if value is None else round(float(value) / ACRE_PER_HECTARE, 4)


def normalize_price_record(record: dict[str, Any], *, target_unit: str = "INR/quintal") -> dict[str, Any]:
    """Ensure a mandi record carries an explicit, consistent price unit."""
    out = dict(record)
    unit = str(out.get("unit") or target_unit)
    keys = ("min_price", "modal_price", "max_price")
    if unit.lower() in ("inr/tonne", "rs/tonne") and target_unit.lower() == "inr/quintal":
        for key in keys:
            if out.get(key) is not None:
                out[key] = price_tonne_to_quintal(out[key])
        unit = target_unit
    elif unit.lower() in ("inr/quintal", "rs/quintal") and target_unit.lower() == "inr/tonne":
        for key in keys:
            if out.get(key) is not None:
                out[key] = price_quintal_to_tonne(out[key])
        unit = target_unit
    out["unit"] = unit
    return out


# ─────────────────────────── text hygiene + PII ────────────────────────────

#: Indian mobile numbers (10 digits starting 6–9, optional +91) and e-mail.
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
#: National identifiers: never stored, always rejected.
AADHAAR_RE = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
#: Encoding damage: U+FFFD plus the classic UTF-8-read-as-Latin-1 artefacts
#: (``Ã`` + a C1 control/punctuation byte, ``â€`` from smart quotes, ``Â`` + NBSP).
MOJIBAKE_RE = re.compile("\ufffd|Ã[\u0080-\u00bf]|â€|Â[\u00a0-\u00bf]")

REDACTION = "[redacted]"


def find_pii(text: str) -> dict[str, list[str]]:
    """Return PII occurrences by kind (``phone``/``email``/``aadhaar``/``pan``)."""
    if not text:
        return {}
    found: dict[str, list[str]] = {}
    for kind, pattern in (
        ("aadhaar", AADHAAR_RE), ("pan", PAN_RE), ("phone", PHONE_RE), ("email", EMAIL_RE),
    ):
        hits = pattern.findall(text)
        if hits:
            found[kind] = [str(h) for h in hits]
    return found


def redact_pii(text: str, *, drop_identifiers: bool = False) -> tuple[str, list[str]]:
    """Redact contact details; optionally blank national identifiers too.

    Returns ``(redacted_text, kinds_found)``. Original Indic text is otherwise
    untouched — this never transliterates or rewrites the farmer's words.
    """
    if not text:
        return text, []
    kinds = list(find_pii(text).keys())
    out = PHONE_RE.sub(REDACTION, text)
    out = EMAIL_RE.sub(REDACTION, out)
    if drop_identifiers:
        out = AADHAAR_RE.sub(REDACTION, out)
        out = PAN_RE.sub(REDACTION, out)
    return out, kinds


def normalize_text(text: str) -> str:
    """NFC-normalize and collapse whitespace (never changes the script)."""
    if not text:
        return text
    return " ".join(unicodedata.normalize("NFC", str(text)).split())


def has_mojibake(text: str) -> bool:
    return bool(text and MOJIBAKE_RE.search(text))


# ─────────────────────────── batch helper ──────────────────────────────────


def refine_records(
    records: Iterable[dict[str, Any]],
    *,
    date_mapping: dict[str, str],
    redact: bool = True,
    text_fields: tuple[str, ...] = ("query_original", "answer_original", "answer_normalized", "text"),
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Apply date canonicalization + PII redaction across a batch.

    Returns ``(records, problems)`` where each problem is
    ``{"record_hash", "field", "problem"}`` for the caller's DQ report.
    """
    out: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    for record in records:
        row, issues = canonicalize_dates(record, date_mapping)
        for issue in issues:
            problems.append(
                {"record_hash": str(row.get("record_hash", "")), "field": issue.split("=")[0], "problem": issue}
            )
        if redact:
            kinds: list[str] = []
            for field_name in text_fields:
                value = row.get(field_name)
                if isinstance(value, str) and value:
                    cleaned, found = redact_pii(value, drop_identifiers=False)
                    if found:
                        row[field_name] = cleaned
                        kinds += found
            if kinds:
                row["pii_redacted"] = True
                row["pii_kinds"] = sorted(set(kinds))
        out.append(row)
    return out, problems
