"""India National Air Quality Index (NAQI) helpers for PM2.5 and PM10.

Breakpoints and health statements follow the CPCB National Air Quality Index
(2014). NAQI is defined on 24-hour averages; when applied to a single hourly
value the category is indicative only, and the UI labels it that way.
"""

from __future__ import annotations

from dataclasses import dataclass

# (conc_lo, conc_hi, index_lo, index_hi, category)
PM25_BREAKPOINTS: list[tuple[float, float, int, int, str]] = [
    (0, 30, 0, 50, "Good"),
    (31, 60, 51, 100, "Satisfactory"),
    (61, 90, 101, 200, "Moderate"),
    (91, 120, 201, 300, "Poor"),
    (121, 250, 301, 400, "Very Poor"),
    (251, 380, 401, 500, "Severe"),
]

PM10_BREAKPOINTS: list[tuple[float, float, int, int, str]] = [
    (0, 50, 0, 50, "Good"),
    (51, 100, 51, 100, "Satisfactory"),
    (101, 250, 101, 200, "Moderate"),
    (251, 350, 201, 300, "Poor"),
    (351, 430, 301, 400, "Very Poor"),
    (431, 510, 401, 500, "Severe"),
]

HEALTH_STATEMENT: dict[str, str] = {
    "Good": "Minimal impact.",
    "Satisfactory": "Minor breathing discomfort to sensitive people.",
    "Moderate": (
        "Breathing discomfort to people with lung disease such as asthma, and "
        "discomfort to people with heart disease, children and older adults."
    ),
    "Poor": (
        "Breathing discomfort to people on prolonged exposure, and discomfort to "
        "people with heart disease."
    ),
    "Very Poor": (
        "Respiratory illness to people on prolonged exposure. Effect may be more "
        "pronounced in people with lung and heart diseases."
    ),
    "Severe": (
        "Respiratory effects even on healthy people, and serious health impacts on "
        "people with lung or heart disease. Health impacts may be experienced even "
        "during light physical activity."
    ),
}

CATEGORY_ORDER = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]


@dataclass(frozen=True)
class SubIndex:
    value: int
    category: str


def _sub_index(conc: float, table: list[tuple[float, float, int, int, str]]) -> SubIndex:
    if conc < 0:
        raise ValueError("concentration cannot be negative")
    # CPCB truncates concentrations to integers before lookup.
    c = float(int(conc))
    for lo, hi, ilo, ihi, cat in table:
        if lo <= c <= hi:
            value = round(ilo + (ihi - ilo) * (c - lo) / (hi - lo))
            return SubIndex(value, cat)
        # gap between integer bands (e.g. 30 < c < 31 after truncation never occurs)
    lo, hi, ilo, ihi, cat = table[-1]
    # above the top breakpoint: cap at 500 and keep the top category
    return SubIndex(500 if c > hi else ilo, cat)


def pm25_sub_index(conc: float) -> SubIndex:
    return _sub_index(conc, PM25_BREAKPOINTS)


def pm10_sub_index(conc: float) -> SubIndex:
    return _sub_index(conc, PM10_BREAKPOINTS)


def pm25_category(conc: float) -> str:
    return pm25_sub_index(conc).category


def category_rank(category: str) -> int:
    return CATEGORY_ORDER.index(category)
