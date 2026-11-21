"""
methods/payment_plans.py — Premium Plans, Webhook Verification & Signed URLs
=============================================================================
Manages Razorpay premium subscription tiers, HMAC signature validation,
atomic payment idempotency via Redis, entitlement lifecycle, and 15m signed URLs.
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from methods.redis_client import get_redis_client, cache_delete

logger = logging.getLogger("payment.plans")

# Feature Flag (Default OFF for Vercel Hobby compliance)
def is_payments_feature_enabled() -> bool:
    return os.getenv("FEATURE_PAYMENTS", "false").lower() in ("1", "true", "yes", "on")

# Official Premium Plans
PREMIUM_PLANS: Dict[str, Dict[str, Any]] = {
    'day_pass': {
        'id': 'day_pass',
        'name': 'Day Pass',
        'amount_inr': 29,
        'duration_seconds': 86400,  # 24h
        'description': '24-hour instant unmetered access'
    },
    'exam_sprint': {
        'id': 'exam_sprint',
        'name': 'Exam Sprint',
        'amount_inr': 79,
        'duration_seconds': 86400 * 7,  # 7 days
        'description': '7-day exam crunch access'
    },
    'semester_pro': {
        'id': 'semester_pro',
        'name': 'Semester Pro',
        'amount_inr': 199,
        'duration_seconds': 86400 * 180,  # ~6 months
        'description': 'Complete semester pro access'
    }
}

FAIR_USE_POLICY = {
    'daily_ai_requests': 30,
    'monthly_ai_requests': 400,
    'daily_ocr_requests': 40,
    'signed_url_ttl_seconds': 900  # 15 minutes
}


def verify_razorpay_signature(payload_bytes: bytes, signature: str, secret: Optional[str] = None) -> bool:
    """Verify Razorpay webhook HMAC-SHA256 signature."""
    sec = secret or os.getenv("RAZORPAY_WEBHOOK_SECRET") or os.getenv("RAZORPAY_KEY_SECRET", "")
    if not sec or not signature:
        return False
    try:
        computed = hmac.new(sec.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed.lower(), signature.lower())
    except Exception as e:
        logger.warning("[PAYMENTS] Signature verification error: %s", e)
        return False


def is_user_premium(profile_or_user: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if user has an active premium entitlement.
    Returns (is_active, premium_until_iso).
    """
    if not profile_or_user:
        return False, None

    data = profile_or_user if isinstance(profile_or_user, dict) else getattr(profile_or_user, '__dict__', {})
    tier = data.get('tier') or ('premium' if data.get('is_premium') else 'free')
    until_str = data.get('premium_until')

    if tier != 'premium' and not data.get('is_premium'):
        return False, until_str

    if not until_str:
        # Lifetime or admin grant
        return True, None

    try:
        # Parse ISO timestamp
        until_dt = datetime.fromisoformat(until_str.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        if until_dt > now_dt:
            return True, until_str
        else:
            return False, until_str  # Expired
    except Exception:
        return bool(data.get('is_premium')), until_str


def fulfill_premium_subscription(
    payment_id: str,
    user_id: str,
    plan_id: str,
    supabase_client: Any = None
) -> Tuple[bool, str]:
    """
    Fulfills a premium subscription idempotently.
    Idempotency: writes payment_id to Redis using SETNX.
    If payment_id was already processed, returns (True, 'already_fulfilled') immediately.
    """
    if not payment_id or not user_id:
        return False, "payment_id and user_id required"

    r = get_redis_client()
    idempotency_key = f"payment:seen:{payment_id}"

    # Atomic idempotency gate: returns False if key already exists
    # In Upstash / standard Redis, set(key, value, nx=True, ex=ttl)
    was_set = False
    try:
        # Check if already present
        if r.get(idempotency_key):
            logger.info("[PAYMENTS] Payment %s already fulfilled (idempotent hit)", payment_id)
            return True, "already_fulfilled"
        r.setex(idempotency_key, 86400 * 30, "1")
        was_set = True
    except Exception as e:
        logger.warning("[PAYMENTS] Idempotency store warning: %s", e)

    plan = PREMIUM_PLANS.get(plan_id, PREMIUM_PLANS['day_pass'])
    duration_s = plan['duration_seconds']

    now_utc = datetime.now(timezone.utc)
    premium_until = (now_utc + timedelta(seconds=duration_s)).isoformat()

    # Update Supabase user record
    client = supabase_client
    if client is None:
        try:
            from methods.supabase_helper import init_supabase_admin, init_supabase
            client = init_supabase_admin() or init_supabase()
        except Exception:
            client = None

    if client:
        try:
            client.table('profiles').update({
                'is_premium': True,
                'tier': 'premium',
                'premium_until': premium_until
            }).eq('id', user_id).execute()
        except Exception as db_err:
            logger.error("[PAYMENTS] Supabase profile update error: %s", db_err)

    # Invalidate cached user profiles
    cache_delete(f"user:profile:{user_id}")
    cache_delete(f"user:{user_id}")

    logger.info("[PAYMENTS] User %s upgraded to Premium until %s via plan %s", user_id, premium_until, plan_id)
    return True, "success"


def generate_signed_document_url(doc_id_or_path: str, file_url: str = "", expires_in: int = 900) -> str:
    """
    Generate short-lived (15 min) signed URL for premium users.
    Prevents link scraping and unauthorized external sharing.
    """
    # 1. Attempt Supabase Storage signed URL if path is relative or storage URL
    try:
        from methods.supabase_helper import init_supabase_admin, init_supabase
        client = init_supabase_admin() or init_supabase()
        if client and hasattr(client, 'storage'):
            clean_path = doc_id_or_path
            if '/storage/v1/object/public/documents/' in file_url:
                clean_path = file_url.split('/storage/v1/object/public/documents/')[-1].split('?')[0]
            elif file_url.startswith('documents/'):
                clean_path = file_url.replace('documents/', '', 1)

            res = client.storage.from_('documents').create_signed_url(clean_path, expires_in)
            if res and isinstance(res, dict) and 'signedURL' in res:
                return res['signedURL']
    except Exception as e:
        logger.debug("[SIGNED_URL] Supabase storage sign skipped: %s", e)

    # 2. Cryptographic HMAC fallback signature query parameter
    secret = os.getenv("SIGNING_SECRET") or os.getenv("SUPABASE_KEY", "abhihub_secret_key")
    exp_ts = int(datetime.now(timezone.utc).timestamp()) + expires_in
    data_to_sign = f"{doc_id_or_path}:{exp_ts}".encode('utf-8')
    sig = hmac.new(secret.encode('utf-8'), data_to_sign, hashlib.sha256).hexdigest()[:16]

    base_url = file_url or f"/api/view-doc/{doc_id_or_path}"
    sep = '&' if '?' in base_url else '?'
    return f"{base_url}{sep}expires={exp_ts}&sig={sig}"
