"""Respectful web crawler: robots.txt + license gate before fetching.

Pipeline:
    URL discovered → robots/terms/license check → HTML → boilerplate removal →
    article extraction → language detection → agri entity extraction → claims →
    source attribution → RAG chunks
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from connectors.web.license_checker import LicenseChecker, LicenseClass

logger = logging.getLogger("agrilake.connectors.crawler")


class WebCrawler:
    def __init__(self, *, user_agent: str = "agrilake/0.1 (+contact)", delay: float = 1.0) -> None:
        self.user_agent = user_agent
        self.delay = delay
        self.license_checker = LicenseChecker()
        self._robots_cache: dict[str, RobotFileParser] = {}

    def robots_allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots_cache:
            rp = RobotFileParser()
            rp.set_url(urljoin(f"https://{host}/", "/robots.txt"))
            try:
                rp.read()
            except Exception:  # noqa: BLE001 - assume disallowed on failure
                logger.warning("robots.txt unavailable for %s", host)
                return False
            self._robots_cache[host] = rp
        return self._robots_cache[host].can_fetch(self.user_agent, url)

    def fetch(self, url: str, declared_license: str | None = None) -> dict[str, Any]:
        decision = self.license_checker.classify(url, declared_license)
        if decision.decision is LicenseClass.BLOCK:
            return {"ok": False, "reason": decision.reason, "decision": decision.decision}
        if decision.decision is LicenseClass.REVIEW:
            logger.info("URL requires review: %s (%s)", url, decision.reason)
        if not self.robots_allowed(url):
            return {"ok": False, "reason": "robots.txt disallows", "decision": LicenseClass.BLOCK}
        time.sleep(self.delay)
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": self.user_agent})
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"fetch failed: {type(exc).__name__}", "decision": decision.decision}
        return {
            "ok": True,
            "url": url,
            "status": resp.status_code,
            "content_type": resp.headers.get("content-type"),
            "html": resp.text,
            "license_decision": decision.decision,
        }
