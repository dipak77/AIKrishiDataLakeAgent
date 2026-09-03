"""Ops middleware (V6 2a) — rate limiting + optional API token. Stdlib only.

Two lightweight ASGI guards, both configurable from the environment so a dev
sandbox stays open while a production deploy can lock down:

  - ``AGRILAKE_API_TOKEN``  — when set, every request must send
    ``Authorization: Bearer <token>`` (or ``X-API-Token``), else 401.
  - ``AGRILAKE_RATE_LIMIT`` — max requests per ``AGRILAKE_RATE_WINDOW`` seconds
    per client (default 120 req / 60 s), else 429.

State is in-memory (single-process); swap for a shared store (Redis) when the
service scales horizontally — the guard functions are the seam for that.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


#: Paths that stay open for load-balancer / k8s probes even when
#: AGRILAKE_API_TOKEN is set. Everything under /api/ still requires auth.
OPEN_PATHS = frozenset({"/health", "/", "/docs", "/openapi.json", "/redoc"})


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class RateLimiter:
    """Sliding-window limiter keyed by client id (IP). Thread-safe."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = max(1, limit)
        self.window_s = float(window_s)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > self.window_s:
                dq.popleft()
            if len(dq) >= self.limit:
                return False
            dq.append(now)
            # Opportunistic sweep: drop idle client buckets so the table
            # cannot grow without bound behind a NAT / scanner (≈1/s amortised).
            if now - self._last_sweep > 60.0:
                cutoff = now - self.window_s
                for k in list(self._hits):
                    q = self._hits[k]
                    while q and q[0] < cutoff:
                        q.popleft()
                    if not q:
                        del self._hits[k]
                self._last_sweep = now
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request) -> str:
    """Best-effort client identity (X-Forwarded-For aware, preview-proxy safe)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_auth(request: Request) -> bool:
    """True when the request is authorized (or auth is disabled).

    Health/docs probes stay open so orchestrators can check liveness without
    a secret. Uses constant-time comparison to avoid timing oracles.
    """
    if request.url.path in OPEN_PATHS:
        return True
    token = os.environ.get("AGRILAKE_API_TOKEN")
    if not token:
        return True
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        return hmac.compare_digest(auth[len("Bearer "):], token)
    presented = request.headers.get("x-api-token") or ""
    return bool(presented) and hmac.compare_digest(presented, token)


class OpsMiddleware(BaseHTTPMiddleware):
    """Auth (401) → rate-limit (429) → downstream."""

    def __init__(self, app: Any, *, rate_limit: int | None = None, window_s: float | None = None) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(
            rate_limit if rate_limit is not None else _env_int("AGRILAKE_RATE_LIMIT", 120),
            window_s if window_s is not None else _env_int("AGRILAKE_RATE_WINDOW", 60),
        )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not check_auth(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        if not self.limiter.allow(client_key(request)):
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(int(self.limiter.window_s))},
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request log: method, path, status, latency (JSON lines)."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        from pipelines.logging import get_json_logger, log_event

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event(
            get_json_logger("krushi-mitra.request"),
            "request",
            method=request.method,
            path=request.url.path,
            status=getattr(response, "status_code", 0),
            elapsed_ms=elapsed_ms,
        )
        return response
