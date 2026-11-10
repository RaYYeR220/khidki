"""Deterministic clean-air window planner.

Given an hourly PM2.5 forecast for one place, find the start time inside the
person's own constraints that minimises the PM2.5 they breathe, and compare it
with the time they would have gone anyway. No language model is involved: the
agent layer calls this and only explains the result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping

from .aqi import pm25_category
from .exposure import (
    INHALATION_RATE_M3_PER_MIN,
    Activity,
    AgeBand,
    Home,
    Intensity,
    indoor_series,
    inhalation_rate,
    interval_dose,
)

SEVERE_PM25 = 250.0  # NAQI "Severe" lower bound (µg/m³, 24-h basis)


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    mean_conc: float
    dose_ug: float


@dataclass
class WindowPlan:
    status: str  # ok | no_data | stale
    activity: str
    minutes: int
    best: Slot | None = None
    habitual: Slot | None = None
    worst: Slot | None = None
    alternatives: list[Slot] = field(default_factory=list)
    dose_avoided_ug: float | None = None
    reduction_pct: float | None = None
    best_category: str | None = None
    confidence: float | None = None  # P(best really beats habitual)
    flags: list[str] = field(default_factory=list)
    reason: str | None = None


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def candidate_starts(earliest: datetime, latest_end: datetime, minutes: int, step: int) -> list[datetime]:
    out: list[datetime] = []
    t = earliest
    last = latest_end - timedelta(minutes=minutes)
    while t <= last:
        out.append(t)
        t += timedelta(minutes=step)
    return out


def _slot(series: Mapping[datetime, float], start: datetime, minutes: int, rate: float) -> Slot | None:
    d = interval_dose(series, start, minutes, rate)
    if d is None:
        return None
    return Slot(start, start + timedelta(minutes=minutes), d.mean_conc, d.dose_ug)


def _non_overlapping(slots: list[Slot], k: int, exclude: Slot | None) -> list[Slot]:
    chosen: list[Slot] = []
    for s in slots:
        if exclude and s.start < exclude.end and exclude.start < s.end:
            continue
        if any(s.start < c.end and c.start < s.end for c in chosen):
            continue
        chosen.append(s)
        if len(chosen) == k:
            break
    return chosen


def _uncertainty_confidence(
    sigma_log: Mapping[datetime, float] | None, best: Slot, habitual: Slot
) -> float | None:
    if sigma_log is None or habitual.mean_conc <= 0 or best.mean_conc <= 0:
        return None

    def mean_sigma(slot: Slot) -> float | None:
        vals = []
        t = slot.start.replace(minute=0, second=0, microsecond=0)
        while t < slot.end:
            v = sigma_log.get(t)
            if v is None:
                return None
            vals.append(v)
            t += timedelta(hours=1)
        return sum(vals) / len(vals)

    sb, sh = mean_sigma(best), mean_sigma(habitual)
    if sb is None or sh is None:
        return None
    gap = math.log(habitual.mean_conc) - math.log(best.mean_conc)
    spread = math.sqrt(sb * sb + sh * sh)
    if spread == 0:
        return 1.0 if gap > 0 else 0.5
    return _phi(gap / spread)


def plan_window(
    forecast: Mapping[datetime, float],
    *,
    activity: Activity,
    minutes: int,
    earliest: datetime,
    latest_end: datetime,
    habitual_start: datetime | None = None,
    age: AgeBand = AgeBand.adult,
    step_minutes: int = 15,
    sigma_log: Mapping[datetime, float] | None = None,
    issued_at: datetime | None = None,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=30),
    alternatives: int = 2,
) -> WindowPlan:
    """Pick the cleanest start time for an outdoor activity.

    Fails closed: if the forecast is older than ``max_age`` or does not cover any
    full candidate interval, the plan carries a non-ok status and no best slot.
    """
    plan = WindowPlan(status="ok", activity=activity.value, minutes=minutes)
    if minutes <= 0 or latest_end <= earliest:
        raise ValueError("invalid time constraints")
    if issued_at is not None and now is not None and now - issued_at > max_age:
        plan.status = "stale"
        plan.reason = f"forecast issued {issued_at.isoformat()} is older than {max_age}"
        return plan

    rate = inhalation_rate(activity, age)
    slots = [
        s
        for s in (_slot(forecast, t, minutes, rate) for t in candidate_starts(earliest, latest_end, minutes, step_minutes))
        if s is not None
    ]
    if not slots:
        plan.status = "no_data"
        plan.reason = "no forecast covers a full interval inside the allowed times"
        return plan

    ranked = sorted(slots, key=lambda s: (s.dose_ug, s.start))
    plan.best = ranked[0]
    plan.worst = max(slots, key=lambda s: (s.dose_ug, -s.start.timestamp()))
    plan.alternatives = _non_overlapping(ranked[1:], alternatives, plan.best)
    plan.best_category = pm25_category(plan.best.mean_conc)

    if habitual_start is not None:
        plan.habitual = _slot(forecast, habitual_start, minutes, rate)
        if plan.habitual is None:
            plan.flags.append("habitual_not_covered")
        else:
            avoided = plan.habitual.dose_ug - plan.best.dose_ug
            plan.dose_avoided_ug = avoided
            plan.reduction_pct = 100.0 * avoided / plan.habitual.dose_ug if plan.habitual.dose_ug > 0 else 0.0
            if avoided <= 1e-9:
                plan.flags.append("habitual_is_best")
            plan.confidence = _uncertainty_confidence(sigma_log, plan.best, plan.habitual)

    if plan.best.mean_conc >= SEVERE_PM25:
        plan.flags.append("severe_all_window")
    if len(slots) < len(candidate_starts(earliest, latest_end, minutes, step_minutes)):
        plan.flags.append("partial_coverage")
    return plan


# --- Airing: when to open the windows ------------------------------------------------


@dataclass
class AiringPlan:
    status: str
    open_minutes: int
    best_start: datetime | None = None
    habitual_start: datetime | None = None
    best_indoor_dose_ug: float | None = None
    habitual_indoor_dose_ug: float | None = None
    dose_avoided_ug: float | None = None
    reduction_pct: float | None = None
    best_outdoor_mean: float | None = None
    flags: list[str] = field(default_factory=list)
    reason: str | None = None


def _indoor_day_dose(
    outdoor: Mapping[datetime, float],
    hours: list[datetime],
    start: datetime,
    open_minutes: int,
    home: Home,
    rate: float,
) -> float:
    interval = [(start, start + timedelta(minutes=open_minutes))]
    indoor = indoor_series(outdoor, hours, interval, home)
    return sum(indoor[h] for h in hours) * rate * 60.0


def plan_airing(
    forecast: Mapping[datetime, float],
    *,
    day_start: datetime,
    open_minutes: int = 30,
    earliest: datetime,
    latest_end: datetime,
    habitual_start: datetime | None = None,
    home: Home = Home(),
    age: AgeBand = AgeBand.adult,
    step_minutes: int = 30,
) -> AiringPlan:
    """Choose when to open the windows for ``open_minutes`` so the people at home
    breathe the least PM2.5 over the 24 hours starting at ``day_start``."""
    plan = AiringPlan(status="ok", open_minutes=open_minutes)
    hours = [day_start + timedelta(hours=i) for i in range(24)]
    if any(h not in forecast for h in hours):
        plan.status = "no_data"
        plan.reason = "forecast does not cover the full day"
        return plan
    rate = INHALATION_RATE_M3_PER_MIN[age][Intensity.sedentary]
    starts = candidate_starts(earliest, latest_end, open_minutes, step_minutes)
    if not starts:
        raise ValueError("invalid airing window constraints")
    scored = [(s, _indoor_day_dose(forecast, hours, s, open_minutes, home, rate)) for s in starts]
    best_start, best_dose = min(scored, key=lambda x: (x[1], x[0]))
    plan.best_start = best_start
    plan.best_indoor_dose_ug = best_dose
    plan.best_outdoor_mean = forecast[best_start.replace(minute=0, second=0, microsecond=0)]
    if habitual_start is not None:
        hd = _indoor_day_dose(forecast, hours, habitual_start, open_minutes, home, rate)
        plan.habitual_start = habitual_start
        plan.habitual_indoor_dose_ug = hd
        plan.dose_avoided_ug = hd - best_dose
        plan.reduction_pct = 100.0 * (hd - best_dose) / hd if hd > 0 else 0.0
        if plan.dose_avoided_ug <= 1e-9:
            plan.flags.append("habitual_is_best")
    if plan.best_outdoor_mean is not None and plan.best_outdoor_mean >= SEVERE_PM25:
        plan.flags.append("keep_closed_if_possible")
    return plan
