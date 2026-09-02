"""Trained intent classification + named-entity recognition (V5-F).

Replaces the hand-written keyword router with a model that is *fit on data* —
deterministically, offline, with no heavy dependencies (pure Python):

- **IntentClassifier** — multinomial Naive Bayes over Unicode word tokens and
  character n-grams (3–4), trained on a corpus generated from the seed
  ontologies (crop/alias lexicon, symptom lexicon, disease/pest lists, growth
  stages, geography) with per-intent templates in English + Hindi/Marathi/
  Tamil/Telugu. Character n-grams make it robust to Indic scripts and typos.
- **EntityTagger** — a greedy first-order sequence tagger (BIO) using the same
  NB scorer over per-token features (token, prefix/suffix, character n-grams,
  gazetteer membership, previous label) plus a maximal-munch gazetteer pass for
  multi-word entities. Produces crop / location / growth-stage / symptom spans
  with confidence.

Both models are serialized to ``data/gold/nlu_model.json`` and retrained
(reproducibly, seeded) if the file is missing or the schema version changes.
Every prediction falls back to the heuristic router if training ever fails.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from pipelines.storage import GOLD_DIR, ensure_dir

MODEL_PATH = GOLD_DIR / "nlu_model.json"
MODEL_VERSION = 2

INTENTS = [
    "diagnosis",
    "fertilizer",
    "mandi_price",
    "weather",
    "crop_planning",
    "evidence",
]

# Keep Latin letters/digits (\w), Indic script blocks (Devanagari, Tamil,
# Telugu) *including* vowel signs / matras, and combining marks, so words like
# "काळे" or "புள்ளிகள்" tokenize as single units instead of splitting on matras.
_TOKEN_RE = re.compile(
    r"[^\w\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0300-\u036F]+", re.UNICODE
)
_RNG = random.Random(42)


# ── tokenization & features ───────────────────────────────────────────────────
def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.split(text.lower()) if t]


def _padded_ngrams(word: str, n: int) -> list[str]:
    if len(word) < n:
        return []
    padded = "#" + word + "$"
    return [padded[i : i + n] for i in range(len(padded) - n + 1)]


def _intent_features(text: str) -> Counter:
    """Word tokens + per-token char n-grams (prefixes avoid collisions)."""
    feats: Counter = Counter()
    for tok in tokenize(text):
        feats["w:" + tok] += 1
        for n in (3, 4):
            for g in _padded_ngrams(tok, n):
                feats[f"{n}:{g}"] += 1
    return feats


# ── multinomial Naive Bayes (log-space) ───────────────────────────────────────
class MultinomialNB:
    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.classes_: list[str] = []
        self.class_log_prior_: dict[str, float] = {}
        self.feature_log_prob_: dict[str, dict[str, float]] = {}
        self._default_: dict[str, float] = {}

    def fit(self, X: Sequence[Counter], y: Sequence[str]) -> "MultinomialNB":
        self.classes_ = sorted(set(y))
        n = len(y)
        class_counts = Counter(y)
        feat_counts = {c: Counter() for c in self.classes_}
        class_totals = {c: 0 for c in self.classes_}
        for xi, yi in zip(X, y):
            feat_counts[yi].update(xi)
            class_totals[yi] += sum(xi.values())
        vocab: set[str] = set()
        for c in self.classes_:
            vocab.update(feat_counts[c])
        V = len(vocab)
        for c in self.classes_:
            self.class_log_prior_[c] = math.log(class_counts[c] / n)
            denom = class_totals[c] + self.alpha * V
            self.feature_log_prob_[c] = {
                f: math.log((feat_counts[c][f] + self.alpha) / denom) for f in vocab
            }
            self._default_[c] = math.log(self.alpha / denom)
        return self

    def predict_log_proba(self, X: Sequence[Counter]) -> list[dict[str, float]]:
        out: list[dict[str, float]] = []
        for xi in X:
            scores = {}
            for c in self.classes_:
                s = self.class_log_prior_[c]
                flp = self.feature_log_prob_[c]
                for f, cnt in xi.items():
                    s += cnt * flp.get(f, self._default_[c])
                scores[c] = s
            out.append(scores)
        return out

    def predict_proba(self, X: Sequence[Counter]) -> list[dict[str, float]]:
        out: list[dict[str, float]] = []
        for logp in self.predict_log_proba(X):
            mx = max(logp.values())
            exps = {c: math.exp(v - mx) for c, v in logp.items()}
            tot = sum(exps.values())
            out.append({c: v / tot for c, v in exps.items()})
        return out

    def predict(self, X: Sequence[Counter]) -> list[str]:
        return [max(lp, key=lp.get) for lp in self.predict_log_proba(X)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "classes": self.classes_,
            "class_log_prior": self.class_log_prior_,
            "feature_log_prob": self.feature_log_prob_,
            "default": self._default_,
            "alpha": self.alpha,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MultinomialNB":
        m = cls(alpha=d.get("alpha", 1.0))
        m.classes_ = d["classes"]
        m.class_log_prior_ = d["class_log_prior"]
        m.feature_log_prob_ = d["feature_log_prob"]
        m._default_ = d["default"]
        return m


# ── ontology-backed vocabularies (shared by intent + NER) ─────────────────────
def _crop_names() -> dict[str, str]:
    """canonical English crop name → crop_id."""
    from domain.catalog import CROP_LOOKUP

    out: dict[str, str] = {}
    for name, cid in CROP_LOOKUP["by_norm_en"].items():
        out.setdefault(name, cid)
    return out


def _crop_aliases() -> dict[str, str]:
    """normalized crop mention (any script) → crop_id.

    Built from the clean multi-language ``CROP_ALIASES`` (matras intact) plus
    any extra English aliases in ``CROP_LOOKUP`` (e.g. "paddy"). The legacy
    ``by_alias`` matra-stripped entries are ignored — they lose vowel signs and
    collide across words ("काळे" → "क ळ" == "केळ").
    """
    from domain.catalog import CROP_LOOKUP
    from domain.seed_data import CROP_ALIASES

    out: dict[str, str] = {}
    for cid, langs in CROP_ALIASES.items():
        for _lang, name in langs.items():
            if name:
                out.setdefault(_norm(name), cid)
    for alias, cid in CROP_LOOKUP["by_alias"].items():
        out.setdefault(_norm(alias), cid)
    return out


def _symptom_terms() -> dict[str, str]:
    """normalized symptom term (any script) → canonical English."""
    from domain.seed_data import SYMPTOM_LEXICON

    out: dict[str, str] = {}
    for lang_terms in SYMPTOM_LEXICON.values():
        for term, eng in lang_terms.items():
            out.setdefault(term.strip().lower(), eng)
    return out


def _disease_names() -> list[str]:
    from domain.seed_data import DISEASES

    return [d["name"] for d in DISEASES]


def _pest_names() -> list[str]:
    from domain.seed_data import PESTS

    return [p["name"] for p in PESTS]


def _stage_terms() -> dict[str, str]:
    from domain.seed_data import GROWTH_STAGES

    out: dict[str, str] = {}
    for st in GROWTH_STAGES:
        out[st["name"].lower()] = st["name"]
    out["fruiting"] = "fruit_set"
    out["fruit development"] = "fruit_set"
    return out


# ── intent training data ──────────────────────────────────────────────────────
_ENGLISH_SYMPTOMS = [
    "black spots", "brown spots", "yellowing", "wilting", "leaf curl", "curling",
    "white powder", "powdery mildew", "rust", "red spots", "water soaked",
    "lesions", "stunted", "drooping", "dieback", "pale leaves", "necrotic",
    "leaf spots", "rotting", "holes in leaves", "webbing", "galls", "mosaic",
]
_FERT_WORDS = ["urea", "dap", "mop", "npk", "potash", "zinc sulphate", "compost", "farmyard manure"]
_DEFICIENCIES = [
    "zinc", "iron", "nitrogen", "boron", "calcium", "magnesium", "potassium",
    "phosphorus", "sulphur", "manganese",
]
_TOPICS = [
    "crop rotation", "drip irrigation", "organic farming", "soil health",
    "integrated pest management", "seed treatment", "mulching", "zero tillage",
]

_INTENT_TEMPLATES: dict[str, list[str]] = {
    "diagnosis": [
        "my {crop} has {sym}",
        "{crop} leaves have {sym}",
        "{crop} plant showing {sym} and wilting",
        "what disease causes {sym} on {crop}",
        "control of {pest} in {crop}",
        "how to treat {disease} in {crop}",
        "{crop} is attacked by {pest}",
        "treatment for {disease}",
        "{deficiency} deficiency in {crop}",
        "{crop} {deficiency} deficiency",
        "{crop} is deficient in {deficiency}",
        "deficiency symptoms in {crop}",
    ],
    "fertilizer": [
        "how much urea for {crop}",
        "fertilizer dose for {crop}",
        "dap and mop for {crop}",
        "npk recommendation for {crop}",
        "nutrient management in {crop}",
        "how much {fert} to apply for {crop}",
        "soil test based fertilizer for {crop}",
    ],
    "mandi_price": [
        "price of {crop} in mandi",
        "today {crop} rate in market",
        "mandi bhav for {crop}",
        "what is the market price of {crop}",
        "sell {crop} at which price",
    ],
    "weather": [
        "weather in {loc}",
        "rain forecast for {loc}",
        "will it rain in {loc}",
        "temperature and humidity in {loc}",
        "monsoon forecast for {loc}",
    ],
    "crop_planning": [
        "when to sow {crop}",
        "sowing time for {crop}",
        "best season to plant {crop}",
        "when to plant {crop} in {loc}",
        "transplanting time for {crop}",
        "crop calendar for {crop}",
    ],
    "evidence": [
        "research on {topic}",
        "best practices for {crop} cultivation",
        "package of practices for {crop}",
        "information about {topic}",
        "scientific guide for {crop} cultivation",
    ],
}

# Minimal Indic intent signals (keyword + short phrases per script).
_INDIC_INTENT_PHRASES: dict[str, dict[str, list[str]]] = {
    "diagnosis": {
        "hi": ["{crop} पर {sym}", "{crop} में {sym}", "{sym} रोग"],
        "mr": ["{crop}वर {sym}", "{crop} मध्ये {sym}"],
        "ta": ["{crop} இல் {sym}", "{crop}ல் {sym}"],
        "te": ["{crop} లో {sym}"],
    },
    "fertilizer": {
        "hi": ["खत की मात्रा", "उर्वरक", "यूरिया खाद"],
        "mr": ["खत किती", "युरिया खत"],
        "ta": ["உரம்", "யூரியா உரம்"],
        "te": ["ఎరువు", "యూరియా ఎరువు"],
    },
    "mandi_price": {
        "hi": ["मंडी भाव", "दाम", "कीमत"],
        "mr": ["मंडई भाव", "भाव काय"],
        "ta": ["விலை", "சந்தை விலை"],
        "te": ["ధర", "మార్కెట్ ధర"],
    },
    "weather": {
        "hi": ["बारिश", "मौसम", "वर्षा"],
        "mr": ["पाऊस", "हवामान"],
        "ta": ["மழை", "வானிலை"],
        "te": ["వర్షం", "వాతావరణం"],
    },
    "crop_planning": {
        "hi": ["बुवाई", "बोना कब"],
        "mr": ["पेरणी", "बियाणे"],
        "ta": ["விதைக்க", "விதைப்பு"],
        "te": ["విత్తనం", "నాటు"],
    },
    "evidence": {
        "hi": ["जानकारी", "अनुसंधान"],
        "mr": ["माहिती", "संशोधन"],
        "ta": ["தகவல்", "முறை"],
        "te": ["సమాచారం", "పద్ధతి"],
    },
}


def build_intent_examples(max_crops: int = 40) -> list[tuple[str, str]]:
    """Deterministically generate a labeled intent corpus from seed ontologies."""
    from domain.seed_data import CROP_ALIASES, SYMPTOM_LEXICON

    crop_ids = list(_crop_names().values())
    _RNG.shuffle(crop_ids)
    crop_ids = crop_ids[:max_crops]
    crop_pool = [n for n, cid in _crop_names().items() if cid in crop_ids][:max_crops]

    diseases = _disease_names()
    pests = _pest_names()

    from domain.catalog import GEOGRAPHY_LOOKUP

    locs = [r["district_name"] for r in GEOGRAPHY_LOOKUP["by_district"].values()] + [
        r["name"] for r in GEOGRAPHY_LOOKUP["by_state"].values()
    ]
    _RNG.shuffle(locs)
    locs = locs[:60]

    examples: list[tuple[str, str]] = []
    for intent, templates in _INTENT_TEMPLATES.items():
        for tpl in templates:
            for crop in crop_pool:
                text = tpl.format(
                    crop=crop,
                    sym=_RNG.choice(_ENGLISH_SYMPTOMS),
                    pest=_RNG.choice(pests) if pests else "borer",
                    disease=_RNG.choice(diseases) if diseases else "blight",
                    deficiency=_RNG.choice(_DEFICIENCIES),
                    fert=_RNG.choice(_FERT_WORDS),
                    loc=_RNG.choice(locs),
                    topic=_RNG.choice(_TOPICS),
                )
                examples.append((text, intent))

    # Indic: symptom-lexicon + crop-alias phrases (per-language, so Devanagari
    # hi/mr stay distinct and Tamil/Telugu terms are covered).
    for intent, per_lang in _INDIC_INTENT_PHRASES.items():
        for lang, phrases in per_lang.items():
            syms = list(SYMPTOM_LEXICON[lang].keys())
            crops = [CROP_ALIASES.get(cid, {}).get(lang) for cid in crop_ids]
            crops = [c for c in crops if c]
            for phrase in phrases:
                if "{sym}" in phrase:
                    for sym in syms[:12]:
                        examples.append(
                            (phrase.format(sym=sym, crop=_RNG.choice(crops or [""])), intent)
                        )
                elif "{crop}" in phrase:
                    for crop in crops[:8]:
                        examples.append((phrase.format(crop=crop), intent))
                else:
                    examples.append((phrase, intent))
    return examples


# ── intent classifier ─────────────────────────────────────────────────────────
# Greetings / pleasantries are a closed class; short OOV inputs like "hello"
# would otherwise leak into "diagnosis" via char n-gram overlap ("hello" ~
# "yellowing"). Deterministic pre-check mirrors the heuristic router's
# "no domain signal → general" fallback.
_GREETINGS = {
    "hello", "hi", "hey", "help", "thanks", "thank you", "good morning",
    "good evening", "good afternoon", "who are you", "what can you do",
    "how are you", "bye", "ok", "okay", "namaste", "namaskar", "vanakkam",
    "dhanyavad", "shukriya", "salaam",
    "नमस्ते", "नमस्कार", "प्रणाम", "धन्यवाद", "शुक्रिया", "नमस्ते जी",
    "वणक्कम", "வணக்கம்", "நன்றி", "వణక్కం", "నమస్తే", "ధన్యవాదాలు", "నమస్కారం",
}

# Leading-token greetings (catches "hello there", "नमस्ते जी", …).
_GREETING_LEAD = {
    "hello", "hi", "hey", "namaste", "namaskar", "vanakkam", "dhanyavad",
    "shukriya", "salaam", "thanks", "thank",
    "नमस्ते", "नमस्कार", "प्रणाम", "धन्यवाद", "शुक्रिया",
    "वणक्कम", "வணக்கம்", "நன்றி", "వణక్కం", "నమస్తే", "ధన్యవాదాలు", "నమస్కారం",
}


class IntentClassifier:
    def __init__(self, threshold: float = 0.30) -> None:
        self.threshold = threshold
        self.nb = MultinomialNB()

    def train(self, examples: Sequence[tuple[str, str]]) -> "IntentClassifier":
        X = [_intent_features(text) for text, _ in examples]
        y = [label for _, label in examples]
        self.nb.fit(X, y)
        return self

    def predict(self, text: str) -> tuple[str, dict[str, float], float]:
        toks = tokenize(text)
        if _norm(text) in _GREETINGS or (
            toks and len(toks) <= 3 and toks[0] in _GREETING_LEAD
        ):
            probs = {c: 0.0 for c in self.nb.classes_}
            return "general", probs, 1.0
        feats = _intent_features(text)
        # Only known vocabulary contributes — out-of-vocabulary tokens (greetings,
        # copulas, unknown words) carry no evidence, so they cannot skew the
        # result toward whichever class happens to have the smallest token mass.
        vocab = self.nb.feature_log_prob_[self.nb.classes_[0]]
        feats = Counter({f: c for f, c in feats.items() if f in vocab})
        if not feats:
            # Entirely out-of-vocabulary input carries no evidence; never let a
            # class *prior* decide (priors shift as training data grows).
            return "general", {c: 0.0 for c in self.nb.classes_}, 1.0
        probs = self.nb.predict_proba([feats])[0]
        label = max(probs, key=probs.get)
        conf = probs[label]
        if conf < self.threshold:
            return "general", probs, conf
        return label, probs, conf

    def accuracy(self, examples: Sequence[tuple[str, str]]) -> float:
        if not examples:
            return 0.0
        ok = sum(1 for t, y in examples if self.predict(t)[0] == y)
        return ok / len(examples)


# ── NER: gazetteers + BIO tagger ──────────────────────────────────────────────
BIO_TYPES = ("CROP", "LOC", "STAGE", "SYMPTOM")
_BIO = ["O"] + [f"{p}-{t}" for p in ("B", "I") for t in BIO_TYPES]


def _build_gazetteers() -> dict[str, Any]:
    """token→type sets and phrase→type maps (normalized, lowercase)."""
    token_types: dict[str, set[str]] = {}
    phrase_types: dict[str, str] = {}

    def add(phrase: str, typ: str) -> None:
        norm = _norm(phrase)
        if not norm:
            return
        phrase_types.setdefault(norm, typ)
        for tok in norm.split():
            token_types.setdefault(tok, set()).add(typ)

    for name in _crop_names():
        add(name, "CROP")
    for alias in _crop_aliases():
        add(alias, "CROP")
    for term in _symptom_terms():
        add(term, "SYMPTOM")
    for s in _ENGLISH_SYMPTOMS:
        add(s, "SYMPTOM")
    for st in _stage_terms():
        add(st, "STAGE")

    from domain.catalog import GEOGRAPHY_LOOKUP

    for name in GEOGRAPHY_LOOKUP["by_state"]:
        add(name, "LOC")
    for alias in GEOGRAPHY_LOOKUP["by_alias"]:
        add(alias, "LOC")
    for (_sc, dname) in GEOGRAPHY_LOOKUP["by_district"]:
        add(dname, "LOC")
    for (_sc, dname) in GEOGRAPHY_LOOKUP["by_district_alias"]:
        add(dname, "LOC")

    crop_aliases = sorted(
        (a for a, t in phrase_types.items() if t == "CROP"), key=len, reverse=True
    )
    return {"token": token_types, "phrase": phrase_types, "crop_aliases": crop_aliases}


def _norm(s: str) -> str:
    return _TOKEN_RE.sub(" ", s.lower()).strip()


def _token_features(tok: str, prev: str, gaz: dict[str, Any]) -> Counter:
    feats: Counter = Counter()
    feats["w:" + tok] += 1
    feats["pre:" + tok[:3]] += 1
    feats["suf:" + tok[-3:]] += 1
    feats["prev:" + prev] += 1
    feats["shape:" + ("D" if tok.isdigit() else "A" if tok.isalpha() else "M")] += 1
    for g in _padded_ngrams(tok, 3):
        feats["3:" + g] += 1
    hits = gaz["token"].get(tok, set())
    if hits:
        for t in hits:
            feats["gz:" + t] += 1
    else:
        feats["gz:NONE"] += 1
    return feats


_NER_TEMPLATES: list[tuple[str, dict[str, str]]] = [
    ("my {crop} has {sym} on the leaves", {"crop": "CROP", "sym": "SYMPTOM"}),
    ("{crop} leaves turning {sym}", {"crop": "CROP", "sym": "SYMPTOM"}),
    ("weather in {loc}", {"loc": "LOC"}),
    ("rain forecast for {loc}", {"loc": "LOC"}),
    ("when to sow {crop}", {"crop": "CROP"}),
    ("when to plant {crop} in {loc}", {"crop": "CROP", "loc": "LOC"}),
    ("price of {crop} in {loc} mandi", {"crop": "CROP", "loc": "LOC"}),
    ("{crop} at {stage} stage has {sym}", {"crop": "CROP", "stage": "STAGE", "sym": "SYMPTOM"}),
    ("fertilizer dose for {crop}", {"crop": "CROP"}),
    ("how to treat {disease} in {crop}", {"disease": "SYMPTOM", "crop": "CROP"}),
]

# Indic NER templates (spaced postpositions so token alignment is exact).
_INDIC_NER_TEMPLATES: dict[str, list[tuple[str, dict[str, str]]]] = {
    "hi": [("{crop} पर {sym}", {"crop": "CROP", "sym": "SYMPTOM"}),
           ("{crop} में {sym}", {"crop": "CROP", "sym": "SYMPTOM"})],
    "mr": [("{crop} मध्ये {sym}", {"crop": "CROP", "sym": "SYMPTOM"})],
    "ta": [("{crop} இல் {sym}", {"crop": "CROP", "sym": "SYMPTOM"}),
           ("{crop}ல் {sym}", {"crop": "CROP", "sym": "SYMPTOM"})],
    "te": [("{crop} లో {sym}", {"crop": "CROP", "sym": "SYMPTOM"})],
}


def build_ner_examples(max_crops: int = 30, max_locs: int = 40) -> list[tuple[list[str], list[str]]]:
    from domain.catalog import GEOGRAPHY_LOOKUP
    from domain.seed_data import CROP_ALIASES, SYMPTOM_LEXICON

    crop_pool = list(_crop_names())[:max_crops]
    loc_pool = (
        [r["name"] for r in GEOGRAPHY_LOOKUP["by_state"].values()]
        + [r["district_name"] for r in GEOGRAPHY_LOOKUP["by_district"].values()]
    )
    _RNG.shuffle(loc_pool)
    loc_pool = loc_pool[:max_locs]
    stage_pool = list(_stage_terms().keys())
    sym_pool = _ENGLISH_SYMPTOMS + list(_symptom_terms())

    examples: list[tuple[list[str], list[str]]] = []

    def _add(tpl: str, slots: dict[str, str], fill: dict[str, str]) -> None:
        text = tpl.format(**fill)
        tokens = tokenize(text)
        labels = _label_by_slot(tpl, slots, fill, tokens)
        if len(tokens) == len(labels):
            examples.append((tokens, labels))

    for tpl, slots in _NER_TEMPLATES:
        for _ in range(120):
            fill: dict[str, str] = {}
            for slot in slots:
                if slot == "crop":
                    fill[slot] = _RNG.choice(crop_pool)
                elif slot == "loc":
                    fill[slot] = _RNG.choice(loc_pool)
                elif slot == "stage":
                    fill[slot] = _RNG.choice(stage_pool)
                elif slot == "sym":
                    fill[slot] = _RNG.choice(sym_pool)
                elif slot == "disease":
                    fill[slot] = _RNG.choice(_disease_names() or ["blight"])
            _add(tpl, slots, fill)

    # Indic copulas / postpositions as O-only examples, so OOV function words
    # ("आहेत", "உள்ளது", …) are not pulled into an entity span by transition.
    _INDIC_STOPWORDS: dict[str, list[str]] = {
        "hi": ["है", "हैं", "में", "पर", "की", "का", "के"],
        "mr": ["आहे", "आहेत", "मध्ये", "ची", "चा", "चे"],
        "ta": ["உள்ளது", "இருக்கு", "க்கு"],
        "te": ["ఉంది", "కి"],
    }
    for lang, words in _INDIC_STOPWORDS.items():
        for w in words:
            examples.append(([w], ["O"]))

    # Indic: crop aliases + symptom lexicon per language (matras intact).
    for lang, templates in _INDIC_NER_TEMPLATES.items():
        crops = [CROP_ALIASES.get(cid, {}).get(lang) for cid in _crop_names().values()]
        crops = [c for c in crops if c][:max_crops]
        syms = list(SYMPTOM_LEXICON[lang].keys())
        for tpl, slots in templates:
            for _ in range(80):
                fill = {
                    s: (_RNG.choice(crops) if s == "crop" else _RNG.choice(syms))
                    for s in slots
                }
                _add(tpl, slots, fill)
    return examples


def _label_by_slot(
    tpl: str, slots: dict[str, str], fill: dict[str, str], tokens: list[str]
) -> list[str]:
    """Assign BIO labels by re-deriving each token's source (slot vs template)."""
    slot_types = {slot: typ for slot, typ in slots.items()}
    # Reconstruct per-token origin: split template on slots into literal parts.
    parts: list[tuple[str, str | None]] = []
    rest = tpl
    for slot in slots:
        marker = "{" + slot + "}"
        idx = rest.find(marker)
        if idx == -1:
            continue
        parts.append((rest[:idx], None))
        parts.append((marker, slot))
        rest = rest[idx + len(marker):]
    parts.append((rest, None))

    # Build expected token stream: literal parts tokenized; slots tokenized from fill.
    expected: list[tuple[str, str | None]] = []  # (token, slot or None)
    for literal, slot in parts:
        if slot is None:
            for tok in tokenize(literal):
                expected.append((tok, None))
        else:
            for tok in tokenize(fill[slot]):
                expected.append((tok, slot))

    labels: list[str] = []
    # Align expected to actual tokens (same tokenization, so index-aligned).
    prev_slot = None
    for i, tok in enumerate(tokens):
        slot = expected[i][1] if i < len(expected) else None
        if slot is None:
            labels.append("O")
            prev_slot = None
        else:
            typ = slot_types[slot]
            labels.append(("I-" if prev_slot == slot else "B-") + typ)
            prev_slot = slot
    return labels


