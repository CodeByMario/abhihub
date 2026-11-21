"""
methods/ad_manager.py — Adsterra Banner Ad Engine & Intensity Governor
======================================================================
Strict Hard Caps (Admin cannot override):
1. FEATURE_ADS flag defaults to OFF (commercial use on Vercel Hobby is prohibited).
2. Max 3 ads on screen.
3. NEVER for Premium / VIP users.
4. NEVER when queue status is 'ready' or 'exhausted'.
5. ONLY on the waiting screen.
6. NO popunder/social bar/push scripts (only 300x250, 728x90, 468x60, 320x50, native).
7. Each ad runs in its own sandboxed iframe WITHOUT allow-same-origin.
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from methods.redis_client import get_redis_client, cache_get_json, cache_set_json
from methods.load_governor import get_user_tier

logger = logging.getLogger("ad.manager")

# Hard Caps
MAX_ADS_PER_SCREEN = 3
ALLOWED_SLOTS = {'300x250', '728x90', '468x60', '320x50', 'native'}

DEFAULT_CONFIG = {
    'level': 2,           # 0=Off, 1=Light, 2=Standard (default), 3=Boosted
    'new_user_level': 1,  # Cap for user's first 3 visits
    'auto_guard': True,   # Automatically throttle ads if abandon rate > 35%
    'guard_abandon_pct': 35
}


def is_ads_feature_enabled() -> bool:
    """FEATURE_ADS defaults to False (Vercel Hobby compliance)."""
    val = os.getenv("FEATURE_ADS", "false").lower()
    return val in ("1", "true", "yes", "on")


def get_ad_config() -> Dict[str, Any]:
    """Retrieve global ad configuration from Redis cfg:ads (cached in process/Redis)."""
    cfg = cache_get_json("cfg:ads")
    if not cfg or not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def set_ad_config(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Admin updates ad configuration with strict validation and bounds clamping."""
    current = get_ad_config()

    # Validate and clamp level (0 to 3)
    if 'level' in new_cfg:
        lvl = int(new_cfg['level'])
        current['level'] = max(0, min(3, lvl))

    if 'new_user_level' in new_cfg:
        nu_lvl = int(new_cfg['new_user_level'])
        current['new_user_level'] = max(0, min(3, nu_lvl))

    if 'auto_guard' in new_cfg:
        current['auto_guard'] = bool(new_cfg['auto_guard'])

    if 'guard_abandon_pct' in new_cfg:
        pct = int(new_cfg['guard_abandon_pct'])
        current['guard_abandon_pct'] = max(10, min(80, pct))

    # Clear throttle when admin updates config
    try:
        r = get_redis_client()
        r.delete("ads:throttled")
    except Exception:
        pass

    cache_set_json("cfg:ads", current, ttl_seconds=86400 * 30)
    return current


def check_and_apply_auto_guard() -> bool:
    """
    Evaluates auto-guard: if waited >= 50 and abandon% > threshold,
    sets ads:throttled for 6h which lowers effective ad level by 1.
    """
    try:
        r = get_redis_client()
        from datetime import datetime, timezone
        d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        waited = int(r.get(f"metrics:wait:wait_started:{d}") or 0)
        abandoned = int(r.get(f"metrics:wait:abandoned:{d}") or 0)

        cfg = get_ad_config()
        if not cfg.get('auto_guard'):
            return False

        threshold = cfg.get('guard_abandon_pct', 35)
        if waited >= 50 and (abandoned / waited * 100.0) > threshold:
            r.setex("ads:throttled", 21600, "1")  # 6 hours
            return True
    except Exception as e:
        logger.debug("[AD_GUARD] Check skipped: %s", e)
    return False


def get_effective_level(user: Any = None) -> int:
    """Calculate effective ad level after user cap, throttle, and feature flag."""
    if not is_ads_feature_enabled():
        return 0

    tier = get_user_tier(user)
    if tier == 'premium':
        return 0  # Hard cap: Never for premium

    cfg = get_ad_config()
    level = cfg.get('level', 2)

    # Check auto-guard throttle
    r = get_redis_client()
    if r.get("ads:throttled"):
        level = max(0, level - 1)

    return level


def resolve_adaptive_banner(viewport_width: int) -> str:
    """Adaptive banner = 728x90 (>=800px), 468x60 (>=520px), else 320x50."""
    if viewport_width >= 800:
        return '728x90'
    elif viewport_width >= 520:
        return '468x60'
    return '320x50'


def resolve_waiting_screen_ads(
    user: Any,
    queue_status: str,
    viewport_width: int = 360,
    eta_s: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Resolves exact ad slots for waiting screen respecting all hard caps.
    Returns None if no ads should be rendered.
    """
    # Hard cap 1: Only on waiting screen
    if queue_status != 'waiting':
        return None

    # Hard cap 2: Never for premium/VIP
    if get_user_tier(user) == 'premium':
        return None

    # Hard cap 3: FEATURE_ADS check
    level = get_effective_level(user)
    if level == 0:
        return None

    banner = resolve_adaptive_banner(viewport_width)

    slots: List[str] = []
    delay_s = 3
    min_eta_s = 5

    if level == 1:
        # Light: 1 small adaptive banner, delay 8s, min ETA 10s
        slots = [banner]
        delay_s = 8
        min_eta_s = 10
    elif level == 2:
        # Standard: 300x250 + adaptive banner, delay 3s, min ETA 5s
        slots = ['300x250', banner]
        delay_s = 3
        min_eta_s = 5
    elif level == 3:
        # Boosted: 300x250 + adaptive banner + native, delay 2s, min ETA 15s
        slots = ['300x250', banner, 'native']
        delay_s = 2
        min_eta_s = 15

    # If eta_s is less than min_eta_s, do not show ads to prevent flashing
    if eta_s < min_eta_s:
        return None

    # Hard cap: Clamp to MAX_ADS_PER_SCREEN (3)
    slots = slots[:MAX_ADS_PER_SCREEN]

    return {
        'level': level,
        'slots': slots,
        'delay_s': delay_s,
        'min_eta_s': min_eta_s,
        'sponsor_url': 'https://araplhn.org/4/6fb79dd9f780432692f5cdf35bfb4dcf'
    }
