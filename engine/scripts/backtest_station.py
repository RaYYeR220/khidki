"""Backtest one OpenAQ location against measured data.

usage: uv run python scripts/backtest_station.py <location_id> <lat> <lon> <start> <end> [label]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from khidki.backtest import backtest_station, rows_as_dicts, summarise
from khidki.sources.openaq import Archive, hourly_pm25
from khidki.sources.openmeteo import OpenMeteo


def main() -> None:
    loc, lat, lon = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
    start, end = date.fromisoformat(sys.argv[4]), date.fromisoformat(sys.argv[5])
    label = sys.argv[6] if len(sys.argv) > 6 else str(loc)
    hist_start = start - timedelta(days=16)
    obs = hourly_pm25(Archive("data/cache/openaq").range(loc, hist_start, end + timedelta(days=1)))
    cams = OpenMeteo().cams(lat, lon, start=hist_start, end=end).series("pm2_5")
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows = backtest_station(label, obs, cams, days)
    summary = summarise(rows)
    out = Path("results") / f"backtest-{label}-{start}-{end}.json"
    out.write_text(json.dumps({"station": label, "location_id": loc, "lat": lat, "lon": lon,
                               "start": str(start), "end": str(end), "obs_hours": len(obs),
                               "cams_hours": len(cams), "summary": summary}, indent=1))
    Path("data/cache").mkdir(parents=True, exist_ok=True)
    (Path("data/cache") / f"rows-{label}-{start}-{end}.json").write_text(json.dumps(rows_as_dicts(rows)))
    print(out, "obs", len(obs), "cams", len(cams))
    for sc, pols in summary.items():
        print("==", sc)
        for p, m in sorted(pols.items(), key=lambda x: -(x[1]["reduction_vs_habitual_pct"] or -999)):
            print(f"  {p:14s} red {m['reduction_vs_habitual_pct']:6}%  capt {m['captured_of_hindsight_best_pct']}%  >rule {m['beats_rule_of_thumb_pct']}%  worse {m['worse_than_habitual_pct']}%  n={m['station_days']}")


if __name__ == "__main__":
    main()
