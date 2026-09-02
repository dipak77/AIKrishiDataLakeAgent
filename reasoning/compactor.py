"""Pluggable context compactor (V6 2b) — truncation default, opt-in LLM/MT.

After fusion + reranking, the gateway compacts segments to a token budget. The
shipped default is a **deterministic** truncation compactor (no dependencies,
reproducible). A learned summarizer / IndicTrans2 compactor is opt-in via
``AGRI_COMPACTOR`` and raises ``CompactorUnavailable`` until its runtime is
installed — the same opt-in seam used by V5-C/V5-D.

Compactors return **new** segment objects via ``dataclasses.replace``, so they
work on any dataclass with a ``text`` field and never import the gateway.
"""

from __future__ import annotations

import importlib.util
import os
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, List, Optional, Sequence, TypeVar

T = TypeVar("T")


class CompactorUnavailable(Exception):
    """Raised when an opt-in compactor is selected but its runtime is absent."""


class Compactor(ABC):
    name: str = "compactor"

    @abstractmethod
    def compact(
        self,
        query: str,
        segments: Sequence[T],
        top_k: int,
        max_chars_per: int = 480,
    ) -> List[T]:
        """Return compacted copies of the top segments within the budget."""


class TruncationCompactor(Compactor):
    """Whitespace-normalize + per-segment truncation (deterministic)."""

    name = "truncation"

    def compact(
        self,
        query: str,
        segments: Sequence[T],
        top_k: int,
        max_chars_per: int = 480,
    ) -> List[T]:
        out: List[T] = []
        for seg in segments[:top_k]:
            text = " ".join(seg.text.split())
            if len(text) > max_chars_per:
                text = text[:max_chars_per].rstrip() + "…"
            out.append(replace(seg, text=text))
        return out


class _UnavailableCompactor(Compactor):
    hint = "runtime/weights not installed (opt-in download)"

    def compact(
        self,
        query: str,
        segments: Sequence[T],
        top_k: int,
        max_chars_per: int = 480,
    ) -> List[T]:
        raise CompactorUnavailable(f"{self.name} compactor unavailable: {self.hint}")


class LLMCompactor(_UnavailableCompactor):
    """Opt-in generative summarizer (e.g. a small open-weight LLM)."""

    name = "llm"
    hint = "set AGRI_COMPACTOR_LLM_URL (self-hosted OpenAI-compatible endpoint) — opt-in."

    def is_available(self) -> bool:
        return bool(os.environ.get("AGRI_COMPACTOR_LLM_URL"))


class IndicTransCompactor(_UnavailableCompactor):
    """Opt-in IndicTrans2-based compaction (research-grade transliteration+summary)."""

    name = "indic_trans"
    hint = "install ai4bharat IndicTrans2 + set AGRI_COMPACTOR_MODEL — opt-in."

    def is_available(self) -> bool:
        return importlib.util.find_spec("IndicTransToolkit") is not None


_COMPACTORS: dict[str, type[Compactor]] = {
    "truncation": TruncationCompactor,
    "llm": LLMCompactor,
    "indic_trans": IndicTransCompactor,
}


def get_compactor(name: Optional[str] = None) -> Compactor:
    """Resolve a compactor: explicit arg → ``AGRI_COMPACTOR`` env → truncation."""
    key = (name or os.environ.get("AGRI_COMPACTOR") or "truncation").strip().lower()
    cls = _COMPACTORS.get(key)
    if cls is None:
        raise CompactorUnavailable(f"unknown compactor {key!r}; available: {sorted(_COMPACTORS)}")
    return cls()
