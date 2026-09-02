"""Evidence retrieval over research chunks (Track 9 → V5-A hybrid).

Two retrievers share one corpus of provenance-only excerpts (institution, year,
crop, section, page, short text — never whole articles); every hit carries
source + authority + license so a diagnosis or advisory can cite *retrieved*
evidence in addition to the seed ontology.

  - ``SearchIndex.search``  — classic Okapi BM25 (lexical)
  - ``HybridIndex.hybrid_search`` — BM25 ⊕ dense (feature-hashing embeddings)
    fused with Reciprocal Rank Fusion + ontology query expansion (V5-A)

Swap the dense ranker for a vector store behind the same API when Qdrant lands.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR
from reasoning.embeddings import HashingEmbedder, cosine, expand_query

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"

_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "be", "by", "at", "from", "that", "this", "as", "it", "its",
    "use", "using", "used", "only", "also", "can", "may", "when", "which", "into",
}


@dataclass
class EvidenceHit:
    chunk_id: str
    document: str
    institution: str
    year: int | None
    crop: list[str]
    topics: list[str]
    section: str | None
    page: int | None
    text: str
    score: float
    authority: str
    authority_score: float
    source_url: str | None
    license: dict[str, Any] = field(default_factory=lambda: {"type": "institutional (per-document terms)"})

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


def tokenize(text: str) -> list[str]:
    return [w for w in _TOKEN_RE.sub(" ", text.lower()).split() if len(w) > 2 and w not in _STOP]


def load_chunks(lake: Path | None = None) -> list[dict[str, Any]]:
    """Read `research_chunk` from the lake; fall back to the ICAR fixture."""
    from pipelines.storage import FIXTURES_DIR, get_read_connection

    lake = Path(lake or DEFAULT_LAKE)
    if lake.exists():
        con = get_read_connection(lake)
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='gold'"
            ).fetchall()
        }
        if "research_chunk" in tables:
            cols = [r[1] for r in con.execute("PRAGMA table_info('gold.research_chunk')").fetchall()]
            select = ",".join(f'"{c}"' for c in cols)
            return [dict(zip(cols, r)) for r in con.execute(f"SELECT {select} FROM gold.research_chunk").fetchall()]
    fixture = FIXTURES_DIR / "icar_research_chunk.json"
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8"))
    return []


class SearchIndex:
    """Okapi BM25 over a small chunk corpus (fields: text + document + topics)."""

    def __init__(self, chunks: list[dict[str, Any]], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.doc_tokens: list[list[str]] = []
        self.doc_lens: list[int] = []
        self.df: Counter = Counter()
        for c in chunks:
            fields = " ".join(
                [c.get("text") or "", c.get("document") or "", " ".join(c.get("topics") or [])]
            )
            toks = tokenize(fields)
            self.doc_tokens.append(toks)
            self.doc_lens.append(len(toks))
            for t in set(toks):
                self.df[t] += 1
        self.n = len(chunks) or 1
        self.avgdl = sum(self.doc_lens) / self.n if self.n else 1.0

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n - df + 0.5) / (df + 0.5) + 1.0)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        crop: str | None = None,
    ) -> list[EvidenceHit]:
        crop_id = None
        if crop:
            from pipelines.entities import resolve_crop

            crop_id = (resolve_crop(crop) or {}).get("crop_id") or crop
        qterms = [t for t in dict.fromkeys(tokenize(query))]
        scored: list[tuple[float, int]] = []
        for i, toks in enumerate(self.doc_tokens):
            if crop_id:
                if crop_id not in (self.chunks[i].get("crop") or []) and crop_id not in (
                    self.chunks[i].get("topics") or []
                ):
                    continue
            tf = Counter(toks)
            dl = self.doc_lens[i] or 1
            score = 0.0
            for q in qterms:
                f = tf.get(q, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                score += self._idf(q) * (f * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: -x[0])
        return [self._hit(score, i) for score, i in scored[:top_k]]

    def _hit(self, score: float, i: int) -> EvidenceHit:
        c = self.chunks[i]
        return EvidenceHit(
            chunk_id=c.get("chunk_id") or c.get("record_id", ""),
            document=c.get("document") or "",
            institution=c.get("institution") or "",
            year=c.get("year"),
            crop=c.get("crop") or [],
            topics=c.get("topics") or [],
            section=c.get("section"),
            page=c.get("page"),
            text=c.get("text") or "",
            score=round(score, 4),
            authority=c.get("authority", "research"),
            authority_score=float(c.get("authority_score") or 0.0),
            source_url=c.get("source_url"),
        )


@lru_cache(maxsize=4)
def _bm25_index(lake: str) -> SearchIndex:
    """Cached BM25 index per lake path (index build is the dominant RAG cost)."""
    return SearchIndex(load_chunks(Path(lake) if lake else None))


def search(
    query: str,
    *,
    top_k: int = 5,
    crop: str | None = None,
    lake: Path | None = None,
) -> list[EvidenceHit]:
    """One-shot: load chunks, build the BM25 index, return ranked evidence hits."""
    index = _bm25_index(str(lake or ""))
    return index.search(query, top_k=top_k, crop=crop)


class HybridIndex(SearchIndex):
    """BM25 ⊕ dense embeddings, fused with Reciprocal Rank Fusion."""

    def __init__(self, chunks: list[dict[str, Any]], *, dim: int = 1024) -> None:
        super().__init__(chunks)
        self.embedder = HashingEmbedder(dim=dim)
        self.doc_fields: list[str] = []
        self.doc_vecs: list[dict[int, float]] = []
        for c in chunks:
            fields = " ".join(
                [c.get("text") or "", c.get("document") or "", " ".join(c.get("topics") or [])]
            )
            self.doc_fields.append(fields)
            self.doc_vecs.append(self.embedder.embed(fields))

    def _crop_filter(self, crop: str | None) -> set[int] | None:
        if not crop:
            return None
        from pipelines.entities import resolve_crop

        crop_id = (resolve_crop(crop) or {}).get("crop_id") or crop
        allowed: set[int] = set()
        for i, c in enumerate(self.chunks):
            if crop_id in (c.get("crop") or []) or crop_id in (c.get("topics") or []):
                allowed.add(i)
        return allowed

    def _bm25_ranks(self, qterms: list[str], allowed: set[int] | None) -> list[int]:
        scored: list[tuple[float, int]] = []
        for i, toks in enumerate(self.doc_tokens):
            if allowed is not None and i not in allowed:
                continue
            tf = Counter(toks)
            dl = self.doc_lens[i] or 1
            score = 0.0
            for q in qterms:
                f = tf.get(q, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                score += self._idf(q) * (f * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: -x[0])
        return [i for _, i in scored]

    def _dense_ranks(self, query: str, allowed: set[int] | None, min_sim: float) -> list[int]:
        qv = self.embedder.embed(expand_query(query))
        scored = [(cosine(qv, self.doc_vecs[i]), i) for i in range(self.n)
                  if (allowed is None or i in allowed)]
        # Drop near-zero similarities (hash-collision noise) below the floor.
        scored = [(s, i) for s, i in scored if s >= min_sim]
        scored.sort(key=lambda x: -x[0])
        return [i for _, i in scored]

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        crop: str | None = None,
        rrf_k: int = 60,
        dense_min: float = 0.12,
    ) -> list[EvidenceHit]:
        allowed = self._crop_filter(crop)
        qterms = [t for t in dict.fromkeys(tokenize(query))]
        bm25_ranks = self._bm25_ranks(qterms, allowed)
        dense_ranks = self._dense_ranks(query, allowed, dense_min)

        # If no ranker matched anything, return nothing (avoids hash-noise spam).
        if not bm25_ranks and not dense_ranks:
            return []

        fused: dict[int, float] = defaultdict(float)
        for i in (bm25_ranks, dense_ranks):
            for rank, doc_id in enumerate(i):
                fused[doc_id] += 1.0 / (rrf_k + rank + 1)

        # Authority score as a deterministic tiebreak (tiny, non-dominant).
        for doc_id in fused:
            fused[doc_id] += 0.0001 * float(self.chunks[doc_id].get("authority_score") or 0.0)

        ranked = sorted(fused.items(), key=lambda x: -x[1])[:top_k]
        return [self._hit(round(score, 4), i) for i, score in ranked]


@lru_cache(maxsize=4)
def _hybrid_index(lake: str) -> HybridIndex:
    """Cached hybrid index per lake path (dense vectors are the dominant cost)."""
    return HybridIndex(load_chunks(Path(lake) if lake else None))


def hybrid_search(
    query: str,
    *,
    top_k: int = 5,
    crop: str | None = None,
    lake: Path | None = None,
) -> list[EvidenceHit]:
    """One-shot hybrid (BM25 ⊕ dense, RRF-fused) evidence search."""
    index = _hybrid_index(str(lake or ""))
    return index.hybrid_search(query, top_k=top_k, crop=crop)


def evidence_for_diagnosis(crop: str, symptoms: str, *, top_k: int = 3, lake: Path | None = None) -> list[EvidenceHit]:
    """Retrieve supporting evidence for a farmer diagnosis (crop + symptoms)."""
    from pipelines.entities import resolve_crop

    crop_row = resolve_crop(crop)
    crop_id = crop_row["crop_id"] if crop_row else None
    query = f"{crop_row['canonical_en'] if crop_row else crop} {symptoms}"
    hits = hybrid_search(query, top_k=max(top_k, 10), crop=crop_id, lake=lake)
    return hits[:top_k]
