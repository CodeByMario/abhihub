"""
AbhiHub Scoring Engine — Dynamic Access & Contribution Economy.

Reads all point values from abhihub.scoring_config (admin-editable, cached).
Processes activity events and awards contribution points via the existing
award_contribution_xp() pipeline in methods/supabase_helper.py.

Phase 1 scope: config loader + event processing with unique-view dedupe.
"""
import logging
import time
from typing import Dict, Optional

from methods.supabase_helper import init_supabase

# In-process config cache (per worker). TTL keeps admin edits effective quickly.
_CONFIG_CACHE: Dict = {}
_CONFIG_CACHE_AT: float = 0.0
CONFIG_TTL_SECONDS = 300

DEFAULT_POINTS = {
    "view": 0.1, "like": 2, "bookmark": 5, "publish": 5, "comment": 1,
    "spam_penalty_min": -10, "spam_penalty_max": -25,
}


def _get_client():
    """
    Client for server-side economy tables. Prefers the admin (service key)
    client — RLS-bypassing, correct for trusted server-side scoring — and
    falls back to the anon client.
    """
    from methods.supabase_helper import init_supabase_admin
    client = init_supabase_admin()
    if client:
        return client
    return init_supabase()


def get_config(key: str, default=None):
    """Fetch one scoring_config key with TTL cache. Falls back to defaults."""
    global _CONFIG_CACHE, _CONFIG_CACHE_AT
    now = time.time()
    if not _CONFIG_CACHE or (now - _CONFIG_CACHE_AT) > CONFIG_TTL_SECONDS:
        try:
            client = _get_client()
            res = client.table("scoring_config").select("key,value").execute()
            _CONFIG_CACHE = {r["key"]: r["value"] for r in (res.data or [])}
            _CONFIG_CACHE_AT = now
        except Exception as e:
            logging.warning(f"[ScoringEngine] config load failed, using defaults: {e}")
            if not _CONFIG_CACHE:
                return default
    if key in _CONFIG_CACHE:
        return _CONFIG_CACHE[key]
    if default is not None:
        return default
    return DEFAULT_POINTS.get(key)


def get_points() -> Dict:
    """Current point values (config table or sane defaults)."""
    pts = get_config("points")
    if isinstance(pts, dict):
        merged = dict(DEFAULT_POINTS)
        merged.update(pts)
        return merged
    return dict(DEFAULT_POINTS)


def is_unique_view(user_id: str, document_id: str) -> bool:
    """
    True if this (user, document) pair hasn't been scored within the dedupe
    window. Refreshes don't re-score. Uses document_views history.
    """
    client = _get_client()
    if not client:
        return False
    try:
        rules = get_config("view_dedupe") or {}
        window_days = int(rules.get("window_days", 1))
        # Look for any prior view of this doc by this user in the window.
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        res = (
            client.table("document_views")
            .select("id")
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .gte("accessed_at", since)
            .limit(1)
            .execute()
        )
        # Unique only if no prior view exists in the window.
        return not (res.data)
    except Exception as e:
        logging.warning(f"[ScoringEngine] unique-view check failed: {e}")
        return False  # fail closed: don't score on errors


def _rate_limit_ok(user_id: str, event_type: str) -> bool:
    """
    Sliding per-hour rate limit from scoring_config.rate_limits.
    Counts scored contribution_logs entries of this event type in the last hour.
    Fail-open on errors (availability over strictness at this stage).
    """
    try:
        limits = get_config("rate_limits") or {}
        key = {
            "resource_viewed": "views_per_hour",
            "resource_liked": "likes_per_hour",
            "resource_bookmarked": "bookmarks_per_hour",
        }.get(event_type)
        if not key:
            return True
        limit = int(limits.get(key, 10**9))
        client = _get_client()
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        res = (
            client.table("contribution_logs")
            .select("id")
            .eq("user_id", user_id)
            .eq("action_type", event_type)
            .gte("created_at", since)
            .limit(limit + 1)
            .execute()
        )
        return len(res.data or []) < limit
    except Exception as e:
        logging.warning(f"[ScoringEngine] rate-limit check failed (fail-open): {e}")
        return True


def get_access_level(abhihub_score: float) -> str:
    """Map a rolling AbhiHub Score to its access level via config thresholds."""
    try:
        levels = get_config("access_levels") or {}
        pairs = sorted(((float(v), k) for k, v in levels.items()), reverse=True)
        for threshold, name in pairs:
            if abhihub_score >= threshold:
                return name
    except Exception as e:
        logging.warning(f"[ScoringEngine] access-level lookup failed: {e}")
    return "explorer"


