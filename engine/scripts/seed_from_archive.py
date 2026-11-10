"""Seed a local database from the OpenAQ archive + live CAMS, then publish
tomorrow's windows. For development without an OpenAQ API key.

usage: uv run python scripts/seed_from_archive.py <db> <location_id:lat:lon:name> [...]
"""
import sys
from datetime import date, timedelta

from khidki import jobs
from khidki.sources.openaq import Archive, hourly_pm25
from khidki.sources.openmeteo import OpenMeteo
from khidki.store import Store


def main() -> None:
    store = Store(sys.argv[1])
    specs = [s.split(":", 3) for s in sys.argv[2:]]
    now = jobs.now_ist()
    store.upsert_stations(
        [{"id": f"oaq:{loc}", "source": "openaq", "name": name, "lat": float(lat), "lon": float(lon)} for loc, lat, lon, name in specs],
        now=now.isoformat(),
    )
    arch = Archive("data/cache/openaq")
    for loc, lat, lon, name in specs:
        series = hourly_pm25(arch.range(int(loc), now.date() - timedelta(days=20), now.date()))
        store.put_obs(f"oaq:{loc}", series)
        print(name, "readings", len(series), "last", max(series) if series else None)
    print("cams", jobs.ingest_cams(store, OpenMeteo()))
    print(jobs.publish(store, now.date() + timedelta(days=1), issued_at=now))


if __name__ == "__main__":
    main()
