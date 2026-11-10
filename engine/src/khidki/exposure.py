"""Inhaled-dose arithmetic.

Dose (µg) = concentration (µg/m³) × inhalation rate (m³/min) × minutes.

Inhalation rates are the mean short-term values from U.S. EPA Exposure Factors
Handbook (2011), Table 6-2 (males and females combined). We use three age bands
that cover the people Khidki plans for: children 6–<11, adults 31–<41 and
older adults 61–<71.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Mapping


class Intensity(str, Enum):
    sleep = "sleep"
    sedentary = "sedentary"
    light = "light"
    moderate = "moderate"
    high = "high"


class AgeBand(str, Enum):
    child = "child"  # 6 to <11 years
    adult = "adult"  # 31 to <41 years
    older = "older"  # 61 to <71 years


# m³/minute, EPA EFH 2011 Table 6-2, mean values.
INHALATION_RATE_M3_PER_MIN: dict[AgeBand, dict[Intensity, float]] = {
    AgeBand.child: {
        Intensity.sleep: 4.5e-3,
        Intensity.sedentary: 4.8e-3,
        Intensity.light: 1.1e-2,
        Intensity.moderate: 2.2e-2,
        Intensity.high: 4.2e-2,
    },
    AgeBand.adult: {
        Intensity.sleep: 4.6e-3,
        Intensity.sedentary: 4.3e-3,
        Intensity.light: 1.2e-2,
        Intensity.moderate: 2.7e-2,
        Intensity.high: 4.9e-2,
    },
    AgeBand.older: {
        Intensity.sleep: 5.2e-3,
        Intensity.sedentary: 4.9e-3,
        Intensity.light: 1.2e-2,
        Intensity.moderate: 2.6e-2,
        Intensity.high: 4.7e-2,
    },
}


class Activity(str, Enum):
    walk = "walk"  # brisk or morning walk
    run = "run"
    cycle = "cycle"
    yoga = "yoga"  # outdoor yoga / exercise in a park
    play = "play"  # children's outdoor play or school PE
    commute_walk = "commute_walk"
    commute_two_wheeler = "commute_two_wheeler"
    errand = "errand"  # shopping, waiting at a stop
    outdoor_work = "outdoor_work"


ACTIVITY_INTENSITY: dict[Activity, Intensity] = {
    Activity.walk: Intensity.moderate,
    Activity.run: Intensity.high,
    Activity.cycle: Intensity.high,
    Activity.yoga: Intensity.light,
    Activity.play: Intensity.high,
    Activity.commute_walk: Intensity.moderate,
    Activity.commute_two_wheeler: Intensity.light,
    Activity.errand: Intensity.light,
    Activity.outdoor_work: Intensity.moderate,
}


def inhalation_rate(activity: Activity, age: AgeBand = AgeBand.adult) -> float:
    """m³ of air breathed per minute for an activity."""
    return INHALATION_RATE_M3_PER_MIN[age][ACTIVITY_INTENSITY[activity]]


@dataclass(frozen=True)
class DoseResult:
    dose_ug: float  # µg of PM2.5 inhaled
    mean_conc: float  # time-weighted mean concentration over the interval
    minutes_covered: float  # minutes for which a concentration was known


def interval_dose(
    series: Mapping[datetime, float],
    start: datetime,
    minutes: float,
    rate_m3_per_min: float,
) -> DoseResult | None:
    """Dose over [start, start+minutes) from an hourly step series.

    ``series`` maps the START of each hour (tz-aware) to the hourly mean
    concentration for that hour. Returns None if any part of the interval falls
    in an hour with no value: we never fill gaps silently.
    """
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    end = start + timedelta(minutes=minutes)
    t = start
    weighted = 0.0
    covered = 0.0
    while t < end:
        hour = t.replace(minute=0, second=0, microsecond=0)
        nxt = min(hour + timedelta(hours=1), end)
        c = series.get(hour)
        if c is None:
            return None
        span = (nxt - t).total_seconds() / 60.0
        weighted += c * span
        covered += span
        t = nxt
    mean_c = weighted / covered
    return DoseResult(dose_ug=mean_c * rate_m3_per_min * covered, mean_conc=mean_c, minutes_covered=covered)


# --- Indoor air: single-zone mass balance -----------------------------------

@dataclass(frozen=True)
class Home:
    """Parameters of a typical naturally ventilated Indian home.

    ach_closed: air changes per hour with windows shut (leaky envelope).
    ach_open: air changes per hour with windows open.
    penetration: fraction of outdoor PM2.5 that survives entry through cracks.
    deposition: indoor particle loss rate (1/h).
    """

    ach_closed: float = 1.0
    ach_open: float = 6.0
    penetration: float = 0.8
    deposition: float = 0.2


def indoor_series(
    outdoor: Mapping[datetime, float],
    hours: list[datetime],
    open_intervals: list[tuple[datetime, datetime]],
    home: Home = Home(),
    c0: float | None = None,
    substeps: int = 12,
) -> dict[datetime, float]:
    """Simulate hourly-mean indoor PM2.5 for consecutive ``hours``.

    Windows are open during each [start, end) in ``open_intervals``: the exchange
    rate is then ``ach_open`` and penetration 1.0; otherwise ``ach_closed`` and
    ``home.penetration``. Explicit Euler with ``substeps`` per hour (dt = 5 min by
    default) is stable for ach_open ≤ 12. The initial indoor level is the
    closed-window steady state for the first hour unless ``c0`` is given.
    """
    if not hours:
        return {}
    cin = c0 if c0 is not None else outdoor[hours[0]] * home.penetration * home.ach_closed / (
        home.ach_closed + home.deposition
    )
    out: dict[datetime, float] = {}
    dt = 1.0 / substeps
    step = timedelta(minutes=60.0 / substeps)
    for h in hours:
        cout = outdoor[h]
        acc = 0.0
        for i in range(substeps):
            t = h + step * i
            is_open = any(a <= t < b for a, b in open_intervals)
            ach = home.ach_open if is_open else home.ach_closed
            p = 1.0 if is_open else home.penetration
            cin = cin + dt * (ach * p * cout - (ach + home.deposition) * cin)
            acc += cin
        out[h] = acc / substeps
    return out
