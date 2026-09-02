"""Language detection for Indian farmer text.

Dependency-free: script detection from Unicode ranges, Hindi/Marathi
disambiguation from a small distinctive-word lexicon (plus an optional
geographic hint), and a rule-based Devanagari → Latin transliterator.
For production-grade accuracy, swap the detector for a fasttext/indic model and
the transliterator for a proper transliteration library behind the same API.

Translation (V5-D): ``translate()`` is now a pluggable backend with an offline
**lexicon fallback** (crop aliases + symptom lexicon + a small function-word
glossary + Devanagari transliteration). Real MT backends (IndicTrans2 /
IndicMT / an external API) are opt-in via ``AGRI_MT_BACKEND``.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

# Script → language(s). Shared scripts list the primary language plus candidates.
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

SUPPORTED_LANGUAGES = [
    "en", "hi", "mr", "gu", "pa", "bn", "od", "ta", "te", "kn", "ml", "as",
]

# Distinctive (mostly non-overlapping) function/content words for Hindi vs
# Marathi, used to disambiguate Devanagari text.
HI_WORDS = {
    "है", "हैं", "की", "को", "में", "से", "और", "यह", "वह", "क्या", "कैसे",
    "क्यों", "लिए", "गया", "हुआ", "रहा", "था", "थी", "थे", "नहीं", "हम", "आप",
    "मेरा", "हमारा", "पत्तियों", "पत्तियाँ", "फसल", "खेत", "किसान", "बीज",
    "उर्वरक", "दवा", "छिड़काव", "सिंचाई", "उपज", "मिट्टी", "गोबर", "गेहूं",
    "धान", "मक्का", "गन्ना", "आम", "केला", "प्याज", "टमाटर", "आलू", "मिर्च",
}
MR_WORDS = {
    "आहे", "आहेत", "आहेस", "च्या", "चे", "ची", "मध्ये", "आणि", "हे", "ते",
    "कसे", "साठी", "गेले", "झाले", "होते", "नाही", "आम्ही", "तुम्ही", "माझे",
    "आमचे", "पाने", "पानांवर", "पीक", "शेत", "शेतकरी", "बियाणे", "खत", "किडा",
    "औषध", "फवारणी", "सिंचन", "उत्पादन", "माती", "शेण", "गहू", "भात", "मका",
    "ऊस", "आंबा", "केळी", "कांदा", "टोमॅटो", "बटाटा", "मिरची",
}

# Geographic hint: Devanagari text from these states is more likely Marathi.
MR_STATES = {
    "IN-MH", "Maharashtra",
}


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
            language = langs[0]
            confidence = 0.7 if len(langs) == 1 else 0.5
            if name == "devanagari":
                language, confidence = disambiguate_devanagari(text)
            return {
                "script": name,
                "language": language,
                "candidates": langs,
                "confidence": confidence,
            }
    if LATIN_RE.search(text):
        return {"script": "latin", "language": "en", "candidates": ["en"], "confidence": 0.7}
    return {"script": "unknown", "language": None, "candidates": [], "confidence": 0.0}


def disambiguate_devanagari(text: str, state_hint: str | None = None) -> tuple[str, float]:
    """hi vs mr for Devanagari text using a distinctive-word lexicon.

    Returns (language, confidence). Tie broken by a geographic hint
    (Maharashtra → Marathi), else Hindi (the more common default).
    """
    hi = sum(1 for w in HI_WORDS if w in text)
    mr = sum(1 for w in MR_WORDS if w in text)
    if hi > mr:
        return "hi", min(0.9, 0.5 + 0.1 * (hi - mr))
    if mr > hi:
        return "mr", min(0.9, 0.5 + 0.1 * (mr - hi))
    # Tie: use geographic prior if available.
    if state_hint in MR_STATES or state_hint in {"mr", "Marathi"}:
        return "mr", 0.55
    return "hi", 0.5


# ── Devanagari → Latin (ITRANS-lite, ASCII) ────────────────────────────────
_DEV_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
_DEV_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}
_DEV_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ळ": "l",  # Marathi retroflex l
}
_DEV_NUKTA = {"क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y"}


def transliterate_devanagari(text: str) -> str:
    """Best-effort ASCII transliteration of Devanagari (ITRANS-lite).

    Handles independent vowels, matras, consonants, halant (virama → no
    inherent 'a'), anusvara/visarga/chandrabindu. Conjunct clusters are
    approximated (the halant simply suppresses the inherent vowel).
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Nukta forms (consonant + nukta)
        if i + 1 < n and ch + text[i + 1] in _DEV_NUKTA:
            out.append(_DEV_NUKTA[ch + text[i + 1]])
            i += 2
            continue
        if ch in _DEV_VOWELS:
            out.append(_DEV_VOWELS[ch])
        elif ch in _DEV_CONSONANTS:
            out.append(_DEV_CONSONANTS[ch])
            # inherent 'a' unless followed by matra/halant
            if i + 1 < n and (text[i + 1] in _DEV_MATRAS or text[i + 1] in ("्", "़")):
                pass
            else:
                out.append("a")
        elif ch in _DEV_MATRAS:
            # matra without a preceding consonant (rare) — emit vowel
            out.append(_DEV_MATRAS[ch])
        elif ch == "्":  # halant: suppress the trailing 'a' just added
            if out and out[-1] == "a":
                out.pop()
        elif ch == "ं" or ch == "ँ":  # anusvara / chandrabindu
            out.append("n")
        elif ch == "ः":  # visarga
            out.append("h")
        elif ch == "ॅ" or ch == "ॆ" or ch == "ॊ":  # Marathi short vowels (approx)
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def translate(text: str, target: str = "en", backend: str | None = None) -> dict[str, Any]:
    """Translate Indic text to English through the configured backend.

    Backend selection order: explicit ``backend`` arg → ``AGRI_MT_BACKEND`` env
    → the offline lexicon. If a real MT backend is requested but unavailable
    (weights/runtime not installed), the call falls back to the lexicon and
    records ``fallback_reason`` so callers never silently mistrust a result.
    """
    try:
        translator = get_translator(backend)
        return translator.translate(text, target=target)
    except MTBackendUnavailable as exc:
        result = LexiconBackend().translate(text, target=target)
        result["fallback_reason"] = str(exc)
        return result


