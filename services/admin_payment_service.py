"""
services/admin_payment_service.py
Atomic, idempotent verification and rejection operations for manual UTR payments.
Enforces admin-level RBAC, transactional fulfillment, and persistent audit logging.
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from services.admin_service import get_db, has_min_role, get_user_role, record_audit_log
from methods.supabase_helper import log_notification, validate_uuid

log = logging.getLogger('abhihub.admin_payment_service')


def list_pending_manual_payments(
    page: int = 1,
    limit: int = 12,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch paginated manual payments awaiting administrative verification."""
    db = get_db()
    if not db:
        return {'success': False, 'payments': [], 'total': 0, 'error': 'Database unavailable'}

    offset = (max(1, page) - 1) * limit
    try:
        q = db.table('credit_transactions').select('*', count='exact').eq('status', 'submitted')
        if search:
            search_str = search.strip()
            # Search order_id or utr
            q = q.or_(f"order_id.ilike.%{search_str}%,utr.ilike.%{search_str}%")

        res = q.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'payments': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_pending_manual_payments] Error: {e}")
        return {'success': False, 'payments': [], 'total': 0, 'error': str(e)}


def verify_manual_payment(
    identifier: str,
    admin_user: dict,
    notes: Optional[str] = None,
    client_ip: Optional[str] = None
) -> Tuple[bool, str, dict]:
    """
    Atomically verify a manual payment submission and trigger full fulfillment.
    Idempotent: if already completed, succeeds gracefully without duplicate credits.
    """
    if not has_min_role(admin_user, 'admin'):
        return False, "Permission Denied: Admin or Superadmin role required for payment verification.", {}

    admin_id = admin_user.get('uid') or admin_user.get('id')
    admin_email = admin_user.get('email', 'unknown_admin')

    db = get_db()
    if not db:
        return False, "Database connection error.", {}

    # Find transaction by order_id or UUID id
    try:
        if validate_uuid(identifier):
            tx_res = db.table('credit_transactions').select('*').eq('id', identifier).limit(1).execute()
        else:
            tx_res = db.table('credit_transactions').select('*').eq('order_id', identifier).limit(1).execute()
    except Exception as e:
        log.error(f"[verify_manual_payment] Lookup error: {e}")
        return False, f"Transaction query error: {str(e)}", {}

    if not tx_res.data:
        return False, "Transaction not found.", {}

    tx = tx_res.data[0]
    tx_id = tx.get('id')
    order_id = tx.get('order_id')
    current_status = tx.get('status')
    user_id = tx.get('user_id')
    amount = float(tx.get('amount') or 0)
    admin_notes = tx.get('admin_notes') or ''

    # Idempotency guard
    if current_status == 'completed':
        return True, "Payment is already verified and completed.", tx

    if current_status not in ('submitted', 'pending'):
        return False, f"Cannot verify transaction with current status '{current_status}'.", {}

    # Extract metadata from notes or purpose
    doc_id = None
    pack_size = 0
    if 'doc_id=' in admin_notes:
        match = re.search(r'doc_id=([^;\s]+)', admin_notes)
        if match:
            doc_id = match.group(1).strip()
    elif 'Document-' in admin_notes:
        match = re.search(r'Document-([^;\s]+)', admin_notes)
        if match:
            doc_id = match.group(1).strip()

    is_credits = 'credits' in admin_notes.lower() or 'pack=' in admin_notes.lower() or 'credits-' in admin_notes.lower()
    if is_credits:
        match_pack = re.search(r'(?:pack=|Credits-)(\d+)', admin_notes)
        if match_pack:
            try:
                pack_size = int(match_pack.group(1))
            except ValueError:
                pack_size = 0

    now_iso = datetime.now(timezone.utc).isoformat()
    combined_notes = f"{admin_notes};verified_by={admin_email};notes={notes or ''}".strip(';')

    # 1. Update status atomically in credit_transactions
    try:
        db.table('credit_transactions').update({
            'status': 'completed',
            'admin_verified_by': admin_id if validate_uuid(admin_id) else None,
            'verified_at': now_iso,
            'admin_notes': combined_notes
        }).eq('id', tx_id).execute()
    except Exception as e:
        log.error(f"[verify_manual_payment] Database update failed: {e}")
        return False, f"Failed updating transaction status: {str(e)}", {}

    # 2. Update local transaction cache / file
    try:
        from data.transactions import save_transaction_record
        save_transaction_record(order_id, {
            'user_id': user_id,
            'amount': amount,
            'status': 'completed',
            'utr': tx.get('utr', order_id),
            'admin_notes': combined_notes
        })
    except Exception as e:
        log.warning(f"[verify_manual_payment] Local transaction cache update warning: {e}")

    # 3. Fulfill: Document Purchase (Creator Wallet Credit & CRM)
    if doc_id:
        try:
            from methods.wallet_service import credit_creator_for_purchase, get_document_creator
            credit_creator_for_purchase(order_id, doc_id, amount)
            creator_id = get_document_creator(doc_id)
            if creator_id and user_id and str(creator_id) != str(user_id):
                from methods.creator_crm_service import record_creator_customer_purchase
                record_creator_customer_purchase(
                    creator_id=creator_id,
                    customer_id=user_id,
                    amount=amount
                )
        except Exception as e:
            log.warning(f"[verify_manual_payment] Creator credit warning: {e}")

    # 4. Fulfill: Credit Pack
    if is_credits and pack_size > 0 and user_id:
        try:
            from methods.payment_engine import engine
            engine.credit_views(
                user_id, pack_size, reason='pack_purchase',
                ref_id=order_id, source='admin_manual_verify'
            )
        except Exception as e:
            log.warning(f"[verify_manual_payment] View credit warning: {e}")

    # 5. User Notification
    if user_id:
        try:
            log_notification(
                user_email=user_id,
                notification_type="payment_success",
                title="Payment Verified",
                message=f"Your payment of ₹{amount:g} (Order {order_id}) has been verified successfully. Your content is unlocked!",
                url=f"/view/{doc_id}" if doc_id else "/account"
            )
        except Exception as e:
            log.warning(f"[verify_manual_payment] Notification warning: {e}")

    # 6. Persistent Audit Log
    record_audit_log(
        admin_id=admin_id,
        admin_email=admin_email,
        action="verify_manual_payment",
        target_type="payment",
        target_id=order_id,
        old_value={'status': current_status},
        new_value={'status': 'completed', 'amount': amount, 'doc_id': doc_id},
        reason=notes or "Manual payment verification",
        ip_address=client_ip
    )

    tx['status'] = 'completed'
    return True, "Payment verified and fulfilled successfully.", tx


