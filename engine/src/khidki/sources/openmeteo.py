"""Open-Meteo clients: CAMS air-quality forecasts and weather forecasts.

Both APIs are free and keyless. We request hourly values in Asia/Kolkata and
return tz-aware datetimes for the start of each hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
WX_ARCHIVE_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

IST = timezone(timedelta(hours=5, minutes=30))

WX_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "boundary_layer_height",
    "precipitation",
]


@dataclass
class HourlyFrame:
    times: list[datetime]
    values: dict[str, list[float | None]]

    def series(self, var: str) -> dict[datetime, float]:
        return {t: v for t, v in zip(self.times, self.values[var]) if v is not None}


def _parse(payload: dict, variables: list[str]) -> HourlyFrame:
    h = payload["hourly"]
    times = [datetime.fromisoformat(t).replace(tzinfo=IST) for t in h["time"]]
    return HourlyFrame(times, {v: h.get(v, [None] * len(times)) for v in variables})


class OpenMeteo:
    def __init__(self, client: httpx.Client | None = None, timeout: float = 30.0):
        self.client = client or httpx.Client(timeout=timeout, headers={"user-agent": "khidki/0.1"})

    def _get(self, url: str, params: dict) -> dict:
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def cams(
        self,
        lat: float,
        lon: float,
        *,
        forecast_days: int = 3,
        past_days: int = 0,
        start: date | None = None,
        end: date | None = None,
        variables: list[str] | None = None,
    ) -> HourlyFrame:
        variables = variables or ["pm2_5", "pm10"]
        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(variables),
            "timezone": "Asia/Kolkata",
            "domains": "cams_global",
        }
        if start and end:
            params.update(start_date=start.isoformat(), end_date=end.isoformat())
        else:
            params.update(forecast_days=forecast_days, past_days=past_days)
        return _parse(self._get(AQ_URL, params), variables)

    def cams_many(
        self, points: list[tuple[float, float]], past_days: int = 15, forecast_days: int = 3
    ) -> list[dict[datetime, float]]:
        """CAMS PM2.5 for many points in one request (Open-Meteo accepts
        comma-separated coordinates and returns a list in the same order)."""
        if not points:
            return []
        params = {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points),
            "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "hourly": "pm2_5",
            "timezone": "Asia/Kolkata",
            "domains": "cams_global",
            "past_days": past_days,
            "forecast_days": forecast_days,
        }
        data = self._get(AQ_URL, params)
        if isinstance(data, dict):
            data = [data]
        return [_parse(d, ["pm2_5"]).series("pm2_5") for d in data]

    def weather(
        self,
        lat: float,
        lon: float,
        *,
        forecast_days: int = 3,
        past_days: int = 0,
        start: date | None = None,
        end: date | None = None,
        variables: list[str] | None = None,
    ) -> HourlyFrame:
        variables = variables or WX_VARS
        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(variables),
            "timezone": "Asia/Kolkata",
        }
        url = WX_URL
        if start and end:
            url = WX_ARCHIVE_URL
            params.update(start_date=start.isoformat(), end_date=end.isoformat())
        else:
            params.update(forecast_days=forecast_days, past_days=past_days)
        return _parse(self._get(url, params), variables)
