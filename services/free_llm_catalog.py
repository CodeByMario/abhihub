"""Curated integration metadata sourced from the Free-LLM directory.

The directory is used as a setup reference, not as a runtime dependency. Provider
limits and free-tier terms change, so this metadata deliberately does not promise
quotas or route requests to an unverified provider.
"""
from __future__ import annotations

FREE_LLM_SOURCE = "https://github.com/nejib1/Free-LLM"
FREE_LLM_DIRECTORY = "https://free-llm.com"

PROVIDERS = (
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/keys",
        "free_tier": "Free models are marked with :free; verify current limits.",
        "tarika_status": "active",
        "recommended": True,
    },
    {
        "id": "groq",
        "name": "Groq",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "free_tier": "Free developer tier; limits vary by model.",
        "tarika_status": "active",
        "recommended": True,
    },
    {
        "id": "gemini",
        "name": "Google AI Studio",
        "env_key": "GEMINI_API_KEY",
        "base_url": "Google Generative Language API",
        "key_url": "https://aistudio.google.com/app/apikey",
        "free_tier": "Free tier is model- and region-dependent.",
        "tarika_status": "active",
        "recommended": True,
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "env_key": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/",
        "free_tier": "Free tier availability and verification requirements can change.",
        "tarika_status": "active",
        "recommended": False,
    },
    {
        "id": "cerebras",
        "name": "Cerebras",
        "env_key": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "key_url": "https://cloud.cerebras.ai/",
        "free_tier": "Trial or promotional credits may apply; verify before enabling.",
        "tarika_status": "active",
        "recommended": False,
    },
    {
        "id": "nvidia",
        "name": "NVIDIA NIM",
        "env_key": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_url": "https://build.nvidia.com/",
        "free_tier": "Trial credits and model access vary by account.",
        "tarika_status": "active",
        "recommended": False,
    },
)


def get_provider_catalog() -> list[dict]:
    """Return a copy so callers cannot mutate the shared catalog."""
    return [dict(provider) for provider in PROVIDERS]
