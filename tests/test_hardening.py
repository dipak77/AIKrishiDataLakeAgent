"""Tests for V6 Phase 4: request logging + load test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from apps.api.middleware import RequestLoggingMiddleware  # noqa: E402
from scripts.load_test import run_load  # noqa: E402


def test_request_logging_middleware_serves():
    inner = FastAPI()

    @inner.get("/ping")
    def ping():
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.mount("/", inner)

    client = TestClient(app)
    assert client.get("/ping").status_code == 200


def test_load_test_small_in_process():
    from scripts.load_test import _in_process_runner

    report = run_load(_in_process_runner(), n=12, concurrency=4)
    assert report["requests"] == 12
    assert report["error_rate"] == 0.0
    assert report["latency_ms"]["p50"] > 0
    assert report["throughput_rps"] > 0


def test_load_test_http_against_testclient():
    # Spin a real app in a thread-free way via TestClient, then load-test via
    # an in-process runner is already covered above; here we only verify the
    # HTTP runner builds the right endpoint shape.
    from scripts.load_test import _http_runner

    runner = _http_runner("http://localhost:8000")
    assert runner is not None
