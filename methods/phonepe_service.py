import os
import json
import time
import base64
import hashlib
import requests
from typing import Dict, Any

# PhonePe Gateway Service supporting:
# 1. New V2 Standard Checkout (OAuth client_id, client_secret)
# 2. Legacy V1 Checksum (Salt Key)

_v2_token_cache = {"token": None, "expires_at": 0}


def _get_config() -> Dict[str, Any]:
    client_id = os.getenv('PHONEPE_CLIENT_ID', '').strip()
    client_secret = os.getenv('PHONEPE_CLIENT_SECRET', '').strip()
    client_version = os.getenv('PHONEPE_CLIENT_VERSION', '1').strip()
    merchant_id = os.getenv('PHONEPE_MERCHANT_ID', client_id or 'PGTESTPAYUAT86').strip()
    salt_key = os.getenv('PHONEPE_SALT_KEY', '96434309-7796-489d-8924-ab56988a6076').strip()
    salt_index = os.getenv('PHONEPE_SALT_INDEX', '1').strip()
    env = os.getenv('PHONEPE_ENV', 'SANDBOX').upper().strip()

    is_v2 = bool(client_id and client_secret)

    if env == "PRODUCTION":
        auth_url = "https://api.phonepe.com/apis/identity-manager/v1/oauth/token"
        pg_base_url = "https://api.phonepe.com/apis/pg"
        v1_base_url = "https://api.phonepe.com/apis/hermes"
    else:
        auth_url = "https://api-preprod.phonepe.com/apis/pg-sandbox/v1/oauth/token"
        pg_base_url = "https://api-preprod.phonepe.com/apis/pg-sandbox"
        v1_base_url = "https://api-preprod.phonepe.com/apis/pg-sandbox"

    return {
        "is_v2": is_v2,
        "client_id": client_id,
        "client_secret": client_secret,
        "client_version": client_version,
        "merchant_id": merchant_id,
        "salt_key": salt_key,
        "salt_index": salt_index,
        "env": env,
        "auth_url": auth_url,
        "pg_base_url": pg_base_url,
        "v1_base_url": v1_base_url,
    }


