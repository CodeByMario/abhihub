import os
import hmac
import logging
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional

_razorpay_client = None

def _get_config():
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not key_id or not key_secret:
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
            key_id = os.getenv("RAZORPAY_KEY_ID", "")
            key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
            webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        except Exception:
            pass
    return {
        "key_id": key_id,
        "key_secret": key_secret,
        "webhook_secret": webhook_secret
    }

def get_client():
    global _razorpay_client
    cfg = _get_config()
    if not cfg["key_id"] or not cfg["key_secret"]:
        raise ValueError("Razorpay API credentials not configured in environment (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)")
    expected_auth = (cfg["key_id"], cfg["key_secret"])
    if _razorpay_client is None or getattr(_razorpay_client, '_auth_creds', None) != expected_auth:
        import razorpay
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        _razorpay_client = razorpay.Client(auth=expected_auth)
        _razorpay_client._auth_creds = expected_auth
        _razorpay_client.session.timeout = 10.0
        adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504]))
        _razorpay_client.session.mount('https://', adapter)
    return _razorpay_client


def to_paise(amount_inr: float) -> int:
    d = Decimal(str(amount_inr))
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))

def create_order(amount_inr: float, receipt: str = '', receipt_id: str = '', notes: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    client = get_client()
    paise = to_paise(amount_inr)
    if paise < 100:
        raise ValueError("Amount must be at least 100 paise (₹1.00)")
    rcpt = (receipt or receipt_id or '')[:40]
    data = {
        "amount": paise,
        "currency": "INR",
        "receipt": rcpt,
        "payment_capture": 1,
        "notes": notes or {}
    }
    return client.order.create(data=data)


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    cfg = _get_config()
    secret = cfg.get("key_secret", "")
    if not secret:
        logging.warning("[Razorpay] Cannot verify signature: RAZORPAY_KEY_SECRET not configured")
        return False
    try:
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        generated_signature = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(generated_signature, razorpay_signature)
    except Exception as e:
        logging.warning(f"[Razorpay] Signature verification error: {e}")
        return False


def verify_webhook_signature(payload_body: str, signature: str) -> bool:
    client = get_client()
    cfg = _get_config()
    try:
        client.utility.verify_webhook_signature(payload_body, signature, cfg["webhook_secret"])
        return True
    except Exception as e:
        logging.warning(f"[Razorpay] Webhook signature invalid: {e}")
        return False

def hash_signature(razorpay_signature: str) -> str:
    """Return SHA-256 hash of signature for DB storage. Never store raw signature."""
    return hashlib.sha256(razorpay_signature.encode()).hexdigest()
