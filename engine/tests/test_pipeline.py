import json
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from khidki import jobs
from khidki.audit import audit_day, frozen_runs
from khidki.ledger import (
    build_commitment,
    canonical_json,
    ots_file,
    sha256_hex,
    verify_payload,
)
from khidki.store import Store

IST = timezone(timedelta(hours=5, minutes=30))
SHAPE = [2.2, 2.2, 2.1, 2.1, 2.1, 2.2, 2.4, 2.5, 2.2, 1.8, 1.4, 1.2, 1.1, 1.0, 0.95, 0.9, 1.0, 1.3, 1.7, 2.0, 2.2, 2.4, 2.4, 2.3]


def ds(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IST)


def synthetic(day0: date, days: int, base: float = 100.0, jitter: float = 0.0) -> dict[datetime, float]:
    out = {}
    for d in range(days):
        for h in range(24):
            wobble = 1 + jitter * math.sin(d * 1.7 + h)
            out[ds(day0) + timedelta(days=d, hours=h)] = base * SHAPE[h] * wobble
    return out


# --- ledger ------------------------------------------------------------------------

def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_commitment_hash_roundtrip_and_tamper_detection():
    recs = [
        {"station": "oaq:2", "scenario": "x", "start": "15:00"},
        {"station": "oaq:1", "scenario": "x", "start": "14:45"},
    ]
    c = build_commitment("2026-11-12", "2026-11-11T21:00:00+05:30", "blend", recs)
    assert c.n_stations == 2 and c.n_recommendations == 2
    assert verify_payload(c.payload, c.sha256)
    body = json.loads(c.payload)
    assert [r["station"] for r in body["recommendations"]] == ["oaq:1", "oaq:2"]
    tampered = c.payload.replace("14:45", "15:00")
    assert not verify_payload(tampered, c.sha256)
    # order of input does not change the hash
    c2 = build_commitment("2026-11-12", "2026-11-11T21:00:00+05:30", "blend", list(reversed(recs)))
    assert c2.sha256 == c.sha256


def test_ots_file_layout():
    digest = sha256_hex("x")
    blob = ots_file(digest, {"cal-a": b"\xf0\x01a", "cal-b": b"\xf0\x01b"})
    assert blob.startswith(b"\x00OpenTimestamps\x00\x00Proof\x00")
    assert bytes.fromhex(digest) in blob
    assert blob.endswith(b"\xff\xf0\x01a\xf0\x01b")
    assert ots_file(digest, {}) is None


# --- audit -------------------------------------------------------------------------

def test_frozen_runs_detected():
    d0 = ds(date(2026, 11, 10))
    s = {d0 + timedelta(hours=h): 150.0 for h in range(3, 9)}
    s.update({d0 + timedelta(hours=h): 100.0 + h for h in range(9, 24)})
    runs = frozen_runs(s, d0)
    assert runs == [(d0 + timedelta(hours=3), 6, 150.0)]


def test_audit_flags_dark_during_severe():
    d0 = ds(date(2026, 11, 10))
    stations = {"a": (28.60, 77.20), "b": (28.61, 77.21), "c": (28.62, 77.20), "far": (19.07, 72.88)}
    hours = [d0 + timedelta(hours=h) for h in range(24)]
    series = {
        "a": {t: 300.0 + t.hour for t in hours if not 5 <= t.hour < 10},  # silent 05-09
        "b": {t: 310.0 + (t.hour % 2) for t in hours},
        "c": {t: 290.0 + (t.hour % 3) for t in hours},
        "far": {t: 60.0 + t.hour for t in hours},
    }
    flags = audit_day(d0, stations, series)
    by = {(f.station_id, f.kind): f for f in flags}
    assert by[("a", "missing_hours")].detail["missing"] == 5
    dark = by[("a", "dark_during_severe")]
    assert dark.detail["hours"] == ["05", "06", "07", "08", "09"]
    assert min(dark.detail["neighbour_median"]) >= 250
    assert not any(f.station_id == "far" for f in flags)


