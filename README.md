# Khidki · खिड़की

**Same walk. 40% less smoke.** Khidki tells people in India *when* the air over their street is cleanest, for their walk, their run, their children's playtime and the windows at home. It publishes every recommendation the night before and checks it against the measured air the next day, misses included.

> *Khidki* means "window": the hour you go out in, and the window of your home.

## The problem

- **All of India breathes unsafe air.** Every one of India's ~1.4 billion people lives where annual PM2.5 exceeds the WHO guideline; 46% live above India's own national standard (AQLI 2025).
- **It kills.** Air pollution was linked to more than 2 million deaths in India in 2023 (State of Global Air 2025) and cost US$339.4 billion, 9.5% of GDP, in 2022 (Lancet Countdown 2025).
- **The air has hours.** On a Delhi winter morning smoke is trapped under a low lid of air. At New Delhi–Chanakyapuri the boundary layer sits at about 80 m at 06:00 and lifts to about 1,072 m by mid-afternoon (winter median, weather model). PM2.5 follows: a winter median of 181 µg/m³ at 06:00 against 94 at 15:00.
- **People go out at the worst time.** Morning walkers, runners and school assemblies are outdoors in the dirtiest hours, breathing hard: one brisk hour is about a fifth of the air an adult breathes in a day (U.S. EPA Exposure Factors Handbook, Table 6-2).

## What Khidki does

1. **Finds your window.** Tell it what you do and when you could do it ("an hour's walk, usually 6 am, any time before 9 pm"). It forecasts tomorrow's hourly PM2.5 at the government monitors around you and picks the start time with the least PM2.5 breathed, inside your limits.
2. **Reminds you.** On Telegram, 45 minutes before the window, in English or Hindi.
3. **Proves it.** The next morning you tap when you went. Khidki measures, from the monitors around your home, what you breathed against your usual time.
4. **Publishes in advance.** Every evening at 21:00 IST it publishes tomorrow's windows for every monitor, hashes the document with SHA-256 and timestamps it in Bitcoin through OpenTimestamps. The next day each recommendation is graded against the measured air, in public.
5. **Audits the monitors.** Every day it flags monitors that went silent, froze, or went dark while their neighbours read Severe.

## Results

**Replay, winter 2025–26, New Delhi–Chanakyapuri** (113 days; nothing was published in advance that winter, so this is a backtest with forecasts issued at 21:00 the evening before using only data available then):

| a 60-minute morning walk, usually at 06:00 | PM2.5 breathed vs 06:00 |
|---|---|
| Khidki's day-ahead window | **−40%** |
| a fixed "go at 15:00" rule | −41% |
| best hour in hindsight (unreachable) | −51% |

| other everyday limits | Khidki vs usual time |
|---|---|
| children's outdoor play inside school hours (usually 08:00) | −36% |
| evening walk between 15:00 and 22:00 (usually 18:30) | −22% |
| a walk that must end by 10:00 | +1.6%: winter mornings have no clean slot, and Khidki says so |

**Replay across India, winter 2025–26** (490 reference-grade monitors in 262 cities and towns, 49,983 monitor-days):

| a 60-minute walk, usually at 06:00 | PM2.5 breathed vs 06:00 | worse than 06:00 on |
|---|---|---|
| Khidki's day-ahead window | **−29%** | 25% of days |
| a fixed "go at 15:00" rule | −27% | 29% of days |
| best hour in hindsight | −44% | 0% |

One rule does not travel: in Bengaluru the fixed 15:00 rule made the morning walk 5% smokier, while Khidki, which learns each monitor's own day, cut it by 11%. It is not ahead everywhere: in Mumbai, Chennai and Patna the fixed rule did better (per-city table on the ledger page and in `engine/results/backtest-national-*.json`).

**What we found and say plainly:** at this Delhi monitor a fixed afternoon rule does as well as our forecast (41% vs 40%). We also tried a weather-aware gradient-boosted model (boundary-layer height, wind, temperature, humidity, CAMS): −35% on the same days. Khidki's value is not a cleverer guess at "3 pm". It is getting people out of the 6 am habit, fitting the hour to their real limits, covering every monitor and every home, and checking itself in public. The window was worse than 06:00 on 22 of 113 days; those days are published like the others.

**The assistant** (18 pre-registered cases in English, Hindi, Hinglish, Tamil and Bengali, three runs, graded mechanically against an answer key):

| | Khidki agent | same model, no tools |
|---|---|---|
| names the hour the engine computed | 35/36 | 10/36 |
| replies containing a number not in the data or the question | 7/54 | 49/54 |
| constraint fields read correctly | 227/231 | n/a |
| replies in the person's script | 52/54 | 49/54 |

The grader is strict: a number counts as unsupported unless it appears in a tool result or in the person's own words, so even reading "by 10" as 10:00 counts against the agent. Cases, grader and every reply: `engine/evals/planner_cases.json`, `engine/scripts/eval_planner.py`, `engine/results/agent-eval-run*.json`.

**Live record:** see the [ledger](https://khidki-air.vercel.app/ledger) for every day published so far and how it measured up.

## Try it

- Web: https://khidki-air.vercel.app
- Telegram: https://t.me/Khidkitgbot
- API: `GET https://khidki-engine-ptslyhnp7q-el.a.run.app/v1/window?lat=28.59&lon=77.22&activity=walk&minutes=60&habitual=06:00&day=tomorrow` ([docs](https://khidki-engine-ptslyhnp7q-el.a.run.app/docs))
- For other agents (MCP, streamable HTTP): `https://khidki-engine-ptslyhnp7q-el.a.run.app/mcp/`

## How it works

See [docs/METHOD.md](docs/METHOD.md) for every formula, source and limit. In short: hourly PM2.5 from India's reference-grade monitors via OpenAQ, the CAMS global forecast via Open-Meteo, a per-monitor bias-corrected day-ahead forecast, inverse-distance blending to any point, a 15-minute window search on inhaled dose (EPA inhalation rates), a fail-closed planner, and deterministic next-day verification. The conversational layer is two agents built with Google's Agent Development Kit: they only explain numbers that come from the engine.

```
engine/   Python: data sources, forecast, planner, verification, ledger, audit, agents, API, Telegram, MCP
web/      Next.js: landing, your window, the ledger, monitor health, impact
docs/     method, claims and how to check them
```

## Run it

```bash
cd engine
uv sync
uv run pytest                       # 54 tests
uv run uvicorn khidki.api:app --reload
```

Environment: see `engine/.env.example`. Deployment: `engine/deploy/cloudrun.sh` (Cloud Run, Mumbai, SQLite replicated by Litestream, a scheduler tick every 15 minutes).

## Honest limits

- Forecasts miss; misses are published.
- Monitors are sparse outside big cities; beyond 15 km Khidki falls back to the CAMS model and says the forecast is uncertain.
- We measure PM2.5 breathed, not health outcomes.
- The winter numbers above are a replay. The published-in-advance record starts in November 2026.

Data: CPCB and state pollution control boards via [OpenAQ](https://openaq.org) · CAMS (ECMWF/Copernicus) and weather via [Open-Meteo](https://open-meteo.com). Licence: MIT.
