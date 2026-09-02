"""Retry with exponential backoff + jitter, and HTTP-status awareness.

Used by the connector base class so a transient API 5xx / timeout does not kill
an ingestion run. Safe to import anywhere — pure stdlib.

Two production rules are enforced here (see `docs/v7-plan.md` F11):

* **Never retry a client error.** A 401/403/404 means the request is wrong or
  unauthorised; hammering it wastes quota and hides the real failure. Only
  408/425/429/5xx (and status-less network errors) are retried.
* **Honour ``Retry-After``.** When the upstream tells us how long to wait, that
  value wins over the exponential schedule.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.0      # seconds; doubles each attempt
DEFAULT_MAX_BACKOFF = 30.0
DEFAULT_JITTER = 0.25      # ± fraction applied to the sleep
DEFAULT_MAX_RETRY_AFTER = 120.0

#: HTTP statuses that are worth retrying. Anything else (400/401/403/404/422…)
#: is a *client* error and fails fast.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def http_status(exc: BaseException) -> int | None:
    """Best-effort extraction of an HTTP status code from an exception.

    Understands our own :class:`pipelines.http.HTTPStatusError`, ``requests``
    ``HTTPError``/``Response``, and anything exposing ``status_code``/``status``.
    Returns ``None`` when the exception carries no HTTP status (e.g. a timeout
    or a DNS failure), which callers treat as retryable.
    """
    for attr in ("status", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if isinstance(value, int) and 100 <= value <= 599:
                return value
    return None


def retry_after_seconds(exc: BaseException) -> float | None:
    """Extract a server-requested wait (``Retry-After``) from an exception."""
    value = getattr(exc, "retry_after", None)
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    for key, raw in dict(headers).items():
        if str(key).lower() == "retry-after":
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                return None
    return None


def retry_call(
    fn: Callable[..., T],
    *args: Any,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    jitter: float = DEFAULT_JITTER,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    logger: logging.Logger | None = None,
    retry_on_status: frozenset[int] | set[int] | None = RETRYABLE_STATUS,
    honor_retry_after: bool = True,
    max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
    on_retry: Callable[[dict[str, Any]], None] | None = None,
    **kwargs: Any,
) -> T:
    """Call ``fn(*args, **kwargs)``, retrying only on retryable failures.

    Sleeps ``backoff * 2**attempt`` seconds (capped at ``max_backoff``) with a
    random ±``jitter`` fraction to avoid thundering herds, unless the server
    sent ``Retry-After``. Raises the last exception if every attempt fails, and
    raises immediately for non-retryable HTTP statuses.
    """
    logger = logger or logging.getLogger("agrilake.retry")
    attempt = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except exceptions as exc:  # noqa: PERF203 - retry loop
            status = http_status(exc)
            if status is not None and retry_on_status is not None and status not in retry_on_status:
                logger.warning(
                    "Not retrying HTTP %d (client error): %s", status, exc
                )
                raise

            attempt += 1
            if attempt > retries:
                logger.warning("Giving up after %d attempts: %s", attempt, exc)
                raise

            delay = min(backoff * (2 ** (attempt - 1)), max_backoff)
            delay *= 1.0 + random.uniform(-jitter, jitter)
            retry_after = retry_after_seconds(exc) if honor_retry_after else None
            if retry_after is not None:
                delay = max(delay, min(retry_after, max_retry_after))

            info = {
                "attempt": attempt,
                "retries": retries,
                "status": status,
                "error": f"{type(exc).__name__}: {exc}",
                "delay_s": round(max(delay, 0.0), 3),
                "retry_after_s": retry_after,
            }
            logger.info(
                "Attempt %d/%d failed (%s); retrying in %.2fs",
                attempt, retries + 1, info["error"], max(delay, 0.0),
            )
            if on_retry is not None:
                on_retry(info)
            time.sleep(max(delay, 0.0))
