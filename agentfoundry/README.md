# Khidki agents — AgentFoundry project

This folder is the AgentFoundry project for Khidki's two agents:

- **khidki-planner** — talks to people (Telegram, web) in their own language and script, turns "I walk an hour at 6, I can go any time before 9" into a plan, and explains the engine's answer.
- **khidki-auditor** — turns the daily monitor audit into a neutral bulletin in English and Hindi.

Open this folder in AgentFoundry (Projects → +) to see the agents in the Agents panel, run their eval suites and replay recorded runs. The manifests, prompts and evals live under `.codenow/agent-studio/`; tool implementations in `tools/` call the Khidki engine (`../engine`), so the numbers an agent states always come from the engine, never from the model.

The production runtime of the same agents is `engine/src/khidki/agents/` (Google ADK), served by the engine API and the Telegram bot.
