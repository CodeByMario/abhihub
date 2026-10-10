"""
Safe Payment Transaction Store.
Provides resilient local storage + Supabase sync without crashing if schema table is missing.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

_DATA_DIR = os.path.dirname(__file__)
TRANSACTIONS_FILE = os.path.join(_DATA_DIR, 'payment_transactions.json')


def save_transaction_record(order_id: str, record: Dict[str, Any]):
    """Persists transaction to local JSON and attempts sync to Supabase without raising errors."""
    if not order_id:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    record_with_time = {**record, 'order_id': order_id, 'updated_at': now_iso}

    # 1. Local JSON file persistence
    try:
        data = {}
        if os.path.exists(TRANSACTIONS_FILE):
            try:
                with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[order_id] = {**data.get(order_id, {}), **record_with_time}
        with open(TRANSACTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.warning(f"[save_transaction_record] Local file warning: {e}")

    # 2. Supabase sync attempt (silent catch for PGRST205 missing table)
    try:
        from data.db import get_client
        supabase = get_client()
        if supabase:
            check = supabase.table('credit_transactions').select('id').eq('order_id', order_id).limit(1).execute()
            if check.data:
                supabase.table('credit_transactions').update(record).eq('order_id', order_id).execute()
            else:
                supabase.table('credit_transactions').insert({**record, 'order_id': order_id}).execute()
    except Exception as e:
        # Expected if credit_transactions table is not in database yet
        logging.debug(f"[save_transaction_record] Supabase credit_transactions note: {e}")


def get_transaction_record(order_id: str) -> Dict[str, Any]:
    """Retrieves transaction record by order_id."""
    if not order_id:
        return {}
    try:
        if os.path.exists(TRANSACTIONS_FILE):
            with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if order_id in data:
                    return data[order_id]
    except Exception:
        pass

    try:
        from data.db import get_client
        supabase = get_client()
        if supabase:
            res = supabase.table('credit_transactions').select('*').eq('order_id', order_id).limit(1).execute()
            if res.data:
                return res.data[0]
    except Exception:
        pass
    return {}


def is_order_completed(order_id: str) -> bool:
    """Checks if order was already completed/verified (idempotency check)."""
    rec = get_transaction_record(order_id)
    return rec.get('status') in ['completed', 'verified']


def get_user_transactions(user_id: str = '', limit: int = 50) -> list:
    """Returns sorted list of recent transactions for a given user."""
    results = {}

    # 1. From local store
    try:
        if os.path.exists(TRANSACTIONS_FILE):
            with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for oid, tx in data.items():
                    if user_id and tx.get('user_id') == user_id:
                        results[oid] = tx
                    elif not user_id:
                        results[oid] = tx
    except Exception as e:
        logging.warning(f"[get_user_transactions] Error reading local file: {e}")

    # 2. From Supabase (if available)
    if user_id:
        try:
            from data.db import get_client
            supabase = get_client()
            if supabase:
                res = supabase.table('credit_transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
                for row in (res.data or []):
                    oid = row.get('order_id')
                    if oid:
                        results[oid] = {**results.get(oid, {}), **row}
        except Exception:
            pass

    tx_list = list(results.values())
    tx_list.sort(key=lambda x: x.get('updated_at') or x.get('created_at') or '', reverse=True)
    return tx_list[:limit]
