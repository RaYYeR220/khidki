"""Winter diurnal profile at one monitor: median PM2.5 and boundary-layer height by hour.

usage: uv run python scripts/diurnal_profile.py <location_id> <lat> <lon> <start> <end> <label>
"""
import json
import statistics
import sys
from datetime import date
from pathlib import Path

from khidki.sources.openaq import Archive, hourly_pm25
from khidki.sources.openmeteo import OpenMeteo

loc, lat, lon = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
start, end, label = date.fromisoformat(sys.argv[4]), date.fromisoformat(sys.argv[5]), sys.argv[6]
pm = hourly_pm25(Archive("data/cache/openaq").range(loc, start, end))
wx = OpenMeteo().weather(lat, lon, start=start, end=end, variables=["boundary_layer_height"]).series("boundary_layer_height")
by_pm = {h: [v for t, v in pm.items() if t.hour == h and start <= t.date() <= end] for h in range(24)}
by_blh = {h: [v for t, v in wx.items() if t.hour == h] for h in range(24)}
out = {
    "monitor": f"openaq:{loc}",
    "period": [start.isoformat(), end.isoformat()],
    "pm25_median_by_hour": [round(statistics.median(by_pm[h]), 1) for h in range(24)],
    "pm25_hours": sum(len(v) for v in by_pm.values()),
    "blh_median_m_by_hour": [round(statistics.median(by_blh[h])) for h in range(24)],
    "blh_source": "Open-Meteo historical forecast API, boundary_layer_height",
}
Path("results").mkdir(exist_ok=True)
p = Path("results") / f"diurnal-{label}-{start}-{end}.json"
p.write_text(json.dumps(out, indent=1))
print(p, out["pm25_median_by_hour"][6], out["pm25_median_by_hour"][15], out["blh_median_m_by_hour"][6], out["blh_median_m_by_hour"][15])
