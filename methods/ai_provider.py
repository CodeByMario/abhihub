"""
ai_provider.py — LLM provider abstraction layer.

Core never calls OpenRouter directly. All provider-specific logic lives here.
Addresses: F3 (brittle abstraction), F5 (key safety), F6 (vendor lock-in), F8 (error taxonomy).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import requests

log = logging.getLogger(__name__)

# ── Error taxonomy (F8) ───────────────────────────────────────────────────────

class ProviderError(Exception):
    """Generic provider failure — retry once, then surface."""

class RateLimitError(ProviderError):
    """HTTP 429 — try next model in fallback list."""

class ContextLimitError(ProviderError):
    """Context too long — compact session and retry."""

class KeyInvalidError(ProviderError):
    """HTTP 401 on BYOK key — surface immediately, NEVER fall back to platform key."""

# ── Response type (the only thing core ever sees) ─────────────────────────────

_KEY_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

def _strip_key(text: str) -> str:
    """Remove any Bearer token from error strings before they leave this module."""
    return _KEY_PATTERN.sub("Bearer [REDACTED]", text or "")


@dataclass
class ProviderResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str
    finish_reason: str          # 'stop' | 'length' | 'error'
    raw_error: str | None = field(default=None)  # sanitised — never contains key material


# ── Provider interface ────────────────────────────────────────────────────────

@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.3,
    ) -> ProviderResponse: ...


# ── OpenRouter adapter ────────────────────────────────────────────────────────

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free models tried in order; adapter stops at first success.
# OpenRouter handles provider-level load balancing internally.
_FREE_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "openai/gpt-oss-20b:free",
    "meta-llama/llama-3.1-8b-instruct:free",
]


class OpenRouterAdapter:
    """Adapter for OpenRouter. Owns 100% of request/response serialisation.

    Core code passes messages[], gets back ProviderResponse. Done.
    """

    provider_name = "openrouter"

    def __init__(self, api_key: str, models: list[str] | None = None) -> None:
        self._key = api_key
        self._models = models or _FREE_MODELS
        # Expose the primary model name for logging; actual call may use a fallback.
        self.model_name = self._models[0]

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        """Try each model in order. Raises ProviderError if all fail."""
        last_err: Exception | None = None

        for model_id in self._models:
            try:
                resp = requests.post(
                    _OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://abhihub.edu.eu.org",
                        "X-Title": "AbhiHub",
                    },
                    json={
                        "model": model_id,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "provider": {"allow_fallbacks": True, "sort": "throughput"},
                    },
                    timeout=30,
                )

                if resp.status_code == 401:
                    raise KeyInvalidError("API key rejected by provider")

                if resp.status_code == 429:
                    log.warning("[ai_provider] %s rate-limited, trying next", model_id)
                    last_err = RateLimitError(f"{model_id} rate-limited")
                    continue

                if not resp.ok:
                    log.warning("[ai_provider] %s HTTP %s", model_id, resp.status_code)
                    last_err = ProviderError(f"{model_id} HTTP {resp.status_code}")
                    continue

                body = resp.json()
                choice = (body.get("choices") or [{}])[0]
                usage = body.get("usage", {})
                # cost: OpenRouter may return in 'usage.cost'; default to 0 for free models
                cost = float((usage.get("cost") or body.get("cost") or 0))
                tokens_in = int(usage.get("prompt_tokens") or 0)
                tokens_out = int(usage.get("completion_tokens") or 0)

                return ProviderResponse(
                    text=choice.get("message", {}).get("content", "").strip(),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    model_used=model_id,
                    finish_reason=choice.get("finish_reason", "stop"),
                )

            except (KeyInvalidError, RateLimitError):
                raise
            except requests.Timeout:
                log.warning("[ai_provider] %s timed out", model_id)
                last_err = ProviderError(f"{model_id} timed out")
                continue
            except Exception as exc:
                # Strip key from any exception string before re-raising or logging
                safe_msg = _strip_key(str(exc))
                log.warning("[ai_provider] %s error: %s", model_id, safe_msg)
                last_err = ProviderError(safe_msg)
                continue

        raise (last_err or ProviderError("All models failed"))

    def validate(self) -> None:
        """One cheap call to verify the key works. Raises KeyInvalidError on 401."""
        self.complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=4,
            temperature=0.0,
        )


# ── Key resolution (F5) ───────────────────────────────────────────────────────

import os

def _fernet():
    """Return a Fernet instance. Lazy import so startup doesn't fail if unused."""
    from cryptography.fernet import Fernet
    raw = os.getenv("FERNET_KEY", "").strip()
    if not raw:
        raise RuntimeError("FERNET_KEY env var is required for BYOK key encryption")
    return Fernet(raw.encode())


def encrypt_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def resolve_provider(ai_profile: dict) -> tuple[OpenRouterAdapter, float | None]:
    """Return (adapter, cost_ceiling_usd).

    cost_ceiling_usd is None for BYOK (no ceiling); float for free tier.
    Never logs key values.
    """
    plan = ai_profile.get("ai_plan", "free")
    key_enc = ai_profile.get("ai_key_enc")

    if plan == "byok" and key_enc:
        try:
            key = decrypt_key(key_enc)
            return OpenRouterAdapter(api_key=key), None  # ponytail: None = no ceiling
        except Exception as exc:
            log.error("[ai_provider] BYOK decrypt failed: %s", exc)
            raise KeyInvalidError("Could not decrypt stored key — please re-enter it in Settings")

    # Free tier: use platform key
    platform_key = os.getenv("OPENROUTER_API_KEY", "").strip().strip("'\"")
    if not platform_key:
        raise ProviderError("Platform AI key not configured")

    ceiling = float(os.getenv("AI_MAX_COST_USD_PER_DAY", "0.02"))
    return OpenRouterAdapter(api_key=platform_key), ceiling


# ── Startup validation ────────────────────────────────────────────────────────

def validate_startup() -> None:
    """Called once at app startup. Logs key presence; validates FERNET_KEY format."""
    platform_key = os.getenv("OPENROUTER_API_KEY", "")
    log.info("[ai_provider] OPENROUTER_API_KEY present: %s", bool(platform_key))

    fernet_key = os.getenv("FERNET_KEY", "")
    if fernet_key:
        try:
            _fernet()  # will raise if malformed
            log.info("[ai_provider] FERNET_KEY: valid")
        except Exception as exc:
            log.error("[ai_provider] FERNET_KEY invalid: %s", exc)
    else:
        log.info("[ai_provider] FERNET_KEY: not set (BYOK unavailable)")


# ── Ponytail self-check ───────────────────────────────────────────────────────

if __name__ == "__main__":
    # Verifies _strip_key and ProviderResponse construction. No network call.
    dirty = "Error: Bearer sk-abc123 was rejected"
    clean = _strip_key(dirty)
    assert "sk-abc123" not in clean, "key leaked in error string"
    assert "REDACTED" in clean

    pr = ProviderResponse(
        text="hello",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.0,
        model_used="test/model",
        finish_reason="stop",
    )
    assert pr.text == "hello"
    assert pr.raw_error is None
    print("ai_provider self-check: PASS")
