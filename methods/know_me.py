"""
know_me.py — MemoryWall DB helpers
Follows existing supabase_helper.py pattern: init_supabase() -> {"success": bool, ...}
"""

import hashlib
import random
import string
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from methods.supabase_helper import init_supabase


# ── Utilities ────────────────────────────────────────────────────────────────

def _hash_ip(ip: str) -> str:
    """SHA-256 hash of IP. Never store raw IP addresses."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _rand_suffix(n: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def generate_slug(name: str) -> str:
    """Create a URL-safe slug: first-word-of-name + 5 random chars."""
    base = (name or "wall").strip().lower()
    base = "".join(c if c.isalnum() else "-" for c in base)
    base = base[:20].strip("-")
    return f"{base}-{_rand_suffix(5)}"


# ── Wall CRUD ─────────────────────────────────────────────────────────────────

def create_wall(user_id: str, title: str, college: str = None,
                branch: str = None, graduation_year: int = None) -> Dict:
    client = init_supabase()
    if not client:
        return {"success": False, "message": "DB unavailable"}
    try:
        # Enforce 1 wall per user
        existing = client.table("memory_wall").select("id, slug").eq("user_id", user_id).execute()
        if existing.data:
            return {"success": False, "message": "already_exists", "data": existing.data[0]}

        slug = generate_slug(title or "wall")
        # Retry once on slug collision (extremely rare)
        try:
            res = client.table("memory_wall").insert({
                "user_id": user_id,
                "slug": slug,
                "title": title,
                "college": college,
                "branch": branch,
                "graduation_year": graduation_year,
            }).execute()
        except Exception:
            slug = generate_slug(title or "wall")
            res = client.table("memory_wall").insert({
                "user_id": user_id,
                "slug": slug,
                "title": title,
                "college": college,
                "branch": branch,
                "graduation_year": graduation_year,
            }).execute()

        if res.data:
            logging.info(f"[MemoryWall] Wall created: {slug} for user {user_id}")
            return {"success": True, "data": res.data[0]}
        return {"success": False, "message": "Insert returned no data"}
    except Exception as e:
        logging.error(f"[MemoryWall] create_wall error: {e}")
        return {"success": False, "message": str(e)}


def get_wall_by_slug(slug: str) -> Dict:
    client = init_supabase()
    if not client:
        return {"success": False, "data": None}
    try:
        res = client.table("memory_wall").select("*").eq("slug", slug).execute()
        if res.data:
            return {"success": True, "data": res.data[0]}
        return {"success": False, "data": None, "message": "not_found"}
    except Exception as e:
        return {"success": False, "data": None, "message": str(e)}


def get_wall_by_user(user_id: str) -> Dict:
    client = init_supabase()
    if not client:
        return {"success": False, "data": None}
    try:
        res = client.table("memory_wall").select("*").eq("user_id", user_id).execute()
        if res.data:
            return {"success": True, "data": res.data[0]}
        return {"success": False, "data": None, "message": "not_found"}
    except Exception as e:
        return {"success": False, "data": None, "message": str(e)}


# ── Response Submission ───────────────────────────────────────────────────────

def _is_rate_limited(ip_hash: str, limit: int = 5, window_hours: int = 1) -> bool:
    """Check if this IP has submitted >= limit times in the last window_hours."""
    client = init_supabase()
    if not client:
        return False
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        res = client.table("memory_response") \
            .select("id", count="exact") \
            .eq("ip_hash", ip_hash) \
            .gte("created_at", since) \
            .execute()
        count = res.count if res.count is not None else len(res.data or [])
        return count >= limit
    except Exception:
        return False


def submit_response(wall_id: str, friend_name: str, word_1: str, word_2: str,
                    word_3: str, message: str = None, emoji: str = None,
                    anonymous: bool = False, raw_ip: str = None,
                    signature_url: str = None) -> Dict:
    client = init_supabase()
    if not client:
        return {"success": False, "message": "DB unavailable"}
    try:
        ip_hash = _hash_ip(raw_ip or "unknown")

        # Rate limit check (5 per hour per IP)
        if _is_rate_limited(ip_hash):
            return {"success": False, "message": "rate_limited"}

        # Input length guards (server-side)
        friend_name = (friend_name or "").strip()[:50]
        word_1 = (word_1 or "").strip()[:30]
        word_2 = (word_2 or "").strip()[:30]
        word_3 = (word_3 or "").strip()[:30]
        message = (message or "").strip()[:500] if message else None
        emoji = (emoji or "").strip()[:20] if emoji else None

        if not all([friend_name, word_1, word_2, word_3]):
            return {"success": False, "message": "missing_required_fields"}

        # Insert response
        resp_res = client.table("memory_response").insert({
            "wall_id": wall_id,
            "friend_name": friend_name,
            "word_1": word_1,
            "word_2": word_2,
            "word_3": word_3,
            "memory_message": message,
            "emoji": emoji,
            "anonymous": anonymous,
            "ip_hash": ip_hash,
        }).execute()

        if not resp_res.data:
            return {"success": False, "message": "Failed to save response"}

        response_id = resp_res.data[0]["id"]

        # Insert signature if provided
        if signature_url:
            client.table("signature").insert({
                "response_id": response_id,
                "signature_url": signature_url,
            }).execute()

        # Increment response count on wall
        wall_res = client.table("memory_wall").select("response_count").eq("id", wall_id).execute()
        if wall_res.data:
            new_count = (wall_res.data[0].get("response_count") or 0) + 1
            client.table("memory_wall").update({
                "response_count": new_count,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", wall_id).execute()

        logging.info(f"[MemoryWall] Response submitted for wall {wall_id}")
        return {"success": True, "response_id": response_id}
    except Exception as e:
        logging.error(f"[MemoryWall] submit_response error: {e}")
        return {"success": False, "message": str(e)}


# ── Read Helpers ──────────────────────────────────────────────────────────────

def get_response_count(wall_id: str) -> int:
    client = init_supabase()
    if not client:
        return 0
    try:
        res = client.table("memory_wall").select("response_count").eq("id", wall_id).execute()
        return res.data[0].get("response_count", 0) if res.data else 0
    except Exception:
        return 0


def get_top_words(wall_id: str) -> List[Dict]:
    """Return [{word, count}, ...] sorted by frequency."""
    client = init_supabase()
    if not client:
        return []
    try:
        res = client.table("memory_response") \
            .select("word_1, word_2, word_3") \
            .eq("wall_id", wall_id) \
            .execute()
        freq: Dict[str, int] = {}
        for row in (res.data or []):
            for w in [row.get("word_1"), row.get("word_2"), row.get("word_3")]:
                if w:
                    key = w.strip().lower()
                    freq[key] = freq.get(key, 0) + 1
        return sorted([{"word": k, "count": v} for k, v in freq.items()],
                      key=lambda x: x["count"], reverse=True)
    except Exception as e:
        logging.error(f"[MemoryWall] get_top_words error: {e}")
        return []


def get_recent_responses(wall_id: str, limit: int = 20) -> List[Dict]:
    client = init_supabase()
    if not client:
        return []
    try:
        res = client.table("memory_response") \
            .select("*, signature(signature_url)") \
            .eq("wall_id", wall_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return res.data or []
    except Exception as e:
        logging.error(f"[MemoryWall] get_recent_responses error: {e}")
        return []


def reveal_wall(wall_id: str) -> Dict:
    """Return full response list + word frequency for reveal page."""
    responses = get_recent_responses(wall_id, limit=200)
    words = get_top_words(wall_id)
    # Build flat word list for wordcloud generation (repeated by frequency)
    word_list = []
    for entry in words:
        word_list.extend([entry["word"]] * entry["count"])
    return {
        "success": True,
        "responses": responses,
        "words": words,
        "word_list": word_list,
    }
