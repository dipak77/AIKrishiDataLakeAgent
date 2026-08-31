"""Lightweight language detection for Indian farmer text.

Deliberately dependency-free: it detects the writing script from Unicode code
point ranges, which is enough to distinguish the Indian languages + English
that the lake treats as first-class. For higher accuracy at scale, swap this
for a real model (e.g. `fasttext` language id) behind the same interface.
"""

from __future__ import annotations

import re

# Script → language(s). Where a script is shared by several languages the
# detector returns the primary and a list of candidates (disambiguation by
# word frequency is left to the caller / a future model).
SCRIPT_RANGES: list[tuple[str, str, list[str]]] = [
    ("gurmukhi", r"\u0A00-\u0A7F", ["pa"]),
    ("gujarati", r"\u0A80-\u0AFF", ["gu"]),
    ("oriya", r"\u0B00-\u0B7F", ["od"]),
    ("tamil", r"\u0B80-\u0BFF", ["ta"]),
    ("telugu", r"\u0C00-\u0C7F", ["te"]),
    ("kannada", r"\u0C80-\u0CFF", ["kn"]),
    ("malayalam", r"\u0D00-\u0D7F", ["ml"]),
    ("bengali", r"\u0980-\u09FF", ["bn", "as"]),
    ("devanagari", r"\u0900-\u097F", ["hi", "mr"]),
]

LATIN_RE = re.compile(r"[A-Za-z]")


def detect_script(text: str) -> str:
    for name, _range, _langs in SCRIPT_RANGES:
        if re.search(f"[{_range}]", text):
            return name
    return "latin" if LATIN_RE.search(text) else "unknown"


def detect_language(text: str) -> dict:
    """Return {script, language, candidates, confidence} for a text."""
    if not text:
        return {"script": "unknown", "language": None, "candidates": [], "confidence": 0.0}
    for name, _range, langs in SCRIPT_RANGES:
        matches = re.findall(f"[{_range}]", text)
        if matches:
            return {
                "script": name,
                "language": langs[0],
                "candidates": langs,
                "confidence": 0.7 if len(langs) == 1 else 0.5,
            }
    if LATIN_RE.search(text):
        return {"script": "latin", "language": "en", "candidates": ["en"], "confidence": 0.7}
    return {"script": "unknown", "language": None, "candidates": [], "confidence": 0.0}


SUPPORTED_LANGUAGES = [
    "en", "hi", "mr", "gu", "pa", "bn", "od", "ta", "te", "kn", "ml", "as",
]