class EntityTagger:
    def __init__(self) -> None:
        self.nb = MultinomialNB()
        self.gaz: dict[str, Any] = {}

    def train(self, examples: Sequence[tuple[list[str], list[str]]]) -> "EntityTagger":
        self.gaz = _build_gazetteers()
        X: list[Counter] = []
        y: list[str] = []
        for tokens, labels in examples:
            prev = "O"
            for tok, lab in zip(tokens, labels):
                X.append(_token_features(tok, prev, self.gaz))
                y.append(lab)
                prev = lab
        self.nb.fit(X, y)
        return self

    def tag(self, tokens: Sequence[str]) -> list[tuple[str, str, float]]:
        """Greedy BIO tagging with maximal-munch gazetteer override."""
        n = len(tokens)
        labels = ["O"] * n
        prev = "O"
        for i, tok in enumerate(tokens):
            feats = _token_features(tok, prev, self.gaz)
            probs = self.nb.predict_proba([feats])[0]
            lab = max(probs, key=probs.get)
            # maximal-munch gazetteer: prefer multi-word exact matches
            match = self._gazette_override(tokens, i)
            if match is not None:
                phrase, typ = match
                for j in range(i, i + len(phrase.split())):
                    labels[j] = ("I-" if j > i else "B-") + typ
                    prev = labels[j]
                continue
            labels[i] = lab
            prev = lab
        # BIO consistency: lone I- → B-.
        for i in range(n):
            if labels[i].startswith("I-"):
                typ = labels[i][2:]
                if i == 0 or labels[i - 1] != "B-" + typ and labels[i - 1] != "I-" + typ:
                    labels[i] = "B-" + typ
        return [(tok, labels[i], 1.0) for i, tok in enumerate(tokens)]

    def _gazette_override(self, tokens: Sequence[str], i: int) -> tuple[str, str] | None:
        """Exact multi-word match, else single-token crop prefix match.

        The prefix rule recovers inflected forms ("tomatoes", "टोमॅटोवर",
        "தக்காளியில்") that the statistical tagger sees out-of-vocabulary.
        """
        for length in range(min(4, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + length])
            if phrase in self.gaz["phrase"]:
                return phrase, self.gaz["phrase"][phrase]
        tok = tokens[i]
        hits = self.gaz["token"].get(tok, set())
        if hits:
            return None  # exact single-token gazetteer; let the NB tagger decide
        if len(tok) >= 4:
            for alias in self.gaz["crop_aliases"]:
                if len(alias) >= 3 and tok.startswith(alias):
                    return tok, "CROP"
        return None


