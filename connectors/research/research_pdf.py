"""Research PDF → structured chunks pipeline (V1 skeleton).

Do not dump PDFs. Convert:

    PDF → document structure detection → section extraction → table extraction
        → figure metadata → references → semantic chunking

Chunks carry institution, year, crop, topics, section, page, text, and an
authority score. Heavy parsing dependencies (pypdf/pdfplumber, layout models)
are optional; the hooks are defined here so the pipeline is pluggable.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from connectors.base import AgricultureSourceConnector
from pipelines.entities import extract_crops

logger = logging.getLogger("agrilake.connectors.research_pdf")

SECTION_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)\.?\s+)?(abstract|introduction|materials and methods|"
    r"methodology|results|discussion|conclusion|references|management|"
    r"control measures|recommendations)\b",
    re.IGNORECASE,
)


class ResearchPdfConnector(AgricultureSourceConnector):
    source_id = "RESEARCH_PDF"
    domain = "research"

    def discover(self) -> list[dict[str, Any]]:
        return []

    def fetch(self, resource: dict[str, Any]) -> Any:
        raise NotImplementedError("Provide a PDF path / URL to parse.")

    def normalize(self, raw: Any, resource: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    # ── reusable helpers for downstream PDF parsers ────────────────────────
    @staticmethod
    def detect_sections(lines: list[str]) -> list[dict[str, Any]]:
        """Group raw text lines into labelled sections."""
        sections: list[dict[str, Any]] = []
        current = {"title": "preamble", "lines": []}
        for line in lines:
            m = SECTION_RE.match(line)
            if m and len(line.strip()) < 90:
                if current["lines"]:
                    sections.append(current)
                current = {"title": m.group(2).lower(), "lines": [line]}
            else:
                current["lines"].append(line)
        if current["lines"]:
            sections.append(current)
        return sections

    @staticmethod
    def chunk(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
        """Naive sentence-boundary chunker (swap for semantic chunking later)."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        buf = ""
        for sent in sentences:
            if len(buf) + len(sent) + 1 > max_chars and buf:
                chunks.append(buf.strip())
                buf = buf[-overlap:] if overlap else ""
            buf += " " + sent
        if buf.strip():
            chunks.append(buf.strip())
        return chunks

    @staticmethod
    def build_chunk_record(
        *,
        document: str,
        institution: str,
        year: int | None,
        section: str,
        page: int | None,
        text: str,
        authority: str = "research",
        authority_score: float = 0.95,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        crops = extract_crops(text)
        return {
            "chunk_id": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "document": document,
            "institution": institution,
            "year": year,
            "crop": [c["crop_id"] for c in crops],
            "topics": [c["canonical_en"] for c in crops],
            "section": section,
            "page": page,
            "text": text,
            "authority": authority,
            "authority_score": authority_score,
            "source_url": source_url,
        }