# ── tokenization (keeps Indic matras; strips ASCII punctuation) ───────────────
_WS_RE = re.compile(r"\s+")
_EDGE_PUNCT_RE = re.compile(r"^[\s'\".,!?;:()\[\]{}]+|[\s'\".,!?;:()\[\]{}]+$")


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _WS_RE.split(text):
        tok = _EDGE_PUNCT_RE.sub("", tok)
        if tok:
            out.append(tok)
    return out


def _is_devanagari(tok: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", tok))


# ── offline glossary (crop aliases + symptoms + function words) ───────────────
_GLOSSARY: dict[str, dict[str, str]] | None = None

_FUNCTION_WORDS: dict[str, dict[str, str]] = {
    "hi": {
        "है": "is", "हैं": "are", "था": "was", "और": "and", "में": "in",
        "पर": "on", "के": "of", "का": "of", "की": "of", "को": "to",
        "से": "from", "क्या": "what", "कैसे": "how", "कब": "when",
        "क्यों": "why", "कौन": "who", "नहीं": "not", "पानी": "water",
        "खेत": "field", "किसान": "farmer", "फसल": "crop", "बीज": "seed",
        "मिट्टी": "soil", "बारिश": "rain", "धूप": "sunlight", "कीट": "pest",
        "रोग": "disease", "दवा": "medicine", "पत्ते": "leaves",
        "पत्तियां": "leaves", "फल": "fruit", "फूल": "flower", "जड़": "root",
        "तना": "stem",
    },
    "mr": {
        "आहे": "is", "आहेत": "are", "आणि": "and", "मध्ये": "in", "वर": "on",
        "च्या": "of", "चा": "of", "ची": "of", "ला": "to", "कडून": "from",
        "काय": "what", "कसे": "how", "केव्हा": "when", "का": "why",
        "कोण": "who", "नाही": "not", "पाणी": "water", "शेत": "field",
        "शेतकरी": "farmer", "पीक": "crop", "बियाणे": "seed", "माती": "soil",
        "पाऊस": "rain", "किडा": "pest", "रोग": "disease", "औषध": "medicine",
        "पाने": "leaves", "फळ": "fruit", "फूल": "flower", "मुळे": "roots",
        "खोड": "stem",
    },
    "ta": {
        "இல்லை": "not", "மழை": "rain", "நீர்": "water", "விதை": "seed",
        "மண்": "soil", "பயிர்": "crop", "விவசாயி": "farmer", "இலை": "leaf",
        "வேர்": "root", "பூ": "flower", "பழம்": "fruit", "நோய்": "disease",
        "பூச்சி": "pest",
    },
    "te": {
        "లేదు": "not", "వర్షం": "rain", "నీరు": "water", "విత్తనం": "seed",
        "నేల": "soil", "పంట": "crop", "రైతు": "farmer", "ఆకు": "leaf",
        "వేరు": "root", "పువ్వు": "flower", "పండు": "fruit", "వ్యాధి": "disease",
        "పురుగు": "pest",
    },
}


def _build_glossary() -> dict[str, dict[str, str]]:
    global _GLOSSARY
    if _GLOSSARY is not None:
        return _GLOSSARY
    from domain.seed_data import CROP_ALIASES, SYMPTOM_LEXICON

    glossary: dict[str, dict[str, str]] = {}
    for _cid, langs in CROP_ALIASES.items():
        en = langs.get("en")
        if not en:
            continue
        for lang, term in langs.items():
            if lang == "en" or not term:
                continue
            glossary.setdefault(lang, {})[term] = en
    for lang, terms in SYMPTOM_LEXICON.items():
        for term, eng in terms.items():
            glossary.setdefault(lang, {})[term.strip()] = eng
    for lang, words in _FUNCTION_WORDS.items():
        glossary.setdefault(lang, {}).update(words)
    _GLOSSARY = glossary
    return _GLOSSARY


# ── translation backends ──────────────────────────────────────────────────────
class MTBackendUnavailable(Exception):
    """A real MT backend is requested but its runtime/weights are absent."""


class TranslationBackend(ABC):
    name: str = "base"

    @abstractmethod
    def translate(self, text: str, target: str = "en") -> dict[str, Any]:
        """Translate text; return the standard result dict."""


class LexiconBackend(TranslationBackend):
    """Offline, deterministic glossary + transliteration translation (→ English)."""

    name = "lexicon"

    def translate(self, text: str, target: str = "en") -> dict[str, Any]:
        src = detect_language(text)["language"]
        base = {
            "backend": self.name,
            "source_language": src,
            "target": target,
            "original_text": text,
        }
        if target != "en":
            return {
                **base,
                "status": "pending_mt",
                "translation": None,
                "coverage": 0.0,
                "untranslated": [],
                "reason": f"lexicon backend translates to English only (target={target!r})",
            }
        if src == "en" or src is None:
            return {
                **base,
                "status": "ok",
                "translation": text,
                "coverage": 1.0,
                "untranslated": [],
            }

        glossary = _build_glossary().get(src, {})
        tokens = _tokenize(text)
        translated: list[str] = []
        untranslated: list[str] = []
        for tok in tokens:
            if tok in glossary:
                translated.append(glossary[tok])
            elif _is_devanagari(tok):
                translated.append(transliterate_devanagari(tok))
                untranslated.append(tok)
            else:
                translated.append(tok)
                untranslated.append(tok)
        coverage = 1.0 - (len(untranslated) / len(tokens)) if tokens else 1.0
        return {
            **base,
            "status": "ok" if coverage == 1.0 else "partial",
            "translation": " ".join(translated),
            "coverage": round(coverage, 4),
            "untranslated": untranslated,
        }


def _mt_result(
    backend: str,
    text: str,
    target: str,
    translation: str,
    *,
    coverage: float = 1.0,
) -> dict[str, Any]:
    src = detect_language(text)["language"]
    return {
        "backend": backend,
        "source_language": src,
        "target": target,
        "original_text": text,
        "status": "ok",
        "translation": translation,
        "coverage": round(coverage, 4),
        "untranslated": [],
    }


class IndicTrans2Backend(TranslationBackend):
    """ai4bharat IndicTrans2 — real translation when the toolkit is installed."""

    name = "indictrans2"
    hint = "install IndicTransToolkit + transformers and set AGRI_MT_MODEL_DIR — opt-in."

    def _is_available(self) -> bool:
        import importlib.util

        return (
            importlib.util.find_spec("IndicTransToolkit") is not None
            and bool(os.environ.get("AGRI_MT_MODEL_DIR"))
        )

    def translate(self, text: str, target: str = "en") -> dict[str, Any]:
        if not self._is_available():
            raise MTBackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            from IndicTransToolkit import IndicProcessor  # type: ignore
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # type: ignore

            model_dir = os.environ["AGRI_MT_MODEL_DIR"]
            src = detect_language(text)["language"] or "hi"
            tgt = target if target != "en" else "eng_Latn"
            tokenizer = AutoTokenizer.from_pretrained(model_dir, src_lang=f"{src}_IN", tgt_lang=tgt)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_dir)
            ip = IndicProcessor()
            batch = ip.preprocess_batch([text], src_lang=f"{src}_IN", tgt_lang=tgt)
            inputs = tokenizer(batch, truncation=True, padding=True, return_tensors="pt")
            out = model.generate(**inputs, max_length=256)
            decoded = tokenizer.batch_decode(out, skip_special_tokens=True)
            translated = ip.postprocess_batch(decoded, lang=tgt)[0]
            return _mt_result(self.name, text, target, translated)
        except MTBackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - runtime errors → graceful fallback
            raise MTBackendUnavailable(f"{self.name} inference failed: {exc}") from exc