def _resolve_crop_span(phrase: str) -> dict[str, Any] | None:
    """Resolve a crop span, tolerating attached suffixes (e.g. Marathi -वर,
    English plural 'tomatoes') via prefix match on known crop names/aliases.

    Exact matches only for short strings — ``resolve_crop``'s substring
    fallback is too aggressive for tiny tokens ("in" → "finger millet ragi").
    """
    from domain.catalog import CROP_LOOKUP

    norm = _norm(phrase)
    if not norm:
        return None
    if norm in CROP_LOOKUP["by_norm_en"]:
        cid = CROP_LOOKUP["by_norm_en"][norm]
        return dict(CROP_LOOKUP["rows"][cid], resolved_via="exact")
    aliases = _crop_aliases()
    if norm in aliases:
        return dict(CROP_LOOKUP["rows"][aliases[norm]], resolved_via="exact")
    if len(norm) >= 4:
        for alias, cid in aliases.items():
            if len(alias) >= 3 and (norm.startswith(alias) or alias.startswith(norm)):
                return dict(CROP_LOOKUP["rows"][cid], resolved_via="prefix")
    return None


def _resolve_location(phrase: str) -> dict[str, Any]:
    from domain.catalog import GEOGRAPHY_LOOKUP

    norm = _norm(phrase)
    if not norm:
        return {}
    if norm in GEOGRAPHY_LOOKUP["by_state"]:
        row = GEOGRAPHY_LOOKUP["by_state"][norm]
        return {"state": row["name"], "state_code": row["state_code"]}
    if norm in GEOGRAPHY_LOOKUP["by_alias"]:
        row = GEOGRAPHY_LOOKUP["by_alias"][norm]
        return {"state": row["name"], "state_code": row["state_code"]}
    for (_sc, dname), row in GEOGRAPHY_LOOKUP["by_district"].items():
        if dname == norm:
            return {
                "district": row["district_name"],
                "district_code": row["district_code"],
                "state": row["state_name"],
                "state_code": row["state_code"],
            }
    for (_sc, dname), row in GEOGRAPHY_LOOKUP["by_district_alias"].items():
        if dname == norm:
            return {
                "district": row["district_name"],
                "district_code": row["district_code"],
                "state": row["state_name"],
                "state_code": row["state_code"],
            }
    return {}


