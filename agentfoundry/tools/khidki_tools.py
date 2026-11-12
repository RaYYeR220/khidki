"""Khidki tools for the AgentFoundry agents.

Each tool calls the live Khidki API, so every number an agent states comes from
India's government air monitors and the engine's forecast, never from the
model. Standard library only, so AgentFoundry's tool tester can run them as is.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

API = os.environ.get("KHIDKI_API", "https://khidki-engine-ptslyhnp7q-el.a.run.app")


def tool(fn):
    """Marks a function as an agent tool (picked up by AgentFoundry's tool scan)."""
    fn.is_tool = True
    return fn


def _get(path: str, params: dict) -> dict:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    with urllib.request.urlopen(f"{API}{path}?{q}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


@tool
def find_window(
    lat: float,
    lon: float,
    activity: str = "walk",
    minutes: int = 60,
    earliest: str = "05:00",
    latest_end: str = "21:00",
    usual_time: str = "06:00",
    day: str = "tomorrow",
    age: str = "adult",
) -> dict:
    """Cleanest start time for an outdoor activity at a place in India.

    activity: walk, run, cycle, yoga, play, commute_walk, commute_two_wheeler, errand, outdoor_work.
    Times are 24-hour HH:MM; day is today, tomorrow or YYYY-MM-DD; age is child, adult or older.
    Returns the best and usual slots with forecast PM2.5, % less PM2.5, confidence, flags,
    the CPCB health note and the monitors used.
    """
    out = _get(
        "/v1/window",
        dict(lat=lat, lon=lon, activity=activity, minutes=minutes, earliest=earliest,
             latest_end=latest_end, habitual=usual_time, day=day, age=age),
    )
    out.pop("curve", None)
    return out


@tool
def find_airing_time(lat: float, lon: float, open_minutes: int = 30, usual_time: str = "07:00", day: str = "tomorrow") -> dict:
    """When to open a home's windows so the people inside breathe the least outdoor PM2.5."""
    return _get("/v1/airing", dict(lat=lat, lon=lon, open_minutes=open_minutes, habitual=usual_time, day=day))


@tool
def air_now(lat: float, lon: float) -> dict:
    """Latest measured PM2.5 at the government monitors within 15 km of a place in India."""
    return _get("/v1/air-now", dict(lat=lat, lon=lon))


@tool
def monitor_health(day: str = "") -> dict:
    """Data-quality flags for India's air monitors on a day, with exact summary counts."""
    return _get("/v1/audit", dict(day=day))


if __name__ == "__main__":
    print(json.dumps(find_window(28.5931, 77.2197), indent=1)[:1200])
