# Khidki agents — AgentFoundry project

The AgentFoundry project for Khidki's two agents (kit: **Google ADK, Python**):

| agent | what it does | tools |
|---|---|---|
| **khidki-planner** | talks to people in their own language and script, turns "I walk an hour at 6, I can go any time before 9" into a plan, explains the engine's answer | `find_window`, `find_airing_time`, `air_now` |
| **khidki-auditor** | turns the daily monitor audit into a neutral bulletin in English and Hindi | `monitor_health` |

```
.codenow/agent-studio/agents/   manifests (khidki-planner.json, khidki-auditor.json)
.codenow/agent-studio/prompts/  system prompts
.codenow/agent-studio/evals/    eval suites run from the Agents panel (Eval tab)
tools/khidki_tools.py           tool implementations: calls to the live Khidki API
agent.py                        runnable ADK agents (python agent.py "...")
```

Open this folder in AgentFoundry (Open Project Folder) and use the **Agents** panel to run the eval suites, test each tool in isolation and replay recorded runs. The tools call the Khidki engine, so the numbers an agent states always come from India's government monitors and the engine's forecast, never from the model.

The same agents run in production inside the engine (`../engine/src/khidki/agents`), behind the Telegram bot and the web chat. The graded evaluation with tools and a no-tools baseline is `../engine/scripts/eval_planner.py`.

## Eval runs in AgentFoundry

Every run of the two suites from AgentFoundry's Eval tab is kept, unedited apart from the local path of the suite file, in `.codenow/agent-studio/evals/results/`. These runs use AgentFoundry's SMART-Code model with the system prompt only and **no tools**, so they test behaviour (language and script, refusing places outside India, sending chest symptoms to medical care, never confirming a number the person typed), not grounding; grounding is graded with tools in `../engine/scripts/eval_planner.py`.

| suite | runs | all cases passed | lowest | cases that failed at least once |
|---|---|---|---|---|
| khidki-planner (8 cases) | 12 | 6 runs (8/8) | 4/8 | asks for location when none is saved (4), chest tightness goes to medical care (4), Tamil in, Tamil out (2), Devanagari in, Devanagari out (1), no invented forecast without data (1), does not confirm an injected number (1) |
| khidki-auditor (2 cases) | 12 | 9 runs (2/2) | 0/2 | no accusations (3), writes Hindi too (2) |

Without tools the model cannot see a saved location or call the engine, which is why "asks for location" and the medical-care case fail most often here; in production both go through tools and the session state.