def _resolve_stage(phrase: str) -> str | None:
    terms = _stage_terms()
    norm = _norm(phrase)
    if norm in terms:
        return terms[norm]
    return None


_SYMPTOM_VOCAB: set[str] | None = None


def _symptom_vocab() -> set[str]:
    """Single-token symptom vocabulary (Indic lexicon + English word list)."""
    global _SYMPTOM_VOCAB
    if _SYMPTOM_VOCAB is None:
        vocab: set[str] = set()
        for term in _symptom_terms():
            vocab.update(_norm(term).split())
        for phrase in _ENGLISH_SYMPTOMS:
            vocab.update(_norm(phrase).split())
        vocab.update(
            "spots spot leaves leaf yellow yellowing wilting wilt curling curl "
            "stunted powdery rust red soaked lesions blight rot holes webbing "
            "galls mosaic mildew scorch dieback drooping pale patches necrosis".split()
        )
        _SYMPTOM_VOCAB = vocab
    return _SYMPTOM_VOCAB


def extract_entities(
    tagger: EntityTagger, text: str
) -> dict[str, Any]:
    """Tag a query and resolve spans → {crop, location, stage, symptoms}."""
    from pipelines.entities import resolve_crop

    tokens = tokenize(text)
    tagged = tagger.tag(tokens)
    spans: list[tuple[str, list[str]]] = []
    for tok, lab, _ in tagged:
        if lab.startswith("B-"):
            spans.append((lab[2:], [tok]))
        elif lab.startswith("I-") and spans and spans[-1][0] == lab[2:]:
            spans[-1][1].append(tok)

    # merge adjacent spans of the same type (e.g. two single-token symptoms)
    merged: list[tuple[str, list[str]]] = []
    for typ, toks in spans:
        if merged and merged[-1][0] == typ:
            merged[-1][1].extend(toks)
        else:
            merged.append((typ, toks))

    crop = None
    location: dict[str, Any] = {}
    stage = None
    symptoms: list[str] = []
    for typ, toks in merged:
        phrase = " ".join(toks)
        if typ == "CROP" and crop is None:
            crop = _resolve_crop_span(phrase)
        elif typ == "LOC" and not location:
            location = _resolve_location(phrase)
        elif typ == "STAGE" and stage is None:
            stage = _resolve_stage(phrase)
        elif typ == "SYMPTOM":
            cleaned = [t for t in toks if t in _symptom_vocab()]
            if cleaned:
                symptoms.append(" ".join(cleaned))

    # fallbacks: token-level prefix resolution (handles attached postpositions
    # like "टोमॅटोवर" or plurals "tomatoes"), then boundary-based extraction.
    if crop is None:
        for tok in tokens:
            crop = _resolve_crop_span(tok)
            if crop is not None:
                break
    if crop is None:
        from pipelines.entities import extract_crops

        found = extract_crops(text)
        crop = found[0] if found else None
    if not location:
        location = _fallback_location(text)
    if stage is None:
        stage = _fallback_stage(text)
    return {
        "crop": crop,
        "district": location.get("district"),
        "state": location.get("state"),
        "state_code": location.get("state_code"),
        "district_code": location.get("district_code"),
        "stage": stage,
        "symptoms": symptoms,
    }


