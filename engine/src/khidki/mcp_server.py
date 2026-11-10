"""Khidki as tools for other agents (Model Context Protocol, streamable HTTP).

Any MCP-capable assistant can ask Khidki for the cleanest window at a place,
the airing time, the latest readings, a day's public commitment or the monitor
audit. Read-only: no tool here changes state.
"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from . import service
from .exposure import Activity, AgeBand
from .jobs import now_ist

mcp = MCPServer(
    name="khidki",
    title="Khidki clean-air windows",
    description="When is the air cleanest today at a place in India, from India's government air monitors.",
    instructions=(
        "Use find_window to get the cleanest start time for an outdoor activity at a latitude/longitude in India. "
        "Numbers are forecasts from government monitor data; status other than 'ok' means no answer is available."
    ),
    version="0.1.0",
)


def _store():
    from .api import get_store

    return get_store()


def _cams(lat: float, lon: float):
    from .api import _cams_point

    return _cams_point(lat, lon)


@mcp.tool(description="Cleanest start time for an outdoor activity at a place in India, with the % less PM2.5 than the usual time.")
def find_window(
    lat: float,
    lon: float,
    activity: str = "walk",
    minutes: int = 60,
    earliest: str = "05:00",
    latest_end: str = "21:00",
    usual_time: str = "06:00",
    day: str = "today",
    age: str = "adult",
) -> dict:
    try:
        w = service.compute_window(
            _store(), lat=lat, lon=lon, activity=Activity(activity), minutes=minutes, earliest=earliest,
            latest_end=latest_end, habitual=usual_time or None, age=AgeBand(age), day=day, now=now_ist(),
            cams_fallback=_cams,
        )
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    w.pop("inhalation_m3_per_min", None)
    return w


@mcp.tool(description="When to open a home's windows for fresh air so the people inside breathe the least outdoor PM2.5.")
def find_airing_time(lat: float, lon: float, open_minutes: int = 30, day: str = "tomorrow") -> dict:
    try:
        return service.compute_airing(_store(), lat=lat, lon=lon, open_minutes=open_minutes, day=day, now=now_ist(), cams_fallback=_cams)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}


@mcp.tool(description="Latest measured PM2.5 at the government monitors within 15 km of a place in India.")
def air_now(lat: float, lon: float) -> dict:
    try:
        service._check_point(lat, lon)
    except ValueError as e:
        return {"status": "error", "reason": str(e)}
    return service.air_now(_store(), lat, lon, now_ist())


@mcp.tool(description="The public commitment for a day: SHA-256 and counts of the recommendations published before it began.")
def ledger_day(day: str) -> dict:
    r = _store().one("SELECT day, issued_at, model, sha256, n_stations, n_recommendations, anchor FROM commitments WHERE day=?", (day,))
    return dict(r) if r else {"status": "not_found", "day": day}


@mcp.tool(description="Data-quality flags for India's air monitors on a day (silent, frozen, dark during Severe air, disagreeing).")
def monitor_health(day: str = "") -> dict:
    store = _store()
    if not day:
        r = store.one("SELECT MAX(day) d FROM audit_flags")
        day = r["d"] if r and r["d"] else ""
    rows = store.q("SELECT station_id, kind, severity, detail FROM audit_flags WHERE day=?", (day,))
    return {"day": day, "flags": [{**{k: r[k] for k in ("station_id", "kind", "severity")}, "detail": json.loads(r["detail"])} for r in rows][:300]}