class IndicMTBackend(TranslationBackend):
    """indicMT (Indic↔English) — real translation when the package is installed."""

    name = "indicmt"
    hint = "install indicMT and set AGRI_MT_MODEL_DIR — opt-in."

    def _is_available(self) -> bool:
        import importlib.util

        return (
            importlib.util.find_spec("indicMT") is not None
            and bool(os.environ.get("AGRI_MT_MODEL_DIR"))
        )

    def translate(self, text: str, target: str = "en") -> dict[str, Any]:
        if not self._is_available():
            raise MTBackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            import indicMT  # type: ignore

            model = indicMT.Model(os.environ["AGRI_MT_MODEL_DIR"])
            src = detect_language(text)["language"] or "hi"
            translated = model.translate(text, src_lang=src, tgt_lang=target)
            return _mt_result(self.name, text, target, translated)
        except MTBackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MTBackendUnavailable(f"{self.name} inference failed: {exc}") from exc


class APIMTBackend(TranslationBackend):
    """External MT API — real translation when ``AGRI_MT_API_URL`` is configured."""

    name = "api"
    hint = "external MT API not configured (set AGRI_MT_API_URL); opt-in."

    def _is_available(self) -> bool:
        return bool(os.environ.get("AGRI_MT_API_URL"))

    def translate(self, text: str, target: str = "en") -> dict[str, Any]:
        if not self._is_available():
            raise MTBackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            import requests

            resp = requests.post(
                os.environ["AGRI_MT_API_URL"],
                json={"text": text, "target": target},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            translation = data.get("translation") or data.get("text") or ""
            return _mt_result(self.name, text, target, translation)
        except MTBackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MTBackendUnavailable(f"{self.name} API failed: {exc}") from exc


_BACKENDS: dict[str, type[TranslationBackend]] = {
    "lexicon": LexiconBackend,
    "indictrans2": IndicTrans2Backend,
    "indicmt": IndicMTBackend,
    "api": APIMTBackend,
}


def get_translator(backend: str | None = None) -> TranslationBackend:
    """Resolve a translation backend: arg → ``AGRI_MT_BACKEND`` env → lexicon."""
    name = (backend or os.environ.get("AGRI_MT_BACKEND") or "lexicon").strip().lower()
    if name in ("auto", "lexicon"):
        return LexiconBackend()
    cls = _BACKENDS.get(name)
    if cls is None:
        raise MTBackendUnavailable(
            f"unknown MT backend {name!r}; available: {sorted(_BACKENDS)}"
        )
    return cls()
