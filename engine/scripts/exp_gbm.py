"""Experiment: can weather (boundary-layer height, wind) beat the fixed 3 pm rule?

Walk-forward at one monitor: a LightGBM model of log PM2.5 is retrained every 7
days on all earlier days and forecasts the next day issued at 21:00. Compares
window choices on measured data with the habit, the fixed rule, the current
`blend` model and the hindsight best.

usage: uv run python scripts/exp_gbm.py <location_id> <lat> <lon> <train_start> <test_start> <test_end>
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np

from khidki.backtest import IST, RULE_OF_THUMB, SCENARIOS, summarise, DayResult
from khidki.exposure import inhalation_rate, interval_dose
from khidki.forecast import clim_profile, make_forecast, obs_before
from khidki.planner import candidate_starts, plan_window
from khidki.sources.openaq import Archive, hourly_pm25
from khidki.sources.openmeteo import OpenMeteo

WX = ["boundary_layer_height", "wind_speed_10m", "temperature_2m", "relative_humidity_2m"]


def features(day: date, obs_hist: dict, cams: dict, wx: dict) -> list[list[float]] | None:
    ds = datetime.combine(day, time(0), tzinfo=IST)
    clim = clim_profile(obs_hist, ds, 14)
    if len(clim) < 24:
        return None
    rows = []
    for h in range(24):
        t = ds + timedelta(hours=h)
        y = obs_hist.get(t - timedelta(days=1))
        c = cams.get(t)
        w = [wx[v].get(t) for v in WX]
        if c is None or any(x is None for x in w):
            return None
        rows.append(
            [
                h,
                math.sin(2 * math.pi * h / 24),
                math.cos(2 * math.pi * h / 24),
                math.log(max(c, 1)),
                math.log(max(clim[h], 1)),
                math.log(max(y, 1)) if y else math.log(max(clim[h], 1)),
                math.log(max(w[0], 10)),
                w[1],
                w[2],
                w[3],
                # the day's lift: afternoon lid over morning lid (forecast)
                math.log(max(wx["boundary_layer_height"].get(ds + timedelta(hours=14)) or 10, 10))
                - math.log(max(wx["boundary_layer_height"].get(ds + timedelta(hours=6)) or 10, 10)),
            ]
        )
    return rows


def main() -> None:
    loc, lat, lon = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
    train_start, test_start, test_end = (date.fromisoformat(x) for x in sys.argv[4:7])
    hist = train_start - timedelta(days=16)
    obs = hourly_pm25(Archive("data/cache/openaq").range(loc, hist, test_end + timedelta(days=1)))
    om = OpenMeteo()
    cams = om.cams(lat, lon, start=hist, end=test_end).series("pm2_5")
    wxf = om.weather(lat, lon, start=hist, end=test_end, variables=WX)
    wx = {v: wxf.series(v) for v in WX}

    def day_xy(d: date):
        ds = datetime.combine(d, time(0), tzinfo=IST)
        issued = ds - timedelta(hours=3)
        past = obs_before(obs, issued)
        X = features(d, past, cams, wx)
        if X is None:
            return None, None
        ys = [obs.get(ds + timedelta(hours=h)) for h in range(24)]
        return X, ys

    model = None
    last_train = None
    rows: list[DayResult] = []
    d = test_start
    while d <= test_end:
        if model is None or (d - last_train).days >= 7:
            Xs, Ys = [], []
            t = train_start
            while t < d:
                X, ys = day_xy(t)
                if X is not None:
                    for x, y in zip(X, ys):
                        if y is not None and y > 0:
                            Xs.append(x)
                            Ys.append(math.log(y))
                t += timedelta(days=1)
            model = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)
            model.fit(np.array(Xs), np.array(Ys))
            last_train = d
        X, _ = day_xy(d)
        ds = datetime.combine(d, time(0), tzinfo=IST)
        if X is not None:
            pred = {ds + timedelta(hours=h): float(math.exp(v)) for h, v in enumerate(model.predict(np.array(X)))}
            issued = ds - timedelta(hours=3)
            past = obs_before(obs, issued)
            blend = make_forecast("blend", obs=past, cams=cams, day_start=ds, issued_at=issued)
            for sc in SCENARIOS:
                rate = inhalation_rate(sc.activity, sc.age)
                e = datetime.combine(d, sc.earliest, tzinfo=IST)
                le = datetime.combine(d, sc.latest_end, tzinfo=IST)
                hab_s = datetime.combine(d, sc.habitual, tzinfo=IST)
                hab = interval_dose(obs, hab_s, sc.minutes, rate)
                if hab is None:
                    continue
                oracle_s, oracle = None, None
                for s in candidate_starts(e, le, sc.minutes, 15):
                    dd = interval_dose(obs, s, sc.minutes, rate)
                    if dd is not None and (oracle is None or dd.dose_ug < oracle.dose_ug):
                        oracle_s, oracle = s, dd
                if oracle is None:
                    continue
                pols = {
                    "habitual": hab_s,
                    "rule_of_thumb": min(max(datetime.combine(d, RULE_OF_THUMB, tzinfo=IST), e), le - timedelta(minutes=sc.minutes)),
                    "oracle": oracle_s,
                }
                for name, fc in (("gbm_weather", pred), ("blend", blend.values if blend else None)):
                    if fc:
                        p = plan_window(fc, activity=sc.activity, age=sc.age, minutes=sc.minutes, earliest=e, latest_end=le)
                        if p.best:
                            pols[name] = p.best.start
                for name, s in pols.items():
                    dd = interval_dose(obs, s, sc.minutes, rate)
                    if dd is None:
                        continue
                    rows.append(DayResult("x", d.isoformat(), sc.key, name, s.strftime("%H:%M"), round(dd.mean_conc, 2), round(dd.dose_ug, 3), round(hab.dose_ug, 3), round(oracle.dose_ug, 3)))
        d += timedelta(days=1)
    s = summarise(rows)
    Path("results").mkdir(exist_ok=True)
    Path(f"results/exp-gbm-weather-{loc}-{test_start}-{test_end}.json").write_text(json.dumps(s, indent=1))
    for sc, pols in s.items():
        print("==", sc)
        for p, m in sorted(pols.items(), key=lambda x: -(x[1]["reduction_vs_habitual_pct"] or -999)):
            print(f"  {p:14s} red {m['reduction_vs_habitual_pct']:7}%  capt {m['captured_of_hindsight_best_pct']}%  >rule {m['beats_rule_of_thumb_pct']}%  worse {m['worse_than_habitual_pct']}%  n={m['station_days']}")


if __name__ == "__main__":
    main()
