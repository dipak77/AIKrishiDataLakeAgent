"""data.gov.in (OGD Platform India) connector.

Generic OGD resource fetch with pagination. Concrete datasets (KCC, Agmarknet)
subclass this and map raw rows to canonical silver records.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pipelines.http import HttpClient

logger = logging.getLogger("agrilake.connectors.data_gov")

# Public demo key published in data.gov.in API documentation examples.
DEMO_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
BASE_URL = "https://api.data.gov.in"


class DataGovConnector:
    """Mixin providing authenticated access to the OGD Platform API.

    All traffic goes through :class:`pipelines.http.HttpClient`, so the
    connector inherits the platform-wide transport contract: ``live`` |
    ``record`` | ``replay`` | ``offline`` (``AGRILAKE_TRANSPORT``), token-bucket
    throttling, credential redaction and cassette capture for offline tests.
    """

    #: per-instance transport handle (created lazily so tests can inject one)
    _http: HttpClient | None = None

    def http(self) -> HttpClient:
        """Return this connector's mode-aware HTTP client."""
        if self._http is None:
            self._http = HttpClient()
        return self._http

    def api_key(self) -> str:
        from pipelines.config import load_settings

        return load_settings().data_gov_api_key or os.environ.get("DATA_GOV_IN_API_KEY") or DEMO_API_KEY

    def fetch_resource(
        self,
        resource_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
        fmt: str = "json",
        filters: dict[str, Any] | None = None,
        timeout: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "api-key": self.api_key(),
            "format": fmt,
            "offset": offset,
            "limit": limit,
        }
        if filters:
            for key, value in filters.items():
                params[f"filters[{key}]"] = value
        url = f"{BASE_URL}/resource/{resource_id}"
        payload = self.http().get_json(url, params=params, timeout=timeout)
        # OGD answers 200 with an error body for retired/unknown resources
        # ("Meta not found"); that must surface as a failure, never as an
        # empty-but-successful batch (docs/v7-plan.md F1).
        status = str(payload.get("status", "")).strip().lower()
        if status and status != "ok":
            raise LookupError(
                f"resource {resource_id} not available: {payload.get('message') or status}"
            )
        return payload

    def fetch_all(
        self, resource_id: str, *, limit: int = 100, max_records: int = 1000
    ) -> list[dict[str, Any]]:
        """Paginate an OGD resource up to `max_records` rows."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < max_records:
            payload = self.fetch_resource(resource_id, limit=limit, offset=offset)
            batch = payload.get("records") or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return rows[:max_records]
