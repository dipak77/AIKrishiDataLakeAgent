"""Dependency-free dense embeddings + ontology-driven query expansion (V5-A).

The *hashing trick*: each text is mapped to a fixed-dimension sparse vector by
feature-hashing word tokens and character n-grams (3–5). Term frequencies get
sublinear weighting (1 + log tf) and the vector is L2-normalized, so cosine
similarity is a dot product. Deterministic across runs (no numpy, no model
weights) — a pluggable stand-in for a real embedding model; swap the embedder
for ONNX/sentence-transformers behind the same `embed()` / `cosine()` API when
Qdrant + a model land.

`expand_query()` enriches a query from the seed ontology: crop aliases →
canonical + scientific names, and disease/deficiency *names* → their symptom
keywords (so "Khaira" also matches "brown spots white bud stunted").
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "be", "by", "at", "from", "that", "this", "as", "it", "its",
    "use", "using", "used", "only", "also", "can", "may", "when", "which", "into",
}

DEFAULT_DIM = 1024


def _words(text: str) -> list[str]:
    return [w for w in _TOKEN_RE.sub(" ", text.lower()).split() if len(w) > 2 and w not in _STOP]


def _char_ngrams(text: str, nmin: int = 3, nmax: int = 5) -> list[str]:
    s = _TOKEN_RE.sub("", text.lower())
    out: list[str] = []
    for n in range(nmin, nmax + 1):
        out.extend(s[i:i + n] for i in range(len(s) - n + 1))
    return out


def _stable_hash(feature: str, seed: int) -> int:
    digest = hashlib.md5(f"{seed}:{feature}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


class HashingEmbedder:
    """Feature-hashing text embedder → sparse {index: weight} vectors."""

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    def features(self, text: str) -> Counter:
        feats: Counter = Counter()
        for w in _words(text):
            feats[f"w:{w}"] += 1
        for ng in _char_ngrams(text):
            feats[f"c:{ng}"] += 1
        return feats

    def embed(self, text: str) -> dict[int, float]:
        """Sparse L2-normalized embedding of `text` (empty dict if no features)."""
        raw: dict[int, float] = {}
        for feature, count in self.features(text).items():
            weight = 1.0 + math.log(count)
            idx = _stable_hash(feature, 1) % self.dim
            sign = 1.0 if (_stable_hash(feature, 2) & 1) else -1.0
            raw[idx] = raw.get(idx, 0.0) + sign * weight
        norm2 = sum(v * v for v in raw.values())
        if norm2 <= 0:
            return {}
        norm = math.sqrt(norm2)
        return {i: v / norm for i, v in raw.items()}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    """Cosine similarity between two sparse normalized vectors (a·b)."""
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def expand_query(query: str) -> str:
    """Add ontology synonyms to a query (canonical + scientific crop names,
    disease/deficiency symptom keywords)."""
    from domain.seed_data import DISEASES, NUTRIENT_DEFICIENCIES
    from pipelines.entities import extract_crops

    terms: list[str] = [query]
    q = query.lower()

    # Crop aliases → canonical + scientific + family.
    for crop in extract_crops(query):
        for key in ("canonical_en", "scientific_name", "family"):
            val = crop.get(key)
            if val and val.lower() not in q:
                terms.append(val)

    # Disease/deficiency *names* → symptom keywords (name appears in query).
    for entity in list(DISEASES) + list(NUTRIENT_DEFICIENCIES):
        name = entity.get("name") or entity.get("crop")
        if name and len(name) > 3 and name.lower() in q:
            symptoms = entity.get("symptoms")
            if symptoms:
                terms.append(symptoms)
    return " ".join(terms)


def nearest(
    query_vec: dict[int, float],
    doc_vecs: Iterable[dict[int, float]],
) -> list[tuple[int, float]]:
    """Rank doc indices by cosine similarity to `query_vec` (descending)."""
    scored = [(i, cosine(query_vec, dv)) for i, dv in enumerate(doc_vecs)]
    return sorted(scored, key=lambda x: -x[1])
