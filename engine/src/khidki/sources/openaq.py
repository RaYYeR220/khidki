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


class OpenAQClient:
    """Thin v3 client. Requires OPENAQ_API_KEY."""

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        key = api_key or os.environ.get("OPENAQ_API_KEY")
        if not key:
            raise RuntimeError("OPENAQ_API_KEY is not set")
        self.client = client or httpx.Client(
            timeout=30.0, headers={"X-API-Key": key, "user-agent": "khidki/0.1"}
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self.client.get(f"{API}{path}", params=params or {})
        r.raise_for_status()
        return r.json()

    def india_pm25_locations(self) -> list[Location]:
        out: list[Location] = []
        page = 1
        while True:
            data = self._get(
                "/locations",
                {"iso": "IN", "parameters_id": PM25_PARAMETER_ID, "limit": 1000, "page": page},
            )
            for loc in data.get("results", []):
                sensor = next(
                    (s for s in loc.get("sensors", []) if s.get("parameter", {}).get("name") == "pm25"),
                    None,
                )
                coords = loc.get("coordinates") or {}
                out.append(
                    Location(
                        id=loc["id"],
                        name=loc.get("name") or str(loc["id"]),
                        lat=coords.get("latitude"),
                        lon=coords.get("longitude"),
                        locality=loc.get("locality"),
                        provider=(loc.get("provider") or {}).get("name"),
                        pm25_sensor_id=sensor["id"] if sensor else None,
                        last_seen=((loc.get("datetimeLast") or {}).get("utc")),
                    )
                )
            if len(data.get("results", [])) < 1000:
                break
            page += 1
        return out

    def sensor_hours(self, sensor_id: int, start: datetime, end: datetime) -> dict[datetime, float]:
        """Hourly means for one sensor; keyed by hour start."""
        out: dict[datetime, float] = {}
        page = 1
        while True:
            data = self._get(
                f"/sensors/{sensor_id}/hours",
                {
                    "datetime_from": start.isoformat(),
                    "datetime_to": end.isoformat(),
                    "limit": 1000,
                    "page": page,
                },
            )
            res = data.get("results", [])
            for r in res:
                period = r.get("period") or {}
                frm = (period.get("datetimeFrom") or {}).get("local") or (period.get("datetimeFrom") or {}).get("utc")
                if frm is None or r.get("value") is None:
                    continue
                out[datetime.fromisoformat(frm.replace("Z", "+00:00"))] = float(r["value"])
            if len(res) < 1000:
                break
            page += 1
        return out

    def latest(self) -> list[tuple[int, datetime, float]]:
        """(location_id, hour_start, value) for every location's latest PM2.5.
        OpenAQ stamps the END of the averaging hour; we key by hour start."""
        out: list[tuple[int, datetime, float]] = []
        for r in self.latest_pm25():
            dt = (r.get("datetime") or {}).get("local") or (r.get("datetime") or {}).get("utc")
            loc = r.get("locationsId") or r.get("locationId")
            val = r.get("value")
            if dt is None or loc is None or val is None:
                continue
            end = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            hour_end = end.replace(minute=0, second=0, microsecond=0)
            out.append((int(loc), (hour_end - timedelta(hours=1)).astimezone(IST), float(val)))
        return out

    def latest_pm25(self) -> list[dict]:
        """Latest PM2.5 value for every location (all countries); filter by id."""
        out: list[dict] = []
        page = 1
        while True:
            data = self._get(f"/parameters/{PM25_PARAMETER_ID}/latest", {"limit": 1000, "page": page})
            res = data.get("results", [])
            out.extend(res)
            if len(res) < 1000:
                break
            page += 1
        return out
