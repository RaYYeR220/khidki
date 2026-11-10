"""Walk-forward backtest across every reference-grade PM2.5 monitor in India.

usage: OPENAQ_API_KEY=... uv run python scripts/backtest_national.py 2025-11-01 2026-02-28 [--max N]

Data: hourly PM2.5 from the OpenAQ S3 archive (CPCB and state-board monitors),
CAMS from Open-Meteo. Writes results/backtest-national-<start>-<end>.json with
the pooled summary, a per-city table and a per-monitor table.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from khidki.backtest import backtest_station, summarise
from khidki.sources.openaq import Archive, OpenAQClient, hourly_pm25
from khidki.sources.openmeteo import OpenMeteo


def main() -> None:
    start, end = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
    max_n = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else None
    hist = start - timedelta(days=16)
    client = OpenAQClient()
    locs = [l for l in client.india_pm25_locations() if l.is_monitor and l.lat is not None]
    # monitors that existed during the period (last seen after it began)
    locs = [l for l in locs if not l.last_seen or l.last_seen[:10] >= start.isoformat()]
    locs.sort(key=lambda l: l.id)
    if max_n:
        locs = locs[:max_n]
    print("monitors", len(locs))

    arch = Archive("data/cache/openaq")

    def load(l):
        return l, hourly_pm25(arch.range(l.id, hist, end + timedelta(days=1), workers=4))

    with ThreadPoolExecutor(max_workers=8) as ex:
        obs_by = {l.id: (l, s) for l, s in ex.map(load, locs)}
    usable = [(l, s) for l, s in obs_by.values() if len(s) >= 24 * 30]
    print("with >=30 days of readings", len(usable))

    om = OpenMeteo()
    cams_by: dict[int, dict] = {}
    for i in range(0, len(usable), 25):
        chunk = usable[i : i + 25]
        frames = []
        # Open-Meteo accepts many coordinates with a date range in one request
        params_lat = [l.lat for l, _ in chunk]
        params_lon = [l.lon for l, _ in chunk]
        data = om._get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            {
                "latitude": ",".join(f"{x:.4f}" for x in params_lat),
                "longitude": ",".join(f"{x:.4f}" for x in params_lon),
                "hourly": "pm2_5",
                "timezone": "Asia/Kolkata",
                "domains": "cams_global",
                "start_date": hist.isoformat(),
                "end_date": end.isoformat(),
            },
        )
        frames = data if isinstance(data, list) else [data]
        from khidki.sources.openmeteo import _parse

        for (l, _), f in zip(chunk, frames):
            cams_by[l.id] = _parse(f, ["pm2_5"]).series("pm2_5")
        print("cams", min(i + 25, len(usable)), "/", len(usable))

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    all_rows = []
    per_station = {}
    by_city: dict[str, list] = defaultdict(list)
    for l, obs in usable:
        rows = backtest_station(f"oaq:{l.id}", obs, cams_by.get(l.id, {}), days)
        if not rows:
            continue
        all_rows.extend(rows)
        s = summarise(rows)
        per_station[f"oaq:{l.id}"] = {
            "name": l.name,
            "city": l.locality,
            "provider": l.provider,
            "lat": l.lat,
            "lon": l.lon,
            "morning_walk": s.get("morning_walk", {}),
        }
        by_city[l.locality or "unknown"].extend(rows)

    pooled = summarise(all_rows)
    cities = {}
    for city, rows in by_city.items():
        s = summarise(rows)
        mw = s.get("morning_walk", {})
        cities[city] = {
            "monitors": len({r.station for r in rows}),
            "station_days": mw.get("blend", {}).get("station_days"),
            "khidki_reduction_pct": mw.get("blend", {}).get("reduction_vs_habitual_pct"),
            "rule_reduction_pct": mw.get("rule_of_thumb", {}).get("reduction_vs_habitual_pct"),
            "oracle_reduction_pct": mw.get("oracle", {}).get("reduction_vs_habitual_pct"),
        }
    out = {
        "period": [start.isoformat(), end.isoformat()],
        "monitors_listed": len(locs),
        "monitors_used": len(per_station),
        "cities": len(cities),
        "station_days": len({(r.station, r.day) for r in all_rows}),
        "pooled": pooled,
        "by_city": dict(sorted(cities.items(), key=lambda kv: -(kv[1]["monitors"] or 0))),
        "by_monitor": per_station,
    }
    Path("results").mkdir(exist_ok=True)
    path = Path("results") / f"backtest-national-{start}-{end}.json"
    path.write_text(json.dumps(out, indent=1))
    print(path)
    mw = pooled.get("morning_walk", {})
    for pol in ("habitual", "rule_of_thumb", "clim", "cams", "cams_bc", "blend", "oracle"):
        if pol in mw:
            print(f"{pol:14s} {mw[pol]['reduction_vs_habitual_pct']:7}%  n={mw[pol]['station_days']}  worse {mw[pol]['worse_than_habitual_pct']}%")


if __name__ == "__main__":
    main()
