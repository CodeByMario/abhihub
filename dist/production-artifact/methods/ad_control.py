"""Persistent admin controls for page- and user-level ad overrides."""
import logging
from typing import Optional

from methods.supabase_helper import init_supabase, init_supabase_admin

log = logging.getLogger(__name__)


def _client():
    return init_supabase_admin() or init_supabase()


def get_ad_override(
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    page_path: Optional[str] = None,
):
    """Return the highest-priority active override, or None if unset."""
    try:
        from cache_manager import get_cache
        cache = get_cache()
        c_key = f"ad_override:{user_id or '*'}:{email or '*'}:{page_path or '*'}"
        cached_val, _ = cache.l1.get(c_key)
        if cached_val is not None:
            return None if cached_val == '__NONE__' else cached_val
    except Exception:
        cache = None
        c_key = None

    client = _client()
    if not client:
        return None

    keys = []
    if user_id:
        keys.append(("user", str(user_id).strip()))
    if email:
        keys.append(("user", str(email).strip().lower()))
    if page_path:
        keys.append(("page", str(page_path).strip()))
    keys.append(("global", "*"))

    try:
        for scope_type, scope_key in keys:
            result = client.table("ad_overrides").select(
                "scope_type, scope_key, enabled, note, updated_at"
            ).eq("scope_type", scope_type).eq("scope_key", scope_key).limit(1).execute()
            if result.data:
                val = result.data[0]
                if cache and c_key:
                    cache.l1.set(c_key, val, ttl=300)
                return val
    except Exception as exc:
        log.warning("[Ads] override lookup unavailable: %s", exc)

    if cache and c_key:
        cache.l1.set(c_key, '__NONE__', ttl=120)
    return None


def apply_ad_override(decision: dict, override):
    if not override:
        return decision
    enabled = bool(override.get("enabled"))
    return {
        **decision,
        "show_ads": enabled,
        "density": decision.get("density") if enabled else "off",
        "override": {
            "scope_type": override.get("scope_type"),
            "scope_key": override.get("scope_key"),
            "enabled": enabled,
            "note": override.get("note"),
        },
    }
