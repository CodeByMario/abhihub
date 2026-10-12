"""
Creator Wallet and Withdrawal Management Service.
Handles 30-day holding periods, ledger reconciliation, and minimum ₹100 payout requests.
"""

import re
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
VIEW_EARNING_RATE_INR = 0.20


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
        query = supabase.table('wallet_ledger').select('*').eq('type', 'credit').eq('status', 'locked').lte('unlock_at', now_iso)
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


def get_creator_views_and_earnings(creator_id):
    """
    Computes total unique views across all uploaded documents for a creator
    excluding self-views and duplicates, calculating gross earnings at ₹0.20 per unique view.
    """
    if not creator_id:
        return 0, 0.0
    try:
        # Check RPC function if deployed
        try:
            rpc_res = supabase.rpc('get_creator_unique_views', {'p_creator_id': str(creator_id)}).execute()
            if rpc_res.data is not None:
                unique_views = int(rpc_res.data)
                return unique_views, round(unique_views * VIEW_EARNING_RATE_INR, 2)
        except Exception:
            pass

        # Python fallback: distinct (document_id, viewer) excluding creator
        docs_res = supabase.table('documents').select('id').eq('uploader_id', str(creator_id)).execute()
        doc_ids = [d['id'] for d in (docs_res.data or []) if d.get('id')]
        if not doc_ids:
            return 0, 0.0

        views_res = supabase.table('document_views').select('document_id, user_id, ip_address').in_('document_id', doc_ids).execute()
        unique_keys = set()
        for v in (views_res.data or []):
            u_id = v.get('user_id')
            ip = v.get('ip_address')
            if u_id and str(u_id) == str(creator_id):
                continue
            viewer = str(u_id) if u_id else (str(ip) if ip else None)
            if viewer and v.get('document_id'):
                unique_keys.add((str(v['document_id']), viewer))

        unique_views = len(unique_keys)
        view_earnings = round(unique_views * VIEW_EARNING_RATE_INR, 2)
        return unique_views, view_earnings
    except Exception as e:
        logging.error(f"[WALLET] Error calculating view earnings for {creator_id}: {e}")
        return 0, 0.0


