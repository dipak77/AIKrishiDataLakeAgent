"""License gate for web/image ingestion (ALLOW / REVIEW / BLOCK).

A publicly viewable page or image does not imply permission to redistribute or
train on it. This checker classifies every candidate before ingestion.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any


class LicenseClass(str, enum.Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


ALLOW_PATTERNS = [
    r"\bcc0\b",
    r"\bcc-by\b",
    r"\bcc-by-sa\b",
    r"creativecommons\.org/licenses/(by|zero|by-sa)",
    r"\bpublic\s*domain\b",
    r"\bgodl\b",  # Government Open Data License - India
    r"open data license",
    r"\bmit\b|\bapache-?2\.0\b",
    r"explicit.*machine learning.*permission|permitted.*train",
]

BLOCK_PATTERNS = [
    r"\ball rights reserved\b",
    r"personal.*photos?",
    r"authenticated|login required|paywall",
    r"do not (reproduce|redistribute|copy)",
]

SOCIAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "whatsapp.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "reddit.com",
}


@dataclass
class LicenseDecision:
    decision: LicenseClass
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


class LicenseChecker:
    """Classify a URL + declared license into ALLOW / REVIEW / BLOCK."""

    def classify(self, url: str | None, declared_license: str | None = None) -> LicenseDecision:
        host = ""
        if url:
            host = re.sub(r"^https?://", "", url).split("/")[0].lower()
            base_domain = ".".join(host.split(".")[-2:])
            if base_domain in SOCIAL_DOMAINS:
                return LicenseDecision(
                    LicenseClass.BLOCK,
                    "social-media platform: scraping blocked by default",
                    {"url": url},
                )
            if re.search(r"\.(gov|nic)\.in$", host):
                return LicenseDecision(
                    LicenseClass.ALLOW, "Indian government domain (GODL-India)", {"url": url}
                )

        text = (declared_license or "").strip()
        if not text and url:
            return LicenseDecision(
                LicenseClass.REVIEW,
                "no declared license: review terms before ingestion",
                {"url": url},
            )
        if not text:
            return LicenseDecision(
                LicenseClass.REVIEW, "no declared license: review terms before ingestion", {}
            )

        for pat in BLOCK_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return LicenseDecision(LicenseClass.BLOCK, f"blocked pattern: {pat}", {"license": text})
        for pat in ALLOW_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return LicenseDecision(LicenseClass.ALLOW, f"open license: {pat}", {"license": text})
        return LicenseDecision(
            LicenseClass.REVIEW, "license present but not auto-classified", {"license": text}
        )
