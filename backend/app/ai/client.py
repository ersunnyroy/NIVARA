"""Thin wrapper around the Anthropic SDK for structured (JSON-schema) explanations."""
from __future__ import annotations

import json
import logging

from app.config.settings import get_settings

log = logging.getLogger(__name__)


class AIUnavailable(Exception):
    pass


def ai_configured() -> bool:
    s = get_settings()
    return bool(s.ai_enabled and s.anthropic_api_key)


def structured_call(system: str, user: str, schema: dict, max_tokens: int = 8000) -> tuple[dict, str]:
    """Returns (parsed JSON, model actually used). Raises AIUnavailable on any failure."""
    s = get_settings()
    if not ai_configured():
        raise AIUnavailable("AI not configured (set ANTHROPIC_API_KEY)")
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=120.0, max_retries=2)
    try:
        resp = client.beta.messages.create(
            model=s.ai_model,
            max_tokens=max_tokens,
            # Static instructions are cached; the per-stock data goes in the user turn.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": s.ai_effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as e:
        raise AIUnavailable("AI rate limited; try again shortly") from e
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"AI API error {e.status_code}") from e
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("AI service unreachable") from e
    if resp.stop_reason == "refusal":
        raise AIUnavailable("AI declined this request")
    if resp.stop_reason == "max_tokens":
        raise AIUnavailable("AI output truncated")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise AIUnavailable("AI returned no text")
    try:
        return json.loads(text), resp.model
    except json.JSONDecodeError as e:
        raise AIUnavailable("AI returned invalid JSON") from e
