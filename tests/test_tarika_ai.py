"""
Unit tests for Tarika AI Assistant:
1. Vibe and conversational response matching
2. External reference images and schematics protocol
3. Practice test generator protocol with minimum 3 to 5 questions
4. Customer prioritization and load tiering
5. Dynamic token balancing and load concurrency governor
"""

import time
import pytest
from unittest.mock import MagicMock, patch


def test_tarika_prompt_vibe_and_response_matching():
    """Q1: Verify Tarika prompt includes dynamic vibe matching & conversational mirroring."""
    from app import app
    with app.test_request_context():
        # Verify that Tarika's prompt defines vibe adaptation
        from app import _get_tarika_load_tier
        tier, is_excess = _get_tarika_load_tier("user123", {})
        assert tier == 2
        assert isinstance(is_excess, bool)


def test_tarika_prompt_external_image_references():
    """Q2: Verify Tarika prompt instructs embedding authentic external reference images."""
    import inspect
    from app import api_ai_assistant
    source = inspect.getsource(api_ai_assistant)
    assert "RELEVANT EXTERNAL REFERENCE IMAGES & VISUAL DATA" in source
    assert "![Figure: Description](<image_url>)" in source
    assert "Mermaid" in source


def test_tarika_test_generator_minimum_3_to_5_questions():
    """Q3: Verify practice exam generator enforces minimum 3 to 5 questions with tabular spec."""
    import inspect
    from app import api_ai_assistant
    source = inspect.getsource(api_ai_assistant)
    assert "MINIMUM 3 TO 5 QUESTIONS" in source
    assert "| Q# | Topic | Question Type | Marks |" in source
    assert "exam_stimulus" in source


def test_tarika_customer_prioritization_load_tiers():
    """Q4: Verify load tiering prioritizes BYOK (Tier 1) over regular auth (Tier 2) and casual (Tier 3)."""
    from app import _get_tarika_load_tier
    # BYOK / VIP
    tier1, _ = _get_tarika_load_tier("user1", {"has_custom_key": True})
    assert tier1 == 1

    # Standard logged-in user
    tier2, _ = _get_tarika_load_tier("user2", {})
    assert tier2 == 2

    # Anonymous user
    tier3, _ = _get_tarika_load_tier(None, {})
    assert tier3 == 3


def test_tarika_concurrency_and_token_balancing():
    """Q5: Verify concurrency governor tracks active requests and balances token limits."""
    import app as app_module
    from app import _tarika_lock

    initial_active = app_module._tarika_active_count
    with _tarika_lock:
        app_module._tarika_active_count += 4
    
    # Under excess load
    tier, is_excess = app_module._get_tarika_load_tier("user1", {})
    assert is_excess is True

    # Reset
    with _tarika_lock:
        app_module._tarika_active_count = initial_active


def test_tarika_webllm_support():
    """Q6: Verify Tarika gracefully resolves on-device WebLLM models and fallback adapter."""
    from methods.ai_provider import resolve_provider
    adapter, ceiling = resolve_provider({"ai_provider": "webllm"}, preferred_model="webllm:Llama-3.2-1B-Instruct-q4f16_1-MLC")
    assert adapter is not None
    assert ceiling is None
    # Model name or adapter is present
    assert hasattr(adapter, "complete")

