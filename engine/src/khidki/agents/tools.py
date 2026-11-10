"""Tools the Khidki agents can call.

Every number an agent says must come from one of these tools. Tools return
plain dicts with a ``status`` field; a non-"ok" status means the agent must say
it cannot answer and why, never guess.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import httpx
from google.adk.tools import ToolContext

from .. import people, service
from ..exposure import Activity, AgeBand
from ..jobs import now_ist
from ..store import Store

ACTIVITIES = [a.value for a in Activity]
AGES = [a.value for a in AgeBand]


@lru_cache(maxsize=1)
def _store() -> Store:
    return Store(os.environ.get("KHIDKI_DB", "data/khidki.db"))


def _cams(lat: float, lon: float):
    from ..sources.openmeteo import OpenMeteo

    return OpenMeteo().cams(lat, lon, past_days=16, forecast_days=2).series("pm2_5")


def _where(tool_context: ToolContext | None, lat: float | None, lon: float | None) -> tuple[float, float] | None:
    if lat is not None and lon is not None:
        return lat, lon
    if tool_context is not None:
        st = tool_context.state
        if st.get("lat") is not None and st.get("lon") is not None:
            return float(st["lat"]), float(st["lon"])
    return None


def _pid(tool_context: ToolContext | None) -> int | None:
    """The person behind this conversation, only for channels that can receive
    reminders (Telegram). Web conversations are anonymous."""
    if tool_context is None or tool_context.state.get("channel") == "web":
        return None
    v = tool_context.state.get("person_id")
    return int(v) if v is not None else None


def find_place(name: str) -> dict:
    """Look up a place in India by name (a neighbourhood, park, school, city).

    Returns up to 5 candidates with latitude and longitude. Ask the person to
    confirm if more than one plausible match comes back.
    """
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "countrycodes": "in", "format": "jsonv2", "limit": 5},
            headers={"user-agent": "khidki-air/0.1 (clean-air window planner; https://github.com/RaYYeR220/khidki)"},
            timeout=15,
        )
        r.raise_for_status()
        items = r.json()
    except httpx.HTTPError as e:
        return {"status": "error", "reason": f"place search failed: {e.__class__.__name__}"}
    if not items:
        return {"status": "not_found", "query": name}
    return {
        "status": "ok",
        "candidates": [
            {"name": i.get("display_name", "")[:120], "lat": round(float(i["lat"]), 5), "lon": round(float(i["lon"]), 5)}
            for i in items
        ],
    }


def remember_location(lat: float, lon: float, tool_context: ToolContext) -> dict:
    """Save the person's home (or usual) location for future plans.

    Use after they share a location or confirm a place from find_place.
    """
    pid = _pid(tool_context)
    try:
        if pid is not None:
            people.set_location(_store(), pid, lat, lon)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    tool_context.state["lat"], tool_context.state["lon"] = lat, lon
    return {"status": "ok", "lat": lat, "lon": lon}


def find_window(
    activity: str,
    minutes: int,
    earliest: str,
    latest_end: str,
    usual_time: str,
    day: str,
    tool_context: ToolContext,
    age: str = "adult",
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """Find the cleanest time for an outdoor activity at the person's location.

    Args:
      activity: one of walk, run, cycle, yoga, play, commute_walk, commute_two_wheeler, errand, outdoor_work.
      minutes: how long the activity lasts.
      earliest: earliest acceptable start, 24-hour HH:MM.
      latest_end: time by which it must be over, 24-hour HH:MM.
      usual_time: when the person usually starts it, HH:MM (used to measure the gain).
      day: "today", "tomorrow" or YYYY-MM-DD.
      age: child (6-10), adult, or older (60+).
      lat, lon: optional; defaults to the saved location.

    Returns the best start, the usual start, the forecast PM2.5 for both, the
    % less PM2.5 breathed, confidence, flags and the official CPCB health note.
    """
    where = _where(tool_context, lat, lon)
    if where is None:
        return {"status": "need_location", "reason": "ask the person to share their location or name their area"}
    if activity not in ACTIVITIES:
        return {"status": "error", "reason": f"activity must be one of {ACTIVITIES}"}
    if age not in AGES:
        age = "adult"
    try:
        w = service.compute_window(
            _store(),
            lat=where[0],
            lon=where[1],
            activity=Activity(activity),
            minutes=int(minutes),
            earliest=earliest,
            latest_end=latest_end,
            habitual=usual_time or None,
            age=AgeBand(age),
            day=day,
            now=now_ist(),
            cams_fallback=_cams,
        )
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    w.pop("curve", None)  # the agent does not need 24 numbers; the app shows the curve
    w.pop("inhalation_m3_per_min", None)
    return w


def find_airing_time(
    tool_context: ToolContext,
    open_minutes: int = 30,
    earliest: str = "06:00",
    latest_end: str = "22:00",
    usual_time: str = "07:00",
    day: str = "tomorrow",
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """Find when to open the home's windows for fresh air so the people inside
    breathe the least outdoor smoke over the day."""
    where = _where(tool_context, lat, lon)
    if where is None:
        return {"status": "need_location"}
    try:
        return service.compute_airing(
            _store(), lat=where[0], lon=where[1], open_minutes=int(open_minutes), earliest=earliest,
            latest_end=latest_end, habitual=usual_time or None, day=day, now=now_ist(), cams_fallback=_cams,
        )
    except ValueError as e:
        return {"status": "error", "reason": str(e)}


def air_now(tool_context: ToolContext, lat: float | None = None, lon: float | None = None) -> dict:
    """Latest measured PM2.5 at the government monitors near the person."""
    where = _where(tool_context, lat, lon)
    if where is None:
        return {"status": "need_location"}
    return service.air_now(_store(), where[0], where[1], now_ist())


def save_routine(
    activity: str,
    minutes: int,
    usual_time: str,
    earliest: str,
    latest_end: str,
    tool_context: ToolContext,
    age: str = "adult",
    label: str = "",
) -> dict:
    """Save a daily routine so Khidki plans it every day and sends a reminder
    before the clean window. Confirm the details with the person first."""
    pid = _pid(tool_context)
    if pid is None:
        return {"status": "error", "reason": "routines can be saved in the Telegram bot"}
    try:
        rid = people.save_routine(
            _store(), pid, activity=activity, minutes=int(minutes), usual_time=usual_time,
            earliest=earliest, latest_end=latest_end, age=age if age in AGES else "adult", label=label or None,
        )
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    return {"status": "ok", "routine_id": rid}


def my_routines(tool_context: ToolContext) -> dict:
    """List the person's saved routines."""
    pid = _pid(tool_context)
    if pid is None:
        return {"status": "ok", "routines": []}
    return {"status": "ok", "routines": people.routines(_store(), pid)}


