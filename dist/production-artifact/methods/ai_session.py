"""
ai_session.py — Tutor session memory with rolling-window compaction.

Addresses: F2 (context bloat).
Amendment 2: compact_if_needed() calls log_turn(mode='compaction') so
compaction cost counts toward the daily ceiling.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from methods.ai_provider import OpenRouterAdapter

log = logging.getLogger(__name__)

_WINDOW = int(os.getenv("AI_SESSION_WINDOW", "6"))
_COMPACT_THRESHOLD = 10   # compact when turn_count hits this
_COMPACT_KEEP = 4          # turns to keep verbatim after compaction


# ── Session CRUD ──────────────────────────────────────────────────────────────

def get_or_create_session(user_id: str, doc_id: str) -> dict:
    """Return existing session row or create one. Returns {} on DB failure."""
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client:
        return {}
    try:
        res = (client.table("tutor_sessions")
               .select("*")
               .eq("user_id", user_id)
               .eq("doc_id", doc_id)
               .execute())
        if res.data:
            return res.data[0]
        ins = client.table("tutor_sessions").insert({
            "user_id": user_id,
            "doc_id": doc_id,
        }).execute()
        return ins.data[0] if ins.data else {}
    except Exception as exc:
        log.warning("[ai_session] get_or_create_session error: %s", exc)
        return {}


def record_turn(session_id: str) -> None:
    """Increment turn_count and update last_active_at. Never raises."""
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client:
        return
    try:
        # Read current count then increment — acceptable at tutor scale
        res = (client.table("tutor_sessions")
               .select("turn_count")
               .eq("id", session_id)
               .single()
               .execute())
        current = (res.data or {}).get("turn_count", 0) or 0
        client.table("tutor_sessions").update({
            "turn_count": current + 1,
            "last_active_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).execute()
    except Exception as exc:
        log.warning("[ai_session] record_turn error: %s", exc)


def update_topic_map(session_id: str, topic: str, doc_id: str, confidence: float) -> None:
    """Upsert a topic entry in topic_map JSONB. Never raises.

    topic_map shape: {topic: {doc_id, confidence, last_seen_at}}
    Per-subject view later = GROUP BY topic WHERE doc_id IN (subject's docs) — query change only.
    """
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client:
        return
    try:
        res = (client.table("tutor_sessions")
               .select("topic_map")
               .eq("id", session_id)
               .single()
               .execute())
        topic_map = (res.data or {}).get("topic_map") or {}
        topic_map[topic] = {
            "doc_id": doc_id,
            "confidence": round(confidence, 2),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("tutor_sessions").update({"topic_map": topic_map}).eq("id", session_id).execute()
    except Exception as exc:
        log.warning("[ai_session] update_topic_map error: %s", exc)


def _save_summary(session_id: str, summary: str) -> None:
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client:
        return
    try:
        client.table("tutor_sessions").update({"summary": summary}).eq("id", session_id).execute()
    except Exception as exc:
        log.warning("[ai_session] _save_summary error: %s", exc)


# ── Context building (F2) ─────────────────────────────────────────────────────

def build_context(session: dict, doc_text: str, system_prompt: str) -> list[dict]:
    """Build the messages list for the provider call.

    Structure (pinned system prompt is NEVER evicted — F2 Claude Code lesson):
      [system: pinned_prompt + doc excerpt + summary]
      [assistant: <compacted summary if exists>]  ← only if summary is set
      [last N turns from session — verbatim]
    """
    summary = session.get("summary") or ""
    topic_map = session.get("topic_map") or {}

    # Build pinned system context — reconstructed fresh every turn, never evicted
    weak_areas = [t for t, v in topic_map.items() if (v.get("confidence") or 1) < 0.5]
    system_content = system_prompt
    if doc_text:
        system_content += f"\n\n--- DOCUMENT EXCERPT ---\n{doc_text[:3000]}\n--- END ---"
    if weak_areas:
        system_content += f"\n\nWeak areas identified in prior turns: {', '.join(weak_areas[:5])}. Address these where relevant."

    messages: list[dict] = [{"role": "system", "content": system_content}]

    # Inject compacted summary as assistant context (not system, avoids injection via F4 boundary)
    if summary:
        messages.append({
            "role": "assistant",
            "content": f"[Prior session context] {summary}",
        })

    return messages


# ── Compaction (F2, amendment 2) ─────────────────────────────────────────────

def compact_if_needed(
    session: dict,
    conversation: list[dict],
    adapter: "OpenRouterAdapter",
) -> tuple[list[dict], str | None]:
    """If turn_count >= threshold, summarise the oldest turns.

    Returns (updated_conversation, new_summary_or_None).
    Logs its own ai_usage_log row with mode='compaction' (amendment 2) so
    compaction cost counts toward the daily free-tier ceiling.
    """
    from methods.ai_usage import log_turn

    turn_count = session.get("turn_count", 0) or 0
    if turn_count < _COMPACT_THRESHOLD or len(conversation) <= _COMPACT_KEEP + 1:
        return conversation, None

    # Split: keep the last _COMPACT_KEEP turns verbatim; summarise the rest
    system_msg = conversation[:1]     # pinned system always first
    to_compact = conversation[1:-_COMPACT_KEEP] if len(conversation) > _COMPACT_KEEP + 1 else []
    to_keep = conversation[-_COMPACT_KEEP:]

    if not to_compact:
        return conversation, None

    compact_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in to_compact
        if isinstance(m.get("content"), str)
    )
    summary_prompt = [
        {"role": "system", "content": "Summarise this tutoring exchange in 3-5 sentences, preserving key concepts, student confusion points, and hints already given."},
        {"role": "user", "content": compact_text[:2000]},
    ]

    t0 = time.monotonic()
    try:
        result = adapter.complete(summary_prompt, max_tokens=200, temperature=0.2)
        duration_ms = int((time.monotonic() - t0) * 1000)
        new_summary = result.text

        # Amendment 2: log this compaction call as its own usage row
        log_turn(
            user_id=session.get("user_id"),
            session_id=session.get("id"),
            provider=adapter.provider_name,
            model=result.model_used,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            duration_ms=duration_ms,
            mode="compaction",
        )
        _save_summary(session.get("id", ""), new_summary)
        return system_msg + to_keep, new_summary
    except Exception as exc:
        log.warning("[ai_session] compaction failed (using uncompacted context): %s", exc)
        return conversation, None


# ── Ponytail self-check ───────────────────────────────────────────────────────

if __name__ == "__main__":
    # build_context: verify system prompt is always first and never evicted
    fake_session = {"summary": "Student knows integration basics.", "topic_map": {
        "chain rule": {"doc_id": "x", "confidence": 0.3, "last_seen_at": "2026-09-18T00:00:00Z"},
    }}
    msgs = build_context(fake_session, "some doc text", "You are a tutor.")
    assert msgs[0]["role"] == "system"
    assert "DOCUMENT EXCERPT" in msgs[0]["content"]
    assert "chain rule" in msgs[0]["content"]   # weak area surfaced
    assert msgs[1]["role"] == "assistant"        # summary injected
    assert len(msgs) == 2
    print("ai_session self-check: PASS")
