"""Small geographic helpers: distances, bearings and inverse-distance weighting."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in degrees."""
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


@dataclass(frozen=True)
class Neighbour:
    id: str
    distance_km: float
    weight: float


def idw_weights(
    lat: float,
    lon: float,
    points: Iterable[tuple[str, float, float]],
    *,
    max_km: float = 15.0,
    k: int = 4,
    power: float = 2.0,
    min_km: float = 0.3,
) -> list[Neighbour]:
    """Inverse-distance weights for the ``k`` nearest points within ``max_km``.

    Distances below ``min_km`` are clamped so a station on your street does not
    get infinite weight; weights sum to 1. Returns [] when nothing is in range.
    """
    near = sorted(
        ((pid, haversine_km(lat, lon, plat, plon)) for pid, plat, plon in points),
        key=lambda x: x[1],
    )
    near = [(pid, d) for pid, d in near if d <= max_km][:k]
    if not near:
        return []
    raw = [(pid, d, 1.0 / max(d, min_km) ** power) for pid, d in near]
    total = sum(w for _, _, w in raw)
    return [Neighbour(pid, d, w / total) for pid, d, w in raw]


def weighted(values: Sequence[float], weights: Sequence[float]) -> float:
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)