def _get_v2_auth_header(cfg: Dict[str, Any]) -> str:
    global _v2_token_cache
    now = time.time()
    if _v2_token_cache["token"] and now < _v2_token_cache["expires_at"] - 60:
        return _v2_token_cache["token"]

    payload = {
        "client_id": cfg["client_id"],
        "client_version": cfg["client_version"],
        "client_secret": cfg["client_secret"],
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(cfg["auth_url"], data=payload, headers=headers, timeout=15)
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ValueError(data.get("message") or data.get("error_description") or "PhonePe OAuth failed")

    token_type = data.get("token_type", "O-Bearer")
    auth_header = f"{token_type} {token}"
    expires_in = int(data.get("expires_in", 3600))
    _v2_token_cache["token"] = auth_header
    _v2_token_cache["expires_at"] = now + expires_in
    return auth_header


def calculate_checksum(payload_str: str, endpoint: str) -> str:
    """Calculates legacy SHA256 checksum for v1."""
    cfg = _get_config()
    data_to_hash = f"{payload_str}{endpoint}{cfg['salt_key']}"
    sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
    return f"{sha256_hash}###{cfg['salt_index']}"


def initiate_phonepe_payment(
    order_id: str,
    amount_inr: float,
    user_id: str,
    redirect_url: str,
    callback_url: str,
    mobile: str = "9999999999"
) -> Dict[str, Any]:
    """Initiates PhonePe payment via V2 Checkout or V1 fallback."""
    cfg = _get_config()
    amount_paise = int(round(float(amount_inr) * 100))
    if amount_paise <= 0:
        return {"success": False, "error": "Invalid amount"}

    # --- PhonePe V2 Standard Checkout (OAuth) ---
    if cfg["is_v2"]:
        try:
            auth_header = _get_v2_auth_header(cfg)
            payload = {
                "merchantOrderId": order_id,
                "amount": amount_paise,
                "expireAfter": 1200,
                "paymentFlow": {
                    "type": "PG_CHECKOUT",
                    "message": "Payment for Document Access",
                    "merchantUrls": {
                        "redirectUrl": redirect_url
                    }
                }
            }
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            resp = requests.post(
                f"{cfg['pg_base_url']}/checkout/v2/pay",
                json=payload,
                headers=headers,
                timeout=15
            )
            data = resp.json()
            redirect_to = data.get("redirectUrl")
            if resp.status_code in (200, 201) and redirect_to:
                return {"success": True, "payment_url": redirect_to, "data": data}
            return {
                "success": False,
                "error": data.get("message") or "Failed to initiate PhonePe payment",
                "raw": data
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- PhonePe V1 Checksum Fallback ---
    payload = {
        "merchantId": cfg["merchant_id"],
        "merchantTransactionId": order_id,
        "merchantUserId": user_id or f"U{order_id[:8]}",
        "amount": amount_paise,
        "redirectUrl": redirect_url,
        "redirectMode": "POST",
        "callbackUrl": callback_url,
        "mobileNumber": mobile,
        "paymentInstrument": {"type": "PAY_PAGE"}
    }
    base64_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
    checksum = calculate_checksum(base64_payload, "/pg/v1/pay")
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": checksum,
        "Accept": "application/json"
    }

    try:
        resp = requests.post(
            f"{cfg['v1_base_url']}/pg/v1/pay",
            json={"request": base64_payload},
            headers=headers,
            timeout=15
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("success"):
            payment_url = (
                data.get("data", {})
                .get("instrumentResponse", {})
                .get("redirectInfo", {})
                .get("url")
            )
            return {"success": True, "payment_url": payment_url, "data": data}
        return {
            "success": False,
            "error": data.get("message") or "Failed to initiate PhonePe payment",
            "raw": data
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_phonepe_status(merchant_transaction_id: str) -> Dict[str, Any]:
    """Checks payment status via PhonePe V2 or V1."""
    cfg = _get_config()

    # --- PhonePe V2 Status ---
    if cfg["is_v2"]:
        try:
            auth_header = _get_v2_auth_header(cfg)
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            resp = requests.get(
                f"{cfg['pg_base_url']}/checkout/v2/order/{merchant_transaction_id}/status",
                headers=headers,
                timeout=15
            )
            data = resp.json()
            state = data.get("state")
            is_paid = (state == "COMPLETED")
            return {
                "success": True,
                "is_paid": is_paid,
                "code": state,
                "message": data.get("message") or f"Payment state: {state}",
                "data": data
            }
        except Exception as e:
            return {"success": False, "is_paid": False, "error": str(e)}

    # --- PhonePe V1 Status ---
    endpoint = f"/pg/v1/status/{cfg['merchant_id']}/{merchant_transaction_id}"
    checksum = calculate_checksum("", endpoint)
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": checksum,
        "X-MERCHANT-ID": cfg["merchant_id"],
        "Accept": "application/json"
    }

    try:
        resp = requests.get(f"{cfg['v1_base_url']}{endpoint}", headers=headers, timeout=15)
        data = resp.json()
        code = data.get("code")
        is_paid = (code == "PAYMENT_SUCCESS")
        return {
            "success": True,
            "is_paid": is_paid,
            "code": code,
            "message": data.get("message"),
            "data": data.get("data", {})
        }
    except Exception as e:
        return {"success": False, "is_paid": False, "error": str(e)}


def validate_order_id(order_id: str) -> bool:
    """Validates order ID conforms to PhonePe requirements (alphanumeric, -, _, max 63 chars)."""
    if not order_id or len(order_id) > 63:
        return False
    import re
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', order_id))


def parse_phonepe_callback_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Safely decodes and extracts merchantOrderId and status from PhonePe webhook callback."""
    if not raw_data:
        return {}
    if 'response' in raw_data:
        try:
            decoded = base64.b64decode(raw_data['response']).decode('utf-8')
            return json.loads(decoded)
        except Exception:
            return {}
    return raw_data
