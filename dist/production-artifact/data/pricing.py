"""
Document Pricing and Access Validation Helper.
Centralized logic for extracting pricing metadata and checking user access.
"""

import os
import json
import logging
from flask import session


def extract_document_pricing(document):
    """Safely extract pricing metadata from document dict, prioritizing relational columns with JSON fallback."""
    if not isinstance(document, dict):
        return {}
    # Priority 1: Direct relational columns from Phase 2
    if document.get('is_paid') is not None or document.get('price') is not None:
        try:
            p = float(document.get('price', 0) or 0)
        except (ValueError, TypeError):
            p = 0.0
        if bool(document.get('is_paid')) and p > 0:
            return {
                'is_paid': True,
                'price': p,
                'seller_id': document.get('seller_id') or document.get('uploader_id'),
                'coupon_code': document.get('coupon_code', ''),
                'coupon_discount': document.get('coupon_discount', 0)
            }

    # Priority 2: Structured 'pricing' dictionary
    if isinstance(document.get('pricing'), dict):
        return document['pricing']

    # Priority 3: Fallback parsing from JSON string in description
    desc_raw = document.get('description')
    if isinstance(desc_raw, dict):
        return desc_raw.get('pricing', {})
    if isinstance(desc_raw, str):
        trimmed = desc_raw.strip()
        if trimmed.startswith('{') and trimmed.endswith('}'):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict) and isinstance(parsed.get('pricing'), dict):
                    return parsed['pricing']
            except Exception:
                pass
    return {}


def has_document_access(user_id, doc_id, document=None):
    """Check if user has full access to a document (free, owner, admin, or purchased)."""
    if not document:
        from methods.supabase_helper import get_document_by_id_rich
        doc_res = get_document_by_id_rich(doc_id)
        if not doc_res.get('success'):
            return False
        document = doc_res.get('data', {})

    pricing = extract_document_pricing(document)
    is_paid = bool(pricing.get('is_paid')) and float(pricing.get('price', 0)) > 0

    # If document is not paid, it's public for everyone
    if not is_paid:
        return True

    # Check 1: Admin (session is_admin or role == 'admin')
    user = session.get('user', {})
    user_role = (user.get('role') or user.get('user_metadata', {}).get('role') or '').lower()
    if session.get('is_admin') or user_role == 'admin':
        return True

    # Check 2: Owner / Uploader / Seller
    u_uid = str(user_id or user.get('uid') or user.get('id') or '').strip()
    u_email = str(user.get('email') or '').strip().lower()
    seller_id = str(pricing.get('seller_id') or '').strip()
    uploader_id = str(document.get('uploader_id') or '').strip()
    uploader_email = str(document.get('uploader_email') or '').strip().lower()

    if u_uid and (u_uid == seller_id or u_uid == uploader_id):
        return True
    if u_email and uploader_email and u_email == uploader_email:
        return True

    # Check 3: Session instant unlock (unlocked in current session after purchase)
    purchased_docs = []
    try:
        purchased_docs = session.get('purchased_documents', []) or []
    except Exception:
        pass
    if not purchased_docs:
        try:
            import app as app_mod
            purchased_docs = getattr(app_mod, 'session', {}).get('purchased_documents', []) or []
        except Exception:
            pass
    if doc_id in purchased_docs:
        return True

    # Check 4: Purchased (Transactions record in local store or Supabase)
    if u_uid or u_email:
        try:
            from data.transactions import TRANSACTIONS_FILE
            if os.path.exists(TRANSACTIONS_FILE):
                with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                    all_tx = json.load(f)
                    for tx in all_tx.values():
                        if tx.get('status') in ['completed', 'verified']:
                            tx_uid = str(tx.get('user_id') or '')
                            tx_notes = str(tx.get('admin_notes') or '') + ' ' + str(tx.get('purpose') or '')
                            if (not tx_uid or tx_uid == u_uid) and doc_id in tx_notes:
                                return True
        except Exception:
            pass

        try:
            from data.db import get_client
            supabase = get_client()
            if supabase:
                res = supabase.table('credit_transactions').select('id, status').eq('user_id', u_uid).ilike('admin_notes', f'%{doc_id}%').execute()
                if res.data and any(t.get('status') in ['submitted', 'verified', 'completed'] for t in res.data):
                    return True
        except Exception:
            pass

    return False


