"""
ai_usage.py — Cost governance and usage logging.

Addresses: F9 (cost surprise).
Amendment notes:
  - Race condition on read-then-write is accepted at MVP scale; see comment in check_ceiling().
  - Compaction calls MUST call log_turn() with mode='compaction' so they count toward ceiling.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timezone, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from methods.ai_provider import ProviderResponse

log = logging.getLogger(__name__)


# ── Typed error ───────────────────────────────────────────────────────────────

class CostCeilingError(Exception):
    """Daily cost ceiling reached for this user."""


# ── Cost ceiling check (F9) ───────────────────────────────────────────────────

def check_ceiling(user_id: str) -> None:
    """Raise CostCeilingError if user has hit today's limit.

    ponytail: read-then-write race — a user could overshoot by ~1 concurrent request.
    Exposure is capped at AI_MAX_COST_USD_PER_DAY (~$0.02). Acceptable at MVP scale;
    replace with a DB-level atomic counter (e.g. SELECT ... FOR UPDATE or pg advisory
    lock) if throughput requires it.
    """
    from methods.supabase_helper import init_supabase
    ceiling = float(os.getenv("AI_MAX_COST_USD_PER_DAY", "0.02"))
    today = date.today().isoformat()

    client = init_supabase()
    if not client:
        log.warning("[ai_usage] DB unavailable — skipping ceiling check (fail-open)")
        return

    try:
        rows = (
            client.table("ai_usage_log")
            .select("cost_usd")
            .eq("user_id", user_id)
            .gte("created_at", f"{today}T00:00:00+00:00")
            .execute()
        )
        total = sum(float(r.get("cost_usd") or 0) for r in (rows.data or []))
        if total >= ceiling:
            raise CostCeilingError(
                f"Daily AI limit reached (${ceiling:.2f}/day). "
                "Add your own API key in Settings to continue, or try again tomorrow."
            )
    except CostCeilingError:
        raise
    except Exception as exc:
        log.warning("[ai_usage] check_ceiling error (fail-open): %s", exc)


# ── Usage logging (F7) ───────────────────────────────────────────────────────

def log_turn(
    *,
    user_id: str | None,
    session_id: str | None,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    duration_ms: int,
    mode: str,                  # 'scaffold' | 'direct' | 'compaction'
    override_used: bool = False,
    error_type: str | None = None,
    safety_flag: str | None = None,
    finish_reason: str | None = "stop",
) -> None:
    """Insert one structured row into ai_usage_log.

    Called after EVERY turn — success, failure, AND compaction (amendment 2).
    Never raises: a logging failure must not break the response flow.
    """
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client:
        log.warning("[ai_usage] DB unavailable — usage row not written")
        return
    try:
        client.table("ai_usage_log").insert({
            "user_id": user_id,
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "duration_ms": duration_ms,
            "mode": mode,
            "override_used": override_used,
            "error_type": error_type,
            "safety_flag": safety_flag,
            "finish_reason": finish_reason,
        }).execute()
    except Exception as exc:
        log.warning("[ai_usage] log_turn insert failed: %s", exc)


# ── User-facing usage query ───────────────────────────────────────────────────

def get_user_usage(user_id: str, days: int = 7) -> list[dict]:
    """Return aggregated daily usage rows for the last N days (user's own data only)."""
    from methods.supabase_helper import init_supabase
    from datetime import timedelta
    client = init_supabase()
    if not client:
        return []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = (
            client.table("ai_usage_log")
            .select("cost_usd, tokens_in, tokens_out, created_at, mode, error_type")
            .eq("user_id", user_id)
            .gte("created_at", since)
            .order("created_at", desc=True)
            .execute()
        )
        return rows.data or []
    except Exception as exc:
        log.warning("[ai_usage] get_user_usage error: %s", exc)
        return []


# ── Ponytail self-check ───────────────────────────────────────────────────────

if __name__ == "__main__":
    # Verify CostCeilingError is raised when total >= ceiling
    import unittest.mock as mock

    dummy_rows = [{"cost_usd": "0.010"}, {"cost_usd": "0.011"}]
    fake_result = mock.MagicMock()
    fake_result.data = dummy_rows
    fake_client = mock.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = fake_result

    with mock.patch("methods.supabase_helper.init_supabase", return_value=fake_client):
        with mock.patch.dict(os.environ, {"AI_MAX_COST_USD_PER_DAY": "0.02"}):
            try:
                check_ceiling("test-user")
                raise AssertionError("Should have raised CostCeilingError")
            except CostCeilingError as e:
                assert "limit reached" in str(e).lower()

    print("ai_usage self-check: PASS")
