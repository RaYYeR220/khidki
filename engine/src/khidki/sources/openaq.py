"""OpenAQ: live station data (API v3, key required) and the public S3 archive.

OpenAQ aggregates India's CPCB continuous monitoring stations (CAAQMS) along
with other reference monitors. The archive is open (no key) and lags a few
days; the v3 API serves the latest hours.
"""

from __future__ import annotations

import csv
import gzip
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

IST = timezone(timedelta(hours=5, minutes=30))

ARCHIVE = "https://openaq-data-archive.s3.amazonaws.com"
API = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2


@dataclass(frozen=True)
class Reading:
    location_id: int
    sensor_id: int
    time: datetime  # start of the averaging hour, tz-aware
    parameter: str
    value: float


def _archive_key(location_id: int, day: date) -> str:
    return (
        f"records/csv.gz/locationid={location_id}/year={day.year}/month={day.month:02d}/"
        f"location-{location_id}-{day.strftime('%Y%m%d')}.csv.gz"
    )


def parse_archive_csv(raw: bytes) -> list[Reading]:
    """Parse one archive day file. OpenAQ timestamps mark the END of the
    averaging period; we shift to the start of the hour so every series in
    Khidki is keyed by hour-start."""
    text = gzip.decompress(raw).decode("utf-8")
    out: list[Reading] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            v = float(row["value"])
        except (TypeError, ValueError):
            continue
        end = datetime.fromisoformat(row["datetime"])
        out.append(
            Reading(
                location_id=int(row["location_id"]),
                sensor_id=int(row["sensors_id"]),
                time=end - timedelta(hours=1),
                parameter=row["parameter"],
                value=v,
            )
        )
    return out


class Archive:
    """Reader for the OpenAQ S3 archive with an on-disk cache."""

    def __init__(self, cache_dir: Path | str = "data/cache/openaq", client: httpx.Client | None = None):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(timeout=30.0, headers={"user-agent": "khidki/0.1"})

    def day(self, location_id: int, day: date) -> list[Reading]:
        key = _archive_key(location_id, day)
        path = self.cache / key.replace("/", "_")
        if path.exists():
            raw = path.read_bytes()
        else:
            r = self.client.get(f"{ARCHIVE}/{key}")
            if r.status_code in (403, 404):
                path.write_bytes(b"")
                return []
            r.raise_for_status()
            raw = r.content
            path.write_bytes(raw)
        return parse_archive_csv(raw) if raw else []

    def range(self, location_id: int, start: date, end: date, workers: int = 8) -> list[Reading]:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            chunks = list(ex.map(lambda d: self.day(location_id, d), days))
        return [r for c in chunks for r in c]


def hourly_pm25(readings: list[Reading], *, lo: float = 0.0, hi: float = 1500.0) -> dict[datetime, float]:
    """Hour-start → PM2.5 (µg/m³). Values outside [lo, hi] are dropped as
    instrument faults; if a location has several PM2.5 sensors we average them."""
    acc: dict[datetime, list[float]] = {}
    for r in readings:
        if r.parameter != "pm25" or not (lo <= r.value <= hi):
            continue
        acc.setdefault(r.time, []).append(r.value)
    return {t: sum(v) / len(v) for t, v in sorted(acc.items())}


@dataclass
class Location:
    id: int
    name: str
    lat: float
    lon: float
    locality: str | None
    provider: str | None
    pm25_sensor_id: int | None
    last_seen: str | None
    is_monitor: bool = True


def city_from_name(name: str) -> str | None:
    """CPCB monitor names look like "R K Puram, Delhi - DPCC": the city sits
    between the last comma and the " - <agency>" suffix."""
    base = name.split(" - ")[0]
    if "," in base:
        city = base.rsplit(",", 1)[1].strip()
        return city or None
    return None


class OpenAQClient:
    """Thin v3 client. Requires OPENAQ_API_KEY. Respects the per-minute limit
    reported in the X-Ratelimit-* headers and retries once on 429."""

    INDIA = 9  # OpenAQ countries_id

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        key = api_key or os.environ.get("OPENAQ_API_KEY")
        if not key:
            raise RuntimeError("OPENAQ_API_KEY is not set")
        self.client = client or httpx.Client(
            timeout=30.0, headers={"X-API-Key": key, "user-agent": "khidki/0.1"}
        )
        self.calls = 0

    def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(3):
            r = self.client.get(f"{API}{path}", params=params or {})
            self.calls += 1
            if r.status_code == 429 or (500 <= r.status_code < 600 and attempt < 2):
                time.sleep(min(60, int(r.headers.get("x-ratelimit-reset", "5") or 5) + 1))
                continue
            r.raise_for_status()
            remaining = r.headers.get("x-ratelimit-remaining")
            if remaining is not None and int(remaining) <= 1:
                time.sleep(int(r.headers.get("x-ratelimit-reset", "60") or 60) + 1)
            return r.json()
        r.raise_for_status()
        return r.json()

    def india_pm25_locations(self) -> list[Location]:
        out: list[Location] = []
        page = 1
        while True:
            data = self._get(
                "/locations",
                {"countries_id": self.INDIA, "parameters_id": PM25_PARAMETER_ID, "limit": 1000, "page": page},
            )
            for loc in data.get("results", []):
                # a monitor may list an old and a current PM2.5 sensor; the current one has the larger id
                pm = [s for s in loc.get("sensors", []) if (s.get("parameter") or {}).get("name") == "pm25"]
                sensor = max(pm, key=lambda s: s["id"]) if pm else None
                coords = loc.get("coordinates") or {}
                name = loc.get("name") or str(loc["id"])
                out.append(
                    Location(
                        id=loc["id"],
                        name=name,
                        lat=coords.get("latitude"),
                        lon=coords.get("longitude"),
                        locality=loc.get("locality") or city_from_name(name),
                        provider=(loc.get("provider") or {}).get("name"),
                        pm25_sensor_id=sensor["id"] if sensor else None,
                        last_seen=((loc.get("datetimeLast") or {}).get("utc")),
                        is_monitor=bool(loc.get("isMonitor", True)),
                    )
                )
            if len(data.get("results", [])) < 1000:
                break
            page += 1
        return out

    def sensor_hours(self, sensor_id: int, start: datetime, end: datetime) -> dict[datetime, float]:
        """Hourly means for one sensor, keyed by hour start (IST)."""
        out: dict[datetime, float] = {}
        page = 1
        while True:
            data = self._get(
                f"/sensors/{sensor_id}/hours",
                {
                    "datetime_from": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "datetime_to": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": 1000,
                    "page": page,
                },
            )
            res = data.get("results", [])
            for r in res:
                period = r.get("period") or {}
                frm = (period.get("datetimeFrom") or {}).get("utc")
                if frm is None or r.get("value") is None:
                    continue
                out[datetime.fromisoformat(frm.replace("Z", "+00:00")).astimezone(IST)] = float(r["value"])
            if len(res) < 1000:
                break
            page += 1
        return out