def _fallback_location(text: str) -> dict[str, Any]:
    """Word-window geography scan (mirrors the heuristic assistant)."""
    from domain.catalog import GEOGRAPHY_LOOKUP

    words = tokenize(text)
    for n in (2, 1):
        for i in range(len(words) - n + 1):
            chunk = " ".join(words[i : i + n])
            res = _resolve_location(chunk)
            if res:
                return res
    return {}


def _fallback_stage(text: str) -> str | None:
    q = text.lower()
    for term, canon in _stage_terms().items():
        if term in q:
            return canon
    return None


# ── NLU pipeline ──────────────────────────────────────────────────────────────
@dataclass
class NLUResult:
    intent: str
    intent_scores: dict[str, float]
    intent_confidence: float
    crop: dict[str, Any] | None
    location: dict[str, Any]
    stage: str | None
    symptoms: list[str]
    model: str = "trained"


@dataclass
class _TrainedModel:
    version: int
    intent: IntentClassifier
    tagger: EntityTagger


class NLUPipeline:
    """Language-aware intent + entity pipeline with heuristic fallback."""

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = Path(model_path or MODEL_PATH)
        self._model: _TrainedModel | None = None
        self._training_ok = True

    def _load_or_train(self) -> _TrainedModel | None:
        return self.ensure_model()

    def ensure_model(self) -> _TrainedModel | None:
        """Load the cached model, or train (reproducibly) and persist it."""
        if self._model is not None:
            return self._model
        if self._training_ok and self.model_path.exists():
            try:
                self._model = _load_model(self.model_path)
                if self._model is not None:
                    return self._model
            except Exception:
                self._model = None
        if self._training_ok:
            try:
                model = train_models()
                ensure_dir(self.model_path.parent)
                self.model_path.write_text(
                    json.dumps(_serialize_model(model), ensure_ascii=False), encoding="utf-8"
                )
                self._model = model
                return model
            except Exception:
                self._training_ok = False
                self._model = None
        return None

    def predict(self, query: str) -> NLUResult:
        model = self.ensure_model()
        if model is not None:
            intent, scores, conf = model.intent.predict(query)
            ents = extract_entities(model.tagger, query)
            return NLUResult(
                intent=intent,
                intent_scores=scores,
                intent_confidence=conf,
                crop=ents["crop"],
                location=ents,
                stage=ents["stage"],
                symptoms=ents["symptoms"],
                model="trained",
            )
        return self._heuristic(query)

    @staticmethod
    def _heuristic(query: str) -> NLUResult:
        from reasoning.assistant import classify_intent, extract_crop, extract_location, extract_stage

        intent, scores = classify_intent(query)
        crop = extract_crop(query)
        loc = extract_location(query)
        stage = extract_stage(query)
        return NLUResult(
            intent=intent,
            intent_scores={k: float(v) for k, v in scores.items()},
            intent_confidence=1.0,
            crop=crop,
            location=loc,
            stage=stage,
            symptoms=[],
            model="heuristic",
        )


