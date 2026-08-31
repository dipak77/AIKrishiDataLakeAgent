"""data.gov.in (OGD Platform India) connector.

Generic OGD resource fetch with pagination. Concrete datasets (KCC, Agmarknet)
subclass this and map raw rows to canonical silver records.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("agrilake.connectors.data_gov")

# Public demo key published in data.gov.in API documentation examples.
DEMO_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
BASE_URL = "https://api.data.gov.in"


class DataGovConnector:
    """Mixin providing authenticated access to the OGD Platform API."""

    def api_key(self) -> str:
        return os.environ.get("DATA_GOV_IN_API_KEY") or DEMO_API_KEY

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
        resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "agrilake/0.1"})
        resp.raise_for_status()
        return resp.json()

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
