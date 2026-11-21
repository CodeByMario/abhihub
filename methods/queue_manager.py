"""
methods/queue_manager.py — Load-Aware Serverless Queue System
=============================================================
Manages free AI pool token bucket (<=15 req/min, 900/1000 daily pool cap),
Redis sorted set queue, heartbeat tab eviction, and single-use atomic tickets.
"""
import os
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from methods.redis_client import get_redis_client
from methods.load_governor import get_user_tier

logger = logging.getLogger("queue.manager")

# Free AI Pool limits
MAX_REQS_PER_MIN = int(os.getenv("MAX_FREE_AI_PER_MIN", 15))
DAILY_FREE_POOL_CAP = int(os.getenv("DAILY_FREE_AI_POOL", 900))
TICKET_TTL_SECONDS = 90
HEARTBEAT_TTL_SECONDS = 30
VIP_SCORE_BONUS_SECONDS = 60.0  # Moves VIP up by ~1 minute in line for heavy jobs


def _get_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_minute_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M")


def get_daily_free_pool_used() -> int:
    """Returns total free AI queries used today."""
    try:
        r = get_redis_client()
        raw = r.get(f"pool:free_ai:{_get_utc_date()}")
        return int(raw or 0)
    except Exception:
        return 0


def get_minute_reqs_used() -> int:
    """Returns free AI queries admitted in the current minute."""
    try:
        r = get_redis_client()
        raw = r.get(f"rate:free_ai:{_get_minute_key()}")
        return int(raw or 0)
    except Exception:
        return 0


def _try_admit_capacity() -> bool:
    """
    Atomically attempts to consume 1 slot from both minute bucket and daily pool.
    Rolls back if either limit is breached.
    """
    r = get_redis_client()
    min_key = f"rate:free_ai:{_get_minute_key()}"
    pool_key = f"pool:free_ai:{_get_utc_date()}"

    # Check daily pool first
    curr_pool = int(r.get(pool_key) or 0)
    if curr_pool >= DAILY_FREE_POOL_CAP:
        return False

    # Check minute bucket
    curr_min = int(r.get(min_key) or 0)
    if curr_min >= MAX_REQS_PER_MIN:
        return False

    # Atomically increment minute counter
    new_min = r.incr(min_key)
    r.expire(min_key, 120)  # expire after 2 minutes
    if new_min > MAX_REQS_PER_MIN:
        # Exceeded: roll back
        r.incrby(min_key, -1)
        return False

    # Atomically increment daily counter
    new_pool = r.incr(pool_key)
    r.expire(pool_key, 172800)  # 48h
    if new_pool > DAILY_FREE_POOL_CAP:
        # Exceeded: roll back both
        r.incrby(pool_key, -1)
        r.incrby(min_key, -1)
        return False

    return True


def create_single_use_ticket(uid: Optional[str] = None, qid: Optional[str] = None) -> str:
    """Generate a single-use ticket with 90s TTL."""
    r = get_redis_client()
    ticket_id = f"tkt_{uuid.uuid4().hex}"
    payload = f"{uid or 'anon'}:{qid or 'direct'}:{time.time()}"
    r.setex(f"ticket:ai:{ticket_id}", TICKET_TTL_SECONDS, payload)
    return ticket_id


def consume_ticket(ticket_id: str) -> bool:
    """
    Atomically consumes a single-use ticket using GETDEL.
    Returns True if valid and consumed; False if invalid or expired.
    """
    if not ticket_id:
        return False
    try:
        r = get_redis_client()
        val = r.getdel(f"ticket:ai:{ticket_id}")
        return val is not None
    except Exception as e:
        logger.warning("[QUEUE] Ticket consumption error: %s", e)
        return False


def prune_ghost_users(queue_key: str = "queue:ai"):
    """Prune queue entries whose heartbeat has expired (>30s inactive)."""
    try:
        r = get_redis_client()
        # Look at the top 20 candidates in queue
        top_candidates = r.zrange(queue_key, 0, 19)
        for cand in top_candidates:
            hb = r.get(f"queue:hb:{cand}")
            if not hb:
                # Heartbeat expired -> tab abandoned
                r.zrem(queue_key, cand)
                logger.info("[QUEUE] Dropped abandoned queue entry: %s", cand)
    except Exception as e:
        logger.debug("[QUEUE] Ghost pruning skipped: %s", e)


