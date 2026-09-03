"""Tests for V6 2a: connection reuse, pre-warm, rate limit + auth middleware."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from apps.api.middleware import OpsMiddleware, RateLimiter, check_auth  # noqa: E402
from pipelines.storage import clear_connection_cache, get_read_connection  # noqa: E402
from reasoning.warmup import prewarm  # noqa: E402


# ─────────────────────────── connection reuse ──────────────────────────────


def test_connection_reuse_same_thread():
    clear_connection_cache()
    lake = ROOT / "data" / "lake" / "agrilake.duckdb"
    a = get_read_connection(lake)
    b = get_read_connection(lake)
    assert a is b, "same thread + lake path must reuse one connection"


def test_connection_cache_distinct_paths(tmp_path):
    import duckdb

    clear_connection_cache()
    lake = ROOT / "data" / "lake" / "agrilake.duckdb"
    other = tmp_path / "other.duckdb"
    con = duckdb.connect(str(other))
    con.execute("CREATE TABLE t(x INT)")
    con.close()

    a = get_read_connection(lake)
    b = get_read_connection(other)
    assert a is not b
    assert b.execute("SELECT count(*) FROM t").fetchone()[0] == 0


def test_connection_missing_lake_raises(tmp_path):
    clear_connection_cache()
    with pytest.raises(Exception):
        get_read_connection(tmp_path / "nope.duckdb")


def test_connection_reuse_after_clear():
    clear_connection_cache()
    lake = ROOT / "data" / "lake" / "agrilake.duckdb"
    a = get_read_connection(lake)
    clear_connection_cache()
    b = get_read_connection(lake)
    assert a is not b


# ─────────────────────────── pre-warm ──────────────────────────────────────


def test_prewarm_returns_report():
    report = prewarm()
    for key in ("nlu_ms", "rag_ms", "graph_ms", "advisory_ms", "total_ms"):
        assert key in report, f"missing prewarm step: {key}"
    assert report["total_ms"] >= 0


def test_prewarm_is_idempotent():
    first = prewarm()
    second = prewarm()
    assert second["total_ms"] <= first["total_ms"] + 50


# ─────────────────────────── rate limiter ──────────────────────────────────


def test_rate_limiter_allows_under_limit():
    rl = RateLimiter(limit=3, window_s=60)
    assert rl.allow("a") and rl.allow("a") and rl.allow("a")
    assert not rl.allow("a")


def test_rate_limiter_keys_are_isolated():
    rl = RateLimiter(limit=1, window_s=60)
    assert rl.allow("a")
    assert not rl.allow("a")
    assert rl.allow("b")


def test_rate_limiter_reset():
    rl = RateLimiter(limit=1, window_s=60)
    assert rl.allow("a")
    assert not rl.allow("a")
    rl.reset()
    assert rl.allow("a")


# ─────────────────────────── auth token ────────────────────────────────────


def test_auth_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGRILAKE_API_TOKEN", raising=False)
    from starlette.requests import Request

    req = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    assert check_auth(req) is True


def test_auth_requires_token_when_set(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setenv("AGRILAKE_API_TOKEN", "secret")
    good = Request(
        {"type": "http", "headers": [(b"authorization", b"Bearer secret")], "method": "GET", "path": "/api/query"}
    )
    bad = Request({"type": "http", "headers": [], "method": "GET", "path": "/api/query"})
    assert check_auth(good) is True
    assert check_auth(bad) is False


def test_auth_leaves_probes_open_when_set(monkeypatch):
    """Liveness probes stay reachable without a secret (k8s/LB health checks)."""
    from starlette.requests import Request

    monkeypatch.setenv("AGRILAKE_API_TOKEN", "secret")
    for open_path in ("/health", "/"):
        req = Request({"type": "http", "headers": [], "method": "GET", "path": open_path})
        assert check_auth(req) is True


# ─────────────────────────── middleware integration ────────────────────────


def test_ops_middleware_rate_limit_429():
    inner = FastAPI()

    @inner.get("/ping")
    def ping():
        return {"ok": True}

    guarded = FastAPI()
    guarded.add_middleware(OpsMiddleware, rate_limit=2, window_s=60)
    guarded.mount("/", inner)  # mount so the middleware wraps the inner routes

    client = TestClient(guarded)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_read_write_after_read_connection(tmp_path):
    """DuckDB forbids mixed-config opens; write path must clear the read cache."""
    import duckdb

    from pipelines.storage import get_read_connection, read_write_connection

    lake = tmp_path / "mixed.duckdb"
    # create + populate read-write
    w = read_write_connection(lake)
    w.execute("CREATE TABLE t(x INT)")
    w.execute("INSERT INTO t VALUES (1)")
    w.close()

    # open a cached read-only connection, then a read-write one (must not error)
    r = get_read_connection(lake)
    assert r.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    w2 = read_write_connection(lake)
    assert w2.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    w2.execute("INSERT INTO t VALUES (2)")
    w2.close()


def test_ensure_graph_tables_idempotent_after_read():
    """ensure_graph_tables must work even after a cached read conn is open."""
    from pipelines.storage import get_read_connection
    from reasoning.graph_query import ensure_graph_tables, graph_summary

    get_read_connection()  # leave a cached read-only handle open
    ensure_graph_tables()
    s = graph_summary()
    assert s["nodes"] > 0