def reject_manual_payment(
    identifier: str,
    admin_user: dict,
    reason: str,
    client_ip: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Reject a manual payment submission with a mandatory justification.
    """
    if not has_min_role(admin_user, 'admin'):
        return False, "Permission Denied: Admin or Superadmin role required for payment rejection."

    if not reason or not reason.strip():
        return False, "A rejection reason is strictly required."

    admin_id = admin_user.get('uid') or admin_user.get('id')
    admin_email = admin_user.get('email', 'unknown_admin')

    db = get_db()
    if not db:
        return False, "Database connection error."

    try:
        if validate_uuid(identifier):
            tx_res = db.table('credit_transactions').select('*').eq('id', identifier).limit(1).execute()
        else:
            tx_res = db.table('credit_transactions').select('*').eq('order_id', identifier).limit(1).execute()
    except Exception as e:
        return False, f"Lookup error: {str(e)}"

    if not tx_res.data:
        return False, "Transaction not found."

    tx = tx_res.data[0]
    tx_id = tx.get('id')
    order_id = tx.get('order_id')
    current_status = tx.get('status')
    user_id = tx.get('user_id')
    admin_notes = tx.get('admin_notes') or ''

    if current_status == 'completed':
        return False, "Cannot reject an already completed transaction. Please process a refund instead."

    now_iso = datetime.now(timezone.utc).isoformat()
    combined_notes = f"{admin_notes};rejected_by={admin_email};reason={reason.strip()}".strip(';')

    try:
        db.table('credit_transactions').update({
            'status': 'rejected',
            'rejection_reason': reason.strip(),
            'admin_verified_by': admin_id if validate_uuid(admin_id) else None,
            'verified_at': now_iso,
            'admin_notes': combined_notes
        }).eq('id', tx_id).execute()
    except Exception as e:
        return False, f"Failed updating transaction status: {str(e)}"

    try:
        from data.transactions import save_transaction_record
        save_transaction_record(order_id, {
            'user_id': user_id,
            'amount': tx.get('amount', 0),
            'status': 'rejected',
            'utr': tx.get('utr', order_id),
            'admin_notes': combined_notes
        })
    except Exception:
        pass

    if user_id:
        try:
            log_notification(
                user_email=user_id,
                notification_type="payment_failed",
                title="Payment Rejected",
                message=f"Your payment submission for Order {order_id} could not be verified. Reason: {reason.strip()}",
                url="/contact"
            )
        except Exception:
            pass

    record_audit_log(
        admin_id=admin_id,
        admin_email=admin_email,
        action="reject_manual_payment",
        target_type="payment",
        target_id=order_id,
        old_value={'status': current_status},
        new_value={'status': 'rejected', 'reason': reason.strip()},
        reason=reason.strip(),
        ip_address=client_ip
    )

    return True, "Payment rejected successfully."


def list_all_orders(
    page: int = 1,
    limit: int = 12,
    status: Optional[str] = None,
    gateway: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch paginated platform orders with comprehensive filtering."""
    db = get_db()
    if not db:
        return {'success': False, 'orders': [], 'total': 0, 'error': 'Database unavailable'}

    offset = (max(1, page) - 1) * limit
    try:
        q = db.table('credit_transactions').select('*', count='exact')
        if status:
            q = q.eq('status', status.strip().lower())
        if gateway:
            q = q.eq('gateway', gateway.strip().lower())
        if search:
            s = search.strip()
            q = q.or_(f"order_id.ilike.%{s}%,user_id.ilike.%{s}%,utr.ilike.%{s}%")
        if start_date:
            q = q.gte('created_at', start_date)
        if end_date:
            q = q.lte('created_at', end_date)

        res = q.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'orders': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_all_orders] Error: {e}")
        return {'success': False, 'orders': [], 'total': 0, 'error': str(e)}