def join_queue(user: Any, op: str = "ai") -> Dict[str, Any]:
    """
    Join the queue for an operation.
    Returns:
      {"status": "ready", "ticket": tkt, "expires_in": 90}
      {"status": "waiting", "qid": qid, "position": pos, "eta_s": eta, "poll_in": sec}
      {"status": "exhausted", "options": ["webllm", "byok", "premium"]}
    """
    tier = get_user_tier(user)
    uid = None
    if isinstance(user, dict):
        uid = user.get('uid') or user.get('id') or user.get('email')

    # Premium users skip queue entirely
    if tier == 'premium':
        ticket = create_single_use_ticket(uid=uid, qid='vip')
        return {
            "status": "ready",
            "ticket": ticket,
            "expires_in": TICKET_TTL_SECONDS,
            "tier": "premium"
        }

    # Check if daily pool is exhausted
    if get_daily_free_pool_used() >= DAILY_FREE_POOL_CAP:
        return {
            "status": "exhausted",
            "message": "Daily free AI capacity is fully exhausted.",
            "options": ["webllm", "byok", "premium"]
        }

    r = get_redis_client()
    queue_key = f"queue:{op}"

    # If queue is empty and rate capacity is immediately available -> admit immediately
    if r.zcard(queue_key) == 0:
        if _try_admit_capacity():
            ticket = create_single_use_ticket(uid=uid, qid='direct')
            return {
                "status": "ready",
                "ticket": ticket,
                "expires_in": TICKET_TTL_SECONDS
            }

    # Otherwise, join the queue
    qid = f"q_{uuid.uuid4().hex[:12]}"
    score = time.time()
    if tier in ('pro', 'vip'):
        score -= VIP_SCORE_BONUS_SECONDS

    r.zadd(queue_key, {qid: score})
    r.setex(f"queue:hb:{qid}", HEARTBEAT_TTL_SECONDS, str(time.time()))

    # Calculate position
    rank = r.zrank(queue_key, qid) or 0
    position = rank + 1
    eta_s = position * 4  # 15/min = 1 every 4s
    poll_in = 2 if position <= 2 else min(10, position * 2)

    return {
        "status": "waiting",
        "qid": qid,
        "position": position,
        "eta_s": eta_s,
        "poll_in": poll_in
    }


def check_queue_status(qid: str, op: str = "ai") -> Dict[str, Any]:
    """
    Check status of a queued request.
    Refreshes heartbeat and admits when at the front of queue.
    """
    r = get_redis_client()
    queue_key = f"queue:{op}"

    # Check if already promoted to a ticket
    ticket_key = f"queue:ready:{qid}"
    ready_ticket = r.get(ticket_key)
    if ready_ticket:
        r.delete(ticket_key)
        return {
            "status": "ready",
            "ticket": ready_ticket,
            "expires_in": TICKET_TTL_SECONDS
        }

    rank = r.zrank(queue_key, qid)
    if rank is None:
        # Not in queue and no ticket -> expired or abandoned
        return {"status": "expired", "message": "Queue session expired or was dropped."}

    # Refresh heartbeat
    r.setex(f"queue:hb:{qid}", HEARTBEAT_TTL_SECONDS, str(time.time()))

    # Prune any ghost entries ahead of this qid
    prune_ghost_users(queue_key)

    # Re-evaluate rank after potential ghost removals
    rank = r.zrank(queue_key, qid)
    if rank is None:
        return {"status": "expired", "message": "Queue session expired."}

    # If at front of the queue (rank == 0), try to admit capacity
    if rank == 0:
        if _try_admit_capacity():
            r.zrem(queue_key, qid)
            r.delete(f"queue:hb:{qid}")
            ticket = create_single_use_ticket(qid=qid)
            return {
                "status": "ready",
                "ticket": ticket,
                "expires_in": TICKET_TTL_SECONDS
            }

    position = rank + 1
    eta_s = position * 4
    poll_in = 2 if position <= 2 else min(10, position * 2)

    return {
        "status": "waiting",
        "position": position,
        "eta_s": eta_s,
        "poll_in": poll_in
    }
