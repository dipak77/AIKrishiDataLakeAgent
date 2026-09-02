"""Tests for Track 14/15: Krushi Mitra REST API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import app  # noqa: E402
from scripts.seed_lake import main as seed_main  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if not (ROOT / "data" / "lake" / "agrilake.duckdb").exists():
        seed_main(["--no-parquet"])
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["lake"]["nodes"] > 0


def test_web_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Krushi Mitra" in r.text


def test_query_endpoint(client):
    r = client.post("/api/query", json={"query": "tomato has black spots on leaves"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "diagnosis"
    assert body["answers"]


def test_query_indic(client):
    r = client.post("/api/query", json={"query": "टोमॅटोवर काळे डाग आहेत"})
    assert r.status_code == 200
    assert r.json()["language"] == "mr"


def test_diagnose_endpoint(client):
    r = client.post("/api/diagnose", json={"crop": "tomato", "symptoms": "black spots"})
    assert r.status_code == 200
    assert r.json()["results"]


def test_fertilizer_endpoint(client):
    r = client.post("/api/fertilizer", json={"crop": "tomato"})
    assert r.status_code == 200
    assert r.json()["crop"] == "Tomato"


def test_fertilizer_404(client):
    r = client.post("/api/fertilizer", json={"crop": "no_such_crop_xyz"})
    assert r.status_code == 404


def test_mandi_endpoint(client):
    r = client.get("/api/mandi", params={"commodity": "onion"})
    assert r.status_code == 200
    assert r.json()["commodity"] == "Onion"


def test_weather_endpoint(client):
    r = client.get("/api/weather", params={"district": "Pune"})
    assert r.status_code == 200
    assert r.json()["district"] == "Pune"


def test_plan_endpoint(client):
    r = client.get("/api/plan", params={"crop": "tomato"})
    assert r.status_code == 200
    assert r.json()["seasons"]


def test_plan_sow_endpoint(client):
    r = client.get("/api/plan/sow", params={"month": 6})
    assert r.status_code == 200
    assert r.json()


def test_evidence_endpoint(client):
    r = client.get("/api/evidence", params={"query": "early blight control", "crop": "tomato"})
    assert r.status_code == 200
    assert r.json()["hits"]


def test_graph_endpoints(client):
    s = client.get("/api/graph/summary")
    assert s.status_code == 200 and s.json()["nodes"] > 0
    n = client.get("/api/graph/neighbors", params={"node_id": "CROP_TOMATO"})
    assert n.status_code == 200 and n.json()
    c = client.get("/api/graph/candidates", params={"symptoms": "black spots"})
    assert c.status_code == 200 and c.json()
    p = client.get("/api/graph/path", params={"src": "CROP_TOMATO", "dst": "PATHOGEN:alternaria solani"})
    assert p.status_code == 200 and len(p.json()) == 3


def test_metrics_endpoint(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["total_gold_records"] > 0


def test_nlu_endpoint(client):
    r = client.post("/api/nlu", json={"query": "टोमॅटोवर काळे डाग आहेत"})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "mr"
    assert body["intent"] == "diagnosis"


def test_gateway_endpoint(client):
    r = client.post("/api/gateway", json={"query": "tomato early blight treatment"})
    assert r.status_code == 200
    body = r.json()
    assert "routing_path" in body
    assert "segments" in body


def test_vision_endpoint_synthetic(client):
    import struct
    import zlib
    import base64

    # Build a tiny 2x2 green PNG in-memory
    def make_tiny_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
        raw = b"\x00\x00\xff\x00\x00\xff\x00\x00\x00\xff\x00\x00\xff\x00"
        compressed = zlib.compress(raw)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        iend = struct.pack(">I", 0) + b"IEND" + iend_crc
        return sig + ihdr + idat + iend

    b64 = base64.b64encode(make_tiny_png()).decode("ascii")
    r = client.post("/api/vision", json={"image_base64": b64, "crop": "tomato"})
    assert r.status_code == 200
    body = r.json()
    assert body["width"] == 2
    assert body["height"] == 2
    assert "descriptor" in body

