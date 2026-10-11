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
    cache_hit: bool = False,
    user_tier: str | None = None,
    route: str | None = None,
    status: str = "ok",
    cost_equiv_usd: float | None = None,
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
        valid_modes = {"scaffold", "direct", "compaction"}
        safe_mode = mode if mode in valid_modes else "direct"
        client.table("ai_usage_log").insert({
            "user_id": user_id,
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "model_id": f"{provider}:{model}",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "cost_equiv_usd": cost_equiv_usd or cost_usd,
            "duration_ms": duration_ms,
            "latency_ms": duration_ms,
            "mode": safe_mode,
            "route": route or safe_mode,
            "cache_hit": cache_hit,
            "user_tier": user_tier or ("auth" if user_id else "guest"),
            "status": status,
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



# ── AI Dashboard & Alerts (Tasks 6.8 & 6.9) ───────────────────────────────────

def get_ai_metrics_dashboard(hours: int = 24) -> dict:
    """Calculates requests, errors, latencies, cost, engine breakdown, and alerts (Tasks 6.8 & 6.9)."""
    from methods.supabase_helper import init_supabase
    from datetime import timedelta
    client = init_supabase()
    if not client:
        return {"success": False, "message": "DB unavailable", "metrics": {}, "alerts": []}
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = (
            client.table("ai_usage_log")
            .select("provider, model, cost_usd, duration_ms, error_type, mode, created_at")
            .gte("created_at", since)
            .execute()
        ).data or []

        total_requests = len(rows)
        errors = [r for r in rows if r.get("error_type")]
        total_errors = len(errors)
        error_rate = round((total_errors / total_requests * 100), 2) if total_requests else 0.0
        total_cost = round(sum(float(r.get("cost_usd") or 0) for r in rows), 4)
        avg_latency = round(sum(int(r.get("duration_ms") or 0) for r in rows) / total_requests, 1) if total_requests else 0.0

        engine_breakdown = {}
        for r in rows:
            p = r.get("provider") or "unknown"
            engine_breakdown[p] = engine_breakdown.get(p, 0) + 1

        alerts = []
        if error_rate > 10.0 and total_requests >= 10:
            alerts.append({"level": "warning", "code": "HIGH_ERROR_RATE", "message": f"AI error rate is {error_rate}% (>10% threshold)"})
        if total_cost > float(os.getenv("AI_MAX_COST_USD_PER_DAY", "5.0")):
            alerts.append({"level": "critical", "code": "COST_CEILING_EXCEEDED", "message": f"Daily AI spend (${total_cost}) has exceeded ceiling"})
        if total_errors >= 5:
            recent_errs = [e for e in errors if e.get("error_type") in ("provider_error", "timeout", "rate_limit")]
            if len(recent_errs) >= 5:
                alerts.append({"level": "warning", "code": "REPEATED_PROVIDER_FAILURES", "message": f"{len(recent_errs)} provider errors detected in the last {hours}h"})

        return {
            "success": True,
            "period_hours": hours,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate_pct": error_rate,
            "total_cost_usd": total_cost,
            "avg_latency_ms": avg_latency,
            "engine_breakdown": engine_breakdown,
            "alerts": alerts
        }
    except Exception as exc:
        log.warning("[ai_usage] get_ai_metrics_dashboard error: %s", exc)
        return {"success": False, "error": str(exc), "metrics": {}, "alerts": []}


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
