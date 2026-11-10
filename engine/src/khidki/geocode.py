"""Place search inside India (OpenStreetMap Nominatim), cached and throttled to
respect the public service's one-request-per-second policy."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

import httpx

from .ratelimit import RateLimiter

_lock = threading.Lock()
_last = [0.0]
_cache: OrderedDict[tuple[str, int], tuple[dict, ...]] = OrderedDict()
_cache_lock = threading.Lock()
_upstream = RateLimiter(rate_per_min=55, burst=5)  # spent only on cache misses
UA = "khidki-air/0.1 (clean-air window planner; https://github.com/RaYYeR220/khidki)"


def search(q: str, limit: int = 5) -> tuple[dict, ...]:
    q = " ".join(q.split())[:120]
    if len(q) < 2:
        return ()
    key = (q.lower(), limit)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not _upstream.allow("nominatim"):
        raise Busy("place search is busy, try again in a moment")
    out = _search_upstream(q, limit)
    with _cache_lock:
        _cache[key] = out
        while len(_cache) > 2048:
            _cache.popitem(last=False)
    return out


def _search_upstream(q: str, limit: int) -> tuple[dict, ...]:
    # One request in flight at a time, at most one per second (Nominatim policy).
    # Callers that would wait more than ~3 s are turned away instead of queueing.
    if not _lock.acquire(timeout=3):
        raise Busy("place search is busy, try again in a moment")
    try:
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        return _fetch(q, limit)
    finally:
        _last[0] = time.monotonic()
        _lock.release()


class Busy(RuntimeError):
    pass


def _fetch(q: str, limit: int) -> tuple[dict, ...]:
    r = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "countrycodes": "in", "format": "jsonv2", "limit": limit, "addressdetails": 0},
        headers={"user-agent": UA, "accept-language": "en"},
        timeout=8,
    )
    r.raise_for_status()
    return tuple(
        {"name": i.get("display_name", "")[:140], "lat": round(float(i["lat"]), 5), "lon": round(float(i["lon"]), 5)}
        for i in r.json()
    )
