"""
PaymentEngine — Unified Reward & Payment System for AbhiHub.

Single authority for ALL credit and INR wallet mutations:
  - Razorpay order creation and fulfillment
  - View credits (paper_quota) earn/spend
  - Creator wallet (INR) crediting and payouts
  - Auto-payout trigger (balance >= ₹10, KYC verified)
  - KYC submission and retrieval
  - Reward grants (referral, upload, admin, tea support)
  - Bank-style passbook generation

RULE: No other module may write to:
  wallet_ledger, creator_wallets, user_credit_ledger, paper_quota_remaining
  directly. All mutations go through this class.
"""

import re
import logging
import time
import secrets
from datetime import datetime, timezone
from typing import Optional

from methods.supabase_helper import init_supabase, init_supabase_admin

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
AUTO_PAYOUT_THRESHOLD = 10.0      # ₹ — auto-request payout above this
PAYOUT_SLA_DAYS = 7               # promised days to credit
DEFAULT_VIEW_QUOTA = 19           # new user starting credits


# ── Internal DB client ────────────────────────────────────────────────────────

def _db():
    client = init_supabase_admin()
    return client or init_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# PaymentEngine
# ═══════════════════════════════════════════════════════════════════════════════

class PaymentEngine:

    # ──────────────────────────────────────────────────────────────────────────
    # RAZORPAY
    # ──────────────────────────────────────────────────────────────────────────

    def create_order(self, amount_inr: float, user_id: str,
                     doc_id: str = '', pack: int = 0,
                     purpose: str = '') -> dict:
        """
        Creates a Razorpay order and saves a pending transaction record.
        Handles doc purchase, credit pack purchase, and generic amounts.
        """
        from methods.razorpay_service import create_order as rzp_create
        from data.transactions import save_transaction_record

        if amount_inr <= 0:
            return {'success': False, 'error': 'Amount must be greater than zero'}

        receipt_id = f"AH_{int(time.time())}_{secrets.token_hex(2).upper()}"[:40]
        notes = {
            'user_id': user_id or 'guest',
            'doc_id': doc_id or '',
            'purpose': purpose or (f"Document {doc_id}" if doc_id else "Payment"),
        }
        if pack:
            notes['pack'] = str(pack)

        try:
            order = rzp_create(amount_inr=amount_inr, receipt_id=receipt_id, notes=notes)
        except Exception as e:
            log.error(f"[ENGINE] Razorpay order creation failed: {e}")
            return {'success': False, 'error': str(e)}

        admin_notes_parts = []
        if doc_id:
            admin_notes_parts.append(f"doc_id={doc_id}")
        if pack:
            admin_notes_parts.append(f"purpose=Credits-{pack};pack={pack};views={pack}")
        if purpose:
            admin_notes_parts.append(f"purpose={purpose}")

        save_transaction_record(order['id'], {
            'user_id': user_id or None,
            'amount': amount_inr,
            'status': 'pending',
            'utr': order['id'],
            'doc_id': doc_id or None,
            'admin_notes': ';'.join(admin_notes_parts),
        })

        import os
        return {
            'success': True,
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order.get('currency', 'INR'),
            'key_id': os.getenv('RAZORPAY_KEY_ID', ''),
            'receipt': receipt_id,
        }

    def verify_and_fulfill(self, order_id: str, payment_id: str,
                            signature: str, user_id: str = '') -> dict:
        """
        Verifies Razorpay HMAC signature then calls fulfill_order().
        Returns redirect URL on success.
        """
        from methods.razorpay_service import verify_payment_signature, hash_signature
        from data.transactions import get_transaction_record, is_order_completed

        rec = get_transaction_record(order_id)
        doc_id = rec.get('doc_id', '') or ''
        if not doc_id:
            for part in (rec.get('admin_notes') or '').split(';'):
                if part.startswith('doc_id='):
                    doc_id = part.replace('doc_id=', '').strip()

        if is_order_completed(order_id):
            return {
                'success': True,
                'message': 'Already verified',
                'redirect_url': f"/payment/receipt?order_id={order_id}&status=success&doc_id={doc_id}&amount={rec.get('amount', 0)}"
            }

        if not verify_payment_signature(order_id, payment_id, signature):
            log.error(f"[ENGINE] Signature mismatch: order={order_id} pay={payment_id}")
            try:
                db = _db()
                if db:
                    db.table('payment_errors').insert({
                        'user_id': rec.get('user_id'),
                        'order_id': order_id,
                        'payment_id': payment_id,
                        'reason': 'signature_mismatch',
                        'created_at': _now(),
                    }).execute()
            except Exception:
                pass
            return {'success': False, 'error': 'Signature verification failed'}

        amount = float(rec.get('amount', 0))
        uid = user_id or rec.get('user_id', '')
        self.fulfill_order(order_id, amount, doc_id=doc_id, user_id=uid, source='razorpay_verify')

        try:
            db = _db()
            if db:
                db.table('credit_transactions').update({
                    'payment_id': payment_id,
                    'rzp_sig_hash': hash_signature(signature),
                    'captured_at': _now(),
                }).eq('order_id', order_id).execute()
        except Exception:
            pass

        return {
            'success': True,
            'message': 'Payment verified',
            'redirect_url': f"/payment/receipt?order_id={order_id}&status=success&doc_id={doc_id}&amount={amount}"
        }

    def fulfill_order(self, order_id: str, amount: float,
                      doc_id: str = '', user_id: str = '',
                      source: str = 'system') -> dict:
        """
        Central fulfillment dispatcher. Replaces fulfill_order_transaction().
        Handles: doc purchase, credit pack, tea/chai support.
        Called from both razorpay verify and webhook handler.
        """
        from data.transactions import save_transaction_record, get_transaction_record

        try:
            rec = get_transaction_record(order_id)
        except Exception:
            rec = {}

        admin_notes = rec.get('admin_notes', '') or ''
        is_credits = 'Credits-' in admin_notes or 'pack=' in admin_notes or 'credits' in admin_notes.lower()
        is_tea = (not doc_id and not is_credits and
                  ('Tea' in admin_notes or 'Chai' in admin_notes or 'supporter' in admin_notes.lower()))

        # Update transaction status
        save_transaction_record(order_id, {
            'user_id': user_id or None,
            'amount': amount,
            'status': 'completed',
            'utr': order_id,
            'admin_notes': f"{admin_notes};verified_via={source}".strip(';'),
        })

        # ── Credit pack ──────────────────────────────────────────────────────
        if is_credits and user_id:
            pack_size = 0
            for part in admin_notes.split(';'):
                if part.startswith('pack='):
                    try: pack_size = int(part.replace('pack=', '').strip())
                    except: pass
                elif part.startswith('purpose=Credits-'):
                    try: pack_size = int(part.replace('purpose=Credits-', '').split('-')[0].strip())
                    except: pass
            if pack_size <= 0 and amount > 0:
                pack_size = int(amount / 2)
            if pack_size > 0:
                self.credit_views(user_id, pack_size, 'pack_purchase', ref_id=order_id)

        # ── Document purchase → credit creator ──────────────────────────────
        elif doc_id:
            try:
                self.credit_creator(order_id, doc_id, amount)
            except Exception as e:
                log.error(f"[ENGINE] credit_creator failed: {e}")

        # ── Tea/Chai supporter ───────────────────────────────────────────────
        elif is_tea:
            try:
                from data.tea_supporters import add_tea_supporter
                s_name, s_msg = '', ''
                for part in admin_notes.split(';'):
                    if part.startswith('name='): s_name = part.replace('name=', '').strip()
                    if part.startswith('msg='): s_msg = part.replace('msg=', '').strip()
                add_tea_supporter(order_id, amount, s_name, s_msg)
            except Exception as e:
                log.warning(f"[ENGINE] add_tea_supporter failed: {e}")
            # Log to credit ledger so it appears in passbook as ₹ received
            if user_id:
                self._ledger_credit(user_id, int(amount), 'tea_support', ref_id=order_id)

        return {'success': True, 'order_id': order_id}

    # ──────────────────────────────────────────────────────────────────────────
    # VIEW CREDITS (paper_quota)
    # ──────────────────────────────────────────────────────────────────────────

    def credit_views(self, user_id: str, amount: int, reason: str,
                     ref_id: str = '', source: str = 'system') -> bool:
        """
        Add view credits to a user. Updates paper_quota_remaining and ledger.
        Replaces all log_credit_transaction('earn') call sites.
        """
        if not user_id or amount <= 0:
            return False
        try:
            db = _db()
            if not db:
                return False
            res = db.table('profiles').select('paper_quota_remaining, email').eq('id', user_id).limit(1).execute()
            curr = 0
            if res.data:
                val = res.data[0].get('paper_quota_remaining')
                if val is not None:
                    curr = int(val)
                else:
                    from methods.domain_tier_service import classify_email
                    curr = classify_email(res.data[0].get('email', ''))['starting_views']
            new_bal = curr + amount
            db.table('profiles').update({'paper_quota_remaining': new_bal}).eq('id', user_id).execute()
            self._ledger_credit(user_id, amount, reason, ref_id=ref_id, source=source, balance=new_bal)
            self._invalidate_quota_cache(user_id)
            log.info(f"[ENGINE] credit_views user={user_id} +{amount} reason={reason} bal={new_bal}")
            return True
        except Exception as e:
            log.error(f"[ENGINE] credit_views error: {e}")
            return False

    def deduct_view(self, user_id: str, doc_name: str = '') -> bool:
        """
        Deduct 1 view credit when user opens a document.
        Replaces log_credit_transaction(user_id, -1, 'spend', ...) call sites.
        """
        if not user_id:
            return False
        try:
            db = _db()
            if not db:
                return False
            res = db.table('profiles').select('paper_quota_remaining, email').eq('id', user_id).limit(1).execute()
            curr = 0
            if res.data:
                val = res.data[0].get('paper_quota_remaining')
                if val is not None:
                    curr = int(val)
                else:
                    from methods.domain_tier_service import classify_email
                    curr = classify_email(res.data[0].get('email', ''))['starting_views']
            if curr <= 0:
                return False
            new_bal = curr - 1
            db.table('profiles').update({'paper_quota_remaining': new_bal}).eq('id', user_id).execute()
            self._ledger_credit(user_id, -1, 'view_spend',
                                ref_id=doc_name[:80] if doc_name else None,
                                source='system', balance=new_bal)
            self._invalidate_quota_cache(user_id)
            return True
        except Exception as e:
            log.error(f"[ENGINE] deduct_view error: {e}")
            return False

    def get_view_balance(self, user_id: str) -> int:
        """Returns current paper_quota_remaining for user."""
        try:
            db = _db()
            if not db:
                return 0
            res = db.table('profiles').select('paper_quota_remaining').eq('id', user_id).limit(1).execute()
            if res.data:
                return int(res.data[0].get('paper_quota_remaining') or 0)
        except Exception as e:
            log.error(f"[ENGINE] get_view_balance error: {e}")
        return 0

    # ──────────────────────────────────────────────────────────────────────────
    # CREATOR WALLET (INR)
    # ──────────────────────────────────────────────────────────────────────────

    def credit_creator(self, order_id: str, doc_id: str, gross_amount: float) -> bool:
        """Credits creator's wallet with 30-day lock. Delegates to wallet_service."""
        from methods.wallet_service import credit_creator_for_purchase
        ok, msg = credit_creator_for_purchase(order_id, doc_id, gross_amount)
        if not ok:
            log.error(f"[ENGINE] credit_creator failed: {msg}")
        return ok

    def unlock_if_needed(self, creator_id: str) -> int:
        """
        Conditionally unlocks matured wallet entries.
        Replaces unconditional unlock_eligible_entries() on every GET.
        Only writes if there are locked entries past their unlock_at date.
        """
        from methods.wallet_service import unlock_eligible_entries
        try:
            db = _db()
            if not db:
                return 0
            count_res = db.table('wallet_ledger') \
                .select('id', count='exact') \
                .eq('creator_id', creator_id) \
                .eq('status', 'locked') \
                .lte('unlock_at', _now()) \
                .execute()
            count = count_res.count or 0
            if count > 0:
                return unlock_eligible_entries(creator_id)
            return 0
        except Exception as e:
            log.error(f"[ENGINE] unlock_if_needed error: {e}")
            return 0

    def get_creator_wallet(self, creator_id: str) -> dict:
        """Fetch creator wallet data. Uses unlock_if_needed (not unconditional)."""
        self.unlock_if_needed(creator_id)
        from methods.wallet_service import get_creator_wallet as _get
        return _get(creator_id)

    def request_payout(self, creator_id: str, amount: float,
                       payout_method: str, payout_details: dict) -> tuple:
        """Request a manual payout. Delegates to wallet_service."""
        from methods.wallet_service import request_withdrawal
        return request_withdrawal(creator_id, amount, payout_method, payout_details)

    def auto_request_payout(self, creator_id: str) -> bool:
        """
        Auto-trigger payout if:
          - KYC is verified
          - withdrawable balance >= AUTO_PAYOUT_THRESHOLD (₹10)
          - no existing pending/processing payout (idempotency guard)
        Called from the daily wallet_unlock_reconciler job (Job 5).
        """
        kyc = self.get_kyc(creator_id)
        if not kyc or not kyc.get('is_verified'):
            return False

        wallet_info = self.get_creator_wallet(creator_id)
        if not wallet_info.get('success'):
            return False

        withdrawable = float(wallet_info['wallet'].get('withdrawable_balance', 0))
        if withdrawable < AUTO_PAYOUT_THRESHOLD:
            return False

        # Idempotency guard — existing pending_check in request_withdrawal also covers this
        db = _db()
        if db:
            existing = db.table('creator_payout_requests') \
                .select('id') \
                .eq('creator_id', creator_id) \
                .in_('status', ['pending', 'processing']) \
                .limit(1) \
                .execute()
            if existing.data:
                return False

        method = kyc.get('preferred_method', 'upi')
        details = {
            'upi_id': kyc.get('upi_id'),
            'account_number': kyc.get('account_number'),
            'ifsc_code': kyc.get('ifsc_code'),
            'account_holder_name': kyc.get('full_name'),
            'pan_number': kyc.get('pan_number'),
        }

        from methods.wallet_service import request_withdrawal
        ok, result = request_withdrawal(creator_id, withdrawable, method, details)
        if ok:
            log.info(f"[ENGINE] Auto-payout triggered: creator={creator_id} amount=₹{withdrawable}")
            self._notify_auto_payout(creator_id, withdrawable)
        return ok

    # ──────────────────────────────────────────────────────────────────────────
    # PASSBOOK
    # ──────────────────────────────────────────────────────────────────────────

    def get_passbook(self, user_id: str, page: int = 1, limit: int = 20) -> dict:
        """
        Returns a bank-style unified transaction history combining:
          - wallet_ledger (INR credits/debits/payouts)
          - user_credit_ledger (view credit earn/spend)
        With balance summary and pagination.
        """
        db = _db()
        if not db:
            return {'success': False, 'error': 'DB unavailable'}

        try:
            # Balance summary
            wallet_info = self.get_creator_wallet(user_id)
            wallet = wallet_info.get('wallet', {}) if wallet_info.get('success') else {}
            view_bal = self.get_view_balance(user_id)
            kyc = self.get_kyc(user_id)

            pending_payout = None
            try:
                pp = db.table('creator_payout_requests') \
                    .select('id, amount, status, created_at') \
                    .eq('creator_id', user_id) \
                    .in_('status', ['pending', 'processing']) \
                    .limit(1).execute()
                if pp.data:
                    pending_payout = pp.data[0]
            except Exception:
                pass

            # Fetch wallet ledger entries (INR)
            offset = (page - 1) * limit
            ledger_res = db.table('wallet_ledger') \
                .select('*') \
                .eq('creator_id', user_id) \
                .order('created_at', desc=True) \
                .range(offset, offset + limit - 1) \
                .execute()

            # Fetch view credit ledger entries
            credit_res = db.table('user_credit_ledger') \
                .select('*') \
                .eq('user_id', user_id) \
                .order('created_at', desc=True) \
                .range(offset, offset + limit - 1) \
                .execute()

            entries = []

            for row in (ledger_res.data or []):
                tx_type = row.get('type', 'credit')
                is_debit = tx_type in ('payout', 'debit')
                entries.append({
                    'date': row.get('created_at'),
                    'description': _inr_description(row),
                    'type': 'debit' if is_debit else 'credit',
                    'currency': 'INR',
                    'amount': float(row.get('amount', 0)) * (-1 if is_debit else 1),
                    'status': row.get('status'),
                    'unlocks_on': row.get('unlock_at') if row.get('status') == 'locked' else None,
                    'ref_id': row.get('order_id'),
                    'balance_after': None,  # INR running balance computed server-side if needed
                })

            for row in (credit_res.data or []):
                delta = int(row.get('delta', 0))
                entries.append({
                    'date': row.get('created_at'),
                    'description': _credit_description(row),
                    'type': 'debit' if delta < 0 else 'credit',
                    'currency': 'VIEWS',
                    'amount': delta,
                    'status': 'completed',
                    'unlocks_on': None,
                    'ref_id': row.get('ref_id'),
                    'balance_after': row.get('balance'),
                })

            # Sort merged entries by date desc
            entries.sort(key=lambda x: x['date'] or '', reverse=True)
            entries = entries[:limit]

            return {
                'success': True,
                'balance_summary': {
                    'total_earned': float(wallet.get('total_withdrawn', 0)) + float(wallet.get('withdrawable_balance', 0)),
                    'pending_balance': float(wallet.get('pending_balance', 0)),
                    'withdrawable': float(wallet.get('withdrawable_balance', 0)),
                    'total_withdrawn': float(wallet.get('total_withdrawn', 0)),
                    'view_credits': view_bal,
                    'kyc_complete': bool(kyc and kyc.get('is_verified')),
                    'kyc_status': _kyc_status_label(kyc),
                    'pending_payout': pending_payout,
                    'can_withdraw': wallet.get('can_withdraw', False),
                    'min_withdrawal': float(wallet.get('min_withdrawal', AUTO_PAYOUT_THRESHOLD)),
                },
                'entries': entries,
                'page': page,
                'limit': limit,
            }
        except Exception as e:
            log.error(f"[ENGINE] get_passbook error: {e}")
            return {'success': False, 'error': str(e)}

    # ──────────────────────────────────────────────────────────────────────────
    # KYC
    # ──────────────────────────────────────────────────────────────────────────

    def submit_kyc(self, user_id: str, data: dict) -> tuple:
        """
        Validates and saves KYC details. Returns (bool, message).
        PAN, UPI, and bank details are validated server-side.
        is_verified is always set False on submit — admin must verify.
        """
        if not user_id:
            return False, 'User not authenticated'

        full_name = str(data.get('full_name', '')).strip()
        if not full_name:
            return False, 'Full name is required'

        pan = str(data.get('pan_number', '')).upper().strip()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            return False, 'Invalid PAN format (e.g. ABCDE1234F)'

        method = str(data.get('preferred_method', 'upi')).lower()
        if method not in ('upi', 'bank'):
            return False, "Payout method must be 'upi' or 'bank'"

        upi_id, account_number, ifsc_code, bank_name = None, None, None, None

        if method == 'upi':
            upi_id = str(data.get('upi_id', '')).strip()
            if not re.match(r'^[\w.\-_]{2,256}@[\w]{2,64}$', upi_id):
                return False, 'Invalid UPI ID format (e.g. yourname@okhdfcbank)'

        elif method == 'bank':
            account_number = str(data.get('account_number', '')).strip()
            ifsc_code = str(data.get('ifsc_code', '')).upper().strip()
            bank_name = str(data.get('bank_name', '')).strip()
            if not re.match(r'^\d{9,18}$', account_number):
                return False, 'Invalid account number (9–18 digits)'
            if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc_code):
                return False, 'Invalid IFSC code (e.g. SBIN0001234)'

        try:
            db = _db()
            if not db:
                return False, 'Database unavailable'
            db.table('user_kyc_details').upsert({
                'user_id': user_id,
                'full_name': full_name,
                'pan_number': pan,
                'upi_id': upi_id,
                'account_number': account_number,
                'ifsc_code': ifsc_code,
                'bank_name': bank_name,
                'account_holder_name': full_name,
                'preferred_method': method,
                'is_verified': False,
                'rejection_reason': None,
                'submitted_at': _now(),
                'updated_at': _now(),
            }).execute()
            return True, 'KYC submitted — verification within 24–48 hours'
        except Exception as e:
            log.error(f"[ENGINE] submit_kyc error: {e}")
            return False, str(e)

    def get_kyc(self, user_id: str) -> Optional[dict]:
        """
        Returns KYC row with masked sensitive fields.
        account_number → ****1234, pan_number → ABCDE****F
        """
        try:
            db = _db()
            if not db:
                return None
            res = db.table('user_kyc_details').select('*').eq('user_id', user_id).limit(1).execute()
            if not res.data:
                return None
            row = dict(res.data[0])
            # Mask PII before returning
            if row.get('pan_number') and len(row['pan_number']) == 10:
                row['pan_number'] = row['pan_number'][:5] + '****' + row['pan_number'][-1]
            if row.get('account_number') and len(row['account_number']) >= 4:
                row['account_number'] = '****' + row['account_number'][-4:]
            return row
        except Exception as e:
            log.error(f"[ENGINE] get_kyc error: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # REWARDS — single entry point for all reward grants
    # ──────────────────────────────────────────────────────────────────────────

    def grant_reward(self, user_id: str, credits: int, reason: str,
                     ref_id: str = '', source: str = 'system') -> bool:
        """
        Universal reward grant. Replaces all direct paper_quota_remaining writes
        for: upload_reward, referral, admin_grant, etc.
        """
        return self.credit_views(user_id, credits, reason, ref_id=ref_id, source=source)

    # ──────────────────────────────────────────────────────────────────────────
    # ADMIN ADJUSTMENTS
    # ──────────────────────────────────────────────────────────────────────────

    def admin_adjust(self, creator_id: str, amount: float,
                     adjustment_type: str, reason: str = '') -> dict:
        """Admin debit/credit on creator INR wallet. Delegates to wallet_service."""
        from methods.wallet_service import admin_adjust_creator_wallet
        ok, result = admin_adjust_creator_wallet(creator_id, amount, adjustment_type, reason)
        return {'success': ok, 'result': result}

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _ledger_credit(self, user_id: str, delta: int, reason: str,
                       ref_id: str = None, source: str = 'system',
                       balance: int = None):
        """Insert a row into user_credit_ledger. balance is the snapshot after this op."""
        try:
            if balance is None:
                balance = self.get_view_balance(user_id)
            db = _db()
            if db:
                db.table('user_credit_ledger').insert({
                    'user_id': user_id,
                    'delta': delta,
                    'balance': balance,
                    'reason': reason,
                    'source': source,
                    'ref_id': str(ref_id)[:100] if ref_id else None,
                    'created_at': _now(),
                }).execute()
        except Exception as e:
            log.warning(f"[ENGINE] _ledger_credit insert error: {e}")

    def _invalidate_quota_cache(self, user_id: str):
        """Bust cache_manager L1 cache entry for user quota."""
        try:
            from cache_manager import get_cache
            cache = get_cache()
            if cache and hasattr(cache, 'l1'):
                cache.l1.delete(f"user:quota:{user_id}")
        except Exception:
            pass

    def _notify_auto_payout(self, user_id: str, amount: float):
        """Send push notification to user and admin when auto-payout fires."""
        try:
            from push_notifications import send_notification_to_user
            send_notification_to_user(
                user_id=user_id,
                title='Payout Requested 💸',
                body=f'₹{amount:.2f} payout request submitted. Expected within {PAYOUT_SLA_DAYS} business days.',
            )
        except Exception as e:
            log.warning(f"[ENGINE] auto-payout push notification failed: {e}")


# ── Module-level singleton ────────────────────────────────────────────────────
engine = PaymentEngine()


# ── Description helpers (for passbook display) ────────────────────────────────

def _inr_description(row: dict) -> str:
    tx_type = row.get('type', '')
    order_id = row.get('order_id', '') or ''
    if tx_type == 'payout':
        return f"Payout → Wallet"
    if order_id.startswith('REFUND-'):
        return 'Payout rejected — refund'
    if order_id.startswith('PAYOUT-'):
        return 'Payout transfer'
    if order_id.startswith('ADMIN-'):
        return 'Admin adjustment'
    if row.get('doc_id'):
        return f"Note sale (doc {str(row['doc_id'])[:8]})"
    return 'Wallet credit'


def _credit_description(row: dict) -> str:
    reason = row.get('reason', '')
    ref = row.get('ref_id', '') or ''
    labels = {
        'upload_reward':  'Upload reward (+3 views)',
        'referral':       'Referral bonus',
        'pack_purchase':  f"Study Pack purchase",
        'view_spend':     f"Viewed: {ref[:40]}" if ref else 'Document view',
        'admin_grant':    'Admin credit',
        'tea_support':    'Chai supporter received',
    }
    return labels.get(reason, reason.replace('_', ' ').title())


def _kyc_status_label(kyc: Optional[dict]) -> str:
    if not kyc:
        return 'not_submitted'
    if kyc.get('is_verified'):
        return 'verified'
    if kyc.get('rejection_reason'):
        return 'rejected'
    return 'pending_review'
