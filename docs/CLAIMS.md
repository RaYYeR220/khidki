# Claims and how to check them

Every statement Khidki makes in public, with how strong the evidence is and where to reproduce it.

| tier | meaning |
|---|---|
| **LIVE** | happening now in the deployed system; check it at the URL |
| **REPRODUCIBLE** | a script in this repo recomputes it from public data |
| **SOURCED** | a published figure from a named source |
| **MODELLED** | an estimate from a model, labelled as such |
| **NOT CLAIMED** | things we deliberately do not say |

## The problem

| claim | tier | source |
|---|---|---|
| All ~1.4 billion people in India live where PM2.5 exceeds the WHO guideline; 46% above India's own standard | SOURCED | AQLI 2025 annual update (EPIC, University of Chicago) |
| Air pollution was linked to more than 2 million deaths in India in 2023 | SOURCED | State of Global Air 2025 (HEI/IHME) |
| US$339.4 billion, 9.5% of GDP, lost to air pollution in 2022 | SOURCED | Lancet Countdown on Health and Climate Change, 2025 report |
| One brisk hour of walking is about a fifth of the air an adult breathes in a day | SOURCED + arithmetic | U.S. EPA Exposure Factors Handbook (2011), Table 6-2; `engine/src/khidki/exposure.py` |
| Winter median PM2.5 at New Delhi–Chanakyapuri: 181 µg/m³ at 06:00, 94 at 15:00 | REPRODUCIBLE | `engine/scripts/diurnal_profile.py` → `engine/results/diurnal-*.json` |
| Boundary layer at the same place: ~80 m at 06:00, ~1,070 m at 15:00 (winter median) | MODELLED | Open-Meteo historical forecast (`boundary_layer_height`); same script |

## What Khidki does

| claim | tier | where to check |
|---|---|---|
| Publishes a window for every active reference-grade monitor in India each evening at 21:00 IST | LIVE | `/v1/ledger`, the web ledger |
| Each day's document is hashed (SHA-256) and the hash is timestamped through OpenTimestamps | LIVE | `/v1/ledger/<day>.json` + `/v1/ledger/<day>.ots`; verify with `ots verify` or opentimestamps.org |
| The next morning every recommendation is graded on measured readings against the usual time, a fixed 15:00 rule and the best hour in hindsight | LIVE | `/v1/scoreboard` |
| Monitors are audited daily for missing hours, frozen values, readings that disagree with neighbours and silence during Severe air | LIVE | `/v1/audit`, `/v1/bulletin` |
| People get a reminder before their window and a measured result the next day | LIVE | Telegram bot; `/v1/impact` counts real people and verified outcomes |

## Results

| claim | tier | reproduce |
|---|---|---|
| Moving a 60-minute 06:00 walk to Khidki's day-ahead window cut the PM2.5 breathed by 40% (113 winter days, Chanakyapuri) | REPRODUCIBLE (replay) | `engine/scripts/backtest_station.py 8118 28.63576 77.22445 2025-11-01 2026-02-28 delhi-chanakyapuri` |
| A fixed "go at 15:00" rule did as well there (−41%) | REPRODUCIBLE (replay) | same file, `rule_of_thumb` |
| Across 490 reference-grade monitors in 262 cities and towns (49,983 monitor-days, winter 2025–26), Khidki's window cut a 06:00 walker's PM2.5 by 29% vs 27% for the fixed 15:00 rule, and was worse than 06:00 on 25% vs 29% of days | REPRODUCIBLE (replay) | `engine/scripts/backtest_national.py 2025-11-01 2026-02-28` (needs a free OpenAQ key) → `engine/results/backtest-national-*.json` |
| In Bengaluru the fixed 15:00 rule made the morning walk 5% smokier; Khidki cut it by 11% | REPRODUCIBLE (replay) | same file, `by_city.Bengaluru` |
| In Mumbai, Chennai and Patna the fixed rule did better than Khidki | REPRODUCIBLE (replay) | same file |
| A weather-aware gradient-boosted model did no better (−35%) | REPRODUCIBLE (replay) | `engine/scripts/exp_gbm.py` |
| The agent names the hour the engine computed in 35 of 36 graded replies; the same model without tools does in 10 of 36 | REPRODUCIBLE | `engine/scripts/eval_planner.py` (needs an LLM key); results `engine/results/agent-eval-run*.json` |

## Not claimed

- No health outcome for any individual: we measure PM2.5 breathed, not illness avoided.
- No claim that Khidki's forecast beats a fixed afternoon rule in Delhi, Mumbai, Chennai or Patna.
- No users we cannot count: `/v1/impact` reports exactly what the database holds.
- The winter 2025–26 numbers are a replay, not a published-in-advance record.
- Monitor audit flags describe reported data, not anyone's conduct.
