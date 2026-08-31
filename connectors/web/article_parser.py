"""HTML → article → attributed RAG chunks.

Store knowledge, not unlicensed copies. For copyrighted pages prefer
facts + short semantic chunks + source linking.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from pipelines.entities import extract_crops
from pipelines.language import detect_language

logger = logging.getLogger("agrilake.connectors.article_parser")

_BOILERPLATE = re.compile(
    r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<nav\b[^>]*>.*?</nav>|"
    r"<footer\b[^>]*>.*?</footer>|<header\b[^>]*>.*?</header>",
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s{2,}")


@dataclass
class ExtractedArticle:
    url: str
    title: str
    text: str
    language: str
    crops: list[dict[str, Any]] = field(default_factory=list)
    publisher: str | None = None
    author: str | None = None
    published_date: str | None = None


class ArticleParser:
    def extract(self, html: str, url: str) -> ExtractedArticle:
        html = _BOILERPLATE.sub(" ", html)
        title = self._meta(html, "og:title") or self._title(html) or ""
        author = self._meta(html, "author")
        published = (
            self._meta(html, "article:published_time") or self._meta(html, "datePublished")
        )
        text = _WS.sub(" ", _TAG.sub(" ", html)).strip()
        lang = detect_language(text)["language"]
        return ExtractedArticle(
            url=url,
            title=title.strip(),
            text=text,
            language=lang,
            crops=extract_crops(text),
            publisher=urlparse(url).netloc,
            author=author,
            published_date=published,
        )

    def to_rag_chunks(
        self,
        article: ExtractedArticle,
        *,
        license_value: str | None,
        copyright_status: str,
        retrieved_date: str,
        max_chars: int = 1000,
    ) -> list[dict[str, Any]]:
        """Attributed RAG chunks with full provenance + content hash."""
        chunks: list[dict[str, Any]] = []
        text = article.text
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for i in range(0, len(text), max_chars):
            piece = text[i : i + max_chars].strip()
            if not piece:
                continue
            chunks.append(
                {
                    "chunk_id": hashlib.sha256(piece.encode("utf-8")).hexdigest()[:16],
                    "source_url": article.url,
                    "publisher": article.publisher,
                    "author": article.author,
                    "title": article.title,
                    "published_date": article.published_date,
                    "retrieved_date": retrieved_date,
                    "license": license_value,
                    "copyright_status": copyright_status,
                    "content_hash": content_hash,
                    "language": article.language,
                    "crop": [c["crop_id"] for c in article.crops],
                    "topics": [c["canonical_en"] for c in article.crops],
                    "text": piece,
                }
            )
        return chunks

    @staticmethod
    def _meta(html: str, key: str) -> str | None:
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
            html,
            re.IGNORECASE,
        )
        return m.group(1) if m else None

    @staticmethod
    def _title(html: str) -> str | None:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return _WS.sub(" ", _TAG.sub(" ", m.group(1))).strip() if m else None