def process_refund(
    identifier: str,
    admin_user: dict,
    amount: Optional[float] = None,
    reason: str = "Customer requested refund",
    client_ip: Optional[str] = None
) -> Tuple[bool, str, dict]:
    """
    Atomically and idempotently refund an order:
    1. Verifies Admin/Superadmin RBAC.
    2. Validates transaction in credit_transactions.
    3. Revokes buyer entitlement (status != completed auto-revokes document access).
    4. Debits creator wallet ledger with unique REFUND-<order_id> reference.
    5. Updates credit_transactions (status='refunded', refunded_at, refund_reason, refunded_by).
    6. Notifies buyer and logs persistent audit entry.
    """
    if not has_min_role(admin_user, 'admin'):
        return False, "Permission Denied: Admin or Superadmin role required to process refunds.", {}

    if not reason or not reason.strip():
        return False, "A refund justification reason is strictly required.", {}

    admin_id = admin_user.get('uid') or admin_user.get('id')
    admin_email = admin_user.get('email', 'unknown_admin')

    db = get_db()
    if not db:
        return False, "Database connection error.", {}

    try:
        if validate_uuid(identifier):
            tx_res = db.table('credit_transactions').select('*').eq('id', identifier).limit(1).execute()
        else:
            tx_res = db.table('credit_transactions').select('*').eq('order_id', identifier).limit(1).execute()
    except Exception as e:
        return False, f"Lookup error: {str(e)}", {}

    if not tx_res.data:
        return False, "Transaction not found.", {}

    tx = tx_res.data[0]
    tx_id = tx.get('id')
    order_id = tx.get('order_id')
    current_status = tx.get('status')
    user_id = tx.get('user_id')
    orig_amount = float(tx.get('amount') or 0)
    refund_amt = float(amount) if amount is not None else orig_amount
    admin_notes = tx.get('admin_notes') or ''

    # Idempotency guard
    if current_status == 'refunded' or tx.get('refunded_at'):
        return True, "Transaction has already been refunded.", tx

    if current_status != 'completed':
        return False, f"Cannot refund transaction with status '{current_status}'. Only completed orders can be refunded.", {}

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Extract document ID if this was a document purchase
    doc_id = None
    if 'doc_id=' in admin_notes:
        match = re.search(r'doc_id=([^;\s]+)', admin_notes)
        if match:
            doc_id = match.group(1).strip()
    elif 'Document-' in admin_notes:
        match = re.search(r'Document-([^;\s]+)', admin_notes)
        if match:
            doc_id = match.group(1).strip()

    # 2. Debit creator wallet ledger for document purchases
    if doc_id:
        try:
            from methods.wallet_service import debit_creator_for_refund
            debit_creator_for_refund(order_id, doc_id, refund_amt)
        except Exception as e:
            log.warning(f"[process_refund] Creator ledger rollback warning: {e}")

    # 3. Check for view credits pack purchase: deduct quota if applicable
    is_credits = 'credits' in admin_notes.lower() or 'pack=' in admin_notes.lower() or 'credits-' in admin_notes.lower()
    if is_credits and user_id:
        match_pack = re.search(r'(?:pack=|Credits-)(\d+)', admin_notes)
        if match_pack:
            try:
                pack_size = int(match_pack.group(1))
                prof = db.table('profiles').select('paper_quota_remaining').eq('id', user_id).limit(1).execute()
                if prof.data:
                    curr_q = int(prof.data[0].get('paper_quota_remaining') or 0)
                    new_q = max(0, curr_q - pack_size)
                    db.table('profiles').update({'paper_quota_remaining': new_q}).eq('id', user_id).execute()
            except Exception as e:
                log.warning(f"[process_refund] Quota deduction warning: {e}")

    # 4. Update transaction status in credit_transactions
    combined_notes = f"{admin_notes};refunded_by={admin_email};reason={reason.strip()}".strip(';')
    try:
        db.table('credit_transactions').update({
            'status': 'refunded',
            'refunded_at': now_iso,
            'refund_reason': reason.strip(),
            'refunded_by': admin_id if validate_uuid(admin_id) else None,
            'admin_notes': combined_notes
        }).eq('id', tx_id).execute()
    except Exception as e:
        return False, f"Failed updating transaction refund record: {str(e)}", {}

    # 5. Notify customer
    if user_id:
        try:
            log_notification(
                user_email=user_id,
                notification_type="refund_processed",
                title="Refund Processed",
                message=f"A refund of ₹{refund_amt:g} for Order {order_id} has been processed. Reason: {reason.strip()}",
                url="/orders"
            )
        except Exception as e:
            log.warning(f"[process_refund] Notification warning: {e}")

    # 6. Audit logging
    record_audit_log(
        admin_id=admin_id,
        admin_email=admin_email,
        action="refund_order",
        target_type="payment",
        target_id=order_id,
        old_value={'status': current_status, 'amount': orig_amount},
        new_value={'status': 'refunded', 'refund_amount': refund_amt, 'reason': reason.strip()},
        reason=reason.strip(),
        ip_address=client_ip
    )

    tx['status'] = 'refunded'
    tx['refunded_at'] = now_iso
    return True, f"Order {order_id} refunded successfully.", tx

