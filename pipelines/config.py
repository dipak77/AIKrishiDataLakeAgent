"""Auto-configuration for the lake.

Settings resolve from three layers, highest priority first:

  1. environment variables (``AGRILAKE_*``)
  2. a ``.env`` file in the repo root (plain ``KEY=VALUE`` lines — parsed here,
     no external dependency, and never written back)
  3. built-in defaults

``detect_capabilities()`` additionally reports which *optional* inputs are
available (API keys, optional Python packages, network reachability) so callers
can degrade gracefully instead of crashing.
"""

from __future__ import annotations

import importlib.util
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


# env var → (Settings attribute, type)  — used by the generic resolver.
_ENV_MAP: dict[str, tuple[str, type]] = {
    "AGRILAKE_DATA_DIR": ("data_dir", Path),
    "AGRILAKE_LOG_LEVEL": ("log_level", str),
    "AGRILAKE_HTTP_TIMEOUT": ("http_timeout", float),
    "AGRILAKE_HTTP_RETRIES": ("http_retries", int),
    "AGRILAKE_DATA_GOV_API_KEY": ("data_gov_api_key", str),
    "AGRILAKE_FAOSTAT_BASE_URL": ("faostat_base_url", str),
    "AGRILAKE_IMD_API_KEY": ("imd_api_key", str),
    "AGRILAKE_OFFLINE": ("offline_mode", _bool),
}

# Optional packages whose presence enables extra capabilities.
_OPTIONAL_PACKAGES: dict[str, str] = {
    "duckdb": "lakehouse + reasoning",
    "pydantic": "schema validation",
    "requests": "live ingestion",
    "pytest": "test suite",
}


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    log_level: str = "INFO"
    http_timeout: float = 20.0
    http_retries: int = 3
    data_gov_api_key: str | None = None
    faostat_base_url: str = "https://fenixservices.fao.org/faostat/api/v1"
    imd_api_key: str | None = None
    offline_mode: bool = False

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def lake_dir(self) -> Path:
        return self.data_dir / "lake"


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines (comments + blanks ignored; quotes stripped)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        # Inline comments only when preceded by whitespace (avoids stripping URLs).
        value = value.split(" #", 1)[0].split("\t#", 1)[0].rstrip()
        out[key.strip()] = value
    return out


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    path = path or DEFAULT_ENV_FILE
    if not path.is_file():
        return {}
    return parse_dotenv(path.read_text(encoding="utf-8"))


def load_settings(env_file: Path | None = None, environ: dict[str, str] | None = None) -> Settings:
    """Resolve settings: defaults ← .env ← environment (env wins)."""
    env_file = env_file or DEFAULT_ENV_FILE
    env = dict(os.environ if environ is None else environ)

    values: dict[str, Any] = {}
    for env_key, (attr, cast) in _ENV_MAP.items():
        raw = env.get(env_key) or load_dotenv(env_file).get(env_key)
        if raw in (None, ""):
            continue
        try:
            values[attr] = cast(raw)
        except (ValueError, TypeError):
            values[attr] = raw  # keep as-is; the dataclass default guards types

    return Settings(**values)


def _optional_packages() -> dict[str, bool]:
    return {
        name: importlib.util.find_spec(name) is not None
        for name in _OPTIONAL_PACKAGES
    }


def probe_network(host: str = "api.data.gov.in", port: int = 443, timeout: float = 2.0) -> bool:
    """Best-effort reachability probe. Returns False on any failure (incl. blocked egress)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_capabilities(settings: Settings | None = None, *, probe_net: bool = False) -> dict[str, Any]:
    """Report which optional inputs are available (no exceptions raised)."""
    settings = settings or load_settings()
    return {
        "data_gov_key": bool(settings.data_gov_api_key),
        "imd_key": bool(settings.imd_api_key),
        "offline_mode": settings.offline_mode,
        "optional_packages": _optional_packages(),
        "network": probe_network() if probe_net else None,
    }


def describe(settings: Settings | None = None) -> str:
    """Human-readable single-line summary of the active configuration."""
    settings = settings or load_settings()
    key = "yes" if settings.data_gov_api_key else "no"
    return (
        f"data_dir={settings.data_dir} log={settings.log_level} "
        f"retries={settings.http_retries} timeout={settings.http_timeout}s "
        f"data.gov.in key={key} offline={settings.offline_mode}"
    )
