"""Verification against measured data.

A recommendation is published before the day starts. Once the station has
reported the actual hourly values, we score it: how much PM2.5 would a person
have breathed at the recommended time versus their usual time, and how close
did the recommendation get to the best time in hindsight (the oracle).

Everything here is arithmetic on measured values. Missing measurements make the
verdict ``unverifiable``; they are never filled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from .exposure import interval_dose
from .planner import candidate_starts


@dataclass(frozen=True)
class Verdict:
    status: str  # verified | unverifiable
    chosen_start: datetime
    habitual_start: datetime | None
    minutes: int
    chosen_mean: float | None = None
    habitual_mean: float | None = None
    oracle_start: datetime | None = None
    oracle_mean: float | None = None
    dose_avoided_ug: float | None = None  # vs habitual, measured
    reduction_pct: float | None = None  # vs habitual, measured
    captured_fraction: float | None = None  # (habitual-chosen)/(habitual-oracle)
    beat_habitual: bool | None = None
    reason: str | None = None


def verify_choice(
    observed: Mapping[datetime, float],
    *,
    chosen_start: datetime,
    minutes: int,
    rate_m3_per_min: float,
    habitual_start: datetime | None,
    earliest: datetime,
    latest_end: datetime,
    step_minutes: int = 15,
) -> Verdict:
    chosen = interval_dose(observed, chosen_start, minutes, rate_m3_per_min)
    if chosen is None:
        return Verdict("unverifiable", chosen_start, habitual_start, minutes, reason="no measurements for the chosen time")

    oracle_start, oracle = None, None
    for s in candidate_starts(earliest, latest_end, minutes, step_minutes):
        d = interval_dose(observed, s, minutes, rate_m3_per_min)
        if d is None:
            continue
        if oracle is None or d.dose_ug < oracle.dose_ug:
            oracle_start, oracle = s, d

    v = dict(
        status="verified",
        chosen_start=chosen_start,
        habitual_start=habitual_start,
        minutes=minutes,
        chosen_mean=chosen.mean_conc,
        oracle_start=oracle_start,
        oracle_mean=oracle.mean_conc if oracle else None,
    )
    if habitual_start is not None:
        hab = interval_dose(observed, habitual_start, minutes, rate_m3_per_min)
        if hab is None:
            return Verdict(
                "unverifiable",
                chosen_start,
                habitual_start,
                minutes,
                chosen_mean=chosen.mean_conc,
                reason="no measurements for the usual time",
            )
        avoided = hab.dose_ug - chosen.dose_ug
        v.update(
            habitual_mean=hab.mean_conc,
            dose_avoided_ug=avoided,
            reduction_pct=100.0 * avoided / hab.dose_ug if hab.dose_ug > 0 else 0.0,
            beat_habitual=avoided > 0,
        )
        if oracle is not None:
            best_gain = hab.dose_ug - oracle.dose_ug
            v["captured_fraction"] = (avoided / best_gain) if best_gain > 1e-9 else 1.0
    return Verdict(**v)


def day_hours(day_start: datetime, n: int = 24) -> list[datetime]:
    return [day_start + timedelta(hours=i) for i in range(n)]
