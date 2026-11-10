"""Monitor-network audit: data-quality flags for government air monitors.

These are flags about the DATA a monitor reported, never accusations about
anyone's conduct. Each flag says what was observed and how to check it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping

from .geo import haversine_km

SEVERE = 250.0


@dataclass
class Flag:
    station_id: str
    day: str
    kind: str  # missing_hours | frozen_value | dark_during_severe | disagrees_with_neighbours | implausible_value
    severity: str  # info | warn | high
    detail: dict = field(default_factory=dict)


def _day_hours(day_start: datetime) -> list[datetime]:
    return [day_start + timedelta(hours=i) for i in range(24)]


def missing_hours(series: Mapping[datetime, float], day_start: datetime) -> list[datetime]:
    return [h for h in _day_hours(day_start) if h not in series]


def frozen_runs(series: Mapping[datetime, float], day_start: datetime, min_len: int = 4) -> list[tuple[datetime, int, float]]:
    """Runs of >= min_len consecutive hours reporting exactly the same value."""
    runs: list[tuple[datetime, int, float]] = []
    hours = _day_hours(day_start)
    i = 0
    while i < len(hours):
        v = series.get(hours[i])
        if v is None:
            i += 1
            continue
        j = i + 1
        while j < len(hours) and series.get(hours[j]) == v:
            j += 1
        if j - i >= min_len:
            runs.append((hours[i], j - i, v))
        i = j
    return runs


def audit_day(
    day_start: datetime,
    stations: Mapping[str, tuple[float, float]],
    series: Mapping[str, Mapping[datetime, float]],
    *,
    neighbour_km: float = 10.0,
    min_missing: int = 4,
    ratio_hi: float = 2.0,
    ratio_lo: float = 0.5,
) -> list[Flag]:
    """Audit one day of hourly PM2.5 across a set of stations.

    ``stations``: id → (lat, lon). ``series``: id → hour → value (stations with
    no data at all may be absent from ``series``).
    """
    day = day_start.date().isoformat()
    flags: list[Flag] = []
    hours = _day_hours(day_start)

    neighbours: dict[str, list[str]] = {}
    ids = list(stations)
    for a in ids:
        la, oa = stations[a]
        neighbours[a] = [b for b in ids if b != a and haversine_km(la, oa, *stations[b]) <= neighbour_km]

    def nb_median(sid: str, h: datetime) -> float | None:
        vals = [series[b][h] for b in neighbours[sid] if b in series and h in series[b]]
        return statistics.median(vals) if vals else None

    for sid in ids:
        s = series.get(sid, {})
        miss = missing_hours(s, day_start)
        if len(miss) == 24:
            flags.append(Flag(sid, day, "missing_hours", "high", {"missing": 24, "note": "no data reported all day"}))
        elif len(miss) >= min_missing:
            flags.append(Flag(sid, day, "missing_hours", "warn", {"missing": len(miss), "hours": [h.strftime("%H") for h in miss]}))

        dark_severe = [h for h in miss if (m := nb_median(sid, h)) is not None and m >= SEVERE]
        if dark_severe:
            flags.append(
                Flag(
                    sid,
                    day,
                    "dark_during_severe",
                    "high",
                    {
                        "hours": [h.strftime("%H") for h in dark_severe],
                        "neighbour_median": [round(nb_median(sid, h) or 0) for h in dark_severe],
                        "note": "no reading while monitors within %g km read Severe" % neighbour_km,
                    },
                )
            )

        runs = frozen_runs(s, day_start)
        if runs:  # one flag per monitor per day, listing every frozen stretch
            flags.append(
                Flag(
                    sid,
                    day,
                    "frozen_value",
                    "warn",
                    {
                        "runs": [{"from": a.strftime("%H"), "hours": n, "value": v} for a, n, v in runs],
                        "hours": sum(n for _, n, _ in runs),
                    },
                )
            )

        implausible = [h for h in hours if h in s and (s[h] <= 0 or s[h] >= 999)]
        if implausible:
            flags.append(Flag(sid, day, "implausible_value", "warn", {"hours": [h.strftime("%H") for h in implausible]}))

        own = [s[h] for h in hours if h in s]
        nb = [m for h in hours if h in s and (m := nb_median(sid, h)) is not None]
        if len(own) >= 12 and len(nb) >= 12:
            own_mean = statistics.mean(own)
            nb_mean = statistics.mean(nb)
            if nb_mean > 0:
                ratio = own_mean / nb_mean
                if ratio >= ratio_hi or ratio <= ratio_lo:
                    flags.append(
                        Flag(
                            sid,
                            day,
                            "disagrees_with_neighbours",
                            "info",
                            {
                                "station_mean": round(own_mean, 1),
                                "neighbour_mean": round(nb_mean, 1),
                                "ratio": round(ratio, 2),
                                "neighbours": len(neighbours[sid]),
                            },
                        )
                    )
    return flags
