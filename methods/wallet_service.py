"""
Creator Wallet and Withdrawal Management Service.
Handles 30-day holding periods, ledger reconciliation, and minimum ₹100 payout requests.
"""

from datetime import datetime, timezone, timedelta
import logging
from methods.supabase_helper import init_supabase, init_supabase_admin


def _get_client():
    client = init_supabase_admin()
    if client:
        return client
    return init_supabase()


class _SupabaseProxy:
    def __getattr__(self, name):
        client = _get_client()
        if not client:
            raise RuntimeError("Supabase client not initialized")
        return getattr(client, name)


supabase = _SupabaseProxy()

MIN_WITHDRAWAL_AMOUNT = 100.0
HOLDING_DAYS = 30


def get_document_creator(doc_id):
    """Fetch the creator (uploader_id) of a document."""
    try:
        res = supabase.table('documents').select('uploader_id').eq('id', str(doc_id)).limit(1).execute()
        if res.data:
            return res.data[0].get('uploader_id')
    except Exception as e:
        logging.error(f"[WALLET] Error getting document creator: {e}")
    return None


def calculate_fee_breakdown(gross_amount: float) -> dict:
    """
    Computes creator earnings (80%) and 20% platform expenses:
    - 80% Creator Share
    - 2% Payment Gateway
    - 4% Storage
    - 4% Hosting
    - 4% Advertisement
    - 6% Platform Revenue
    """
    gross = round(float(gross_amount), 2)
    creator_share = round(gross * 0.80, 2)
    gateway_fee = round(gross * 0.02, 2)
    storage_fee = round(gross * 0.04, 2)
    hosting_fee = round(gross * 0.04, 2)
    ads_fee = round(gross * 0.04, 2)
    revenue_fee = round(gross - (creator_share + gateway_fee + storage_fee + hosting_fee + ads_fee), 2)
    return {
        'gross_amount': gross,
        'creator_amount': creator_share,
        'creator_pct': 80,
        'payment_gateway_2pct': gateway_fee,
        'storage_4pct': storage_fee,
        'hosting_4pct': hosting_fee,
        'advertisement_4pct': ads_fee,
        'platform_revenue_6pct': revenue_fee,
        'total_expense_20pct': round(gross - creator_share, 2)
    }


def credit_creator_for_purchase(order_id, doc_id, amount):
    """
    Credits creator's wallet with 30-day locked status (80% creator share).
    20% covers platform expenses (2% gateway, 4% storage, 4% hosting, 4% ads, 6% revenue).
    """
    creator_id = get_document_creator(doc_id)
    if not creator_id:
        return False, "Creator not found"

    try:
        gross_amt = float(amount)
        if gross_amt <= 0:
            return False, "Invalid amount"
    except (ValueError, TypeError):
        return False, "Invalid amount"

    breakdown = calculate_fee_breakdown(gross_amt)
    creator_amt = breakdown['creator_amount']

    now = datetime.now(timezone.utc)
    unlock_at = now + timedelta(days=HOLDING_DAYS)

    try:
        # Check idempotency
        existing = supabase.table('wallet_ledger').select('id').eq('order_id', str(order_id)).execute()
        if existing.data:
            return True, "Already credited"

        # Record ledger entry with 80% creator share
        supabase.table('wallet_ledger').insert({
            'creator_id': creator_id,
            'amount': creator_amt,
            'type': 'credit',
            'status': 'locked',
            'doc_id': str(doc_id),
            'order_id': str(order_id),
            'unlock_at': unlock_at.isoformat(),
            'created_at': now.isoformat()
        }).execute()

        # Update or create wallet balance
        wallet_res = supabase.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
        if wallet_res.data:
            curr_pending = float(wallet_res.data[0].get('pending_balance', 0))
            supabase.table('creator_wallets').update({
                'pending_balance': round(curr_pending + creator_amt, 2),
                'updated_at': now.isoformat()
            }).eq('user_id', creator_id).execute()
        else:
            supabase.table('creator_wallets').insert({
                'user_id': creator_id,
                'pending_balance': round(creator_amt, 2),
                'withdrawable_balance': 0.00,
                'total_withdrawn': 0.00,
                'updated_at': now.isoformat()
            }).execute()

        return True, "Credited"
    except Exception as e:
        logging.error(f"[WALLET] Credit failed: {e}")
        return False, str(e)


