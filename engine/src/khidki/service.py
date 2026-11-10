"""Use-case layer shared by the HTTP API, the agents and the Telegram bot."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Callable

from . import jobs
from .aqi import HEALTH_STATEMENT, pm25_category
from .exposure import Activity, AgeBand, inhalation_rate
from .jobs import at, now_ist
from .planner import plan_airing, plan_window
from .point import point_forecast
from .store import Store

CamsFallback = Callable[[float, float], dict[datetime, float]] | None

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*$", re.I)


def parse_time(s: str) -> time:
    """Lenient HH:MM parser: '6', '06:30', '6.30', '6 pm', '18:00'."""
    m = _TIME_RE.match(s or "")
    if not m:
        raise ValueError(f"cannot read time {s!r}; use HH:MM (24-hour)")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower().replace(".", "")
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValueError(f"time out of range: {s!r}")
    return time(h, mi)


def resolve_day(day: str, now: datetime | None = None) -> date:
    today = (now or now_ist()).date()
    d = (day or "today").strip().lower()
    if d == "today":
        return today
    if d == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(d)


def slot_dict(s) -> dict | None:
    if s is None:
        return None
    return {
        "start": s.start.strftime("%H:%M"),
        "end": s.end.strftime("%H:%M"),
        "mean_pm25": round(s.mean_conc, 1),
        "dose_ug": round(s.dose_ug, 1),
        "category": pm25_category(s.mean_conc),
    }


def compute_window(
    store: Store,
    *,
    lat: float,
    lon: float,
    activity: Activity = Activity.walk,
    minutes: int = 60,
    earliest: str = "05:00",
    latest_end: str = "21:00",
    habitual: str | None = "06:00",
    age: AgeBand = AgeBand.adult,
    day: str = "today",
    now: datetime | None = None,
    cams_fallback: CamsFallback = None,
    log_event: bool = True,
) -> dict:
    now = now or now_ist()
    d = resolve_day(day, now)
    pf = point_forecast(store, lat, lon, d, now=now, cams_fallback=cams_fallback)
    if pf.source == "none":
        return {"status": "no_data", "reason": "no air monitor within 15 km has a forecast for this day yet", "day": d.isoformat()}
    e, le = at(d, parse_time(earliest)), at(d, parse_time(latest_end))
    if d == now.date():
        nxt = (now + timedelta(minutes=15 - now.minute % 15)).replace(second=0, microsecond=0)
        e = max(e, nxt)
    hab = at(d, parse_time(habitual)) if habitual else None
    if e > le - timedelta(minutes=minutes):
        return {"status": "window_closed", "reason": "the allowed time for this day has already passed", "day": d.isoformat()}
    plan = plan_window(
        pf.values,
        activity=activity,
        age=age,
        minutes=minutes,
        earliest=e,
        latest_end=le,
        habitual_start=hab,
        sigma_log=pf.sigma_log,
    )
    if log_event:
        store.event("window", now.isoformat(), {"lat": round(lat, 2), "lon": round(lon, 2), "activity": activity.value})
    return {
        "status": plan.status,
        "day": d.isoformat(),
        "activity": activity.value,
        "minutes": minutes,
        "best": slot_dict(plan.best),
        "usual": slot_dict(plan.habitual),
        "worst": slot_dict(plan.worst),
        "alternatives": [slot_dict(a) for a in plan.alternatives],
        "dose_avoided_ug": round(plan.dose_avoided_ug, 1) if plan.dose_avoided_ug is not None else None,
        "reduction_pct": round(plan.reduction_pct, 1) if plan.reduction_pct is not None else None,
        "confidence": round(plan.confidence, 2) if plan.confidence is not None else None,
        "flags": plan.flags,
        "health": HEALTH_STATEMENT.get(plan.best_category or "", None),
        "curve": [
            {"hour": h.strftime("%H:%M"), "pm25": round(v, 1), "measured": h in pf.measured_hours}
            for h, v in sorted(pf.values.items())
        ],
        "source": pf.source,
        "neighbours": pf.neighbours,
        "issued_at": pf.issued_at,
        "nowcast_factor": round(pf.nowcast_factor, 2) if pf.nowcast_factor else None,
        "inhalation_m3_per_min": inhalation_rate(activity, age),
    }


def compute_airing(
    store: Store,
    *,
    lat: float,
    lon: float,
    open_minutes: int = 30,
    earliest: str = "06:00",
    latest_end: str = "22:00",
    habitual: str | None = "07:00",
    day: str = "tomorrow",
    now: datetime | None = None,
    cams_fallback: CamsFallback = None,
) -> dict:
    d = resolve_day(day, now)
    pf = point_forecast(store, lat, lon, d, now=now, cams_fallback=cams_fallback)
    if len(pf.values) < 24:
        return {"status": "no_data", "day": d.isoformat(), "reason": "need a full-day forecast for this place"}
    p = plan_airing(
        pf.values,
        day_start=jobs.day_start(d),
        open_minutes=open_minutes,
        earliest=at(d, parse_time(earliest)),
        latest_end=at(d, parse_time(latest_end)),
        habitual_start=at(d, parse_time(habitual)) if habitual else None,
    )
    return {
        "status": p.status,
        "day": d.isoformat(),
        "open_at": p.best_start.strftime("%H:%M") if p.best_start else None,
        "open_minutes": open_minutes,
        "usual": habitual,
        "outdoor_pm25_then": round(p.best_outdoor_mean, 1) if p.best_outdoor_mean is not None else None,
        "reduction_pct": round(p.reduction_pct, 1) if p.reduction_pct is not None else None,
        "dose_avoided_ug": round(p.dose_avoided_ug, 1) if p.dose_avoided_ug is not None else None,
        "flags": p.flags,
        "source": pf.source,
    }


def air_now(store: Store, lat: float, lon: float, now: datetime | None = None) -> dict:
    """Latest measured readings from the monitors around a point."""
    from .geo import idw_weights

    now = now or now_ist()
    rows = [(r["id"], r["lat"], r["lon"]) for r in store.q("SELECT id, lat, lon FROM stations WHERE active=1")]
    near = idw_weights(lat, lon, rows, max_km=15.0, k=4)
    out = []
    for w in near:
        r = store.one("SELECT hour, pm25 FROM obs WHERE station_id=? ORDER BY hour DESC LIMIT 1", (w.id,))
        name = store.one("SELECT name FROM stations WHERE id=?", (w.id,))["name"]
        if r:
            hour = datetime.fromisoformat(r["hour"])
            out.append(
                {
                    "station": name,
                    "km": round(w.distance_km, 1),
                    "pm25": round(r["pm25"], 1),
                    "category": pm25_category(r["pm25"]),
                    "hour": hour.strftime("%Y-%m-%d %H:00"),
                    "hours_old": round((now - hour).total_seconds() / 3600 - 1, 1),
                }
            )
    return {"status": "ok" if out else "no_data", "readings": out}