QUOTA_PER_UPLOAD = 19


def _get_quota():
    """Return the current quota dict from session, synced with backend, processing monthly resets.
    Caches the Supabase response at L1 for 60s to reduce DB load."""
    from datetime import datetime
    from cache_manager import get_cache
    from data.db import get_client
    cache = get_cache()
    supabase = get_client()

    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return {'credits': 19, 'total_views': 0}

    if cache and hasattr(cache, 'l1'):
        cached_quota = cache.l1.get(f"user:quota:{user_id}")
        if cached_quota and cached_quota[0] is not None:
            return cached_quota[0]

    from methods.domain_tier_service import classify_email
    user_email = session.get('user', {}).get('email', '')
    tier_info = classify_email(user_email)
    default_quota = tier_info['starting_views']

    db_quota = default_quota
    _default_month = datetime.utcnow().strftime('%Y-%m')
    last_reset = _default_month

    if supabase:
        try:
            res = supabase.table('profiles').select('paper_quota_remaining, last_quota_reset').eq('id', user_id).execute()
            if res.data:
                db_quota = res.data[0].get('paper_quota_remaining')
                if db_quota is None:
                    db_quota = default_quota
                last_reset = res.data[0].get('last_quota_reset') or _default_month

            current_month = datetime.utcnow().strftime('%Y-%m')
            if last_reset != current_month:
                db_quota = default_quota
                last_reset = current_month
                supabase.table('profiles').update({
                    'paper_quota_remaining': db_quota,
                    'last_quota_reset': last_reset
                }).eq('id', user_id).execute()
        except Exception as e:
            logging.debug(f"[QUOTA] DB fetch note: {e}")

    q = {'credits': db_quota, 'total_views': session.get('paper_quota', {}).get('total_views', 0)}
    session['paper_quota'] = q
    session.modified = True
    return q


def log_credit_transaction(user_id, amount, tx_type, reason):
    """Record credit transaction for ledger tracking via unified payment engine."""
    if not user_id:
        return
    try:
        from methods.payment_engine import engine
        if tx_type == 'earn' or amount > 0:
            engine.credit_views(user_id, abs(amount), reason=reason, source='system')
        else:
            engine.deduct_view(user_id, doc_name=reason)
    except Exception as e:
        logging.warning(f"[CREDIT-LOG] Could not log credit tx: {e}")


def _grant_upload_credits():
    """Award +3 paper quota views and +1 reputation score to the user after a successful upload."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return

    from data.db import get_client
    from cache_manager import get_cache
    from methods.payment_engine import engine

    cache = get_cache()
    supabase = get_client()

    new_quota = engine.grant_reward(user_id, 3, reason='upload_reward')

    if supabase:
        try:
            res = supabase.table('profiles').select('reputation_score').eq('id', user_id).limit(1).execute()
            if res.data:
                curr_rep = res.data[0].get('reputation_score') or 0
                supabase.table('profiles').update({'reputation_score': curr_rep + 1}).eq('id', user_id).execute()
        except Exception as e:
            logging.warning(f"[GRANT_UPLOAD] Error updating reputation: {e}")

    q = session.get('paper_quota', {})
    if isinstance(q, dict):
        q['credits'] = new_quota
        session['paper_quota'] = q
        session.modified = True

    if cache and hasattr(cache, 'l1'):
        cache.l1.delete(f"user:quota:{user_id}")


def _consume_credit(doc_name="Document"):
    """
    Deduct 1 credit for a paper open.
    Returns True if the open is allowed, False if quota is exhausted.
    Admins always pass.
    """
    from routes.auth import ADMIN_EMAILS
    from cache_manager import get_cache
    from methods.payment_engine import engine

    cache = get_cache()
    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    user_id = user.get('uid')

    if user_email in ADMIN_EMAILS:
        return True

    q = _get_quota()
    if q.get('credits', 0) <= 0:
        return False

    allowed, new_credits = engine.deduct_view(user_id, doc_name=doc_name)
    if not allowed:
        return False

    q['credits'] = new_credits
    q['total_views'] = q.get('total_views', 0) + 1
    session['paper_quota'] = q
    session.modified = True

    if cache and hasattr(cache, 'l1'):
        cache.l1.delete(f"user:quota:{user_id}")

    return True

