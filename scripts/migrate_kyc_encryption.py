"""
scripts/migrate_kyc_encryption.py
One-time script to encrypt existing plaintext PAN and UPI / Bank details in Supabase KYC records.
Uses cryptography.fernet.Fernet with KYC_ENCRYPTION_KEY from environment variables only.
Safe & idempotent: checks if values are already Fernet encrypted before touching.
"""

import os
import sys
import logging
from cryptography.fernet import Fernet, InvalidToken

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('kyc_encryption_migration')

# Ensure parent path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from methods.supabase_helper import init_supabase_admin, init_supabase

def get_fernet() -> Fernet:
    key = os.getenv('KYC_ENCRYPTION_KEY')
    if not key:
        raise ValueError("Environment variable 'KYC_ENCRYPTION_KEY' is missing. Please set a valid Fernet key.")
    return Fernet(key.encode() if isinstance(key, str) else key)

def is_fernet_token(val: str, f: Fernet) -> bool:
    if not val or not isinstance(val, str):
        return False
    try:
        f.decrypt(val.encode())
        return True
    except InvalidToken:
        return False
    except Exception:
        return False

def run_kyc_migration():
    client = init_supabase_admin() or init_supabase()
    if not client:
        log.error("Could not initialize Supabase client.")
        return False

    f = get_fernet()
    log.info("Fetching KYC records from abhihub.kyc / creator_kyc...")
    
    # Try kyc table first
    table_name = 'kyc'
    try:
        res = client.table(table_name).select('*').execute()
    except Exception:
        table_name = 'creator_kyc'
        res = client.table(table_name).select('*').execute()

    records = res.data or []
    log.info(f"Found {len(records)} records in '{table_name}'.")

    migrated_count = 0
    for r in records:
        rec_id = r.get('id')
        pan = r.get('pan_number') or r.get('pan')
        upi = r.get('upi_id')
        bank_acc = r.get('bank_account_number') or r.get('account_number')
        
        updates = {}
        if pan and not is_fernet_token(pan, f):
            updates['pan_number' if 'pan_number' in r else 'pan'] = f.encrypt(pan.strip().encode()).decode()
        if upi and not is_fernet_token(upi, f):
            updates['upi_id'] = f.encrypt(upi.strip().encode()).decode()
        if bank_acc and not is_fernet_token(bank_acc, f):
            updates['bank_account_number' if 'bank_account_number' in r else 'account_number'] = f.encrypt(bank_acc.strip().encode()).decode()

        if updates:
            client.table(table_name).update(updates).eq('id', rec_id).execute()
            migrated_count += 1

    log.info(f"Successfully encrypted {migrated_count} KYC records.")
    return True

if __name__ == '__main__':
    run_kyc_migration()