def stop_routine(routine_id: int, tool_context: ToolContext) -> dict:
    """Stop planning and reminding for one routine."""
    pid = _pid(tool_context)
    ok = pid is not None and people.stop_routine(_store(), pid, int(routine_id))
    return {"status": "ok" if ok else "not_found"}


def my_results(tool_context: ToolContext) -> dict:
    """The person's verified results: for each day they told us when they went
    out, the measured PM2.5 then versus at their usual time."""
    pid = _pid(tool_context)
    if pid is None:
        return {"status": "ok", "days_verified": 0, "items": []}
    return {"status": "ok", **people.results(_store(), pid)}


def monitor_health(day: str = "") -> dict:
    """Data-quality flags for government air monitors on a day (default: latest
    audited day): monitors that went dark, froze, or disagree with neighbours."""
    store = _store()
    if not day:
        r = store.one("SELECT MAX(day) d FROM audit_flags")
        day = r["d"] if r and r["d"] else ""
    rows = store.q(
        """SELECT f.station_id, s.name, s.city, f.kind, f.severity, f.detail FROM audit_flags f
           LEFT JOIN stations s ON s.id=f.station_id WHERE f.day=?""",
        (day,),
    )
    audited = store.one("SELECT COUNT(*) n FROM stations WHERE active=1")["n"]
    return {
        "status": "ok" if rows or audited else "no_data",
        "day": day,
        "monitors_audited": audited,
        "flags": [{**{k: r[k] for k in ("station_id", "name", "city", "kind", "severity")}, "detail": json.loads(r["detail"])} for r in rows][:200],
    }


PLANNER_TOOLS = [
    find_place,
    remember_location,
    find_window,
    find_airing_time,
    air_now,
    save_routine,
    my_routines,
    stop_routine,
    my_results,
]
AUDITOR_TOOLS = [monitor_health]
