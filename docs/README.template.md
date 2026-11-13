# Khidki · खिड़की

**Same walk. {{mw_khidki_pct}}% less smoke.** Khidki tells people in India *when* the air over their street is cleanest, for their walk, their run, their children's playtime and the windows at home. It publishes every recommendation the night before and checks it against the measured air the next day, misses included.

> *Khidki* means "window": the hour you go out in, and the window of your home.

## The problem

- **All of India breathes unsafe air.** Every one of India's ~1.4 billion people lives where annual PM2.5 exceeds the WHO guideline; 46% live above India's own national standard (AQLI 2025).
- **It kills.** Air pollution was linked to more than 2 million deaths in India in 2023 (State of Global Air 2025) and cost US$339.4 billion, 9.5% of GDP, in 2022 (Lancet Countdown 2025).
- **The air has hours.** On a Delhi winter morning smoke is trapped under a low lid of air. At New Delhi–Chanakyapuri the boundary layer sits at about {{blh_06}} m at 06:00 and lifts to about {{blh_15}} m by mid-afternoon (winter median, weather model). PM2.5 follows: a winter median of {{pm_06}} µg/m³ at 06:00 against {{pm_15}} at 15:00.
- **People go out at the worst time.** Morning walkers, runners and school assemblies are outdoors in the dirtiest hours, breathing hard: one brisk hour is about a fifth of the air an adult breathes in a day (U.S. EPA Exposure Factors Handbook, Table 6-2).

## What Khidki does

1. **Finds your window.** Tell it what you do and when you could do it ("an hour's walk, usually 6 am, any time before 9 pm"). It forecasts tomorrow's hourly PM2.5 at the government monitors around you and picks the start time with the least PM2.5 breathed, inside your limits.
2. **Reminds you.** On Telegram, 45 minutes before the window, in English or Hindi.
3. **Proves it.** The next morning you tap when you went. Khidki measures, from the monitors around your home, what you breathed against your usual time.
4. **Publishes in advance.** Every evening at 21:00 IST it publishes tomorrow's windows for every monitor, hashes the document with SHA-256 and timestamps it in Bitcoin through OpenTimestamps. The next day each recommendation is graded against the measured air, in public.
5. **Audits the monitors.** Every day it flags monitors that went silent, froze, or went dark while their neighbours read Severe.

## Results

**Replay, winter 2025–26, New Delhi–Chanakyapuri** ({{mw_days}} days; nothing was published in advance that winter, so this is a backtest with forecasts issued at 21:00 the evening before using only data available then):

| a 60-minute morning walk, usually at 06:00 | PM2.5 breathed vs 06:00 |
|---|---|
| Khidki's day-ahead window | **−{{mw_khidki_pct}}%** |
| a fixed "go at 15:00" rule | −{{mw_rule_pct}}% |
| best hour in hindsight (unreachable) | −{{mw_oracle_pct}}% |

| other everyday limits | Khidki vs usual time |
|---|---|
| children's outdoor play inside school hours (usually 08:00) | −{{sp_khidki_pct}}% |
| evening walk between 15:00 and 22:00 (usually 18:30) | −{{ev_khidki_pct}}% |
| a walk that must end by 10:00 | {{bw_khidki_pct}}%: winter mornings have no clean slot, and Khidki says so |

**Replay across India, winter 2025–26** ({{nat_monitors}} reference-grade monitors in {{nat_cities}} cities and towns, {{nat_days}} monitor-days):

| a 60-minute walk, usually at 06:00 | PM2.5 breathed vs 06:00 | worse than 06:00 on |
|---|---|---|
| Khidki's day-ahead window | **−{{nat_khidki}}%** | {{nat_worse_k}}% of days |
| a fixed "go at 15:00" rule | −{{nat_rule}}% | {{nat_worse_r}}% of days |
| best hour in hindsight | −{{nat_oracle}}% | 0% |

One rule does not travel: in Bengaluru the fixed 15:00 rule made the morning walk {{blr_rule}} smokier, while Khidki, which learns each monitor's own day, cut it by {{blr_khidki}}%. It is not ahead everywhere: in Mumbai, Chennai and Patna the fixed rule did better (per-city table on the ledger page and in `engine/results/backtest-national-*.json`).

