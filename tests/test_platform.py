"""Tests for Phase 3 platform: auto-config, retry, atomic IO, idempotent seed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain import seed_data as sd  # noqa: E402
from pipelines import config  # noqa: E402
from pipelines import retry  # noqa: E402
from pipelines.storage import (  # noqa: E402
    LAKE_DIR,
    content_hash,
    write_json,
    write_jsonl,
)
from scripts.seed_lake import SEED_SCHEMA_VERSION, seed_fingerprint  # noqa: E402


# ── auto-configuration ──────────────────────────────────────────────────────
def test_parse_dotenv():
    parsed = config.parse_dotenv(
        """
        # comment
        AGRILAKE_HTTP_RETRIES=5
        AGRILAKE_FAOSTAT_BASE_URL="https://mirror.example/api"
        KEY_WITH_SPACE = value with spaces
        BLANK=
        """
    )
    assert parsed["AGRILAKE_HTTP_RETRIES"] == "5"
    assert parsed["AGRILAKE_FAOSTAT_BASE_URL"] == "https://mirror.example/api"
    assert parsed["KEY_WITH_SPACE"] == "value with spaces"
    assert "BLANK" not in parsed or parsed["BLANK"] == ""


def test_load_settings_env_beats_dotenv():
    # .env supplies data.gov key; the explicit env var wins.
    settings = config.load_settings(
        environ={
            "AGRILAKE_HTTP_RETRIES": "7",
            "AGRILAKE_OFFLINE": "1",
        }
    )
    assert settings.http_retries == 7
    assert settings.offline_mode is True
    assert settings.data_dir == config.REPO_ROOT / "data"


def test_load_settings_defaults():
    settings = config.Settings()
    assert settings.http_retries == 3
    assert settings.log_level == "INFO"
    assert settings.faostat_base_url.startswith("https://fenixservices")


def test_detect_capabilities_no_exceptions():
    caps = config.detect_capabilities(config.load_settings(), probe_net=False)
    assert "optional_packages" in caps
    assert isinstance(caps["data_gov_key"], bool)
    assert caps["network"] is None  # not probed by default


# ── retry ───────────────────────────────────────────────────────────────────
def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert retry.retry_call(flaky, retries=5, backoff=0.01, jitter=0.0) == "ok"
    assert calls["n"] == 3


def test_retry_raises_after_exhaustion():
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError):
        retry.retry_call(always_fails, retries=2, backoff=0.01, jitter=0.0)
    assert calls["n"] == 3  # 1 initial + 2 retries


# ── atomic IO ───────────────────────────────────────────────────────────────
def test_atomic_write_leaves_no_tmp(tmp_path):
    target = tmp_path / "sub" / "report.json"
    write_json(target, {"ok": True})
    assert target.is_file()
    assert list(tmp_path.rglob("*.tmp")) == []


def test_write_jsonl_roundtrip(tmp_path):
    path = tmp_path / "rec.jsonl"
    write_jsonl(path, [{"a": 1}, {"b": "नमस्ते"}])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"a": 1' in lines[0]


# ── idempotent seed fingerprint ─────────────────────────────────────────────
def test_seed_fingerprint_stable():
    assert seed_fingerprint() == seed_fingerprint()
    assert len(seed_fingerprint()) == 64  # sha256 hex


def test_seed_fingerprint_tracks_source():
    src = Path(sd.__file__)
    assert content_hash(src.read_bytes() + SEED_SCHEMA_VERSION.encode()) == seed_fingerprint()


def test_lake_dir_constant():
    assert LAKE_DIR.name == "lake"
