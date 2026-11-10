"""Place search inside India (OpenStreetMap Nominatim), cached and throttled to
respect the public service's one-request-per-second policy."""

from __future__ import annotations

import threading
import time
from functools import lru_cache

import httpx

_lock = threading.Lock()
_last = [0.0]
UA = "khidki-air/0.1 (clean-air window planner; https://github.com/RaYYeR220/khidki)"


@lru_cache(maxsize=2048)
def search(q: str, limit: int = 5) -> tuple[dict, ...]:
    q = " ".join(q.split())[:120]
    if len(q) < 2:
        return ()
    with _lock:
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    r = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "countrycodes": "in", "format": "jsonv2", "limit": limit, "addressdetails": 0},
        headers={"user-agent": UA, "accept-language": "en"},
        timeout=15,
    )
    r.raise_for_status()
    return tuple(
        {"name": i.get("display_name", "")[:140], "lat": round(float(i["lat"]), 5), "lon": round(float(i["lon"]), 5)}
        for i in r.json()
    )