def recalculate_user_scores(user_id: Optional[str] = None, window_days: int = 30) -> Dict:
    """
    Rolling-window recalculation of contribution vs consumption per user.
    Python fallback for migration 023's SQL function (use either, not both,
    in the same nightly job). Updates profiles score columns.
    """
    client = _get_client()
    if not client:
        return {"success": False, "message": "No client"}
    try:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()

        query = client.table("contribution_logs").select("user_id,xp_awarded").gte("created_at", since)
        if user_id:
            query = query.eq("user_id", user_id)
        logs = query.execute().data or []

        contrib = {}
        for r in logs:
            uid = r.get("user_id")
            if not uid:
                continue
            xp = float(r.get("xp_awarded") or 0)
            c = contrib.setdefault(uid, {"contribution": 0.0})
            c["contribution"] += max(xp, 0)

        vq = client.table("document_views").select("user_id,document_id").gte("accessed_at", since)
        if user_id:
            vq = vq.eq("user_id", user_id)
        views = vq.execute().data or []
        consum = {}
        for r in views:
            uid = r.get("user_id")
            if not uid:
                continue
            consum.setdefault(uid, set()).add(r.get("document_id"))

        updated = 0
        user_ids = set(contrib) | set(consum)
        if user_id:  # single-user mode still needs the profile row
            user_ids = {user_id}
        for uid in user_ids:
            contribution = contrib.get(uid, {}).get("contribution", 0.0)
            consumption = float(len(consum.get(uid, set())))
            # Trust weighting: high-trust users keep full credit, low-trust
            # (new/unverified/penalized) accounts earn a fraction of their score.
            trust = get_trust_score(uid)
            # Score = trust-weighted contribution minus mild consumption pressure
            score = max(contribution * (0.5 + 0.5 * trust) - consumption * 0.05, 0.0)
            ccr = round(contribution / max(consumption, 1.0), 3)
            level = get_access_level(score)
            client.table("profiles").update({
                "abhihub_score": round(score, 2),
                "consumption_score": consumption,
                "ccr": ccr,
                "access_level": level,
            }).eq("id", uid).execute()
            updated += 1
        return {"success": True, "updated": updated}
    except Exception as e:
        logging.error(f"[ScoringEngine] recalc failed: {e}")
        return {"success": False, "message": str(e)}