def unlock_eligible_entries(creator_id=None):
    """
    Reconciles locked entries past 30 days and moves funds to withdrawable balance.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        query = supabase.table('wallet_ledger').select('*').eq('status', 'locked').lte('unlock_at', now_iso)
        if creator_id:
            query = query.eq('creator_id', creator_id)
        entries = query.execute().data or []

        if not entries:
            return 0

        # Group unlocks by creator
        creators_delta = {}
        unlocked_ids = []
        for e in entries:
            cid = e['creator_id']
            amt = float(e['amount'])
            creators_delta[cid] = creators_delta.get(cid, 0.0) + amt
            unlocked_ids.append(e['id'])

        # Mark entries available
        for entry_id in unlocked_ids:
            supabase.table('wallet_ledger').update({'status': 'available'}).eq('id', entry_id).execute()

        # Update creator wallets
        for cid, delta in creators_delta.items():
            w = supabase.table('creator_wallets').select('*').eq('user_id', cid).limit(1).execute()
            if w.data:
                curr_pend = max(0.0, float(w.data[0].get('pending_balance', 0)) - delta)
                curr_with = float(w.data[0].get('withdrawable_balance', 0)) + delta
                supabase.table('creator_wallets').update({
                    'pending_balance': round(curr_pend, 2),
                    'withdrawable_balance': round(curr_with, 2),
                    'updated_at': now_iso
                }).eq('user_id', cid).execute()

        return len(entries)
    except Exception as e:
        logging.error(f"[WALLET] Unlock error: {e}")
        return 0


def get_creator_wallet(creator_id):
    """
    Reconciles locks and fetches creator wallet with ledger and payouts.
    """
    unlock_eligible_entries(creator_id)

    wallet = {'pending_balance': 0.0, 'withdrawable_balance': 0.0, 'total_withdrawn': 0.0}
    try:
        w_res = supabase.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
        if w_res.data:
            wallet = w_res.data[0]

        ledger = supabase.table('wallet_ledger').select('*').eq('creator_id', creator_id).order('created_at', desc=True).limit(20).execute().data or []
        payouts = supabase.table('creator_payout_requests').select('*').eq('creator_id', creator_id).order('created_at', desc=True).limit(10).execute().data or []

        return {
            'success': True,
            'wallet': {
                'pending_balance': float(wallet.get('pending_balance', 0)),
                'withdrawable_balance': float(wallet.get('withdrawable_balance', 0)),
                'total_withdrawn': float(wallet.get('total_withdrawn', 0)),
                'min_withdrawal': MIN_WITHDRAWAL_AMOUNT,
                'holding_days': HOLDING_DAYS,
                'can_withdraw': float(wallet.get('withdrawable_balance', 0)) >= MIN_WITHDRAWAL_AMOUNT
            },
            'ledger': ledger,
            'payouts': payouts
        }
    except Exception as e:
        logging.error(f"[WALLET] Fetch error: {e}")
        return {'success': False, 'error': str(e)}


def request_withdrawal(creator_id, amount, payout_method, payout_details):
    """
    Processes a withdrawal request if balance >= 100.
    """
    unlock_eligible_entries(creator_id)

    try:
        amt = round(float(amount), 2)
    except (ValueError, TypeError):
        return False, "Invalid withdrawal amount"

    if amt < MIN_WITHDRAWAL_AMOUNT:
        return False, f"Minimum withdrawal amount is ₹{MIN_WITHDRAWAL_AMOUNT:.0f}"

    if payout_method not in ['upi', 'bank']:
        return False, "Payout method must be 'upi' or 'bank'"

    if not isinstance(payout_details, dict) or not payout_details:
        return False, "Account or UPI details are required"

    try:
        w_res = supabase.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
        if not w_res.data:
            return False, "Wallet not found"

        curr_withdrawable = float(w_res.data[0].get('withdrawable_balance', 0))
        if curr_withdrawable < amt:
            return False, f"Insufficient withdrawable balance (Available: ₹{curr_withdrawable:.2f})"

        now = datetime.now(timezone.utc)
        new_withdrawable = round(curr_withdrawable - amt, 2)
        total_withdrawn = round(float(w_res.data[0].get('total_withdrawn', 0)) + amt, 2)

        # Deduct from wallet
        supabase.table('creator_wallets').update({
            'withdrawable_balance': new_withdrawable,
            'total_withdrawn': total_withdrawn,
            'updated_at': now.isoformat()
        }).eq('user_id', creator_id).execute()

        # Insert payout request
        req = supabase.table('creator_payout_requests').insert({
            'creator_id': creator_id,
            'amount': amt,
            'payout_method': payout_method,
            'payout_details': payout_details,
            'status': 'pending',
            'created_at': now.isoformat()
        }).execute()

        # Record debit in ledger
        supabase.table('wallet_ledger').insert({
            'creator_id': creator_id,
            'amount': amt,
            'type': 'payout',
            'status': 'paid',
            'unlock_at': now.isoformat(),
            'created_at': now.isoformat()
        }).execute()

        return True, req.data[0] if req.data else "Submitted"
    except Exception as e:
        logging.error(f"[WALLET] Withdrawal request error: {e}")
        return False, str(e)


def get_all_payout_requests(status=None, limit=50):
    """Fetch creator payout requests for admin management."""
    try:
        query = supabase.table('creator_payout_requests').select('*').order('created_at', desc=True).limit(limit)
        if status:
            query = query.eq('status', status)
        res = query.execute()
        return {'success': True, 'payouts': res.data or []}
    except Exception as e:
        logging.error(f"[WALLET] Error fetching payout requests: {e}")
        return {'success': False, 'error': str(e), 'payouts': []}


def process_payout_request(payout_id, action, admin_notes=""):
    """
    Admin action to approve ('completed') or reject ('rejected') a withdrawal request.
    If rejected, refunds the withdrawable amount back to the creator wallet and adds a ledger entry.
    """
    if action not in ['completed', 'rejected', 'processing']:
        return False, "Invalid action. Must be 'completed', 'rejected', or 'processing'."

    now = datetime.now(timezone.utc)
    try:
        p_res = supabase.table('creator_payout_requests').select('*').eq('id', str(payout_id)).limit(1).execute()
        if not p_res.data:
            return False, "Payout request not found"

        payout = p_res.data[0]
        prev_status = payout.get('status')
        if prev_status in ['completed', 'rejected']:
            return False, f"Payout already {prev_status}"

        creator_id = payout.get('creator_id')
        amt = float(payout.get('amount', 0))

        # If rejected, refund to creator wallet and ledger
        if action == 'rejected':
            w_res = supabase.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
            if w_res.data:
                curr_w = float(w_res.data[0].get('withdrawable_balance', 0))
                curr_tot = float(w_res.data[0].get('total_withdrawn', 0))
                supabase.table('creator_wallets').update({
                    'withdrawable_balance': round(curr_w + amt, 2),
                    'total_withdrawn': round(max(0.0, curr_tot - amt), 2),
                    'updated_at': now.isoformat()
                }).eq('user_id', creator_id).execute()

            # Record refund in ledger
            supabase.table('wallet_ledger').insert({
                'creator_id': creator_id,
                'amount': amt,
                'type': 'credit',
                'status': 'available',
                'unlock_at': now.isoformat(),
                'created_at': now.isoformat()
            }).execute()

        # Update payout request status
        supabase.table('creator_payout_requests').update({
            'status': action,
            'admin_notes': admin_notes or None,
            'processed_at': now.isoformat()
        }).eq('id', str(payout_id)).execute()

        return True, f"Payout request marked as {action}"
    except Exception as e:
        logging.error(f"[WALLET] Error processing payout {payout_id}: {e}")
        return False, str(e)

