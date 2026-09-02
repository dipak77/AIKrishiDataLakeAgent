"""HTTP transport with four explicit modes: ``live | record | replay | offline``.

Production ingestion must be verifiable in environments with no egress. The
only honest way to do that is to run connectors against **recorded** payloads
that were captured from the real endpoint, rather than against hand-written
fixtures that quietly flatter the pipeline (see `docs/v7-plan.md` F4/F8).

Modes
-----
``live``     Real HTTP. Requires network + credentials.
``record``   Real HTTP, and persist the response as a cassette for CI.
``replay``   Serve from a cassette. A missing cassette is an **error** — it
             never silently falls back to the network or to a fixture.
``offline``  No network, no cassette: every call raises ``TransportOffline``.

Every cassette stores the **redacted** request URL (credential query params
stripped) plus status, headers, body and capture time, so a recorded response
can be audited and diffed in git.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger("agrilake.http")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASSETTE_DIR = REPO_ROOT / "tests" / "fixtures" / "cassettes"

MODES = ("live", "record", "replay", "offline")

# Query parameters that must never be written into a cassette or a log line.
SECRET_PARAMS = frozenset(
    {"api-key", "api_key", "apikey", "key", "token", "access_token", "password", "secret", "signature"}
)


class TransportError(Exception):
    """Base class for transport failures."""


class TransportOffline(TransportError):
    """Raised when a call is attempted while ``mode='offline'``."""


class CassetteMiss(TransportError):
    """Raised in replay mode when no recorded response exists for a URL."""


class CassetteCorrupt(TransportError):
    """Raised when a cassette cannot be parsed."""


class HTTPStatusError(TransportError):
    """A non-2xx HTTP response, carrying the status for retry decisions."""

    def __init__(self, status: int, url: str = "", message: str = "", retry_after: float | None = None) -> None:
        self.status = int(status)
        self.url = url
        self.retry_after = retry_after
        super().__init__(message or f"HTTP {self.status} for {url}")


# ─────────────────────────── url hygiene ───────────────────────────────────


def redact_url(url: str) -> str:
    """Strip credential-bearing query params from a URL (for logs + cassettes)."""""
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in SECRET_PARAMS]
    dropped = len(parse_qsl(parts.query, keep_blank_values=True)) - len(kept)
    query = urlencode(kept)
    if dropped:
        query = f"{query}&_redacted={dropped}" if query else f"_redacted={dropped}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


#: query params whose zero/blank value means "the default page" — requesting
#: ``offset=0`` and omitting ``offset`` are the same call upstream, so they must
#: share one cassette key (otherwise a recording made by one call site can never
#: be replayed by another).
_DEFAULT_VALUED_PARAMS = {"offset": ("0", "")}


def url_key(url: str) -> str:
    """Stable cassette lookup key: scheme+host+path+sorted credential-free query.

    The ``_redacted`` marker added by :func:`redact_url` is excluded, so a
    recorded (redacted) URL and the live URL that produced it share one key.
    """
    parts = urlsplit(url)
    pairs = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in SECRET_PARAMS
        and k.lower() != "_redacted"
        and v not in _DEFAULT_VALUED_PARAMS.get(k.lower(), ())
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))


# ─────────────────────────── rate limiting ─────────────────────────────────


class TokenBucket:
    """Thread-safe token bucket: at most ``rps`` calls/second with a burst.

    Used as a *client-side* rate limit so a shared/low-quota upstream key (the
    data.gov.in demo key returns ``Rate limit exceeded`` after a handful of
    calls) cannot be exhausted by a bulk run.
    """

    def __init__(self, rps: float = 1.0, burst: int = 5, clock: Any = time.monotonic) -> None:
        if rps <= 0:
            raise ValueError("rps must be > 0")
        self.rps = float(rps)
        self.capacity = max(1, int(burst))
        self._clock = clock
        self._tokens = float(self.capacity)
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(float(self.capacity), self._tokens + elapsed * self.rps)
        self._updated = now

    def acquire(self, block: bool = True) -> bool:
        """Take one token, sleeping if necessary. Returns False if non-blocking."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            if not block:
                return False
            wait = (1.0 - self._tokens) / self.rps
        time.sleep(max(wait, 0.0))
        with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)
        return True

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


# ─────────────────────────── cassettes ─────────────────────────────────────


