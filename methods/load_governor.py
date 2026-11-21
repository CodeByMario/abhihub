"""
methods/load_governor.py — CPU Budget Metering, System Load State & Tier Admission
==================================================================================
1. Tracks daily active CPU (time.thread_time()) against Vercel Fluid budget in Redis:
   key `budget:cpu:YYYY-MM-DD`, expire 48h.
2. Evaluates system load state with hysteresis:
   - green:  < 60%
   - yellow: 60% - 85%
   - red:    > 85% (enter at 85%, leave only when dropping to <= 75%)
3. Tier admission matrix (admit(user, op)):
   - free:    AI 3/day, OCR 3/day, Know-Me 1/day
   - premium: AI 30/day (400/month fair-use), OCR 40/day, Know-Me 50/day
   - Returns 'run' | 'queue' | 'limit'.
   - Search is NEVER 'queue'. Under red load, search degrades from fuzzy to prefix/exact.
"""
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from methods.redis_client import get_redis_client

logger = logging.getLogger("load.governor")

# Vercel Fluid compute budget: 4h/mo = ~480 s/day. Planned safety target: 335 s/day.
DEFAULT_DAILY_CPU_BUDGET_MS = int(os.getenv("DAILY_CPU_BUDGET_MS", 335_000))

TIER_LIMITS: Dict[str, Dict[str, int]] = {
    'free': {
        'ai': 3,
        'ocr': 3,
        'know_me': 1,
    },
    'premium': {
        'ai': 30,
        'ai_monthly': 400,
        'ocr': 40,
        'know_me': 50,
    }
}


def _get_utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_request_cpu(cpu_ms: float):
    """Increment daily CPU budget counter in Redis by cpu_ms with 48h TTL."""
    if cpu_ms <= 0:
        return
    try:
        r = get_redis_client()
        date_str = _get_utc_date_str()
        key = f"budget:cpu:{date_str}"
        r.incrby(key, int(round(cpu_ms)))
        r.expire(key, 172800)  # 48h
    except Exception as e:
        logger.debug("[LOAD_GOVERNOR] record_request_cpu failed: %s", e)


def get_daily_cpu_usage(date_str: Optional[str] = None) -> int:
    """Retrieve current daily CPU usage in ms from Redis."""
    try:
        r = get_redis_client()
        d = date_str or _get_utc_date_str()
        raw = r.get(f"budget:cpu:{d}")
        return int(raw or 0)
    except Exception:
        return 0


def get_load_state(budget_ms: Optional[int] = None) -> str:
    """
    Computes system load state with hysteresis:
    - green: < 60%
    - yellow: 60% - 85%
    - red: >= 85% to enter, <= 75% to exit.
    """
    max_budget = budget_ms or DEFAULT_DAILY_CPU_BUDGET_MS
    used_ms = get_daily_cpu_usage()
    pct = (used_ms / max_budget) * 100.0 if max_budget > 0 else 0.0

    r = get_redis_client()
    curr_state_key = "load:state:current"
    prev_state = None
    try:
        prev_state = r.get(curr_state_key)
    except Exception:
        pass

    # Hysteresis logic for Red state
    if prev_state == "red":
        if pct <= 75.0:
            new_state = "yellow" if pct >= 60.0 else "green"
        else:
            new_state = "red"
    else:
        if pct >= 85.0:
            new_state = "red"
        elif pct >= 60.0:
            new_state = "yellow"
        else:
            new_state = "green"

    if new_state != prev_state:
        try:
            r.set(curr_state_key, new_state, ex=300)
        except Exception:
            pass

    return new_state


def get_user_tier(user: Any) -> str:
    """Resolve user tier ('free' or 'premium')."""
    if not user:
        return 'free'
    if isinstance(user, dict):
        if user.get('is_premium') or user.get('premium') or user.get('tier') in ('pro', 'premium', 'ultra', 'vip'):
            return 'premium'
        role = user.get('role') or ''
        if role in ('admin', 'superadmin', 'educator', 'moderator'):
            return 'premium'
    elif hasattr(user, 'is_premium') and user.is_premium:
        return 'premium'
    return 'free'


def get_user_op_usage(user_id: str, op: str) -> int:
    """Get user's daily usage for an operation."""
    if not user_id:
        return 0
    try:
        r = get_redis_client()
        date_str = _get_utc_date_str()
        raw = r.get(f"usage:{op}:{user_id}:{date_str}")
        return int(raw or 0)
    except Exception:
        return 0


def increment_user_op_usage(user_id: str, op: str) -> int:
    """Increment user's daily usage for an operation."""
    if not user_id:
        return 0
    try:
        r = get_redis_client()
        date_str = _get_utc_date_str()
        key = f"usage:{op}:{user_id}:{date_str}"
        val = r.incr(key)
        r.expire(key, 172800)
        return val
    except Exception:
        return 0


def admit(user: Any, op: str) -> str:
    """
    Admission control for an operation.
    Returns: 'run' | 'queue' | 'limit'
    Rule: Search is NEVER 'queue'. Under red load, search degrades instead.
    """
    op_clean = op.lower().replace("-", "_")

    # Search never queues
    if op_clean in ('search', 'uncached_search', 'spotlight_search'):
        return 'run'

    tier = get_user_tier(user)
    user_id = None
    if isinstance(user, dict):
        user_id = user.get('uid') or user.get('id') or user.get('email')
    elif hasattr(user, 'uid'):
        user_id = getattr(user, 'uid')

    tier_cfg = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    limit = tier_cfg.get(op_clean, 999999)

    # Check daily limit
    if user_id:
        current_usage = get_user_op_usage(user_id, op_clean)
        if current_usage >= limit:
            return 'limit'

    # System load state check
    state = get_load_state()

    # Premium users always run immediately unless hard daily limit reached
    if tier == 'premium':
        return 'run'

    # Free tier load management
    if state == 'green':
        return 'run'
    elif state == 'yellow':
        # Free AI queues under yellow load
        if op_clean in ('ai', 'chat', 'assistant'):
            return 'queue'
        return 'run'
    else:  # state == 'red'
        # Under red load, free AI and heavy CPU ops (OCR, Know-Me) queue
        if op_clean in ('ai', 'chat', 'assistant', 'ocr', 'know_me'):
            return 'queue'
        return 'run'
