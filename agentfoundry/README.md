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
