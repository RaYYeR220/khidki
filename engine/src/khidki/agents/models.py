"""Model configuration. Any OpenAI-compatible endpoint works through LiteLLM;
by default we use Venice's API with a Claude model."""

from __future__ import annotations

import os

from google.adk.models.lite_llm import LiteLlm

DEFAULT_BASE = "https://api.venice.ai/api/v1"


def chat_model(env: str = "KHIDKI_CHAT_MODEL", default: str = "claude-haiku-5-5") -> LiteLlm:
    name = os.environ.get(env, default)
    return LiteLlm(
        model=f"openai/{name}",
        api_base=os.environ.get("KHIDKI_LLM_BASE", DEFAULT_BASE),
        api_key=os.environ.get("KHIDKI_LLM_KEY") or os.environ.get("VENICE_API_KEY"),
        # replies go straight to people: no reasoning text in the answer
        extra_body={"venice_parameters": {"disable_thinking": True, "strip_thinking_response": True}},
    )
