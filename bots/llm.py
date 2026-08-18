"""
Thin OpenRouter client + deterministic fallback.

If OPENROUTER_API_KEY is absent, `reason()` returns a structured fallback so the
bots remain runnable and verifiable offline. All prompts are task-specific and
kept small to control cost.
"""
import json
import os

import config


def _call_openrouter(system: str, user: str, max_tokens: int = 600) -> str:
    import requests

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.API_BASE,
        "X-Title": "AbhiHub Company Bots",
    }
    payload = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def reason(system: str, user: str, max_tokens: int = 600,
           fallback: str = "") -> str:
    """Call the LLM if configured, else return `fallback` (deterministic)."""
    if not config.has_llm():
        return fallback
    try:
        return _call_openrouter(system, user, max_tokens).strip()
    except Exception as exc:  # never block the bot cycle on a network error
        return f"[LLM unavailable: {exc}] {fallback}"


def reason_json(system: str, user: str, max_tokens: int = 800,
                default=None):
    """Same as reason() but parse the result as JSON; fall back to `default`."""
    if default is None:
        default = {}
    raw = reason(system, user, max_tokens, fallback=json.dumps(default))
    try:
        return json.loads(raw)
    except Exception:
        # try to extract the first {...} block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                pass
        return default
