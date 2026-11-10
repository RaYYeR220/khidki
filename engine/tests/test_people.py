import math
from datetime import date, datetime, timedelta, timezone

import pytest

from khidki import jobs, people
from khidki.store import Store

IST = timezone(timedelta(hours=5, minutes=30))
SHAPE = [2.2, 2.2, 2.1, 2.1, 2.1, 2.2, 2.4, 2.5, 2.2, 1.8, 1.4, 1.2, 1.1, 1.0, 0.95, 0.9, 1.0, 1.3, 1.7, 2.0, 2.2, 2.4, 2.4, 2.3]
DAY = date(2026, 11, 12)


def ds(d):
    return datetime(d.year, d.month, d.day, tzinfo=IST)


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_stations([{"id": "oaq:1", "source": "openaq", "name": "Lodhi Road", "lat": 28.59, "lon": 77.22}], now="x")
    d0 = ds(DAY) - timedelta(days=20)
    obs = {d0 + timedelta(days=d, hours=h): 100 * SHAPE[h] * (1 + 0.04 * math.sin(d + h)) for d in range(20) for h in range(24)}
    s.put_obs("oaq:1", obs)
    s.put_cams("oaq:1", {d0 + timedelta(days=d, hours=h): 50 * SHAPE[h] for d in range(21) for h in range(24)}, "x")
    jobs.publish(s, DAY, issued_at=ds(DAY) - timedelta(hours=3), anchor=None)
    return s


def test_full_personal_loop(store):
    pid = people.get_or_create_person(store, "telegram", "42", "hi")
    assert people.get_or_create_person(store, "telegram", "42") == pid
    people.set_location(store, pid, 28.60, 77.22)
    rid = people.save_routine(store, pid, activity="walk", minutes=60, usual_time="6 am", earliest="5:00", latest_end="21:00")
    plans = people.plan_day(store, pid, DAY, now=ds(DAY) - timedelta(hours=2))
    assert len(plans) == 1 and plans[0].start == "15:00" and plans[0].habitual == "06:00"

    due = people.due_nudges(store, ds(DAY) + timedelta(hours=14, minutes=30))
    assert [d["plan_id"] for d in due] == [plans[0].plan_id]
    people.mark_nudged(store, plans[0].plan_id, ds(DAY) + timedelta(hours=14, minutes=30))
    assert people.due_nudges(store, ds(DAY) + timedelta(hours=14, minutes=40)) == []
    assert len(people.pending_checkins(store, DAY)) == 1

    people.record_answer(store, plans[0].plan_id, "went_planned")
    # the day's readings arrive
    store.put_obs("oaq:1", {ds(DAY) + timedelta(hours=h): 120 * SHAPE[h] for h in range(24)})
    res = people.verify_outcomes(store, DAY)
    assert res == {"day": DAY.isoformat(), "verified": 1, "unverifiable": 0}
    r = people.results(store, pid)
    assert r["days_verified"] == 1
    item = r["items"][0]
    assert item["went_mean"] == pytest.approx(120 * 0.9, rel=1e-3)
    assert item["habitual_mean"] == pytest.approx(120 * 2.4, rel=1e-3)
    assert item["reduction_pct"] == pytest.approx(62.5, abs=0.1)
    assert rid > 0


def test_outside_india_is_refused(store):
    pid = people.get_or_create_person(store, "web", "abc")
    with pytest.raises(ValueError):
        people.set_location(store, pid, 52.2, 21.0)


def test_skipped_days_are_not_scored(store):
    pid = people.get_or_create_person(store, "telegram", "7")
    people.set_location(store, pid, 28.60, 77.22)
    people.save_routine(store, pid, activity="walk", minutes=60, usual_time="06:00", earliest="05:00", latest_end="21:00")
    p = people.plan_day(store, pid, DAY, now=ds(DAY) - timedelta(hours=2))[0]
    people.record_answer(store, p.plan_id, "skipped")
    assert people.verify_outcomes(store, DAY)["verified"] == 0
