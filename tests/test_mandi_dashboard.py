"""Tests for the Agmarknet dashboard feed (district-wise MH rates + MSP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.government.agmarknet_dashboard import AgmarknetDashboardConnector  # noqa: E402
from pipelines.http import Cassette, CassetteMiss, HttpClient  # noqa: E402
from reasoning.mandi_dashboard import (  # noqa: E402
    dashboard_source,
    district_view,
    known_districts,
    resolve_dashboard_district,
)

CASSETTE = ROOT / "tests" / "fixtures" / "cassettes" / "agmarknet_dashboard_nashik.json"
SAMPLE = ROOT / "data" / "fixtures" / "agmarknet_dashboard_sample.json"
MASTERS = ROOT / "data" / "fixtures" / "agmarknet_dashboard_masters.json"

NASHIK_RESOURCE = {
    "resource_id": "MH-361",
    "state_id": 20,
    "state_name": "Maharashtra",
    "district_id": 361,
    "district_name": "Nashik",
    "date": "2026-09-03",
}

SAMPLE_ROW = {
    "trend": "up",
    "cmdt_name": "Wheat",
    "msp_price": "2585.00",
    "as_on_price": "2739.30",
    "as_on_arrival": "12.50",
    "cmdt_grp_name": "Cereals",
    "reported_date": "01-09-2026",
    "one_day_ago_price": "2800.00",
    "two_day_ago_price": None,
    "one_day_ago_arrival": "10.00",
    "two_day_ago_arrival": None,
}


# ── masters ────────────────────────────────────────────────────────────────
def test_masters_fixture_resolves_maharashtra():
    masters = json.loads(MASTERS.read_text(encoding="utf-8"))
    con = AgmarknetDashboardConnector()
    state = con.state_row(masters)
    assert state is not None and int(state["state_id"]) == 20
    districts = con.districts_for(masters, 20)
    names = {d["district_name"] for d in districts}
    assert len(districts) == 38
    assert {"Nashik", "Pune", "Nagpur", "Ahilyanagar"} <= names


# ── normalize ──────────────────────────────────────────────────────────────
def test_normalize_maps_dashboard_row():
    con = AgmarknetDashboardConnector()
    (rec,) = con.normalize({"records": [SAMPLE_ROW]}, NASHIK_RESOURCE)
    assert rec["source_id"] == "AGMARKNET_DASHBOARD"
    assert rec["state"] == "Maharashtra" and rec["district"] == "Nashik"
    assert rec["commodity_raw"] == "Wheat"
    assert rec["modal_price"] == pytest.approx(2739.30)
    assert rec["prev_day_price"] == pytest.approx(2800.00)
    assert rec["prev_2day_price"] is None
    assert rec["arrival_tonnes"] == pytest.approx(12.50)
    assert rec["msp_price"] == pytest.approx(2585.00)
    assert rec["trend"] == "up"
    assert rec["price_date"] == "2026-09-01"  # DD-MM-YYYY → ISO
    assert rec["price_date_raw"] == "01-09-2026"
    assert rec["price_kind"] == "district_average"
    assert rec["unit"] == "INR/quintal"
    assert rec["source_url"].startswith("https://")


def test_normalize_skips_nameless_rows():
    con = AgmarknetDashboardConnector()
    assert con.normalize({"records": [{"as_on_price": "10"}]}, NASHIK_RESOURCE) == []


# ── district matching (user location) ──────────────────────────────────────
def test_resolve_dashboard_district():
    known = ["Nashik", "Pune", "Ahilyanagar", "Chattrapati Sambhajinagar", "Dharashiv"]
    assert resolve_dashboard_district("Nashik", known) == "Nashik"
    assert resolve_dashboard_district("nashik", known) == "Nashik"
    assert resolve_dashboard_district("Ahmednagar", known) == "Ahilyanagar"  # rename alias
    assert resolve_dashboard_district("Aurangabad", known) == "Chattrapati Sambhajinagar"
    assert resolve_dashboard_district("Osmanabad", known) == "Dharashiv"
    assert resolve_dashboard_district("NoSuchDistrict", known) is None
    assert resolve_dashboard_district("", known) is None


# ── reasoning view ─────────────────────────────────────────────────────────
def _sample_rows():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_district_view_nashik_sample():
    view = district_view("Nashik", _sample_rows())
    assert view is not None
    assert view.district == "Nashik" and view.state == "Maharashtra"
    assert view.data_source == "provided"
    assert len(view.rates) == 6
    wheat = next(r for r in view.rates if r.commodity == "Wheat")
    assert wheat.msp_price and wheat.modal_price
    assert wheat.vs_msp in ("above MSP", "below MSP", "at MSP")
    assert wheat.day_change_pct is not None
    assert view.price_date == "2026-09-01"
    assert view.evidence["license"] == {"type": "GODL-India"}


def test_district_view_alias_and_filters():
    rows = [
        {
            "state": "Maharashtra", "district": "Ahilyanagar", "commodity_raw": "Bajra",
            "modal_price": 3000.0, "prev_day_price": 2900.0, "prev_2day_price": None,
            "arrival_tonnes": 5.0, "msp_price": 2775.0, "trend": "up",
            "price_date": "2026-09-01", "commodity_group": "Cereals",
            "crop": None, "crop_canonical": None,
        }
    ]
    view = district_view("Ahmednagar", rows)  # old name → new dashboard name
    assert view is not None and view.district == "Ahilyanagar"
    (rate,) = view.rates
    assert rate.vs_msp == "above MSP" and rate.vs_msp_pct == pytest.approx(8.1, abs=0.1)
    assert district_view("NoSuchDistrict", rows) is None
    assert district_view("Ahilyanagar", rows, commodity="Wheat") is None


def test_known_districts_and_source():
    assert "Nashik" in known_districts(_sample_rows())
    assert dashboard_source() in ("lake", "fixture", "empty")


# ── replay (offline, deterministic) ────────────────────────────────────────
def test_dashboard_replay_nashik():
    cassette = Cassette.load(CASSETTE)
    con = AgmarknetDashboardConnector()
    con.limit = 100  # default limit caps districts at 10; MH has 38
    con._http = HttpClient(mode="replay", cassette=cassette)
    masters = con.load_masters()
    assert con.state_row(masters)["state_name"] == "Maharashtra"
    assert len(con.districts_for(masters, 20)) == 38
    resources = con.discover()
    assert len(resources) == 38
    raw = con.fetch(NASHIK_RESOURCE)
    assert raw["_method"] == "replay"
    assert len(raw["records"]) == 6
    rows = con.normalize(raw, NASHIK_RESOURCE)
    assert all(r["district"] == "Nashik" for r in rows)


def test_dashboard_replay_unknown_district_misses_closed():
    cassette = Cassette.load(CASSETTE)
    con = AgmarknetDashboardConnector()
    con._http = HttpClient(mode="replay", cassette=cassette)
    other = dict(NASHIK_RESOURCE, district_id=364, district_name="Pune", resource_id="MH-364")
    with pytest.raises(CassetteMiss):
        con.fetch(other)


def test_dashboard_offline_fails_closed(tmp_path, monkeypatch):
    import connectors.government.agmarknet_dashboard as amd

    # No cache on disk: offline must raise, never phone home.
    monkeypatch.setattr(amd, "_masters_cache_path", lambda: tmp_path / "masters.json")
    con = AgmarknetDashboardConnector()
    con._http = HttpClient(mode="offline", cassette_dir=tmp_path)
    with pytest.raises(Exception):
        con.load_masters()


def test_dashboard_offline_uses_fresh_cache(tmp_path, monkeypatch):
    """Offline-first: a fresh masters cache keeps discover working air-gapped."""
    import connectors.government.agmarknet_dashboard as amd

    masters = json.loads(MASTERS.read_text(encoding="utf-8"))
    masters["_cached_at"] = __import__("time").time()
    cache = tmp_path / "masters.json"
    cache.write_text(json.dumps(masters), encoding="utf-8")
    monkeypatch.setattr(amd, "_masters_cache_path", lambda: cache)
    con = AgmarknetDashboardConnector()
    con._http = HttpClient(mode="offline", cassette_dir=tmp_path)
    assert con.state_row(con.load_masters())["state_name"] == "Maharashtra"


# ── API ────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from apps.api.main import app  # noqa: E402

    return TestClient(app, raise_server_exceptions=False)


def test_api_districts_lists_maharashtra(client):
    r = client.get("/api/mandi/districts")
    assert r.status_code == 200
    body = r.json()
    assert "Nashik" in body["districts"]
    assert body["data_source"] in ("lake", "fixture")


def test_api_district_nashik(client):
    r = client.get("/api/mandi/district", params={"district": "Nashik"})
    assert r.status_code == 200
    body = r.json()
    assert body["district"] == "Nashik"
    assert len(body["rates"]) >= 6
    wheat = next(x for x in body["rates"] if x["commodity"] == "Wheat")
    assert wheat["modal_price"] and wheat["msp_price"] and wheat["vs_msp"]
    assert body["evidence"]["license"] == {"type": "GODL-India"}


def test_api_district_unknown_404(client):
    r = client.get("/api/mandi/district", params={"district": "NoSuchDistrict"})
    assert r.status_code == 404
