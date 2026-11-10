# How Khidki works

Khidki answers one question for a person in India: **when, inside the limits of my day, is the air cleanest for the thing I do outdoors?** Then it checks its own answer against the measured air the next day. This page explains every step and its limits.

## 1. What we measure: inhaled dose, not "AQI"

What hurts is the PM2.5 that ends up in your lungs. For an activity of `m` minutes starting at `t`:

```
dose (µg) = mean PM2.5 over [t, t+m) (µg/m³) × inhalation rate (m³/min) × m
```

Inhalation rates are the mean short-term values from the **U.S. EPA Exposure Factors Handbook (2011), Table 6-2**, males and females combined. We use three age bands:

| m³ per minute | sleep | sedentary | light | moderate | high |
|---|---|---|---|---|---|
| child 6 to <11 | 0.0045 | 0.0048 | 0.011 | 0.022 | 0.042 |
| adult 31 to <41 | 0.0046 | 0.0043 | 0.012 | 0.027 | 0.049 |
| older 61 to <71 | 0.0052 | 0.0049 | 0.012 | 0.026 | 0.047 |

Activities map to intensities: walk and walking commute = moderate; run, cycle and children's play = high; yoga, errands and two-wheeler commute = light. One brisk hour of walking (≈1.6 m³) is about a fifth of the ~8.2 m³ an adult breathes in a day, which is why its timing matters.

