"""Day-ahead hourly PM2.5 forecasts for one monitoring station.

Every model sees only data available at issue time (the evening before the
target day). Candidates:

* ``clim``       – median of the last N days at each hour (the station's own
                   recent daily rhythm).
* ``yesterday``  – yesterday's measured values, hour by hour.
* ``cams``       – raw CAMS global forecast at the station's coordinates.
* ``cams_bc``    – CAMS corrected by the station's recent hour-of-day log bias.
* ``blend``      – geometric blend of ``clim`` and ``cams_bc``: the station's
                   rhythm, nudged by the weather CAMS expects tomorrow.

The window planner only needs the *shape* of tomorrow right; levels matter for
the dose estimate, which is re-measured after the fact anyway.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

Series = Mapping[datetime, float]

MODELS = ("clim", "yesterday", "cams", "cams_bc", "blend")


@dataclass
class Forecast:
    model: str
    issued_at: datetime
    values: dict[datetime, float]
    sigma_log: dict[datetime, float]


def _hours(day_start: datetime, n: int = 24) -> list[datetime]:
    return [day_start + timedelta(hours=i) for i in range(n)]


def _floor(x: float) -> float:
    return max(x, 1.0)


def clim_profile(obs: Series, day_start: datetime, days: int = 14, min_samples: int = 4) -> dict[int, float]:
    by_hour: dict[int, list[float]] = {}
    for d in range(1, days + 1):
        base = day_start - timedelta(days=d)
        for h in range(24):
            v = obs.get(base + timedelta(hours=h))
            if v is not None:
                by_hour.setdefault(h, []).append(v)
    return {h: statistics.median(v) for h, v in by_hour.items() if len(v) >= min_samples}


def log_bias_profile(
    obs: Series, cams: Series, day_start: datetime, days: int = 14, min_samples: int = 4, shrink: float = 4.0
) -> dict[int, float]:
    """Median log(obs/cams) per hour-of-day, shrunk towards the all-hours median."""
    per_hour: dict[int, list[float]] = {}
    for d in range(1, days + 1):
        base = day_start - timedelta(days=d)
        for h in range(24):
            t = base + timedelta(hours=h)
            o, c = obs.get(t), cams.get(t)
            if o is not None and c is not None and o > 0 and c > 0:
                per_hour.setdefault(h, []).append(math.log(_floor(o)) - math.log(_floor(c)))
    flat = [x for v in per_hour.values() for x in v]
    if len(flat) < min_samples:
        return {}
    overall = statistics.median(flat)
    out = {}
    for h in range(24):
        v = per_hour.get(h, [])
        n = len(v)
        m = statistics.median(v) if v else overall
        out[h] = (n * m + shrink * overall) / (n + shrink)
    return out


def residual_sigma(obs: Series, profile: dict[int, float], day_start: datetime, days: int = 14) -> dict[int, float]:
    """Spread (std of log ratio) of measured values around a profile, per hour."""
    per_hour: dict[int, list[float]] = {}
    for d in range(1, days + 1):
        base = day_start - timedelta(days=d)
        for h, p in profile.items():
            v = obs.get(base + timedelta(hours=h))
            if v is not None and v > 0 and p > 0:
                per_hour.setdefault(h, []).append(math.log(_floor(v)) - math.log(_floor(p)))
    return {h: (statistics.pstdev(v) if len(v) > 1 else 0.6) for h, v in per_hour.items()}


def make_forecast(
    model: str,
    *,
    obs: Series,
    cams: Series,
    day_start: datetime,
    issued_at: datetime | None = None,
    days: int = 14,
    alpha: float = 0.5,
) -> Forecast | None:
    """Forecast the 24 hours starting ``day_start``. ``obs`` must only contain
    values measured before ``issued_at`` (the caller enforces the cut-off);
    ``cams`` may contain both the past (for bias fitting) and the target day."""
    issued_at = issued_at or (day_start - timedelta(hours=3))
    hours = _hours(day_start)
    clim = clim_profile(obs, day_start, days)
    sigma_c = residual_sigma(obs, clim, day_start, days) if clim else {}

    if model == "clim":
        if len(clim) < 24:
            return None
        vals = {t: clim[t.hour] for t in hours}
        sig = {t: sigma_c.get(t.hour, 0.6) for t in hours}
    elif model == "yesterday":
        vals = {t: obs[t - timedelta(days=1)] for t in hours if (t - timedelta(days=1)) in obs}
        if len(vals) < 24:
            return None
        sig = {t: sigma_c.get(t.hour, 0.6) for t in hours}
    elif model == "cams":
        vals = {t: cams[t] for t in hours if t in cams}
        if len(vals) < 24:
            return None
        sig = {t: 0.6 for t in hours}
    elif model in ("cams_bc", "blend"):
        bias = log_bias_profile(obs, cams, day_start, days)
        if not bias or any(t not in cams for t in hours):
            return None
        bc = {t: math.exp(math.log(_floor(cams[t])) + bias[t.hour]) for t in hours}
        if model == "cams_bc":
            vals = bc
            sig = {t: sigma_c.get(t.hour, 0.6) for t in hours}
        else:
            if len(clim) < 24:
                return None
            vals = {
                t: math.exp(alpha * math.log(_floor(clim[t.hour])) + (1 - alpha) * math.log(_floor(bc[t])))
                for t in hours
            }
            sig = {t: sigma_c.get(t.hour, 0.6) * 0.9 for t in hours}
    else:
        raise ValueError(f"unknown model {model}")
    return Forecast(model=model, issued_at=issued_at, values=vals, sigma_log=sig)


def obs_before(obs: Series, cutoff: datetime) -> dict[datetime, float]:
    """Measurements whose hour ENDED at or before ``cutoff``."""
    return {t: v for t, v in obs.items() if t + timedelta(hours=1) <= cutoff}
