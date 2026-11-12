"""Khidki agents (Google ADK), as run from AgentFoundry.

    pip install -r requirements.txt
    python agent.py "Kal subah 6 baje 1 ghanta walk, Lodhi Garden ke paas. Kab jaun?"
    python agent.py --auditor 2026-11-11

The tools in tools/khidki_tools.py call the live Khidki API; the language model
only explains their results. The same agents run in production inside the
engine (engine/src/khidki/agents).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tools.khidki_tools import air_now, find_airing_time, find_window, monitor_health

HERE = Path(__file__).parent
PROMPTS = HERE / ".codenow" / "agent-studio" / "prompts"


def prompt(name: str) -> str:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).strip()


def model(name: str) -> LiteLlm:
    return LiteLlm(
        model=f"openai/{name}",
        api_base=os.environ.get("KHIDKI_LLM_BASE", "https://api.venice.ai/api/v1"),
        api_key=os.environ.get("KHIDKI_LLM_KEY") or os.environ.get("VENICE_API_KEY"),
        extra_body={"venice_parameters": {"disable_thinking": True, "strip_thinking_response": True}},
    )


planner = Agent(
    name="khidki_planner",
    model=model(os.environ.get("KHIDKI_CHAT_MODEL", "claude-haiku-5-5")),
    description="Plans the cleanest-air time for a person's outdoor activities and window airing in India.",
    instruction=prompt("khidki-planner"),
    tools=[find_window, find_airing_time, air_now],
)

auditor = Agent(
    name="khidki_auditor",
    model=model(os.environ.get("KHIDKI_AUDIT_MODEL", "claude-sonnet-5-5")),
    description="Writes the daily monitor-health bulletin in English and Hindi.",
    instruction=prompt("khidki-auditor"),
    tools=[monitor_health],
)


async def ask(agent: Agent, text: str, state: dict | None = None) -> str:
    runner = Runner(app_name="khidki", agent=agent, session_service=InMemorySessionService())
    await runner.session_service.create_session(app_name="khidki", user_id="local", session_id="s", state=state or {})
    out = []
    async for ev in runner.run_async(user_id="local", session_id="s", new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if ev.is_final_response() and ev.content and ev.content.parts:
            out += [p.text for p in ev.content.parts if getattr(p, "text", None)]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--auditor":
        print(asyncio.run(ask(auditor, f"Write the monitor health bulletin for {sys.argv[2]}.")))
    else:
        q = " ".join(sys.argv[1:]) or "I walk an hour every morning at 6 near Lodhi Garden, New Delhi (28.5931, 77.2197). When should I go tomorrow?"
        print(asyncio.run(ask(planner, q, {"location_note": "no saved location yet"})))