Hourly concentrations are treated as a step function (each hour's mean holds for that hour). An interval that touches an hour with no value is **not scored**; gaps are never filled.

## 2. Where the numbers come from

- **Measurements:** India's continuous ambient air-quality monitoring stations (CPCB CAAQMS and state boards), hourly PM2.5, via **OpenAQ**. Only reference-grade monitors are used (OpenAQ `isMonitor`); low-cost sensors are excluded. Values ≤ 0 or ≥ 1,500 µg/m³ are dropped as instrument faults.
- **Model forecast:** the **CAMS global** atmospheric-composition forecast (ECMWF/Copernicus) at each monitor's coordinates, via Open-Meteo, hourly, up to 3 days ahead.

## 3. Forecasting tomorrow at a monitor

Every evening at **21:00 IST** we forecast the next day's 24 hours for each monitor using only data available at that moment. Candidate models:

| model | idea |
|---|---|
| `clim` | median of the monitor's own last 14 days at each hour of day |
| `yesterday` | yesterday's measured values, hour by hour |
| `cams` | raw CAMS at the monitor |
| `cams_bc` | CAMS × the monitor's recent hour-of-day bias, `exp(median(log obs − log CAMS))`, shrunk towards the all-hours bias |
| `blend` | geometric mean of `clim` and `cams_bc`: the monitor's own daily rhythm, nudged by tomorrow's weather as CAMS sees it |

`blend` is the default; the others are fallbacks when data is short. CAMS alone runs about **2× low** in Delhi in winter, which is why it is never used uncorrected when monitor history exists.

Per-hour uncertainty is the spread of the monitor's log residuals around its 14-day profile. It feeds a confidence value: the probability that the recommended slot really is cleaner than the usual one, `Φ(Δlog / √(σ₁² + σ₂²))`.

## 4. Any point, not just monitors

For a location, Khidki takes up to 4 monitors within 15 km and weights their forecasts by inverse distance squared (distances under 300 m are clamped). Hours that have already happened use the measured values, weighted the same way. For the rest of today the forecast is scaled by the ratio of measured to forecast over the last 3 hours, fading out over 12 hours (a simple nowcast). With no monitor in range Khidki falls back to raw CAMS and says so (`source: cams_only`, low confidence).

## 5. Choosing the window

Given the activity, its length, the earliest start and the latest end the person can live with, Khidki scores every start time on a 15-minute grid and picks the one with the lowest forecast dose. It reports the usual time's forecast dose for comparison, up to two non-overlapping alternatives, the confidence, and flags:

- `severe_all_window`: even the best slot is NAQI "Severe" (≥ 250 µg/m³): move strenuous exercise indoors or shorten it;
- `habitual_is_best`: the usual time is already the cleanest;
- `partial_coverage`: part of the allowed time has no forecast.

It **fails closed**: a forecast older than 30 hours or one that covers no full interval returns `stale` / `no_data` and no recommendation.

**Windows at home.** For airing, a single-zone mass balance simulates indoor PM2.5 hour by hour (closed: 1 air change/h, 80% penetration; open: 6 air changes/h; deposition 0.2/h) and picks the opening time that minimises the household's indoor dose over the day. The best moment is usually when outdoor air has just fallen below the air already inside, often late morning, not necessarily the cleanest outdoor hour.

## 6. Publishing before the day starts

At 21:00 IST Khidki writes every monitor's recommendations for five everyday scenarios into one canonical JSON document (sorted keys, no whitespace) and hashes it with **SHA-256**. The hash is submitted to the public **OpenTimestamps** calendars, which commit it into Bitcoin, so anyone can prove the document existed before the day began without trusting us. The document is served byte-for-byte at `/v1/ledger/<day>.json` and the proof at `/v1/ledger/<day>.ots`.

| scenario | activity | usual start | allowed |
|---|---|---|---|
| `morning_walk` | walk 60 min, adult | 06:00 | 05:00–21:00 |
| `before_work` | walk 45 min, adult | 06:30 | 05:00–10:00 |
| `evening_walk` | walk 60 min, older adult | 18:30 | 15:00–22:00 |
| `school_play` | play 45 min, child | 08:00 | 08:00–14:00 |
| `runner` | run 45 min, adult | 06:00 | 05:00–21:00 |

## 7. Checking it the next day

From 06:00 IST the next morning, for every published recommendation, Khidki takes the monitor's **measured** hourly values and computes the dose at four times:

- `khidki`: the published start;
- `habitual`: the usual start;
- `rule_of_thumb`: a fixed "go at 15:00", moved inside the allowed time;
- `oracle`: the best start in hindsight (the ceiling; nobody can do this in advance).

A recommendation with any missing measurement in those intervals is marked `unverifiable` and left out of the scoreboard. The scoreboard reports, per scenario, the dose-weighted reduction versus the habit, the share of the hindsight-best gain captured, and how often the recommendation was better or worse than the habit.

**For people** the same check runs on their own plans: the next morning the bot asks when they actually went out (buttons, not free text), and once the readings are in it measures that time against their usual one, using the monitors around their saved location.

## 8. The monitor audit

Each day every active monitor's previous day is checked for data-quality flags:

| flag | rule |
|---|---|
| `missing_hours` | ≥ 4 hours without a reading (24 = silent all day) |
| `dark_during_severe` | no reading in hours when the median of monitors within 10 km was ≥ 250 µg/m³ |
| `frozen_value` | the same value reported for ≥ 4 consecutive hours |
| `implausible_value` | readings ≤ 0 or ≥ 999 |
| `disagrees_with_neighbours` | the day's mean is ≥ 2× or ≤ 0.5× the neighbours' median (≥ 12 hours each) |

These describe the data a monitor reported. They are not findings about anyone's conduct; outages and calibration drift have ordinary causes. They matter because alerts, school closures and GRAP stages are decided on these numbers.

## 9. The agents

Two agents sit on top of the engine; they never produce numbers themselves.

- **Planner** (Telegram, web chat): turns what a person says, in English, Hindi, Hinglish, Tamil, Bengali or another language, into tool calls (`find_window`, `find_airing_time`, `air_now`, `save_routine`, …) and explains the result in the person's own language and script. Every PM2.5 value, time and percentage it says must come from a tool result; when a tool returns no data it says so.
- **Auditor**: turns the day's audit flags into a neutral public bulletin in English and Hindi.

Both are built with Google's Agent Development Kit and call an LLM through an OpenAI-compatible endpoint (configurable).

## 10. Honest limits

- **A fixed afternoon rule does about as well on average.** In the winter 2025–26 replay at New Delhi–Chanakyapuri, "go at 15:00" cut the morning walker's dose by 41.0% and Khidki's day-ahead window by 40.3%. What Khidki adds is the rest: it fits your own limits (school hours, office, evenings), it tells you on which days the rule is wrong, it handles windows at home, it covers every monitor, and it proves its record in public.
- **Mornings have no clean slot in winter.** If you must be done by 10:00, timing barely helps (−1.6% in the replay). Khidki says so instead of inventing a gain.
- **Forecasts miss.** In the replay the window was worse than 06:00 on 22 of 113 days. Misses are published like hits.
- **Monitors are sparse.** Beyond 15 km from a monitor Khidki uses the CAMS model alone, with low confidence.
- **Dose, not health outcome.** We measure PM2.5 breathed. We do not claim a health effect for any individual.
- **The winter numbers are a replay.** Nothing was published in advance during winter 2025–26; the live, published-in-advance record starts with the launch in November 2026.
