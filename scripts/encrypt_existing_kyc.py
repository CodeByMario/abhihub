"""
scripts/encrypt_existing_kyc.py
One-time database maintenance script to encrypt existing plaintext PAN,
Account Number, and UPI ID fields in user_kyc_details using Fernet.
"""

import os
import sys
import logging

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from methods.supabase_helper import init_supabase_admin, init_supabase
from services.kyc_crypto_service import encrypt_kyc_value

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("encrypt_kyc")


def migrate_kyc_encryption():
    client = init_supabase_admin() or init_supabase()
    if not client:
        log.error("Failed to connect to Supabase database.")
        sys.exit(1)

    log.info("Fetching existing records from user_kyc_details...")
    res = client.table("user_kyc_details").select("id, pan_number, account_number, upi_id").execute()
    rows = res.data or []
    log.info(f"Found {len(rows)} KYC records to inspect.")

    updated_count = 0
    for row in rows:
        row_id = row.get("id")
        pan = row.get("pan_number")
        acc = row.get("account_number")
        upi = row.get("upi_id")

        updates = {}
        if pan and not pan.startswith("gAAAAA"):
            updates["pan_number"] = encrypt_kyc_value(pan)
        if acc and not acc.startswith("gAAAAA"):
            updates["account_number"] = encrypt_kyc_value(acc)
        if upi and not upi.startswith("gAAAAA"):
            updates["upi_id"] = encrypt_kyc_value(upi)

        if updates:
            try:
                client.table("user_kyc_details").update(updates).eq("id", row_id).execute()
                updated_count += 1
            except Exception as e:
                log.error(f"Failed updating record {row_id}: {e}")

    log.info(f"Migration completed. Successfully encrypted {updated_count} record(s).")


if __name__ == "__main__":
    migrate_kyc_encryption()
