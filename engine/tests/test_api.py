import math
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from khidki import api, jobs
from khidki.ledger import sha256_hex
from khidki.store import Store

IST = timezone(timedelta(hours=5, minutes=30))
SHAPE = [2.2, 2.2, 2.1, 2.1, 2.1, 2.2, 2.4, 2.5, 2.2, 1.8, 1.4, 1.2, 1.1, 1.0, 0.95, 0.9, 1.0, 1.3, 1.7, 2.0, 2.2, 2.4, 2.4, 2.3]
TARGET = date(2026, 11, 12)


def ds(d):
    return datetime(d.year, d.month, d.day, tzinfo=IST)


@pytest.fixture()
def client(monkeypatch):
    s = Store(":memory:")
    s.upsert_stations(
        [
            {"id": "oaq:1", "source": "openaq", "name": "Lodhi Road", "lat": 28.59, "lon": 77.22},
            {"id": "oaq:2", "source": "openaq", "name": "ITO", "lat": 28.63, "lon": 77.24},
        ],
        now="2026-11-01T00:00:00+05:30",
    )
    d0 = ds(TARGET) - timedelta(days=20)
    obs = {d0 + timedelta(days=d, hours=h): 100 * SHAPE[h] * (1 + 0.05 * math.sin(d + h)) for d in range(20) for h in range(24)}
    cams = {d0 + timedelta(days=d, hours=h): 50 * SHAPE[h] for d in range(21) for h in range(24)}
    for sid in ("oaq:1", "oaq:2"):
        s.put_obs(sid, obs)
        s.put_cams(sid, cams, "2026-11-11T20:00:00+05:30")
    jobs.publish(s, TARGET, issued_at=ds(TARGET) - timedelta(hours=3), anchor=None)
    api.app.dependency_overrides[api.get_store] = lambda: s
    monkeypatch.setattr(api, "now_ist", lambda: ds(TARGET) - timedelta(hours=2))
    monkeypatch.setattr(api, "_cams_point", lambda lat, lon: {})
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_window_for_a_point_between_two_stations(client):
    r = client.get("/v1/window", params={"lat": 28.61, "lon": 77.23, "day": TARGET.isoformat(), "habitual": "06:00"})
    j = r.json()
    assert r.status_code == 200, j
    assert j["status"] == "ok"
    assert j["best"]["start"] == "15:00"
    assert j["usual"]["start"] == "06:00"
    assert j["reduction_pct"] > 50
    assert j["source"] == "stations" and len(j["neighbours"]) == 2
    assert len(j["curve"]) == 24


def test_window_far_from_any_monitor_is_honest(client):
    r = client.get("/v1/window", params={"lat": 13.0, "lon": 77.6, "day": TARGET.isoformat()})
    assert r.json()["status"] == "no_data"


def test_ledger_serves_exact_hashed_bytes(client):
    idx = client.get("/v1/ledger").json()["commitments"]
    assert idx[0]["day"] == TARGET.isoformat()
    body = client.get(f"/v1/ledger/{TARGET.isoformat()}.json").content.decode("utf-8")
    assert sha256_hex(body) == idx[0]["sha256"]


def test_impact_counts_are_real(client):
    j = client.get("/v1/impact").json()
    assert j["stations_covered"] == 2
    assert j["days_published_in_advance"] == 1
    assert j["recommendations_verified"] == 0
    assert j["people"] == {}


def test_tick_requires_token(client, monkeypatch):
    monkeypatch.setenv("KHIDKI_JOB_TOKEN", "secret")
    assert client.post("/jobs/tick").status_code == 401