def train_models() -> _TrainedModel:
    intent_examples = build_intent_examples()
    intent = IntentClassifier().train(intent_examples)
    ner_examples = build_ner_examples()
    tagger = EntityTagger().train(ner_examples)
    return _TrainedModel(version=MODEL_VERSION, intent=intent, tagger=tagger)


def _serialize_model(model: _TrainedModel) -> dict[str, Any]:
    return {
        "version": model.version,
        "intent": {
            "threshold": model.intent.threshold,
            "nb": model.intent.nb.to_dict(),
        },
        "tagger": {
            "nb": model.tagger.nb.to_dict(),
        },
    }


def _load_model(path: Path) -> _TrainedModel | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != MODEL_VERSION:
        return None
    intent = IntentClassifier(threshold=data["intent"]["threshold"])
    intent.nb = MultinomialNB.from_dict(data["intent"]["nb"])
    tagger = EntityTagger()
    tagger.nb = MultinomialNB.from_dict(data["tagger"]["nb"])
    tagger.gaz = _build_gazetteers()
    return _TrainedModel(version=data["version"], intent=intent, tagger=tagger)


# ── module-level convenience ──────────────────────────────────────────────────
_PIPELINE: NLUPipeline | None = None


def get_pipeline() -> NLUPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = NLUPipeline()
    return _PIPELINE


def classify_intent_trained(text: str) -> tuple[str, dict[str, float], float]:
    """One-shot trained intent classification (for evaluation/CLI)."""
    model = get_pipeline().ensure_model()
    if model is None:
        return "general", {}, 0.0
    return model.intent.predict(text)


def tag_tokens(text: str) -> list[tuple[str, str, float]]:
    """One-shot BIO tagging of a query (for evaluation/CLI)."""
    model = get_pipeline().ensure_model()
    if model is None:
        return [(t, "O", 0.0) for t in tokenize(text)]
    return model.tagger.tag(tokenize(text))
