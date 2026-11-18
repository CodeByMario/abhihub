"""
services/kyc_crypto_service.py
At-rest encryption and masking for sensitive KYC data (PAN, Bank Account, UPI).
Uses cryptography.fernet with key from KYC_ENCRYPTION_KEY environment variable.
"""

import os
import base64
import hashlib
import logging
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger('abhihub.kyc_crypto')

_fernet_instance = None


def get_fernet() -> Optional[Fernet]:
    """
    Retrieve or initialize the Fernet cipher instance.
    Uses KYC_ENCRYPTION_KEY environment variable.
    If unconfigured in development/test, derives a repeatable dev key from SECRET_KEY.
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key = os.environ.get('KYC_ENCRYPTION_KEY')
    if not key:
        secret = os.environ.get('SECRET_KEY', 'abhihub-dev-secret-kyc-key-2026')
        derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())
        _fernet_instance = Fernet(derived)
        return _fernet_instance

    try:
        key_bytes = key.strip().encode('utf-8')
        if len(key_bytes) == 44 and key_bytes.endswith(b'='):
            _fernet_instance = Fernet(key_bytes)
        else:
            derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
            _fernet_instance = Fernet(derived)
        return _fernet_instance
    except Exception as e:
        log.error(f"[get_fernet] Invalid KYC_ENCRYPTION_KEY: {e}")
        return None


def encrypt_kyc_value(val: Optional[str]) -> Optional[str]:
    """Encrypt a sensitive string using Fernet. Idempotent on already-encrypted strings."""
    if not val or not str(val).strip():
        return val
    s = str(val).strip()
    if s.startswith('gAAAAA'):
        return s
    f = get_fernet()
    if not f:
        return s
    try:
        return f.encrypt(s.encode('utf-8')).decode('utf-8')
    except Exception as e:
        log.error(f"Failed encrypting KYC value: {e}")
        return s


def decrypt_kyc_value(val: Optional[str]) -> Optional[str]:
    """Decrypt a Fernet encrypted string. Returns as-is if plaintext."""
    if not val or not str(val).strip():
        return val
    s = str(val).strip()
    if not s.startswith('gAAAAA'):
        return s
    f = get_fernet()
    if not f:
        return s
    try:
        return f.decrypt(s.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        log.warning("Invalid token when decrypting KYC value, returning as-is")
        return s
    except Exception as e:
        log.error(f"Error decrypting KYC value: {e}")
        return s


def mask_pan(pan: Optional[str]) -> str:
    """Mask PAN to ABCDE****F."""
    if not pan:
        return "—"
    decrypted = decrypt_kyc_value(pan)
    clean = (decrypted or '').strip().upper()
    if len(clean) >= 10:
        return f"{clean[:5]}****{clean[-1]}"
    elif len(clean) >= 4:
        return f"{clean[:2]}****{clean[-2:]}"
    return "—"


def mask_account(acc: Optional[str]) -> str:
    """Mask Bank Account to ************1234."""
    if not acc:
        return "—"
    decrypted = decrypt_kyc_value(acc)
    clean = (decrypted or '').strip()
    if len(clean) >= 4:
        return f"{'*' * max(4, len(clean) - 4)}{clean[-4:]}"
    return "****"


def mask_upi(upi: Optional[str]) -> str:
    """Mask UPI ID to ab****@bank."""
    if not upi:
        return "—"
    decrypted = decrypt_kyc_value(upi)
    clean = (decrypted or '').strip()
    if '@' in clean:
        parts = clean.split('@', 1)
        handle = parts[0]
        vpa = parts[1]
        if len(handle) > 2:
            return f"{handle[:2]}{'*' * (len(handle)-2)}@{vpa}"
        return f"**@{vpa}"
    return "—"


def prepare_kyc_for_display(kyc_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project safe masked fields for normal admin viewing.
    Raw fields remain unexposed.
    """
    rec = dict(kyc_record or {})
    rec['masked_pan'] = mask_pan(rec.get('pan_number'))
    rec['masked_account'] = mask_account(rec.get('account_number'))
    rec['masked_upi'] = mask_upi(rec.get('upi_id'))

    # Remove sensitive plaintext fields from general payload
    rec['pan_number'] = rec['masked_pan']
    rec['account_number'] = rec['masked_account']
    rec['upi_id'] = rec['masked_upi']
    return rec