@dataclass(frozen=True)
class CassetteEntry:
    """One recorded request/response pair."""

    request_url: str          # redacted
    method: str
    status: int
    headers: dict[str, str]
    body: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Cassette:
    """A file of recorded exchanges (``.json`` or ``.json.gz``)."""

    path: Path
    entries: list[CassetteEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Cassette":
        path = Path(path)
        if not path.is_file():
            raise CassetteMiss(f"cassette not found: {path}")
        raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CassetteCorrupt(f"{path}: {exc}") from exc
        rows = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise CassetteCorrupt(f"{path}: expected a list of entries")
        return cls(path=path, entries=[CassetteEntry(**row) for row in rows])

    def save(self) -> Path:
        payload = {
            "schema": "agrilake.cassette/v1",
            "note": "Recorded live responses. Request URLs are redacted of credentials.",
            "entries": [e.to_dict() for e in self.entries],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        data = text.encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.suffix == ".gz":
            self.path.write_bytes(gzip.compress(data))
        else:
            self.path.write_bytes(data)
        return self.path

    def find(self, url: str) -> CassetteEntry | None:
        key = url_key(url)
        for entry in self.entries:
            if url_key(entry.request_url) == key:
                return entry
        return None

    def append(self, entry: CassetteEntry) -> None:
        key = url_key(entry.request_url)
        self.entries = [e for e in self.entries if url_key(e.request_url) != key]
        self.entries.append(entry)


# ─────────────────────────── response + client ─────────────────────────────


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    text: str
    url: str
    from_cassette: bool = False

    def json(self) -> Any:
        return json.loads(self.text)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpClient:
    """Mode-aware HTTP client with throttling, redaction and cassette I/O.

    ``session`` may be injected for tests; it only needs ``.get(url, ...)``
    returning an object with ``status_code``/``headers``/``text``.
    """

    def __init__(
        self,
        mode: str | None = None,
        *,
        cassette_dir: Path | None = None,
        cassette: Cassette | None = None,
        rps: float = 1.0,
        burst: int = 5,
        timeout: float = 20.0,
        user_agent: str = "agrilake/0.7 (production ingestion)",
        session: Any = None,
    ) -> None:
        mode = (mode or os.environ.get("AGRILAKE_TRANSPORT") or "live").strip().lower()
        if mode not in MODES:
            raise ValueError(f"unknown transport mode {mode!r}; expected one of {MODES}")
        self.mode = mode
        self.cassette_dir = Path(cassette_dir or DEFAULT_CASSETTE_DIR)
        self.cassette = cassette
        self.bucket = TokenBucket(rps=rps, burst=burst)
        self.timeout = float(timeout)
        self.user_agent = user_agent
        self._session = session
        self.calls: list[dict[str, Any]] = []   # per-client audit trail (tests + run ledger)

    # ── public API ─────────────────────────────────────────────────────────
    def get(self, url: str, *, params: dict[str, Any] | None = None, timeout: float | None = None) -> Response:
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode({k: v for k, v in params.items() if v is not None})}"

        if self.mode == "offline":
            raise TransportOffline(f"transport=offline; refusing to call {redact_url(url)}")
        if self.mode == "replay":
            return self._replay(url)

        self.bucket.acquire()
        started = time.perf_counter()
        resp = self._live_get(url, timeout or self.timeout)
        self.calls.append(
            {
                "url": redact_url(url),
                "status": resp.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": len(resp.text or ""),
            }
        )
        if self.mode == "record":
            self._write_cassette(url, resp)
        return resp

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    # ── internals ──────────────────────────────────────────────────────────
    def _replay(self, url: str) -> Response:
        cassette = self._active_cassette(url)
        entry = cassette.find(url)
        if entry is None:
            raise CassetteMiss(
                f"no recorded response for {redact_url(url)} in {cassette.path.name}; "
                "re-record with AGRILAKE_TRANSPORT=record in a networked environment"
            )
        return Response(entry.status, dict(entry.headers), entry.body, entry.request_url, from_cassette=True)

    def _active_cassette(self, url: str) -> Cassette:
        if self.cassette is not None:
            return self.cassette
        candidates = sorted(self.cassette_dir.glob("*.json")) + sorted(self.cassette_dir.glob("*.json.gz"))
        for path in candidates:
            cassette = Cassette.load(path)
            if cassette.find(url) is not None:
                self.cassette = cassette
                return cassette
        raise CassetteMiss(
            f"no cassette in {self.cassette_dir} matches {redact_url(url)}"
        )

    def _write_cassette(self, url: str, resp: Response) -> None:
        from pipelines.storage import utcnow_iso

        cassette = self.cassette or Cassette(path=self.cassette_dir / "recorded.json")
        cassette.append(
            CassetteEntry(
                request_url=redact_url(url),
                method="GET",
                status=resp.status,
                headers={k: v for k, v in resp.headers.items()},
                body=resp.text,
                recorded_at=utcnow_iso(),
            )
        )
        cassette.save()
        self.cassette = cassette
        logger.info("recorded cassette entry for %s", redact_url(url))

    def _live_get(self, url: str, timeout: float) -> Response:
        import requests  # imported lazily: replay/offline need no HTTP stack

        session = self._session or requests
        headers = {"User-Agent": self.user_agent}
        resp = session.get(url, timeout=timeout, headers=headers)
        status = int(getattr(resp, "status_code", 0))
        text = getattr(resp, "text", "") or ""
        raw_headers = dict(getattr(resp, "headers", {}) or {})
        if status >= 400:
            raise HTTPStatusError(
                status,
                url=redact_url(url),
                retry_after=_retry_after(raw_headers),
                message=f"HTTP {status} for {redact_url(url)}",
            )
        return Response(status, raw_headers, text, redact_url(url))


def _retry_after(headers: dict[str, str]) -> float | None:
    """Parse a ``Retry-After`` header (seconds form) if present."""
    for key, value in (headers or {}).items():
        if key.lower() == "retry-after":
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return None
    return None
