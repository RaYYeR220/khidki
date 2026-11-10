"""People, their routines, daily plans and verified personal outcomes.

The loop: a routine ("I walk 60 min around 6:00, I could go any time 5–21") →
each day a plan (the cleanest start inside those limits) → a nudge before it →
next day the person says when they actually went → we measure, from the
monitors around their home, what they breathed versus their usual time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .exposure import Activity, AgeBand, inhalation_rate, interval_dose
from .geo import idw_weights
from .jobs import IST, at, day_start, now_ist
from .service import compute_window, parse_time
from .store import Store

ANSWERS = ("went_planned", "went_usual", "went_other", "skipped")


def get_or_create_person(store: Store, channel: str, external_id: str, lang: str = "en") -> int:
    row = store.one("SELECT id FROM people WHERE channel=? AND external_id=?", (channel, external_id))
    if row:
        return row["id"]
    pid = store.x(
        "INSERT INTO people(channel, external_id, lang, created_at) VALUES (?,?,?,?)",
        (channel, external_id, lang, now_ist().isoformat()),
    )
    store.event("person_joined", now_ist().isoformat(), {"channel": channel})
    return pid


def person(store: Store, pid: int) -> dict | None:
    r = store.one("SELECT * FROM people WHERE id=?", (pid,))
    return dict(r) if r else None


def set_location(store: Store, pid: int, lat: float, lon: float) -> None:
    if not (6 <= lat <= 37.5 and 68 <= lon <= 97.5):
        raise ValueError("Khidki covers India only; that location is outside India")
    store.x("UPDATE people SET lat=?, lon=? WHERE id=?", (lat, lon, pid))


def set_lang(store: Store, pid: int, lang: str) -> None:
    store.x("UPDATE people SET lang=? WHERE id=?", (lang[:8], pid))


def save_routine(
    store: Store,
    pid: int,
    *,
    activity: str,
    minutes: int,
    usual_time: str,
    earliest: str,
    latest_end: str,
    age: str = "adult",
    label: str | None = None,
) -> int:
    act = Activity(activity)
    ag = AgeBand(age)
    hab, e, le = parse_time(usual_time), parse_time(earliest), parse_time(latest_end)
    if not (10 <= minutes <= 240):
        raise ValueError("minutes must be between 10 and 240")
    if datetime.combine(date.today(), e) + timedelta(minutes=minutes) > datetime.combine(date.today(), le):
        raise ValueError("the allowed time is shorter than the activity")
    return store.x(
        """INSERT INTO routines(person_id, activity, age, minutes, habitual, earliest, latest_end, label, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (pid, act.value, ag.value, minutes, hab.strftime("%H:%M"), e.strftime("%H:%M"), le.strftime("%H:%M"), label, now_ist().isoformat()),
    )


def routines(store: Store, pid: int) -> list[dict]:
    return [dict(r) for r in store.q("SELECT * FROM routines WHERE person_id=? AND active=1 ORDER BY id", (pid,))]


def stop_routine(store: Store, pid: int, routine_id: int) -> bool:
    return store.x("UPDATE routines SET active=0 WHERE id=? AND person_id=?", (routine_id, pid)) > 0


@dataclass
class DayPlan:
    plan_id: int
    routine_id: int
    day: str
    start: str
    habitual: str
    window: dict


def plan_day(store: Store, pid: int, day: date, *, now: datetime | None = None, cams_fallback=None) -> list[DayPlan]:
    """Create (or refresh) today's plan for each active routine of a person."""
    p = person(store, pid)
    if not p or p["lat"] is None:
        return []
    out = []
    for r in routines(store, pid):
        w = compute_window(
            store,
            lat=p["lat"],
            lon=p["lon"],
            activity=Activity(r["activity"]),
            age=AgeBand(r["age"]),
            minutes=r["minutes"],
            earliest=r["earliest"],
            latest_end=r["latest_end"],
            habitual=r["habitual"],
            day=day.isoformat(),
            now=now,
            cams_fallback=cams_fallback,
            log_event=False,
        )
        if w.get("status") != "ok" or not w.get("best"):
            continue
        store.x(
            """INSERT INTO plans(routine_id, day, start, habitual, forecast_mean, forecast_habitual_mean)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(routine_id, day) DO UPDATE SET start=excluded.start,
                 forecast_mean=excluded.forecast_mean, forecast_habitual_mean=excluded.forecast_habitual_mean
               WHERE plans.nudged_at IS NULL""",
            (r["id"], day.isoformat(), w["best"]["start"], r["habitual"], w["best"]["mean_pm25"], (w.get("usual") or {}).get("mean_pm25")),
        )
        row = store.one("SELECT id, start FROM plans WHERE routine_id=? AND day=?", (r["id"], day.isoformat()))
        out.append(DayPlan(row["id"], r["id"], day.isoformat(), row["start"], r["habitual"], w))
    return out


def record_answer(store: Store, plan_id: int, answer: str, went_at: str | None = None) -> None:
    if answer not in ANSWERS:
        raise ValueError(f"answer must be one of {ANSWERS}")
    plan = store.one("SELECT * FROM plans WHERE id=?", (plan_id,))
    if not plan:
        raise ValueError("unknown plan")
    went = None
    if answer == "went_planned":
        went = plan["start"]
    elif answer == "went_usual":
        went = plan["habitual"]
    elif answer == "went_other":
        if not went_at:
            raise ValueError("went_other needs the time")
        went = parse_time(went_at).strftime("%H:%M")
    store.x(
        "UPDATE plans SET answered=?, answered_at=?, went_at=? WHERE id=?",
        (answer, now_ist().isoformat(), went, plan_id),
    )


