"""Forecast for any point: blend the published station forecasts around it.

Hours that have already happened use measured values (also distance-weighted).
For the rest of today, the forecast is nudged by how far today's readings have
drifted from it so far (a simple intraday nowcast). With no station within
range, we fall back to the raw CAMS model at the point and say so.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .geo import idw_weights
from .jobs import IST, day_start
from .store import Store


@dataclass
class PointForecast:
    day: str
    values: dict[datetime, float]
    sigma_log: dict[datetime, float]
    measured_hours: list[datetime]
    source: str  # stations | cams_only | none
    neighbours: list[dict] = field(default_factory=list)
    issued_at: str | None = None
    nowcast_factor: float | None = None


def _station_rows(store: Store) -> list[tuple[str, float, float]]:
    return [(r["id"], r["lat"], r["lon"]) for r in store.q("SELECT id, lat, lon FROM stations WHERE active=1")]


def point_forecast(
    store: Store,
    lat: float,
    lon: float,
    day: date,
    *,
    now: datetime | None = None,
    max_km: float = 15.0,
    cams_fallback=None,
) -> PointForecast:
    ds = day_start(day)
    hours = [ds + timedelta(hours=i) for i in range(24)]
    now = now or datetime.now(IST)
    weights = idw_weights(lat, lon, _station_rows(store), max_km=max_km)
    pf_vals: dict[datetime, float] = {}
    pf_sig: dict[datetime, float] = {}
    measured: list[datetime] = []
    used = []
    issued = None
    if weights:
        fc_rows = {
            r["station_id"]: r
            for r in store.q(
                f"SELECT * FROM forecasts WHERE day=? AND station_id IN ({','.join('?' * len(weights))})",
                [day.isoformat(), *[w.id for w in weights]],
            )
        }
        obs = {w.id: store.get_obs(w.id, ds, ds + timedelta(days=1)) for w in weights}
        name = {r["id"]: r["name"] for r in store.q("SELECT id, name FROM stations")}
        for w in weights:
            used.append({"id": w.id, "name": name.get(w.id), "km": round(w.distance_km, 2), "weight": round(w.weight, 3), "has_forecast": w.id in fc_rows})
        # forecast part
        fc_w = [(w, json.loads(fc_rows[w.id]["values_json"]), json.loads(fc_rows[w.id]["sigma_json"])) for w in weights if w.id in fc_rows]
        if fc_w:
            issued = max(fc_rows[w.id]["issued_at"] for w, _, _ in fc_w)
            tot = sum(w.weight for w, _, _ in fc_w)
            for h in hours:
                k = h.strftime("%H")
                pf_vals[h] = sum(w.weight * v[k] for w, v, _ in fc_w if k in v) / tot
                pf_sig[h] = sum(w.weight * s.get(k, 0.6) for w, _, s in fc_w) / tot
        # measured part (hours that already ended)
        for h in hours:
            if h + timedelta(hours=1) > now:
                continue
            vals = [(w.weight, obs[w.id][h]) for w in weights if h in obs[w.id]]
            if vals:
                tw = sum(a for a, _ in vals)
                pf_vals[h] = sum(a * v for a, v in vals) / tw
                pf_sig[h] = 0.05
                measured.append(h)
    factor = None
    if pf_vals and measured:
        # intraday nowcast: ratio of measured to forecast over the last 3 measured hours
        recent = sorted(measured)[-3:]
        ratios = []
        for h in recent:
            fc = _forecast_at(store, weights, day, h)
            if fc:
                ratios.append(pf_vals[h] / fc)
        if ratios:
            factor = statistics.median(ratios)
            last = max(measured)
            for h in hours:
                if h > last and h in pf_vals and h not in measured:
                    lead = (h - last).total_seconds() / 3600.0
                    f = 1 + (factor - 1) * max(0.0, 1 - lead / 12.0)
                    pf_vals[h] *= f
    if len(pf_vals) >= 24 or (pf_vals and not cams_fallback):
        return PointForecast(day.isoformat(), pf_vals, pf_sig, measured, "stations", used, issued, factor)
    if cams_fallback is not None:
        series = cams_fallback(lat, lon)
        vals = {h: series[h] for h in hours if h in series}
        if len(vals) == 24:
            return PointForecast(day.isoformat(), vals, {h: 0.7 for h in hours}, [], "cams_only", used, None, None)
    return PointForecast(day.isoformat(), {}, {}, [], "none", used, issued, None)


def _forecast_at(store: Store, weights, day: date, h: datetime) -> float | None:
    rows = store.q(
        f"SELECT station_id, values_json FROM forecasts WHERE day=? AND station_id IN ({','.join('?' * len(weights))})",
        [day.isoformat(), *[w.id for w in weights]],
    )
    k = h.strftime("%H")
    wmap = {w.id: w.weight for w in weights}
    num = den = 0.0
    for r in rows:
        v = json.loads(r["values_json"]).get(k)
        if v is not None:
            num += wmap[r["station_id"]] * v
            den += wmap[r["station_id"]]
    return num / den if den else None
