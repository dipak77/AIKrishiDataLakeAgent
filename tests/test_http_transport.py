"""Tests for the mode-aware HTTP transport (Phase A: pipelines/http.py).

No network: ``replay``/``offline`` modes plus an injected fake session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.http import (  # noqa: E402
    Cassette,
    CassetteEntry,
    CassetteMiss,
    HttpClient,
    HTTPStatusError,
    TokenBucket,
    TransportOffline,
    redact_url,
    url_key,
)

CASSETTE = ROOT / "tests" / "fixtures" / "cassettes" / "goi_agmarknet_daily_mandi_price.json"
RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


# ─────────────────────────── credential hygiene ────────────────────────────


def test_redact_url_strips_credentials():
    redacted = redact_url(f"{RESOURCE_URL}?api-key=supersecret&format=json&limit=1")
    assert "supersecret" not in redacted
    assert "format=json" in redacted and "limit=1" in redacted
    assert "_redacted=1" in redacted


def test_redact_url_handles_token_and_password_params():
    redacted = redact_url("https://x.test/a?token=abc&password=p&user=ok")
    assert "abc" not in redacted and "p&" not in redacted.split("?")[1]
    assert "user=ok" in redacted


def test_url_key_matches_redacted_and_live_forms():
    live = f"{RESOURCE_URL}?api-key=secret&limit=2&format=json"
    recorded = f"{RESOURCE_URL}?format=json&limit=2&_redacted=1"
    assert url_key(live) == url_key(recorded)


# ─────────────────────────── modes ─────────────────────────────────────────


def test_offline_mode_refuses_every_call():
    client = HttpClient(mode="offline")
    with pytest.raises(TransportOffline):
        client.get(f"{RESOURCE_URL}?format=json&limit=1")


def test_replay_mode_serves_recorded_real_payload():
    client = HttpClient(mode="replay", cassette_dir=CASSETTE.parent)
    resp = client.get(f"{RESOURCE_URL}?api-key=x&format=json&limit=2")
    assert resp.status == 200 and resp.from_cassette
    payload = resp.json()
    # these values come from the live response recorded on 2026-09-02
    assert payload["total"] == 17800
    assert payload["updated_date"] == "2026-09-02T17:01:08Z"
    assert payload["records"][0]["arrival_date"] == "02/09/2026"
    assert "supersecret" not in resp.text and "api-key" not in resp.url


def test_replay_mode_raises_on_missing_cassette(tmp_path):
    client = HttpClient(mode="replay", cassette_dir=tmp_path)
    with pytest.raises(CassetteMiss):
        client.get("https://no-such-host.invalid/x?format=json")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        HttpClient(mode="telepathy")


def test_live_mode_uses_injected_session_and_raises_on_4xx():
    class FakeResponse:
        status_code = 404
        headers = {"Content-Type": "application/json"}
        text = '{"error": "not found"}'

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, timeout=None, headers=None):
            self.calls.append(url)
            return FakeResponse()

    session = FakeSession()
    client = HttpClient(mode="live", session=session, rps=1000, burst=100)
    with pytest.raises(HTTPStatusError) as excinfo:
        client.get("https://x.test/missing")
    assert excinfo.value.status == 404
    assert len(session.calls) == 1


def test_record_mode_writes_a_redacted_cassette(tmp_path):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = '{"ok": true}'

    class FakeSession:
        def get(self, url, timeout=None, headers=None):
            return FakeResponse()

    client = HttpClient(mode="record", cassette_dir=tmp_path, session=FakeSession(), rps=1000)
    client.get("https://x.test/data?api-key=secret&format=json")

    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    raw = written[0].read_text(encoding="utf-8")
    assert "secret" not in raw
    data = json.loads(raw)
    assert data["schema"] == "agrilake.cassette/v1"
    assert data["entries"][0]["status"] == 200

    # and the recording is replayable
    replay = HttpClient(mode="replay", cassette_dir=tmp_path)
    assert replay.get("https://x.test/data?api-key=other&format=json").json() == {"ok": True}


# ─────────────────────────── rate limiting ─────────────────────────────────


def test_token_bucket_limits_burst_then_refills():
    clock = {"t": 0.0}
    bucket = TokenBucket(rps=2.0, burst=2, clock=lambda: clock["t"])
    assert bucket.acquire(block=False) is True
    assert bucket.acquire(block=False) is True
    assert bucket.acquire(block=False) is False     # burst exhausted
    clock["t"] += 1.0                               # 1s at 2 rps => 2 tokens
    assert bucket.acquire(block=False) is True
    assert bucket.acquire(block=False) is True


def test_token_bucket_rejects_invalid_rate():
    with pytest.raises(ValueError):
        TokenBucket(rps=0)


def test_client_applies_bucket_before_live_call():
    class FakeResponse:
        status_code = 200
        headers = {}
        text = "{}"

    class FakeSession:
        def get(self, url, timeout=None, headers=None):
            return FakeResponse()

    client = HttpClient(mode="live", session=FakeSession(), rps=1000, burst=5)
    for _ in range(3):
        client.get("https://x.test/a")
    assert len(client.calls) == 3
    assert client.calls[0]["status"] == 200


# ─────────────────────────── cassette file handling ────────────────────────


def test_cassette_roundtrip_and_dedupe(tmp_path):
    path = tmp_path / "c.json"
    cas = Cassette(path=path)
    entry = CassetteEntry("https://x.test/a?k=1", "GET", 200, {}, "{}", "2026-09-02T00:00:00+00:00")
    cas.append(entry)
    cas.append(entry)                      # same URL replaces, never duplicates
    cas.save()
    reloaded = Cassette.load(path)
    assert len(reloaded.entries) == 1
    assert reloaded.find("https://x.test/a?k=1") is not None
    assert reloaded.find("https://x.test/a?k=2") is None


def test_cassette_missing_file_raises(tmp_path):
    with pytest.raises(CassetteMiss):
        Cassette.load(tmp_path / "nope.json")


def test_cassette_corrupt_payload_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    from pipelines.http import CassetteCorrupt

    with pytest.raises(CassetteCorrupt):
        Cassette.load(path)


def test_committed_agmarknet_cassette_is_well_formed():
    cas = Cassette.load(CASSETTE)
    assert len(cas.entries) == 2
    for entry in cas.entries:
        assert entry.status == 200
        assert "api-key" not in entry.request_url
        payload = json.loads(entry.body)
        assert payload["status"] == "ok"
        assert {f["id"] for f in payload["field"]} >= {"arrival_date", "modal_price"}