def test_audit_flags_station_that_disagrees_with_neighbours():
    d0 = ds(date(2026, 11, 10))
    stations = {"a": (28.60, 77.20), "b": (28.61, 77.21), "c": (28.62, 77.20)}
    hours = [d0 + timedelta(hours=h) for h in range(24)]
    series = {
        "a": {t: 120.0 + (t.hour % 2) for t in hours},
        "b": {t: 300.0 + (t.hour % 3) for t in hours},
        "c": {t: 310.0 + (t.hour % 4) for t in hours},
    }
    flags = audit_day(d0, stations, series)
    dis = [f for f in flags if f.kind == "disagrees_with_neighbours"]
    assert [f.station_id for f in dis] == ["a"]
    assert dis[0].detail["ratio"] <= 0.5


def test_audit_reports_station_silent_all_day():
    d0 = ds(date(2026, 11, 10))
    flags = audit_day(d0, {"a": (28.6, 77.2)}, {})
    assert flags[0].kind == "missing_hours" and flags[0].severity == "high"


# --- pipeline ----------------------------------------------------------------------

class FakeCams:
    def __init__(self, series_by_point):
        self.series_by_point = series_by_point

    def cams_many(self, points, past_days, forecast_days):
        return [self.series_by_point[p] for p in points]


class FakeLatest:
    def __init__(self, rows):
        self.rows = rows

    def latest(self):
        return self.rows


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_stations(
        [
            {"id": "oaq:1", "source": "openaq", "name": "Station One", "lat": 28.60, "lon": 77.20},
            {"id": "oaq:2", "source": "openaq", "name": "Station Two", "lat": 28.65, "lon": 77.25},
        ],
        now="2026-11-01T00:00:00+05:30",
    )
    return s


def test_publish_then_verify_end_to_end(store):
    day0 = date(2026, 10, 20)
    target = date(2026, 11, 10)
    obs = synthetic(day0, 22, jitter=0.05)
    cams = synthetic(day0, 22, base=50.0)
    for sid in ("oaq:1", "oaq:2"):
        store.put_obs(sid, {t: v for t, v in obs.items() if t < ds(target)})
        store.put_cams(sid, cams, "2026-11-09T20:00:00+05:30")

    issued = ds(target) - timedelta(hours=3)
    res = jobs.publish(store, target, issued_at=issued, anchor=None)
    assert res["status"] == "published"
    assert res["stations"] == 2
    row = store.one("SELECT * FROM commitments WHERE day=?", (target.isoformat(),))
    assert verify_payload(row["payload"], row["sha256"])
    # cannot publish twice, cannot publish after the day started
    assert jobs.publish(store, target, issued_at=issued, anchor=None)["status"] == "exists"
    with pytest.raises(ValueError):
        jobs.publish(store, target + timedelta(days=1), issued_at=ds(target + timedelta(days=1)), anchor=None)

    recs = store.q("SELECT * FROM recommendations WHERE day=? AND scenario='morning_walk'", (target.isoformat(),))
    assert {r["start"] for r in recs} == {"15:00"}

    # the day happens
    for sid in ("oaq:1", "oaq:2"):
        store.put_obs(sid, {t: v for t, v in obs.items() if ds(target) <= t < ds(target) + timedelta(days=1)})
    v = jobs.verify(store, target)
    assert v["verified"] > 0
    sb = jobs.scoreboard(store)
    assert sb["morning_walk"]["khidki"]["reduction_vs_habitual_pct"] > 50
    assert sb["morning_walk"]["habitual"]["reduction_vs_habitual_pct"] == 0


def test_verify_marks_missing_measurements_unverifiable(store):
    day0 = date(2026, 10, 20)
    target = date(2026, 11, 10)
    obs = synthetic(day0, 21)
    for sid in ("oaq:1", "oaq:2"):
        store.put_obs(sid, obs)
        store.put_cams(sid, synthetic(day0, 22, base=50.0), "2026-11-09T20:00:00+05:30")
    jobs.publish(store, target, issued_at=ds(target) - timedelta(hours=3), anchor=None)
    v = jobs.verify(store, target)  # no readings for the target day at all
    assert v["verified"] == 0 and v["unverifiable"] > 0
    assert jobs.scoreboard(store) == {}


