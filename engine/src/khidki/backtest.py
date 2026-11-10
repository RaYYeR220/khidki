"""Walk-forward backtest of window recommendations against measured data.

For every station and every day, each forecast model is issued at 21:00 IST the
evening before (using only measurements up to then) and the planner picks a
window for a set of everyday scenarios. We then measure, on the station's real
readings, how much PM2.5 each policy would have made a person breathe:

* ``habitual``      – the time they go anyway (the baseline people live with),
* ``rule_of_thumb`` – a fixed "go at 3 pm" heuristic, clipped to their window,
* one row per forecast model,
* ``oracle``        – the best time in hindsight (upper bound, not achievable).
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Mapping

from .exposure import Activity, AgeBand, inhalation_rate, interval_dose
from .forecast import MODELS, make_forecast, obs_before
from .planner import candidate_starts, plan_window

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    activity: Activity
    age: AgeBand
    minutes: int
    habitual: time
    earliest: time
    latest_end: time


SCENARIOS: list[Scenario] = [
    Scenario("morning_walk", "Daily walk, any time of day (usually 6:00)", Activity.walk, AgeBand.adult, 60, time(6), time(5), time(21)),
    Scenario("before_work", "Walk that must finish before 10:00 (usually 6:30)", Activity.walk, AgeBand.adult, 45, time(6, 30), time(5), time(10)),
    Scenario("evening_walk", "Evening walk, 15:00–22:00 (usually 18:30)", Activity.walk, AgeBand.older, 60, time(18, 30), time(15), time(22)),
    Scenario("school_play", "School outdoor play, school hours (usually 8:00)", Activity.play, AgeBand.child, 45, time(8), time(8), time(14)),
    Scenario("runner", "Run, any time of day (usually 6:00)", Activity.run, AgeBand.adult, 45, time(6), time(5), time(21)),
]

RULE_OF_THUMB = time(15)


def _at(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=IST)


def _clip_start(t: datetime, earliest: datetime, latest_end: datetime, minutes: int) -> datetime:
    latest_start = latest_end - timedelta(minutes=minutes)
    return min(max(t, earliest), latest_start)


@dataclass
class DayResult:
    station: str
    day: str
    scenario: str
    policy: str
    start: str
    mean_conc: float
    dose_ug: float
    habitual_dose_ug: float
    oracle_dose_ug: float


def backtest_station(
    station: str,
    obs: Mapping[datetime, float],
    cams: Mapping[datetime, float],
    days: Iterable[date],
    *,
    scenarios: list[Scenario] = SCENARIOS,
    models: tuple[str, ...] = MODELS,
    issue_hour: int = 21,
    step_minutes: int = 15,
) -> list[DayResult]:
    rows: list[DayResult] = []
    for day in days:
        day_start = _at(day, time(0))
        issued_at = day_start - timedelta(hours=24 - issue_hour)
        past = obs_before(obs, issued_at)
        forecasts = {}
        for m in models:
            f = make_forecast(m, obs=past, cams=cams, day_start=day_start, issued_at=issued_at)
            if f is not None:
                forecasts[m] = f
        for sc in scenarios:
            rate = inhalation_rate(sc.activity, sc.age)
            earliest, latest_end = _at(day, sc.earliest), _at(day, sc.latest_end)
            hab_start = _at(day, sc.habitual)
            hab = interval_dose(obs, hab_start, sc.minutes, rate)
            if hab is None:
                continue
            # oracle over measured values
            oracle_start, oracle = None, None
            for s in candidate_starts(earliest, latest_end, sc.minutes, step_minutes):
                d = interval_dose(obs, s, sc.minutes, rate)
                if d is not None and (oracle is None or d.dose_ug < oracle.dose_ug):
                    oracle_start, oracle = s, d
            if oracle is None:
                continue
            policies: dict[str, datetime] = {
                "habitual": hab_start,
                "rule_of_thumb": _clip_start(_at(day, RULE_OF_THUMB), earliest, latest_end, sc.minutes),
                "oracle": oracle_start,
            }
            for m, f in forecasts.items():
                p = plan_window(
                    f.values,
                    activity=sc.activity,
                    age=sc.age,
                    minutes=sc.minutes,
                    earliest=earliest,
                    latest_end=latest_end,
                    step_minutes=step_minutes,
                )
                if p.status == "ok" and p.best is not None:
                    policies[m] = p.best.start
            for name, start in policies.items():
                d = interval_dose(obs, start, sc.minutes, rate)
                if d is None:
                    continue
                rows.append(
                    DayResult(
                        station=station,
                        day=day.isoformat(),
                        scenario=sc.key,
                        policy=name,
                        start=start.strftime("%H:%M"),
                        mean_conc=round(d.mean_conc, 2),
                        dose_ug=round(d.dose_ug, 3),
                        habitual_dose_ug=round(hab.dose_ug, 3),
                        oracle_dose_ug=round(oracle.dose_ug, 3),
                    )
                )
    return rows


def summarise(rows: list[DayResult]) -> dict:
    """Per scenario × policy: dose-weighted reduction vs habitual, share of the
    hindsight-best gain captured, win rate vs the rule of thumb, and how often
    the policy made things worse than the habit."""
    out: dict = {}
    keyed: dict[tuple[str, str, str, str], DayResult] = {(r.station, r.day, r.scenario, r.policy): r for r in rows}
    scenarios = sorted({r.scenario for r in rows})
    policies = sorted({r.policy for r in rows})
    for sc in scenarios:
        out[sc] = {}
        for pol in policies:
            rs = [r for r in rows if r.scenario == sc and r.policy == pol]
            if not rs:
                continue
            hab_total = sum(r.habitual_dose_ug for r in rs)
            dose_total = sum(r.dose_ug for r in rs)
            gain_possible = sum(r.habitual_dose_ug - r.oracle_dose_ug for r in rs)
            gain = hab_total - dose_total
            vs_rule = []
            for r in rs:
                rr = keyed.get((r.station, r.day, sc, "rule_of_thumb"))
                if rr is not None:
                    vs_rule.append(r.dose_ug < rr.dose_ug - 1e-9)
            out[sc][pol] = {
                "station_days": len(rs),
                "reduction_vs_habitual_pct": round(100 * gain / hab_total, 2) if hab_total else None,
                "captured_of_hindsight_best_pct": round(100 * gain / gain_possible, 2) if gain_possible > 0 else None,
                "beats_rule_of_thumb_pct": round(100 * statistics.mean(vs_rule), 1) if vs_rule else None,
                "worse_than_habitual_pct": round(100 * statistics.mean([r.dose_ug > r.habitual_dose_ug + 1e-9 for r in rs]), 1),
                "mean_conc": round(statistics.mean(r.mean_conc for r in rs), 1),
                "dose_avoided_ug_per_day": round(gain / len(rs), 2),
            }
    return out


def rows_as_dicts(rows: list[DayResult]) -> list[dict]:
    return [asdict(r) for r in rows]
