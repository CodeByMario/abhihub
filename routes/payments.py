"""
Payments & Creator Monetization Blueprint (Phase 5.9B Routing Overhaul)
Handles payment status, PhonePe initiation, transactions, document pricing,
coupons, and creator earnings/wallet/withdrawals.
"""
import os
import json
import time
import secrets
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session

from routes.auth import auth_required
from data.pricing import has_document_access, extract_document_pricing
from methods.supabase_helper import init_supabase

payments_bp = Blueprint('payments', __name__)


@payments_bp.route('/api/payment/status', methods=['POST'])
def payment_status_api():
    data = request.get_json(silent=True) or {}
    order_id = str(data.get('order_id', '')).strip()
    utr = str(data.get('utr', '')).strip()
    amount = data.get('amount', '0')
    purpose = str(data.get('purpose', '')).strip()
    doc_id = str(data.get('doc_id', '')).strip()
    if not doc_id and 'Document-' in purpose:
        doc_id = purpose.split('Document-')[-1].strip()

    if not order_id or not utr or not utr.isdigit() or len(utr) < 10:
        return jsonify({'success': False, 'error': 'Invalid order ID or UTR number'}), 400

    user = session.get('user', {})
    user_id = user.get('uid')
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    user_agent = request.headers.get('User-Agent', '')[:255]

    admin_notes = f"purpose={purpose};doc_id={doc_id}" if (purpose or doc_id) else None

    client = init_supabase()
    try:
        insert_payload = {
            'user_id': user_id,
            'amount': float(amount),
            'order_id': order_id,
            'utr': utr,
            'status': 'submitted',
            'client_ip': client_ip,
            'user_agent': user_agent,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        if admin_notes:
            insert_payload['admin_notes'] = admin_notes
        if client:
            client.table('credit_transactions').insert(insert_payload).execute()
    except Exception as e:
        logging.warning(f"[PAYMENT_STATUS] Failed logging transaction: {e}")

    # Credit pack fulfillment
    is_credits = 'Credits-' in purpose or 'pack=' in purpose or 'credits' in purpose.lower()
    if is_credits and user_id and client:
        pack_size = 0
        for part in (purpose or '').split(';'):
            if 'Credits-' in part:
                try: pack_size = int(part.split('Credits-')[1].split('-')[0].strip())
                except: pass
            elif 'pack=' in part:
                try: pack_size = int(part.replace('pack=', '').strip())
                except: pass
        if pack_size <= 0 and float(amount) > 0:
            pack_size = int(float(amount) / 2)
        if pack_size > 0:
            try:
                prof_res = client.table('profiles').select('paper_quota_remaining').eq('id', user_id).execute()
                curr_q = 19
                if prof_res.data:
                    curr_q = prof_res.data[0].get('paper_quota_remaining') or 19
                new_q = curr_q + pack_size
                client.table('profiles').update({'paper_quota_remaining': new_q}).eq('id', user_id).execute()
                if 'paper_quota' in session and isinstance(session['paper_quota'], dict):
                    session['paper_quota']['credits'] = new_q
                else:
                    session['paper_quota'] = {'credits': new_q, 'total_views': 0}
                session.modified = True
                try:
                    from cache_manager import get_cache
                    cache = get_cache()
                    if cache and hasattr(cache, 'l1'):
                        cache.l1.delete(f"user:quota:{user_id}")
                except Exception:
                    pass
                from data.pricing import log_credit_transaction
                log_credit_transaction(user_id, pack_size, 'earn', f"Bought {pack_size} Views Pack (₹{amount})")
                logging.info(f"[PAYMENT_STATUS] Added {pack_size} credits to user {user_id}. New quota: {new_q}")
            except Exception as cred_err:
                logging.warning(f"[PAYMENT_STATUS] Could not add credits: {cred_err}")

    # Instant access unlock in user session
    if doc_id:
        try:
            from methods.wallet_service import credit_creator_for_purchase
            credit_creator_for_purchase(order_id, doc_id, amount)
        except Exception:
            pass

        purchased = session.get('purchased_documents', [])
        if doc_id not in purchased:
            purchased.append(doc_id)
            session['purchased_documents'] = purchased
            session.modified = True

    return jsonify({'success': True, 'status': 'submitted', 'order_id': order_id, 'doc_id': doc_id})


@payments_bp.route('/api/payment/phonepe/initiate', methods=['POST'])
def phonepe_initiate_api():
    from methods.phonepe_service import validate_order_id, initiate_phonepe_payment
    from data.transactions import save_transaction_record

    data = request.get_json(silent=True) or {}
    order_id = str(data.get('order_id', '')).strip()
    doc_id = str(data.get('doc_id', '')).strip()
    purpose = str(data.get('purpose', '')).strip()
    supporter_name = str(data.get('supporter_name', '')).strip()
    message = str(data.get('message', '')).strip()

    if not order_id:
        order_id = f"AH{int(time.time())}{secrets.token_hex(2).upper()}"
    elif not validate_order_id(order_id):
        return jsonify({'success': False, 'error': 'Invalid order ID format'}), 400

    try:
        amount = float(data.get('amount', 49.0))
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be greater than zero'}), 400
    except (ValueError, TypeError):
        amount = 49.0

    if doc_id:
        try:
            client = init_supabase()
            if client:
                p_res = client.table('documents').select('price, is_paid, description').eq('id', doc_id).limit(1).execute()
                if p_res.data:
                    pricing_data = extract_document_pricing(p_res.data[0])
                    expected_price = float(pricing_data.get('price', 0))
                    if expected_price > 0 and amount < 1.0:
                        amount = expected_price
        except Exception:
            pass

    user_id = session.get('user', {}).get('uid', '') or session.get('user', {}).get('id', '')
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    user_agent = request.headers.get('User-Agent', '')[:255]

    save_transaction_record(order_id, {
        'user_id': user_id or None,
        'amount': amount,
        'status': 'initiated',
        'utr': order_id,
        'client_ip': client_ip,
        'user_agent': user_agent,
        'admin_notes': f"purpose={purpose};doc_id={doc_id};name={supporter_name};msg={message}"
    })

    base_url = request.host_url.rstrip('/')
    redirect_url = f"{base_url}/payment/phonepe/redirect?order_id={order_id}&doc_id={doc_id}&user_id={user_id}"
    callback_url = f"{base_url}/api/payment/phonepe/callback"

    res = initiate_phonepe_payment(
        order_id=order_id,
        amount_inr=amount,
        user_id=user_id,
        redirect_url=redirect_url,
        callback_url=callback_url
    )
    return jsonify(res)


@payments_bp.route('/api/user/transactions', methods=['GET'])
@auth_required
def get_user_transactions_api():
    """Fetches recent PhonePe payment and credit transactions for the logged-in user."""
    from data.transactions import get_user_transactions
    user_info = session.get('user', {})
    user_id = user_info.get('uid', '')

    tx_list = get_user_transactions(user_id=user_id, limit=50)

    enriched = []
    for tx in tx_list:
        doc_id = ''
        notes = tx.get('admin_notes') or ''
        for part in notes.split(';'):
            if part.startswith('doc_id='):
                doc_id = part.replace('doc_id=', '').strip()

        doc_title = ''
        if doc_id:
            try:
                from methods.supabase_helper import get_document_by_id_rich
                doc_res = get_document_by_id_rich(doc_id)
                if doc_res.get('success'):
                    doc_title = doc_res.get('data', {}).get('title', '')
            except Exception:
                pass

        status_val = tx.get('status', 'completed')
        enriched.append({
            'order_id': tx.get('order_id'),
            'amount': tx.get('amount'),
            'status': status_val,
            'doc_id': doc_id,
            'doc_title': doc_title,
            'date': tx.get('updated_at') or tx.get('created_at'),
            'receipt_url': f"/payment/receipt?order_id={tx.get('order_id')}&status={'success' if status_val in ['completed', 'verified'] else 'failed'}&doc_id={doc_id}&amount={tx.get('amount')}"
        })

    return jsonify({'success': True, 'transactions': enriched})


@payments_bp.route('/api/document/<doc_id>/access', methods=['GET'])
def get_document_access_status(doc_id):
    """Check if the requesting user has access to view/download this document."""
    user = session.get('user', {})
    user_id = user.get('uid')
    access = has_document_access(user_id, doc_id)
    return jsonify({'success': True, 'doc_id': doc_id, 'has_access': access})


@payments_bp.route('/api/creator/earnings', methods=['GET'])
@auth_required
def api_creator_earnings():
    """Fetch earnings summary and monetized documents for eligible creators."""
    user_id = session.get('user', {}).get('uid')
    from methods.scoring_engine import get_feature_gate
    from methods.wallet_service import get_creator_views_and_earnings, VIEW_EARNING_RATE_INR
    gate = get_feature_gate(user_id)
    is_eligible = (gate.get('level') or '').lower() in ['contributor', 'power_contributor', 'community_leader']
    total_views, view_earnings = get_creator_views_and_earnings(user_id)

    if not is_eligible:
        return jsonify({
            'success': True,
            'eligible': False,
            'level': gate.get('level'),
            'message': 'Reach Contributor rank to sell paid notes. Upload view earnings are active.',
            'total_views': total_views,
            'view_rate': VIEW_EARNING_RATE_INR,
            'view_earnings': view_earnings,
            'paid_notes_count': 0,
            'total_sales': 0,
            'total_earnings': 0.0,
            'combined_earnings': view_earnings,
            'paid_notes': []
        })

    try:
        docs_res = supabase.table('documents').select('id, title, description, created_at').eq('uploader_id', user_id).execute()
        paid_docs = []
        for d in (docs_res.data or []):
            desc = d.get('description') or ''
            if desc.startswith('{'):
                try:
                    p = json.loads(desc).get('pricing', {})
                    if p.get('is_paid'):
                        paid_docs.append({
                            'id': d['id'],
                            'title': d.get('title'),
                            'price': p.get('price', 0),
                            'coupon_code': p.get('coupon_code', '')
                        })
                except Exception:
                    pass

        total_sales = 0
        total_earnings = 0.0
        for d in paid_docs:
            try:
                tx_res = supabase.table('credit_transactions').select('amount, status').ilike('admin_notes', f"%{d['id']}%").execute()
                sales_count = len(tx_res.data or [])
                gross_amt = sum(float(t.get('amount', 0)) for t in (tx_res.data or []))
                earnings = round(gross_amt * 0.80, 2)
                d['sales_count'] = sales_count
                d['gross_amount'] = round(gross_amt, 2)
                d['earnings'] = earnings
                total_sales += sales_count
                total_earnings += earnings
            except Exception:
                d['sales_count'] = 0
                d['gross_amount'] = 0
                d['earnings'] = 0

        combined_earnings = round(total_earnings + view_earnings, 2)

        return jsonify({
            'success': True,
            'eligible': True,
            'level': gate.get('level'),
            'paid_notes_count': len(paid_docs),
            'total_sales': total_sales,
            'total_earnings': round(total_earnings, 2),
            'total_views': total_views,
            'view_rate': VIEW_EARNING_RATE_INR,
            'view_earnings': view_earnings,
            'combined_earnings': combined_earnings,
            'paid_notes': paid_docs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@payments_bp.route('/api/creator/wallet', methods=['GET'])
@auth_required
def api_creator_wallet():
    """Fetch creator wallet, 30-day locked balance, withdrawable balance, and history."""
    user_id = session.get('user', {}).get('uid')
    from methods.wallet_service import get_creator_wallet
    res = get_creator_wallet(user_id)
    return jsonify(res)


@payments_bp.route('/api/creator/withdraw', methods=['POST'])
@auth_required
def api_creator_withdraw():
    """Request a payout if withdrawable balance >= 100."""
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    amount = data.get('amount')
    payout_method = str(data.get('payout_method', '')).lower().strip()
    payout_details = data.get('payout_details', {})

    from methods.wallet_service import request_withdrawal
    ok, result = request_withdrawal(user_id, amount, payout_method, payout_details)
    if not ok:
        return jsonify({'success': False, 'error': result}), 400
    return jsonify({'success': True, 'payout': result})


@payments_bp.route('/api/document/<doc_id>/pricing', methods=['GET'])
def get_document_pricing(doc_id):
    """Get document pricing and coupon availability."""
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database unavailable'}), 500
        res = client.table('documents').select('id, uploader_id, description').eq('id', doc_id).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'Document not found'}), 404
        doc = res.data[0]
        desc_raw = doc.get('description') or ''
        pricing = {}
        if desc_raw.startswith('{'):
            try:
                pricing = json.loads(desc_raw).get('pricing', {})
            except Exception:
                pass
        return jsonify({
            'success': True,
            'is_paid': bool(pricing.get('is_paid')),
            'price': float(pricing.get('price', 0)),
            'has_coupon': bool(pricing.get('coupon_code')),
            'seller_id': pricing.get('seller_id')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@payments_bp.route('/api/document/<doc_id>/coupon', methods=['POST'])
def apply_document_coupon(doc_id):
    """Validate coupon, handle edge cases, and return payment link."""
    data = request.get_json(silent=True) or {}
    coupon_input = str(data.get('coupon_code', '')).strip().upper()

    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database unavailable'}), 500
        res = client.table('documents').select('id, price, is_paid, seller_id, coupon_code, coupon_discount, description, title').eq('id', doc_id).limit(1).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'Document not found'}), 404
        doc = res.data[0]
        pricing = extract_document_pricing(doc)

        base_price = float(pricing.get('price', 0))
        if not pricing.get('is_paid') or base_price <= 0:
            return jsonify({'success': True, 'final_price': 0, 'message': 'This document is free.'})

        expected_coupon = str(pricing.get('coupon_code', '')).strip().upper()
        discount_pct = int(pricing.get('coupon_discount', 0))

        discount_amount = 0.0
        applied = False
        if coupon_input and expected_coupon and coupon_input == expected_coupon:
            discount_amount = round(base_price * (discount_pct / 100.0), 2)
            applied = True

        final_price = max(1.0, round(base_price - discount_amount, 2)) if applied else base_price
        payment_url = f"/payment?amount={final_price:.2f}&purpose=Document-{doc_id}"

        return jsonify({
            'success': True,
            'base_price': base_price,
            'discount_amount': discount_amount,
            'final_price': final_price,
            'coupon_applied': applied,
            'payment_url': payment_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