def get_creator_wallet(creator_id):
    """
    Reconciles locks and fetches creator wallet with view earnings, ledger, and payouts.
    """
    unlock_eligible_entries(creator_id)

    wallet = {'pending_balance': 0.0, 'withdrawable_balance': 0.0, 'total_withdrawn': 0.0}
    try:
        w_res = supabase.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()
        if w_res.data:
            wallet = w_res.data[0]

        total_views, view_earnings = get_creator_views_and_earnings(creator_id)

        # 1. Calculate unlocked and pending note sales from ledger
        credits_res = supabase.table('wallet_ledger').select('amount, order_id, status').eq('creator_id', str(creator_id)).eq('type', 'credit').execute()
        unlocked_sales = sum(
            float(c.get('amount') or 0.0)
            for c in (credits_res.data or [])
            if c.get('status') == 'available' and not str(c.get('order_id') or '').startswith('REFUND-')
        )
        pending_sales = sum(
            float(c.get('amount') or 0.0)
            for c in (credits_res.data or [])
            if c.get('status') == 'locked'
        )

        # 2. Calculate active payout deductions (pending, processing, and completed)
        all_payouts_res = supabase.table('creator_payout_requests').select('amount, status').eq('creator_id', str(creator_id)).execute()
        all_payouts = all_payouts_res.data or []
        active_payouts = [p for p in all_payouts if p.get('status') != 'rejected']
        total_payouts_deducted = sum(float(p.get('amount') or 0.0) for p in active_payouts)
        total_completed_withdrawn = sum(float(p.get('amount') or 0.0) for p in active_payouts if p.get('status') == 'completed')

        # 3. Exact Lifetime Earned and Net Withdrawable Balance
        total_lifetime_earned = round(view_earnings + unlocked_sales, 2)
        effective_withdrawable = max(0.0, round(total_lifetime_earned - total_payouts_deducted, 2))

        # Reconcile sales breakdown and total withdrawn
        sales_withdrawn = min(unlocked_sales, total_payouts_deducted)
        sales_withdrawable = max(0.0, round(unlocked_sales - sales_withdrawn, 2))
        total_withdrawn = total_completed_withdrawn

        # Sync reconciled values into creator_wallets table
        try:
            supabase.table('creator_wallets').upsert({
                'user_id': str(creator_id),
                'pending_balance': round(pending_sales, 2),
                'withdrawable_balance': round(effective_withdrawable, 2),
                'total_withdrawn': round(total_withdrawn, 2),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception:
            pass

        ledger = supabase.table('wallet_ledger').select('*').eq('creator_id', str(creator_id)).order('created_at', desc=True).limit(20).execute().data or []
        payouts = supabase.table('creator_payout_requests').select('*').eq('creator_id', str(creator_id)).order('created_at', desc=True).limit(10).execute().data or []

        # Determine gamified minimum withdrawal threshold:
        # 1st withdrawal: ₹5, 2nd withdrawal: ₹25, 3rd+ withdrawal: ₹100
        payouts_completed = [p for p in (payouts or []) if p.get('status') == 'completed']
        completed_count = len(payouts_completed)
        if completed_count == 0:
            min_limit = 5.0
            withdrawal_tier = 1
        elif completed_count == 1:
            min_limit = 25.0
            withdrawal_tier = 2
        else:
            min_limit = MIN_WITHDRAWAL_AMOUNT
            withdrawal_tier = 3
        can_withdraw = (effective_withdrawable >= min_limit) and (effective_withdrawable > 0)

        return {
            'success': True,
            'wallet': {
                'pending_balance': float(wallet.get('pending_balance', 0)),
                'withdrawable_balance': effective_withdrawable,
                'sales_withdrawable': sales_withdrawable,
                'total_views': total_views,
                'view_earnings': view_earnings,
                'view_rate': VIEW_EARNING_RATE_INR,
                'total_withdrawn': total_withdrawn,
                'min_withdrawal': min_limit,
                'withdrawal_tier': withdrawal_tier,
                'holding_days': HOLDING_DAYS,
                'can_withdraw': can_withdraw,
                'withdrawals_completed': completed_count,
                'is_first_three_free': completed_count < 3
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

    if payout_method not in ['upi', 'bank']:
        return False, "Payout method must be 'upi' or 'bank'"

    if not isinstance(payout_details, dict) or not payout_details:
        return False, "Account or UPI details are required"

    if payout_method == 'upi':
        upi_id = str(payout_details.get('upi_id', '') or payout_details.get('vpa', '')).strip()
        if not upi_id:
            return False, "UPI ID is required"
        if not re.match(r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z0-9]{2,64}$', upi_id):
            return False, "Invalid UPI ID format. Must be in format username@bank (e.g., yourname@okhdfcbank)"
    elif payout_method == 'bank':
        acc_info = str(payout_details.get('account_info', '')).strip()
        if not acc_info or len(acc_info) < 6:
            return False, "Please provide complete bank account details and IFSC code"

    try:
        # Prevent double-spending: disallow new payout if one is already pending/processing
        pending_check = supabase.table('creator_payout_requests')\
            .select('id')\
            .eq('creator_id', str(creator_id))\
            .in_('status', ['pending', 'processing'])\
            .limit(1)\
            .execute()
        if pending_check.data:
            return False, "You already have a payout request under review. Please wait until it is processed."

        w_info = get_creator_wallet(creator_id)
        if not w_info.get('success'):
            return False, "Could not fetch wallet details"

        min_limit = float(w_info['wallet'].get('min_withdrawal', MIN_WITHDRAWAL_AMOUNT))
        if amt < min_limit or amt <= 0:
            return False, f"Minimum withdrawal amount is ₹{min_limit:.0f}"

        curr_withdrawable = float(w_info['wallet'].get('withdrawable_balance', 0))
        if curr_withdrawable < amt:
            return False, f"Insufficient withdrawable balance (Available: ₹{curr_withdrawable:.2f})"

        # Ensure wallet record exists in DB
        w_res = supabase.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()
        now = datetime.now(timezone.utc)
        if not w_res.data:
            supabase.table('creator_wallets').insert({
                'user_id': str(creator_id),
                'pending_balance': 0.0,
                'withdrawable_balance': 0.0,
                'total_withdrawn': 0.0,
                'updated_at': now.isoformat()
            }).execute()
            w_res = supabase.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()

        w_row = w_res.data[0] if w_res.data else {}
        db_sales_withdrawable = float(w_row.get('withdrawable_balance', 0))
        deduct_from_sales = min(db_sales_withdrawable, amt)
        deduct_from_views = round(amt - deduct_from_sales, 2)
        new_sales_withdrawable = round(db_sales_withdrawable - deduct_from_sales, 2)
        new_total_withdrawn = round(float(w_row.get('total_withdrawn', 0)) + amt, 2)

        # Track deduction sources in payout_details for accurate refunds
        payout_details['deducted_sales'] = deduct_from_sales
        payout_details['deducted_views'] = deduct_from_views

        # Deduct from wallet
        supabase.table('creator_wallets').update({
            'withdrawable_balance': new_sales_withdrawable,
            'total_withdrawn': new_total_withdrawn,
            'updated_at': now.isoformat()
        }).eq('user_id', str(creator_id)).execute()

        # Insert payout request
        req = supabase.table('creator_payout_requests').insert({
            'creator_id': str(creator_id),
            'amount': amt,
            'payout_method': payout_method,
            'payout_details': payout_details,
            'status': 'pending',
            'created_at': now.isoformat()
        }).execute()

        payout_id = req.data[0]['id'] if (req.data and len(req.data) > 0) else None
        payout_order_id = f"PAYOUT-{payout_id}" if payout_id else None

        # Record debit in ledger linked to this payout
        supabase.table('wallet_ledger').insert({
            'creator_id': str(creator_id),
            'amount': amt,
            'type': 'payout',
            'status': 'pending',
            'order_id': payout_order_id,
            'unlock_at': None,
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
    If rejected, accurately refunds funds back to the creator wallet and ledger without double-counting.
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
        payout_order_id = f"PAYOUT-{payout_id}"

        # If completed, finalize ledger entry
        if action == 'completed':
            try:
                supabase.table('wallet_ledger').update({'status': 'paid'}).eq('order_id', payout_order_id).execute()
            except Exception:
                pass

        # If rejected, restore funds and cancel ledger debit
        if action == 'rejected':
            p_details = payout.get('payout_details') or {}
            deducted_sales = float(p_details.get('deducted_sales', 0.0))

            w_res = supabase.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
            if w_res.data:
                curr_w = float(w_res.data[0].get('withdrawable_balance', 0))
                curr_tot = float(w_res.data[0].get('total_withdrawn', 0))
                # Only restore what was deducted from sales; view earnings automatically restore via total_withdrawn decrease
                supabase.table('creator_wallets').update({
                    'withdrawable_balance': round(curr_w + deducted_sales, 2),
                    'total_withdrawn': round(max(0.0, curr_tot - amt), 2),
                    'updated_at': now.isoformat()
                }).eq('user_id', creator_id).execute()

            # Mark original payout ledger entry cancelled
            try:
                supabase.table('wallet_ledger').update({'status': 'cancelled'}).eq('order_id', payout_order_id).execute()
            except Exception:
                pass

            # Record refund in ledger for audit with REFUND- prefix
            supabase.table('wallet_ledger').insert({
                'creator_id': creator_id,
                'amount': amt,
                'type': 'credit',
                'status': 'available',
                'order_id': f"REFUND-{payout_id}",
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


def admin_adjust_creator_wallet(creator_id, amount: float, adjustment_type: str, reason: str = ""):
    """
    Allows admin to debit penalties/charges or credit bonuses/adjustments to a creator wallet.
    Records audit entry in wallet_ledger.
    """
    if not creator_id:
        return False, "Creator ID required"
    try:
        amt = round(abs(float(amount)), 2)
        if amt <= 0:
            return False, "Amount must be greater than zero"
    except (ValueError, TypeError):
        return False, "Invalid amount"

    adjustment_type = str(adjustment_type).lower().strip()
    if adjustment_type not in ['penalty', 'charge', 'debit', 'credit', 'bonus']:
        return False, "Invalid adjustment type. Use penalty, charge, debit, credit, or bonus."

    now = datetime.now(timezone.utc)
    try:
        w_res = supabase.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()
        if not w_res.data:
            supabase.table('creator_wallets').insert({
                'user_id': str(creator_id),
                'pending_balance': 0.0,
                'withdrawable_balance': 0.0,
                'total_withdrawn': 0.0,
                'updated_at': now.isoformat()
            }).execute()
            w_res = supabase.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()

        w_row = w_res.data[0] if w_res.data else {}
        db_sales_withdrawable = float(w_row.get('withdrawable_balance', 0))
        curr_total_withdrawn = float(w_row.get('total_withdrawn', 0))

        w_info = get_creator_wallet(creator_id)
        effective_bal = float(w_info.get('wallet', {}).get('withdrawable_balance', 0)) if w_info.get('success') else db_sales_withdrawable

        is_debit = adjustment_type in ['penalty', 'charge', 'debit']
        if is_debit:
            deduct_from_sales = min(db_sales_withdrawable, amt)
            new_sales_withdrawable = round(db_sales_withdrawable - deduct_from_sales, 2)
            new_total_withdrawn = round(curr_total_withdrawn + amt, 2)
            new_effective_bal = max(0.0, round(effective_bal - amt, 2))
            ledger_type = 'debit'
            ledger_status = 'paid'
        else:
            new_sales_withdrawable = round(db_sales_withdrawable + amt, 2)
            new_total_withdrawn = curr_total_withdrawn
            new_effective_bal = round(effective_bal + amt, 2)
            ledger_type = 'credit'
            ledger_status = 'available'

        supabase.table('creator_wallets').update({
            'withdrawable_balance': new_sales_withdrawable,
            'total_withdrawn': new_total_withdrawn,
            'updated_at': now.isoformat()
        }).eq('user_id', str(creator_id)).execute()

        # Insert audit record in wallet_ledger
        supabase.table('wallet_ledger').insert({
            'creator_id': str(creator_id),
            'amount': amt,
            'type': ledger_type,
            'status': ledger_status,
            'doc_id': None,
            'order_id': f"ADMIN-{adjustment_type.upper()}-{int(now.timestamp())}",
            'unlock_at': now.isoformat(),
            'created_at': now.isoformat()
        }).execute()

        return True, {
            'creator_id': creator_id,
            'adjustment_type': adjustment_type,
            'amount': amt,
            'previous_balance': effective_bal,
            'new_balance': new_effective_bal,
            'message': f"Wallet successfully updated. New withdrawable balance: ₹{new_effective_bal:.2f}"
        }
    except Exception as e:
        logging.error(f"[WALLET] Error adjusting wallet for {creator_id}: {e}")
        return False, str(e)

