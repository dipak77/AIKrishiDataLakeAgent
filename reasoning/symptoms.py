"""Symptom tokenization shared by the graph builder and the diagnosis retriever.

Handles two input families:
  1. ASCII / English symptom text → unigrams + bigrams.
  2. Devanagari (Hindi/Marathi) symptom text → mapped to canonical English
     symptom tokens via `SYMPTOM_LEXICON` (substring-tolerant for suffixes like
     "पानांवर" = "on the leaves").

Matching uses light morphological normalization (`leaf`↔`leaves`,
`spot`↔`spots`, `yellowing`↔`yellow`) so token ↔ seed-text agreement is robust.

Other scripts (Tamil/Telugu/…) map through their own lexicons once added.
"""

from __future__ import annotations

import re
from typing import Iterable

from domain.seed_data import SYMPTOM_LEXICON

# Punctuation stripped; ASCII words kept as-is.
_TOKEN_RE = re.compile(r"[^a-z0-9 ]+")

# Script ranges → languages to try against SYMPTOM_LEXICON (in order).
_SCRIPT_LANGS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"[\u0900-\u097F]+"), ["hi", "mr"]),   # Devanagari
    (re.compile(r"[\u0B80-\u0BFF]+"), ["ta"]),          # Tamil
    (re.compile(r"[\u0C00-\u0C7F]+"), ["te"]),          # Telugu
    (re.compile(r"[\u0C80-\u0CFF]+"), ["kn"]),          # Kannada
    (re.compile(r"[\u0D00-\u0D7F]+"), ["ml"]),          # Malayalam
    (re.compile(r"[\u0980-\u09FF]+"), ["bn", "as"]),    # Bengali/Assamese
    (re.compile(r"[\u0A80-\u0AFF]+"), ["gu"]),          # Gujarati
    (re.compile(r"[\u0B00-\u0B7F]+"), ["od"]),          # Odia
    (re.compile(r"[\u0A00-\u0A7F]+"), ["pa"]),          # Gurmukhi
]

# Terms with no diagnostic value for naive lexical matching.
_STOP = {
    "with", "and", "the", "are", "from", "that", "this", "for", "appears", "appear",
    "which", "have", "has", "been", "over", "under", "near", "also", "very", "much",
    "getting", "becoming", "showing", "found", "seen", "there", "they", "some",
    "into", "onto", "out", "along",
}


def _norm(text: str) -> str:
    return _TOKEN_RE.sub(" ", text.lower())


def _canon(word: str) -> str:
    """Light morphological canonicalization for cross-matching."""
    w = word.lower()
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"       # leaves → leaf
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"       # berries → berry
    if w.endswith("es") and len(w) > 3:
        return w[:-2]             # lesions → lesion
    if w.endswith("ing") and len(w) > 4:
        return w[:-3]             # yellowing → yellow
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        return w[:-1]             # spots → spot
    return w


def _indic_tokens(text: str) -> list[str]:
    """Map Indic-script symptom words → canonical English tokens via the lexicon.

    Each script maps to its candidate languages (Devanagari → hi+mr, Tamil →
    ta, Telugu → te, …) and any lexicon term that subsumes or is subsumed by a
    script word is emitted.
    """
    out: list[str] = []
    for pattern, langs in _SCRIPT_LANGS:
        for word in pattern.findall(text):
            for lang in langs:
                lexicon = SYMPTOM_LEXICON.get(lang)
                if not lexicon:
                    continue
                for key, en in lexicon.items():
                    if key in word or word in key:
                        out.append(en)
    return out


def tokenize_symptoms(text: str | None, *, min_len: int = 3) -> list[str]:
    """Return canonical symptom tokens for an English or Indic symptom description."""
    if not text:
        return []

    # Indic (Devanagari) mapping first.
    indic = _indic_tokens(text)

    # ASCII path: unigrams + bigrams.
    words = [w for w in _norm(text).split() if len(w) >= min_len and w not in _STOP]
    ascii_tokens = list(dict.fromkeys(words))
    ascii_tokens += [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

    # Dedupe, preserve order (Indic tokens first so they anchor the match).
    return list(dict.fromkeys(indic + ascii_tokens))


def match_score(tokens: Iterable[str], haystack: str) -> int:
    """Count matched symptom tokens in a haystack (morphologically normalized)."""
    h_canon = {_canon(w) for w in re.split(r"[^a-z0-9]+", _norm(haystack)) if w}
    return sum(1 for t in tokens if t and (_canon(t) in h_canon or t in _norm(haystack)))


def matched_tokens(tokens: Iterable[str], haystack: str) -> list[str]:
    """The subset of tokens that actually matched `haystack` (for display)."""
    h_canon = {_canon(w) for w in re.split(r"[^a-z0-9]+", _norm(haystack)) if w}
    h_norm = _norm(haystack)
    out: list[str] = []
    for t in tokens:
        if t and (_canon(t) in h_canon or t in h_norm):
            out.append(t)
    return out