def get_trust_score(user_id: str) -> float:
    """
    Trust score in [0, 1]: account age + verification + clean history.
    Used to weight contribution value and flag suspicious accounts.
    Components (configurable later): 0.4 * age_factor + 0.3 * verified
    + 0.3 * history_factor. Fails closed to 0.5 (neutral) on errors.
    """
    client = _get_client()
    if not client:
        return 0.5
    try:
        res = (
            client.table("profiles")
            .select("created_at, is_verified")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (res.data or [{}])[0]
        # Age factor: ramps 0→1 over first 90 days
        age_factor = 0.0
        created = row.get("created_at")
        if created:
            from datetime import datetime, timezone
            try:
                created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                days = (datetime.now(timezone.utc) - created_dt).days
                age_factor = min(days / 90.0, 1.0)
            except Exception:
                pass
        verified = 1.0 if row.get("is_verified") else 0.0
        # History factor: penalize spam penalties in contribution_logs
        penalty_res = (
            client.table("contribution_logs")
            .select("xp_awarded")
            .eq("user_id", user_id)
            .lt("xp_awarded", 0)
            .limit(50)
            .execute()
        )
        penalties = len(penalty_res.data or [])
        history_factor = max(1.0 - penalties * 0.2, 0.0)
        return round(0.4 * age_factor + 0.3 * verified + 0.3 * history_factor, 3)
    except Exception as e:
        logging.warning(f"[ScoringEngine] trust score failed, neutral 0.5: {e}")
        return 0.5


# Access-level feature gates (Phase 3). Values are per-day limits;
# 'early_access' features can be toggled later.
FEATURE_GATES = {
    "explorer":           {"daily_uploads": 3,  "daily_searches": 50,  "early_access": False},
    "member":             {"daily_uploads": 5,  "daily_searches": 100, "early_access": False},
    "contributor":        {"daily_uploads": 15, "daily_searches": 300, "early_access": True},
    "power_contributor":  {"daily_uploads": 40, "daily_searches": 1000, "early_access": True},
    "community_leader":   {"daily_uploads": 100, "daily_searches": 5000, "early_access": True},
}


def get_feature_gate(user_id: Optional[str] = None) -> Dict:
    """Feature limits for the user's access level. Anonymous = explorer tier."""
    try:
        if not user_id:
            return dict(FEATURE_GATES["explorer"], level="explorer")
        client = _get_client()
        res = (
            client.table("profiles")
            .select("access_level")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        level = (res.data or [{}])[0].get("access_level") or "explorer"
        gate = dict(FEATURE_GATES.get(level, FEATURE_GATES["explorer"]))
        gate["level"] = level
        return gate
    except Exception as e:
        logging.warning(f"[ScoringEngine] feature gate failed, defaulting: {e}")
        return dict(FEATURE_GATES["explorer"], level="explorer")


def get_access_progress(user_id: Optional[str] = None) -> Dict:
    """Current level, next level, and progress toward it (for UI badges)."""
    try:
        if not user_id:
            return {"level": "explorer", "score": 0, "next_level": "member",
                    "next_threshold": 50, "progress": 0.0}
        client = _get_client()
        res = (
            client.table("profiles")
            .select("access_level, abhihub_score")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (res.data or [{}])[0]
        level = row.get("access_level") or "explorer"
        score = float(row.get("abhihub_score") or 0)
        levels = get_config("access_levels") or {}
        ordered = sorted(((k, float(v)) for k, v in levels.items()), key=lambda x: x[1])
        current_idx = max((i for i, (k, _) in enumerate(ordered) if k == level), default=0)
        if current_idx + 1 < len(ordered):
            next_key, next_thr = ordered[current_idx + 1]
            prev_thr = ordered[current_idx][1]
            span = max(next_thr - prev_thr, 1.0)
            progress = round(min((score - prev_thr) / span, 1.0), 3)
            return {"level": level, "score": round(score, 1), "next_level": next_key,
                    "next_threshold": next_thr, "progress": max(progress, 0.0)}
        return {"level": level, "score": round(score, 1), "next_level": None,
                "next_threshold": None, "progress": 1.0}
    except Exception as e:
        logging.warning(f"[ScoringEngine] access progress failed: {e}")
        return {"level": "explorer", "score": 0, "next_level": "member",
                "next_threshold": 50, "progress": 0.0}


def check_upload_quota(user_id: str) -> Dict:
    """True if the user is under their daily upload limit."""
    gate = get_feature_gate(user_id)
    client = _get_client()
    if not client:
        return {"allowed": True, "remaining": None}
    try:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        res = (
            client.table("contribution_logs")
            .select("id")
            .eq("user_id", user_id)
            .eq("action_type", "upload_document")
            .gte("created_at", since)
            .limit(gate["daily_uploads"] + 1)
            .execute()
        )
        used = len(res.data or [])
        remaining = max(gate["daily_uploads"] - used, 0)
        return {"allowed": used < gate["daily_uploads"],
                "remaining": remaining, "limit": gate["daily_uploads"]}
    except Exception as e:
        logging.warning(f"[ScoringEngine] upload quota check failed (allow): {e}")
        return {"allowed": True, "remaining": None}


def get_ad_decision(user_id: Optional[str] = None) -> Dict:
    """
    Server-side ad decision for the current user, from their access level.
    Returns {'show_ads': bool, 'density': str}. Anonymous users get default
    (show, high) — never manipulate ad rendering beyond frequency reduction.
    """
    default_levels = {"explorer": "high", "member": "medium", "contributor": "low",
                      "power_contributor": "very_low", "community_leader": "minimal"}
    density_map = get_config("ad_density") or default_levels
    try:
        if not user_id:
            return {"show_ads": True, "density": "high", "level": None}
        client = _get_client()
        res = (
            client.table("profiles")
            .select("access_level")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        level = (res.data or [{}])[0].get("access_level") or "explorer"
        density = density_map.get(level, "high")
        # 'minimal' still shows occasional ads; only a future explicit opt-out
        # (e.g. premium tier) would set show_ads False.
        return {"show_ads": True, "density": density, "level": level}
    except Exception as e:
        logging.warning(f"[ScoringEngine] ad decision failed, defaulting: {e}")
        return {"show_ads": True, "density": "high", "level": None}


def process_event(user_id: str, event_type: str, entity_id: Optional[str] = None,
                  entity_type: str = "document", actor_is_owner: bool = False,
                  description: str = "") -> Dict:
    """
    Score one activity event. Returns {'success', 'scored': bool, ...}.

    Anti-abuse baseline: self-actions on own content earn nothing.
    Views must pass unique-view dedupe before scoring.
    """
    try:
        if actor_is_owner:
            return {"success": True, "scored": False,
                    "reason": "self-action not scored"}

        pts = get_points()
        point_map = {
            "resource_viewed": pts.get("view", 0),
            "resource_liked": pts.get("like", 0),
            "resource_bookmarked": pts.get("bookmark", 0),
            "resource_created": pts.get("publish", 0),
            "comment_created": pts.get("comment", 0),
        }
        if event_type not in point_map:
            return {"success": False, "message": f"unknown event {event_type}"}

        if event_type == "resource_viewed" and entity_id:
            if not is_unique_view(user_id, entity_id):
                return {"success": True, "scored": False,
                        "reason": "duplicate view within window"}

        if not _rate_limit_ok(user_id, event_type):
            return {"success": True, "scored": False,
                    "reason": "rate limit exceeded"}

        base = float(point_map[event_type])
        if base <= 0:
            return {"success": True, "scored": False}

        from methods.supabase_helper import award_contribution_xp
        result = award_contribution_xp(
            user_id=user_id,
            action_type=event_type,
            entity_id=entity_id,
            entity_type=entity_type,
            description=description or f"{event_type} scored",
            base_xp=base,
        )
        return {"success": bool(result.get("success")),
                "scored": bool(result.get("success")),
                "xp_gained": result.get("xp_gained"),
                "new_score": result.get("new_score")}
    except Exception as e:
        logging.error(f"[ScoringEngine] process_event({event_type}) failed: {e}")
        return {"success": False, "message": str(e)}
