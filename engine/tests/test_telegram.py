import asyncio
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from khidki import jobs, people, telegram
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
    s.put_obs("oaq:1", {d0 + timedelta(days=d, hours=h): 100 * SHAPE[h] * (1 + 0.04 * math.sin(d + h)) for d in range(20) for h in range(24)})
    s.put_cams("oaq:1", {d0 + timedelta(days=d, hours=h): 50 * SHAPE[h] for d in range(21) for h in range(24)}, "x")
    jobs.publish(s, DAY, issued_at=ds(DAY) - timedelta(hours=3), anchor=None)
    return s


async def fake_agent(pid, lat, lon, text):
    return f"agent:{pid}:{lat}:{text}"


def run(coro):
    return asyncio.run(coro)


def msg(chat, **kw):
    return {"message": {"chat": {"id": chat}, **kw}}


def test_start_location_and_chat(store):
    out = telegram.Outbox()
    run(telegram.handle_update(store, out, msg(5, **{"from": {"language_code": "hi"}, "text": "/start"}), fake_agent))
    assert "खिड़की" in out.sent[-1][1]
    assert out.sent[-1][2]["keyboard"][0][0]["request_location"] is True
    run(telegram.handle_update(store, out, msg(5, location={"latitude": 28.6, "longitude": 77.22}), fake_agent))
    assert "सेव" in out.sent[-1][1]
    run(telegram.handle_update(store, out, msg(5, text="kal kab jaun"), fake_agent))
    assert out.sent[-1][1].startswith("agent:") and ":28.6:" in out.sent[-1][1]


def test_location_outside_india_is_refused(store):
    out = telegram.Outbox()
    run(telegram.handle_update(store, out, msg(9, location={"latitude": 52.2, "longitude": 21.0}), fake_agent))
    assert "India" in out.sent[-1][1]


def test_agent_failure_gives_a_clear_message(store):
    async def broken(*a):
        raise RuntimeError("model down")

    out = telegram.Outbox()
    run(telegram.handle_update(store, out, msg(11, text="hello"), broken))
    assert "went wrong" in out.sent[-1][1]


def test_nudge_checkin_answer_result(store):
    out = telegram.Outbox()
    pid = people.get_or_create_person(store, "telegram", "77", "en")
    people.set_location(store, pid, 28.60, 77.22)
    people.save_routine(store, pid, activity="walk", minutes=60, usual_time="06:00", earliest="05:00", latest_end="21:00")
    r = telegram.daily_people_jobs(store, out, now=ds(DAY) + timedelta(hours=4, minutes=5))
    assert r["planned"] == 1 and r["nudged"] == 0
    r = telegram.daily_people_jobs(store, out, now=ds(DAY) + timedelta(hours=14, minutes=30))
    assert r["nudged"] == 1 and "15:00" in out.sent[-1][1]
    # next morning the day's readings are in and the check-in goes out
    store.put_obs("oaq:1", {ds(DAY) + timedelta(hours=h): 120 * SHAPE[h] for h in range(24)})
    nextday = ds(DAY) + timedelta(days=1, hours=8, minutes=10)
    r = telegram.daily_people_jobs(store, out, now=nextday)
    assert r["checkins"] == 1
    data = out.sent[-1][2]["inline_keyboard"][0][0]["callback_data"]
    assert data.endswith("went_planned")
    assert "checkins" not in telegram.daily_people_jobs(store, out, now=nextday + timedelta(minutes=15))
    # the person taps "At 15:00"; the next tick measures and reports
    run(telegram.handle_update(store, out, {"callback_query": {"id": "c1", "data": data, "message": {"chat": {"id": 77}}}}, fake_agent))
    r = telegram.daily_people_jobs(store, out, now=nextday + timedelta(minutes=30))
    assert r["outcomes"]["verified"] == 1 and r["results_sent"] == 1
    assert "62% less PM2.5" in out.sent[-1][1]
    # and only once
    assert telegram.daily_people_jobs(store, out, now=nextday + timedelta(minutes=45))["results_sent"] == 0


def test_callback_for_someone_elses_plan_is_ignored(store):
    out = telegram.Outbox()
    a = people.get_or_create_person(store, "telegram", "1")
    people.set_location(store, a, 28.6, 77.22)
    people.save_routine(store, a, activity="walk", minutes=60, usual_time="06:00", earliest="05:00", latest_end="21:00")
    plan = people.plan_day(store, a, DAY, now=ds(DAY) - timedelta(hours=2))[0]
    cq = {"callback_query": {"id": "x", "data": f"ci:{plan.plan_id}:skipped", "message": {"chat": {"id": 2}}}}
    run(telegram.handle_update(store, out, cq, fake_agent))
    assert store.one("SELECT answered FROM plans WHERE id=?", (plan.plan_id,))["answered"] is None


def test_service_rejects_out_of_range_inputs(store):
    from khidki import service

    with pytest.raises(ValueError):
        service.compute_window(store, lat=28.6, lon=77.2, minutes=0)
    with pytest.raises(ValueError):
        service.compute_airing(store, lat=28.6, lon=77.2, open_minutes=100000)
    with pytest.raises(ValueError):
        service.compute_window(store, lat=52.2, lon=21.0)