**What we found and say plainly:** at this Delhi monitor a fixed afternoon rule does as well as our forecast ({{mw_rule_pct}}% vs {{mw_khidki_pct}}%). We also tried a weather-aware gradient-boosted model (boundary-layer height, wind, temperature, humidity, CAMS): {{gbm_pct}}% on the same days. Khidki's value is not a cleverer guess at "3 pm". It is getting people out of the 6 am habit, fitting the hour to their real limits, covering every monitor and every home, and checking itself in public. The window was worse than 06:00 on {{mw_worse_days}} of {{mw_days}} days; those days are published like the others.

**The assistant** ({{eval_cases}} pre-registered cases in English, Hindi, Hinglish, Tamil and Bengali, three runs, graded mechanically against an answer key):

| | Khidki agent | same model, no tools |
|---|---|---|
| names the hour the engine computed | {{eval_best_k}} | {{eval_best_b}} |
| replies containing a number not in the data or the question | {{eval_ungr_k}} | {{eval_ungr_b}} |
| constraint fields read correctly | {{eval_args_k}} | n/a |
| replies in the person's script | {{eval_script_k}} | {{eval_script_b}} |

The grader is strict: a number counts as unsupported unless it appears in a tool result or in the person's own words, so even reading "by 10" as 10:00 counts against the agent. Cases, grader and every reply: `engine/evals/planner_cases.json`, `engine/scripts/eval_planner.py`, `engine/results/agent-eval-run*.json`.

**Live record:** see the [ledger]({{app_url}}/ledger) for every day published so far and how it measured up.

## Try it

- Web: {{app_url}}
- Telegram: {{bot_url}}
- API: `GET {{api_url}}/v1/window?lat=28.59&lon=77.22&activity=walk&minutes=60&habitual=06:00&day=tomorrow` ([docs]({{api_url}}/docs))
- For other agents (MCP, streamable HTTP): `{{api_url}}/mcp/`

## How it works

See [docs/METHOD.md](docs/METHOD.md) for every formula, source and limit. In short: hourly PM2.5 from India's reference-grade monitors via OpenAQ, the CAMS global forecast via Open-Meteo, a per-monitor bias-corrected day-ahead forecast, inverse-distance blending to any point, a 15-minute window search on inhaled dose (EPA inhalation rates), a fail-closed planner, and deterministic next-day verification. The conversational layer is two agents built with Google's Agent Development Kit: they only explain numbers that come from the engine.

```
engine/   Python: data sources, forecast, planner, verification, ledger, audit, agents, API, Telegram, MCP
web/      Next.js: landing, your window, the ledger, monitor health, impact
docs/     method, claims and how to check them
```

## Built with AgentFoundry

The two agents are an AgentFoundry project in [`agentfoundry/`](agentfoundry): manifests, system prompts and eval suites under `.codenow/agent-studio/`, tools that AgentFoundry discovers on its own (`agentfoundry/tools/khidki_tools.py`, calling the live engine), the Google ADK kit, and a runnable `agent.py`. Opened in the AgentFoundry IDE, both agents, their four tools, two prompts and two eval suites appear in the Agents panel:

![Khidki's agents in the AgentFoundry Agents panel](docs/agentfoundry/agents-panel.png)

The same agents run in production inside the engine. While building we hit a Windows bug in AgentFoundry's eval buttons (backslashes stripped from the suite path); the cause and a fix are in [docs/agentfoundry/FEEDBACK.md](docs/agentfoundry/FEEDBACK.md), reported upstream as [codenow-wiki#3](https://github.com/karlmehta/codenow-wiki/issues/3).

## Run it

```bash
cd engine
uv sync
uv run pytest                       # {{tests}} tests
uv run uvicorn khidki.api:app --reload
```

Environment: see `engine/.env.example`. Deployment: `engine/deploy/cloudrun.sh` (Cloud Run, Mumbai, SQLite replicated by Litestream, a scheduler tick every 15 minutes).

## Honest limits

- Forecasts miss; misses are published.
- Monitors are sparse outside big cities; beyond 15 km Khidki falls back to the CAMS model and says the forecast is uncertain.
- We measure PM2.5 breathed, not health outcomes.
- The winter numbers above are a replay. The published-in-advance record starts in November 2026.

Data: CPCB and state pollution control boards via [OpenAQ](https://openaq.org) · CAMS (ECMWF/Copernicus) and weather via [Open-Meteo](https://open-meteo.com). Licence: MIT.
