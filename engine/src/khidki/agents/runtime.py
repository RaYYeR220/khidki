"""Run agent turns with persistent sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
)
from google.genai import types

APP = "khidki"


@lru_cache(maxsize=1)
def session_service() -> BaseSessionService:
    url = os.environ.get("KHIDKI_SESSIONS_DB")
    if url:
        return DatabaseSessionService(db_url=url)
    return InMemorySessionService()


@dataclass
class Turn:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)


@lru_cache(maxsize=4)
def _runner(agent_name: str) -> Runner:
    if agent_name == "planner":
        from .planner.agent import root_agent
    elif agent_name == "auditor":
        from .auditor.agent import root_agent
    else:
        raise ValueError(agent_name)
    return Runner(app_name=APP, agent=root_agent, session_service=session_service())


async def run_turn(
    agent_name: str,
    user_id: str,
    text: str,
    *,
    session_id: str | None = None,
    state: dict[str, Any] | None = None,
    runner: Runner | None = None,
) -> Turn:
    runner = runner or _runner(agent_name)
    state = dict(state or {})
    if state.get("lat") is not None and state.get("lon") is not None:
        state["location_note"] = (
            f"saved location {float(state['lat']):.4f}, {float(state['lon']):.4f} (India); tools use it by default"
        )
    else:
        state["location_note"] = "no saved location yet"
    svc = runner.session_service
    sid = session_id or f"{agent_name}:{user_id}"
    sess = await svc.get_session(app_name=APP, user_id=user_id, session_id=sid)
    if sess is None:
        await svc.create_session(app_name=APP, user_id=user_id, session_id=sid, state=state or {})
        delta = None
    else:
        delta = {k: v for k, v in (state or {}).items() if sess.state.get(k) != v} or None
    msg = types.Content(role="user", parts=[types.Part(text=text)])
    out = Turn(text="")
    final_parts: list[str] = []
    async for ev in runner.run_async(user_id=user_id, session_id=sid, new_message=msg, state_delta=delta):
        for call in ev.get_function_calls() or []:
            out.tool_calls.append({"name": call.name, "args": dict(call.args or {})})
        for resp in ev.get_function_responses() or []:
            out.tool_results.append({"name": resp.name, "response": resp.response})
        if ev.is_final_response() and ev.content and ev.content.parts:
            final_parts.extend(p.text for p in ev.content.parts if getattr(p, "text", None))
    out.text = "\n".join(final_parts).strip()
    return out