def test_ingest_latest_only_known_stations(store):
    t = ds(date(2026, 11, 10)) + timedelta(hours=9)
    n = jobs.ingest_latest(store, FakeLatest([(1, t, 210.0), (999, t, 50.0), (2, t, -5.0)]))
    assert n == 1
    assert store.get_obs("oaq:1", t, t + timedelta(hours=1)) == {t: 210.0}


def test_audit_job_writes_flags(store):
    target = date(2026, 11, 10)
    store.put_obs("oaq:1", {ds(target) + timedelta(hours=h): 100.0 for h in range(12)})
    res = jobs.run_audit(store, target)
    assert res["by_kind"]["missing_hours"] == 2  # oaq:1 half day, oaq:2 silent


def test_refresh_stations_keeps_only_live_reference_monitors():
    from types import SimpleNamespace as NS

    s = Store(":memory:")
    now = jobs.now_ist()
    fresh = (now - timedelta(hours=2)).isoformat()
    stale = (now - timedelta(days=30)).isoformat()
    locs = [
        NS(id=1, name="ITO", lat=28.63, lon=77.24, locality="Delhi", provider="CPCB", pm25_sensor_id=11, last_seen=fresh, is_monitor=True),
        NS(id=2, name="Old", lat=28.6, lon=77.2, locality="Delhi", provider="CPCB", pm25_sensor_id=12, last_seen=stale, is_monitor=True),
        NS(id=3, name="LowCost", lat=28.6, lon=77.2, locality="Delhi", provider="X", pm25_sensor_id=13, last_seen=fresh, is_monitor=False),
    ]
    res = jobs.refresh_stations(s, NS(india_pm25_locations=lambda: locs))
    assert res == {"active": 1, "skipped_low_cost_or_no_coords": 1, "skipped_stale": 1}
    assert [r["id"] for r in s.q("SELECT id FROM stations WHERE active=1")] == ["oaq:1"]


def test_upgrade_proofs_stores_completed_proof():
    s = Store(":memory:")
    s.event("ots_proof", "2026-11-11T21:00:00+05:30", {"day": "2026-11-12", "ots_hex": "00aa"})
    calls = []

    def fake_upgrade(b):
        calls.append(b)
        return b + b"\x01", True

    assert jobs.upgrade_proofs(s, fake_upgrade) == {"pending_days": 1, "completed_now": 1, "failed": []}
    # the completed proof is not asked for again
    assert jobs.upgrade_proofs(s, fake_upgrade) == {"pending_days": 0, "completed_now": 0, "failed": []}
    assert len(calls) == 1


def test_upgrade_ots_never_contacts_unknown_calendars(monkeypatch):
    from opentimestamps.core.notary import PendingAttestation
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.serialize import BytesSerializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    from khidki import ledger

    digest = bytes.fromhex(sha256_hex("payload"))
    ts = Timestamp(digest)
    ts.attestations.add(PendingAttestation("http://169.254.169.254/latest"))
    ctx = BytesSerializationContext()
    DetachedTimestampFile(OpSHA256(), ts).serialize(ctx)
    contacted = []

    class Spy:
        def __init__(self, uri):
            contacted.append(uri)

        def get_timestamp(self, *a, **k):
            raise AssertionError("must not be called")

    monkeypatch.setattr("opentimestamps.calendar.RemoteCalendar", Spy)
    out, verified = ledger.upgrade_ots(ctx.getbytes(), header_for=lambda h: None)
    assert contacted == [] and verified is False


def test_bad_proof_does_not_block_other_days():
    s = Store(":memory:")
    s.event("ots_proof", "x", {"day": "2026-11-12", "ots_hex": "zz"})  # not even hex
    s.event("ots_proof", "x", {"day": "2026-11-13", "ots_hex": "00"})
    res = jobs.upgrade_proofs(s, lambda b: (b, True))
    assert res["failed"] == ["2026-11-12"] and res["completed_now"] == 1