def _point_measured(store: Store, lat: float, lon: float, day: date) -> dict[datetime, float]:
    rows = [(r["id"], r["lat"], r["lon"]) for r in store.q("SELECT id, lat, lon FROM stations WHERE active=1")]
    ws = idw_weights(lat, lon, rows, max_km=15.0)
    ds = day_start(day)
    obs = {w.id: store.get_obs(w.id, ds, ds + timedelta(days=1)) for w in ws}
    out = {}
    for i in range(24):
        h = ds + timedelta(hours=i)
        vals = [(w.weight, obs[w.id][h]) for w in ws if h in obs[w.id]]
        if vals:
            tw = sum(a for a, _ in vals)
            out[h] = sum(a * v for a, v in vals) / tw
    return out


def verify_outcomes(store: Store, day: date) -> dict:
    """Measure answered plans of ``day`` against the readings around each home."""
    rows = store.q(
        """SELECT pl.*, r.activity, r.age, r.minutes, pe.lat, pe.lon FROM plans pl
           JOIN routines r ON r.id=pl.routine_id JOIN people pe ON pe.id=r.person_id
           WHERE pl.day=? AND pl.answered IS NOT NULL AND pl.answered!='skipped'
             AND pl.id NOT IN (SELECT plan_id FROM outcomes WHERE status='verified')""",
        (day.isoformat(),),
    )
    done = {"verified": 0, "unverifiable": 0}
    cache: dict[tuple, dict] = {}
    for r in rows:
        key = (round(r["lat"], 3), round(r["lon"], 3))
        if key not in cache:
            cache[key] = _point_measured(store, r["lat"], r["lon"], day)
        measured = cache[key]
        rate = inhalation_rate(Activity(r["activity"]), AgeBand(r["age"]))
        went = interval_dose(measured, at(day, time.fromisoformat(r["went_at"])), r["minutes"], rate)
        hab = interval_dose(measured, at(day, time.fromisoformat(r["habitual"])), r["minutes"], rate)
        ok = went is not None and hab is not None
        store.x(
            """INSERT OR REPLACE INTO outcomes(plan_id, status, went_mean, habitual_mean, dose_avoided_ug, reduction_pct, verified_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                r["id"],
                "verified" if ok else "unverifiable",
                round(went.mean_conc, 1) if ok else None,
                round(hab.mean_conc, 1) if ok else None,
                round(hab.dose_ug - went.dose_ug, 1) if ok else None,
                round(100 * (hab.dose_ug - went.dose_ug) / hab.dose_ug, 1) if ok and hab.dose_ug > 0 else None,
                now_ist().isoformat(),
            ),
        )
        done["verified" if ok else "unverifiable"] += 1
    return {"day": day.isoformat(), **done}


def results(store: Store, pid: int) -> dict:
    rows = store.q(
        """SELECT pl.day, pl.start, pl.habitual, pl.went_at, pl.answered, o.status, o.went_mean, o.habitual_mean,
                  o.dose_avoided_ug, o.reduction_pct, r.activity
           FROM plans pl JOIN routines r ON r.id=pl.routine_id LEFT JOIN outcomes o ON o.plan_id=pl.id
           WHERE r.person_id=? ORDER BY pl.day DESC LIMIT 30""",
        (pid,),
    )
    items = [dict(r) for r in rows]
    verified = [i for i in items if i["status"] == "verified"]
    return {
        "days_planned": len(items),
        "days_verified": len(verified),
        "total_dose_avoided_ug": round(sum(i["dose_avoided_ug"] or 0 for i in verified), 1),
        "items": items,
    }


def pending_checkins(store: Store, day: date) -> list[dict]:
    """Plans of ``day`` that were nudged but not yet answered (ask next morning)."""
    return [
        dict(r)
        for r in store.q(
            """SELECT pl.id plan_id, pl.start, pl.habitual, pe.channel, pe.external_id, pe.lang, r.activity
               FROM plans pl JOIN routines r ON r.id=pl.routine_id JOIN people pe ON pe.id=r.person_id
               WHERE pl.day=? AND pl.nudged_at IS NOT NULL AND pl.answered IS NULL""",
            (day.isoformat(),),
        )
    ]


def due_nudges(store: Store, now: datetime, lead_minutes: int = 45) -> list[dict]:
    """Plans starting within ``lead_minutes`` that were not nudged yet."""
    today = now.date().isoformat()
    out = []
    for r in store.q(
        """SELECT pl.id plan_id, pl.start, pl.habitual, pl.forecast_mean, pl.forecast_habitual_mean,
                  pe.channel, pe.external_id, pe.lang, r.activity, r.minutes
           FROM plans pl JOIN routines r ON r.id=pl.routine_id JOIN people pe ON pe.id=r.person_id
           WHERE pl.day=? AND pl.nudged_at IS NULL AND r.active=1""",
        (today,),
    ):
        start = datetime.combine(now.date(), time.fromisoformat(r["start"]), tzinfo=IST)
        if timedelta(0) <= start - now <= timedelta(minutes=lead_minutes):
            out.append(dict(r))
    return out


def mark_nudged(store: Store, plan_id: int, when: datetime) -> None:
    store.x("UPDATE plans SET nudged_at=? WHERE id=?", (when.isoformat(), plan_id))
