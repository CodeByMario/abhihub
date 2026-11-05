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


def increment_view_count(wall_id: str) -> None:
    """Increment the view_count for a wall."""
    client = init_supabase()
    if not client: return
    try:
        # Fetch current count
        res = client.table("memory_wall").select("view_count").eq("id", wall_id).execute()
        current = res.data[0].get("view_count") if res.data else 0
        current = current if current is not None else 0
        # Update
        client.table("memory_wall").update({"view_count": current + 1}).eq("id", wall_id).execute()
    except Exception as e:
        logging.error(f"[MemoryWall] increment_view_count error (may need column): {e}")


def get_dashboard_metrics(wall_id: str) -> Dict:
    """Build the single-source-of-truth dashboard data."""
    client = init_supabase()
    if not client:
        return {}
    
    try:
        # 1. Fetch wall for response & view counts
        wall_res = client.table("memory_wall").select("response_count, view_count").eq("id", wall_id).execute()
        wall_data = wall_res.data[0] if wall_res.data else {}
        memory_count = wall_data.get("response_count", 0) or 0
        view_count = wall_data.get("view_count", 0) or 0
        
        # 2. Get top words for most loved trait
        words = get_top_words(wall_id)
        word_count = len(words)
        
        most_loved_trait = ""
        most_loved_trait_count = 0
        top_traits = []
        
        if words:
            most_loved_trait = words[0]["word"].capitalize()
            most_loved_trait_count = words[0]["count"]
            top_traits = [(w["word"].capitalize(), w["count"]) for w in words[:5]]
            
        # 3. Get all recent responses to build activity feed & count signatures
        responses = get_recent_responses(wall_id, limit=100)
        signature_count = sum(1 for r in responses if r.get("signature"))
        
        recent_activity = []
        for r in responses:
            fname = r.get("friend_name") or "Someone"
            time_str = r.get("created_at", "").split("T")[0]
            
            # Activities per response
            if r.get("signature"):
                recent_activity.append({"type": "signature", "icon": "✍️", "text": f"{fname} signed your wall", "time": time_str})
            recent_activity.append({"type": "memory", "icon": "💭", "text": f"{fname} left a memory", "time": time_str})
            if r.get("word_1"):
                recent_activity.append({"type": "word", "icon": "🏷️", "text": f"{fname} described you as '{r['word_1']}'", "time": time_str})
                
        # Limit activity feed to top 10
        recent_activity = recent_activity[:10]
        
        # 4. Progress percentage (Goal: 50)
        goal = 50
        progress_percentage = min(int((memory_count / goal) * 100) if goal > 0 else 0, 100)
        
        return {
            "memory_count": memory_count,
            "signature_count": signature_count,
            "word_count": word_count,
            "view_count": view_count,
            "most_loved_trait": most_loved_trait,
            "most_loved_trait_count": most_loved_trait_count,
            "progress_percentage": progress_percentage,
            "recent_activity": recent_activity,
            "top_traits": top_traits
        }
    except Exception as e:
        logging.error(f"[MemoryWall] get_dashboard_metrics error: {e}")
        return {}


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


def generate_personality_summary(metrics: Dict) -> Dict:
    """
    Build a warm, human-sounding personality summary from trait data.
    Fully template-based — no external API needed.
    Swap the return value for a Gemini call later without changing callers.
    """
    if not metrics:
        return {}

    top_traits = metrics.get("top_traits", [])       # [("Helpful", 12), ...]
    memory_count = metrics.get("memory_count", 0)
    most_loved = metrics.get("most_loved_trait", "")
    word_count = metrics.get("word_count", 0)
    sig_count = metrics.get("signature_count", 0)

    if not top_traits or memory_count < 1:
        return {}

    trait_names = [t[0] for t in top_traits]
    t1 = trait_names[0] if len(trait_names) > 0 else ""
    t2 = trait_names[1] if len(trait_names) > 1 else ""
    t3 = trait_names[2] if len(trait_names) > 2 else ""

    # ── Sentence 1: Opening (based on memory count) ──────────────────
    if memory_count >= 50:
        s1 = f"Across {memory_count} memories, a clear picture of you has emerged."
    elif memory_count >= 20:
        s1 = f"{memory_count} people have now shared how they see you, and the picture is becoming very clear."
    elif memory_count >= 10:
        s1 = f"With {memory_count} people sharing their thoughts, some strong patterns are already visible."
    else:
        s1 = f"Even from {memory_count} {'person' if memory_count == 1 else 'people'}, something meaningful has been said about you."

    # ── Sentence 2: Lead trait ────────────────────────────────────────
    lead_templates = [
        f"You are remembered above all else as someone {t1.lower()}.",
        f"The word that keeps coming back is \"{t1}\" — chosen independently by multiple people.",
        f"People consistently reach for \"{t1}\" when they think of you.",
        f"At the core of how others see you is one clear quality: {t1.lower()}.",
    ]
    import random as _r
    _seed = memory_count + len(t1)
    s2 = lead_templates[_seed % len(lead_templates)]

    # ── Sentence 3: Secondary traits ─────────────────────────────────
    if t2 and t3:
        s3 = f"Alongside that, \"{t2}\" and \"{t3}\" surfaced repeatedly — qualities that seem to define how you show up for others."
    elif t2:
        s3 = f"People also frequently described you as \"{t2}\", which speaks to a consistent side of your personality."
    else:
        s3 = f"This trait seems to be a consistent anchor in how people experience you."

    # ── Sentence 4: Depth / reflection ───────────────────────────────
    depth_templates = [
        f"What stands out is that these words weren't suggested — {memory_count} people arrived at them independently.",
        f"These aren't just adjectives. They're {memory_count} separate moments where someone thought of you and felt something.",
        f"There's something powerful about {memory_count} people, on their own, choosing words that overlap this much.",
        f"The consistency across {memory_count} responses suggests this is genuinely how people feel — not just what they thought they should say.",
    ]
    s4 = depth_templates[(_seed + 1) % len(depth_templates)]

    # ── Sentence 5: Closing ───────────────────────────────────────────
    if word_count >= 30:
        s5 = f"With {word_count} unique words used across all responses, the full picture of you is rich and layered."
    elif sig_count > 0:
        s5 = f"{sig_count} people even took the time to leave their signature — a small gesture that says a lot."
    else:
        s5 = "The people in your life clearly notice more about you than they may say out loud."

    sentences = [s1, s2, s3, s4, s5]
    summary = " ".join(sentences)

    return {
        "headline": "How people see you",
        "summary": summary,
        "sentences": sentences,
        "lead_trait": t1,
    }

