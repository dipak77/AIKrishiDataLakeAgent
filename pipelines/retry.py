"""Retry with exponential backoff + jitter for flaky network / IO calls.

Used by the connector base class so a transient API 5xx / timeout does not
kill an ingestion run. Safe to import anywhere — pure stdlib.
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


def retry_call(
    fn: Callable[..., T],
    *args: Any,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    jitter: float = DEFAULT_JITTER,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> T:
    """Call ``fn(*args, **kwargs)``, retrying on ``exceptions``.

    Sleeps ``backoff * 2**attempt`` seconds (capped at ``max_backoff``) with a
    random ±``jitter`` fraction to avoid thundering herds. Raises the last
    exception if every attempt fails.
    """
    logger = logger or logging.getLogger("agrilake.retry")
    attempt = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except exceptions as exc:  # noqa: PERF203 - retry loop
            attempt += 1
            if attempt > retries:
                logger.warning("Giving up after %d attempts: %s", attempt, exc)
                raise
            delay = min(backoff * (2 ** (attempt - 1)), max_backoff)
            delay *= 1.0 + random.uniform(-jitter, jitter)
            logger.info(
                "Attempt %d/%d failed (%s: %s); retrying in %.2fs",
                attempt, retries + 1, type(exc).__name__, exc, max(delay, 0.0),
            )
            time.sleep(max(delay, 0.0))
