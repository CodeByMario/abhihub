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
# Verified live free models on OpenRouter (Sept 2026)
_FREE_MODELS = [
    "deepseek/deepseek-v4-flash-0731:free",
    "qwen/qwen3.8-27b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free",
    "nex-agi/nex-n2.5-mini:free",
    "nex-agi/nex-n2.5-pro:free",
]

_FREE_VISION_MODELS = [
    "inclusionai/ling-3.0-flash-vl:free",
    "nex-agi/nex-n2.5-pro:free",
    "dots-studio/dots-3-note-preview:free",
    "qwen/qwen3.8-27b:free",
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

        # Check if messages contain multimodal image content
        has_image = any(
            isinstance(m.get("content"), list) and any(item.get("type") == "image_url" for item in m.get("content"))
            for m in messages
        )
        models_to_try = self._models
        if has_image:
            # ONLY use verified vision-capable models (exclude text-only models like nex-n2.5-mini)
            models_to_try = [
                "inclusionai/ling-3.0-flash-vl:free",
                "nex-agi/nex-n2.5-pro:free",
                "dots-studio/dots-3-note-preview:free",
            ]
            if max_tokens < 1200:
                max_tokens = 1500

        for model_id in models_to_try:
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
                    timeout=35,
                )

                if resp.status_code == 401:
                    raise KeyInvalidError("API key rejected by provider")

                if resp.status_code == 429:
                    log.warning("[ai_provider] %s rate-limited, trying next", model_id)
                    last_err = RateLimitError(f"{model_id} rate-limited")
                    continue

                if not resp.ok:
                    log.warning("[ai_provider] %s HTTP %s: %s", model_id, resp.status_code, resp.text[:120])
                    last_err = ProviderError(f"{model_id} HTTP {resp.status_code}")
                    continue

                body = resp.json()
                choice = (body.get("choices") or [{}])[0]
                usage = body.get("usage", {})
                # cost: OpenRouter may return in 'usage.cost'; default to 0 for free models
                cost = float((usage.get("cost") or body.get("cost") or 0))
                tokens_in = int(usage.get("prompt_tokens") or 0)
                tokens_out = int(usage.get("completion_tokens") or 0)

                msg_obj = choice.get("message") or {}
                output_text = (msg_obj.get("content") or msg_obj.get("reasoning") or "").strip()

                return ProviderResponse(
                    text=output_text,
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


# ── Anthropic Claude adapter ──────────────────────────────────────────────────

class AnthropicAdapter:
    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self._key = api_key
        self.model_name = model

    def complete(self, messages: list[dict], max_tokens: int = 600, temperature: float = 0.3) -> ProviderResponse:
        system_content = ""
        anthropic_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_content += ("\n" + m.get("content", "")) if system_content else m.get("content", "")
            else:
                anthropic_messages.append({
                    "role": "user" if m.get("role") == "user" else "assistant",
                    "content": m.get("content", "")
                })

        payload = {
            "model": self.model_name,
            "messages": anthropic_messages or [{"role": "user", "content": "hi"}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_content:
            payload["system"] = system_content

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=30
        )
        if resp.status_code == 401:
            raise KeyInvalidError("Anthropic API key rejected")
        if resp.status_code == 429:
            raise RateLimitError("Anthropic rate limited")
        if not resp.ok:
            raise ProviderError(f"Anthropic HTTP {resp.status_code}: {_strip_key(resp.text[:200])}")

        body = resp.json()
        content = "".join([c.get("text", "") for c in body.get("content", []) if c.get("type") == "text"])
        usage = body.get("usage", {})
        return ProviderResponse(
            text=content.strip(),
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            cost_usd=0.0,
            model_used=self.model_name,
            finish_reason=body.get("stop_reason") or "stop"
        )

    def validate(self) -> None:
        self.complete([{"role": "user", "content": "hi"}], max_tokens=2, temperature=0.0)


# ── Google Gemini adapter ─────────────────────────────────────────────────────

class GeminiAdapter:
    provider_name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._key = api_key
        self.model_name = model.replace("models/", "")

    def complete(self, messages: list[dict], max_tokens: int = 600, temperature: float = 0.3) -> ProviderResponse:
        system_instruction = None
        contents = []
        for m in messages:
            if m.get("role") == "system":
                system_instruction = {"parts": [{"text": m.get("content", "")}]}
            else:
                role = "user" if m.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self._key}"
        payload = {
            "contents": contents or [{"role": "user", "parts": [{"text": "hi"}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            }
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        resp = requests.post(url, json=payload, timeout=30)
        if (resp.status_code == 400 and "API_KEY_INVALID" in resp.text) or resp.status_code in (401, 403):
            raise KeyInvalidError("Gemini API key rejected or unauthorized")
        if resp.status_code == 429:
            raise RateLimitError("Gemini rate limited")
        if not resp.ok:
            raise ProviderError(f"Gemini HTTP {resp.status_code}: {_strip_key(resp.text[:200])}")

        body = resp.json()
        candidates = body.get("candidates") or []
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join([p.get("text", "") for p in parts])
        meta = body.get("usageMetadata", {})
        return ProviderResponse(
            text=text.strip(),
            tokens_in=int(meta.get("promptTokenCount") or 0),
            tokens_out=int(meta.get("candidatesTokenCount") or 0),
            cost_usd=0.0,
            model_used=self.model_name,
            finish_reason="stop"
        )

    def validate(self) -> None:
        self.complete([{"role": "user", "content": "hi"}], max_tokens=2, temperature=0.0)


# ── OpenAI-Compatible adapter (OpenAI, NVIDIA NIM, Groq, etc.) ────────────────

class OpenAICompatibleAdapter:
    def __init__(self, api_key: str, base_url: str, provider_name: str, model: str) -> None:
        self._key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self.model_name = model

    def complete(self, messages: list[dict], max_tokens: int = 600, temperature: float = 0.3) -> ProviderResponse:
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30
        )
        if resp.status_code == 401:
            raise KeyInvalidError(f"{self.provider_name.capitalize()} API key rejected")
        if resp.status_code == 429:
            raise RateLimitError(f"{self.provider_name.capitalize()} rate limited")
        if not resp.ok:
            raise ProviderError(f"{self.provider_name.capitalize()} HTTP {resp.status_code}: {_strip_key(resp.text[:200])}")

        body = resp.json()
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage", {})
        return ProviderResponse(
            text=choice.get("message", {}).get("content", "").strip(),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            cost_usd=0.0,
            model_used=self.model_name,
            finish_reason=choice.get("finish_reason", "stop")
        )

    def validate(self) -> None:
        self.complete([{"role": "user", "content": "hi"}], max_tokens=2, temperature=0.0)


# ── Provider Factory & Realtime Catalog ───────────────────────────────────────

def get_adapter(provider: str, api_key: str, model: str | None = None) -> LLMProvider:
    """Instantiate the appropriate provider adapter."""
    p = (provider or "openrouter").lower().strip()
    if p == "anthropic":
        return AnthropicAdapter(api_key=api_key, model=model or "claude-3-5-sonnet-20241022")
    elif p == "gemini":
        return GeminiAdapter(api_key=api_key, model=model or "gemini-2.0-flash")
    elif p == "nvidia":
        return OpenAICompatibleAdapter(
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            provider_name="nvidia",
            model=model or "meta/llama-3.3-70b-instruct"
        )
    elif p == "groq":
        return OpenAICompatibleAdapter(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            provider_name="groq",
            model=model or "llama-3.3-70b-versatile"
        )
    elif p == "openai":
        return OpenAICompatibleAdapter(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            provider_name="openai",
            model=model or "gpt-4o-mini"
        )
    else:  # default openrouter
        models = [model] if model else None
        return OpenRouterAdapter(api_key=api_key, models=models)


def fetch_live_models(provider: str, api_key: str | None = None) -> list[dict]:
    """Fetch live model catalog from the chosen provider in real-time with free tier tagging."""
    models: list[dict] = []
    p = (provider or "openrouter").lower().strip()
    try:
        if p == "openrouter":
            resp = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
            if resp.ok:
                data = resp.json().get("data", [])
                for m in data[:70]:
                    mid = m["id"]
                    is_free = ":free" in mid or "free" in (m.get("name") or "").lower()
                    models.append({
                        "id": mid,
                        "name": m.get("name") or mid,
                        "is_free": is_free
                    })
        elif p == "nvidia":
            key = api_key or os.getenv("NVIDIA_API_KEY", "")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            resp = requests.get("https://integrate.api.nvidia.com/v1/models", headers=headers, timeout=8)
            if resp.ok:
                data = resp.json().get("data", [])
                for m in data[:50]:
                    models.append({
                        "id": m["id"],
                        "name": m.get("id"),
                        "is_free": True  # NVIDIA NIM includes 1000 free API credits
                    })
        elif p == "groq":
            key = api_key or os.getenv("GROQ_API_KEY", "")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=8)
            if resp.ok:
                data = resp.json().get("data", [])
                for m in data:
                    models.append({
                        "id": m["id"],
                        "name": m.get("id"),
                        "is_free": True  # 100% Free on console.groq.com
                    })
        elif p == "gemini":
            key = api_key or os.getenv("GEMINI_API_KEY", "")
            if key:
                resp = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=8)
                if resp.ok:
                    data = resp.json().get("models", [])
                    for m in data:
                        if "generateContent" in m.get("supportedGenerationMethods", []):
                            mid = m["name"].replace("models/", "")
                            is_free = "flash" in mid.lower()  # Google AI Studio offers free tier for Flash
                            models.append({
                                "id": mid,
                                "name": m.get("displayName") or mid,
                                "is_free": is_free
                            })
        elif p == "openai":
            key = api_key or os.getenv("OPENAI_API_KEY", "")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=8)
            if resp.ok:
                data = resp.json().get("data", [])
                for m in data:
                    mid = m["id"]
                    if any(k in mid for k in ("gpt", "o1", "o3")):
                        models.append({
                            "id": mid,
                            "name": mid,
                            "is_free": False
                        })
        elif p == "anthropic":
            key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
            if key:
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
                resp = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=8)
                if resp.ok:
                    data = resp.json().get("data", [])
                    for m in data:
                        models.append({
                            "id": m["id"],
                            "name": m.get("display_name") or m["id"],
                            "is_free": False
                        })
    except Exception as exc:
        log.warning(f"[ai_provider] fetch_live_models error ({provider}): {exc}")

    if not models:
        defaults = {
            "openrouter": [
                {"id": "google/gemma-4-31b-it:free", "name": "Google Gemma 4 31B", "is_free": True},
                {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 3.1 8B Instruct", "is_free": True},
                {"id": "openai/gpt-oss-20b:free", "name": "GPT OSS 20B", "is_free": True},
                {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "is_free": False},
                {"id": "openai/gpt-4o", "name": "GPT-4o", "is_free": False},
                {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "is_free": False},
            ],
            "groq": [
                {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant (Free Tier)", "is_free": True},
                {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile (Free Tier)", "is_free": True},
                {"id": "gemma2-9b-it", "name": "Gemma 2 9B (Free Tier)", "is_free": True},
                {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B (Free Tier)", "is_free": True},
            ],
            "gemini": [
                {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Free Tier Available)", "is_free": True},
                {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (Free Tier Available)", "is_free": True},
                {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro (Pay-as-you-go)", "is_free": False},
            ],
            "nvidia": [
                {"id": "meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B (Free 1K credits)", "is_free": True},
                {"id": "deepseek-ai/deepseek-r1", "name": "DeepSeek R1 (Free 1K credits)", "is_free": True},
                {"id": "nvidia/nemotron-4-340b-instruct", "name": "Nemotron 4 340B (Free 1K credits)", "is_free": True},
            ],
            "openai": [
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Ultra low cost)", "is_free": False},
                {"id": "gpt-4o", "name": "GPT-4o (Flagship)", "is_free": False},
                {"id": "o1-mini", "name": "o1 Mini (Reasoning)", "is_free": False},
            ],
            "anthropic": [
                {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (Affordable)", "is_free": False},
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet (State of the art)", "is_free": False},
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus (Deep logic)", "is_free": False},
            ],
        }
        models = defaults.get(p, defaults["openrouter"])

    # Sort so free models appear first
    models.sort(key=lambda x: (not x.get("is_free", False), x.get("name", "")))
    return models


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


def resolve_provider(ai_profile: dict, preferred_model: str | None = None) -> tuple[LLMProvider, float | None]:
    """Return (adapter, cost_ceiling_usd).

    cost_ceiling_usd is None for BYOK (no ceiling); float for free tier.
    Supports multi-provider BYOK (Anthropic, Gemini, NVIDIA, OpenAI, Groq, OpenRouter).
    """
    plan = ai_profile.get("ai_plan", "free")
    key_enc = ai_profile.get("ai_key_enc")
    provider = ai_profile.get("ai_provider", "openrouter")

    if plan == "byok" and key_enc:
        try:
            key = decrypt_key(key_enc)
            return get_adapter(provider, key, preferred_model), None
        except Exception as exc:
            log.error("[ai_provider] BYOK decrypt failed: %s", exc)
            raise KeyInvalidError("Could not decrypt stored key — please re-enter it in Settings")

    # Free tier: use platform OpenRouter key or NVIDIA fallback
    platform_key = os.getenv("OPENROUTER_API_KEY", "").strip().strip("'\"")
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip().strip("'\"")

    if not platform_key and nvidia_key:
        return OpenAICompatibleAdapter(
            api_key=nvidia_key,
            base_url="https://integrate.api.nvidia.com/v1",
            provider_name="nvidia",
            model=preferred_model or "meta/llama-3.3-70b-instruct"
        ), None

    if not platform_key:
        raise ProviderError("Platform AI key not configured")

    models = _FREE_MODELS
    if preferred_model:
        models = [preferred_model] + [m for m in _FREE_MODELS if m != preferred_model]

    ceiling = float(os.getenv("AI_MAX_COST_USD_PER_DAY", "0.02"))
    return OpenRouterAdapter(api_key=platform_key, models=models), ceiling


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
