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
                prof_res = client.table('profiles').select('paper_quota_remaining, email').eq('id', user_id).execute()
                curr_q = 0
                if prof_res.data:
                    val = prof_res.data[0].get('paper_quota_remaining')
                    if val is not None:
                        curr_q = int(val)
                    else:
                        from methods.domain_tier_service import classify_email
                        curr_q = classify_email(prof_res.data[0].get('email', ''))['starting_views']
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

    if doc_id:
        try:
            from methods.wallet_service import credit_creator_for_purchase, get_document_creator
            credit_creator_for_purchase(order_id, doc_id, amount)
            creator_id = get_document_creator(doc_id)
            user_id = session.get('user', {}).get('uid')
            if creator_id and user_id and str(creator_id) != str(user_id):
                from methods.creator_crm_service import record_creator_customer_purchase
                record_creator_customer_purchase(
                    creator_id=creator_id,
                    customer_id=user_id,
                    amount=amount,
                    customer_name=session.get('user', {}).get('name'),
                    customer_email=session.get('user', {}).get('email')
                )
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
    """Deprecated PhonePe endpoint — forwarded to Razorpay order creation."""
    return initiate_payment()


@payments_bp.route('/api/create-order', methods=['POST'])
@payments_bp.route('/api/payment/initiate', methods=['POST'])
@payments_bp.route('/api/payment/razorpay/initiate', methods=['POST'])
@auth_required
def initiate_payment():
    """Initiates a Razorpay standard checkout order."""
    from methods.razorpay_service import create_order
    from data.transactions import save_transaction_record

    data = request.get_json(silent=True) or {}
    doc_id = str(data.get('doc_id', '')).strip()
    purpose = str(data.get('purpose', '')).strip()
    pack_size = int(data.get('pack', 0) or 0)
    user = session.get('user', {})
    user_id = user.get('uid') or user.get('id') or ''
    user_email = (user.get('email') or '').strip()
    user_name = (user.get('name') or user.get('display_name') or '').strip()
    user_phone = str(data.get('phone') or data.get('contact') or '').strip()

    client = init_supabase()
    if user_id and client:
        try:
            if user_phone:
                client.table('profiles').update({'phone_number': user_phone}).eq('id', user_id).execute()
            else:
                p_res = client.table('profiles').select('phone_number, full_name, email').eq('id', user_id).limit(1).execute()
                if p_res.data:
                    prof = p_res.data[0]
                    user_phone = prof.get('phone_number') or ''
                    if not user_email:
                        user_email = (prof.get('email') or '').strip()
                    if not user_name:
                        user_name = (prof.get('full_name') or '').strip()
        except Exception as p_err:
            logging.warning(f"[PAYMENT] Profile sync error: {p_err}")

    if not user_phone:
        user_phone = (user.get('user_metadata') or {}).get('phone') or ''

    price = 0.0
    admin_notes_parts = []

    # Detect doc_id or credit pack from purpose string if not provided directly
    if not doc_id and 'Document-' in purpose:
        doc_id = purpose.split('Document-')[-1].strip()

    # 1. Credit packs (prioritize pack purchases over doc_id)
    if pack_size or 'credits-' in purpose.lower() or ('view' in purpose.lower() and 'document' not in purpose.lower()):
        if not pack_size and 'Credits-' in purpose:
            try: pack_size = int(purpose.split('Credits-')[1].split('-')[0].strip())
            except Exception: pack_size = 50
        elif not pack_size:
            pack_size = 50

        valid_packs = {50: 100.0, 100: 200.0, 500: 1000.0}
        passed_amount = float(data.get('amount', 0) or 0)
        if passed_amount > 0:
            price = passed_amount
        else:
            price = float(valid_packs.get(pack_size, pack_size * 2))
        admin_notes_parts.append(f"purpose=Credits-{pack_size};pack={pack_size};views={pack_size}")
        currency = 'INR'
    elif request.path.endswith('/create-order') and 'amount' in data and not doc_id and not pack_size:
        raw_paise = float(data.get('amount', 0))
        if raw_paise < 100:
            return jsonify({'success': False, 'error': 'Minimum amount is 100 paise'}), 400
        price = raw_paise / 100.0
        currency = data.get('currency', 'INR')
    elif doc_id:
        passed_amount = float(data.get('amount', 0) or 0)
        if passed_amount > 0:
            price = passed_amount
        else:
            client = init_supabase()
            if client:
                try:
                    p_res = client.table('documents').select('price, is_paid, description').eq('id', doc_id).limit(1).execute()
                    if p_res.data:
                        pricing_data = extract_document_pricing(p_res.data[0])
                        price = float(pricing_data.get('price', 0))
                except Exception:
                    pass
            if price <= 0:
                price = 49.0
        admin_notes_parts.append(f"doc_id={doc_id}")
        if purpose:
            admin_notes_parts.append(f"purpose={purpose}")
        currency = 'INR'
    else:
        try:
            price = float(data.get('amount', 49.0))
        except (ValueError, TypeError):
            price = 49.0
        if purpose:
            admin_notes_parts.append(f"purpose={purpose}")
        currency = data.get('currency', 'INR')


    if price <= 0:
        return jsonify({'success': False, 'error': 'Amount must be greater than zero'}), 400

    receipt_param = str(data.get('receipt', '')).strip()
    receipt_id = receipt_param[:40] if receipt_param else f"AH_{int(time.time())}_{secrets.token_hex(2).upper()}"[:40]
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    user_agent = request.headers.get('User-Agent', '')[:255]

    try:
        order = create_order(
            amount_inr=price,
            receipt_id=receipt_id,
            notes={
                'doc_id': doc_id,
                'user_id': user_id or 'guest',
                'purpose': purpose or (f"Document {doc_id}" if doc_id else "Payment")
            }
        )
    except Exception as e:
        logging.error(f"[RZP] Order creation failed: {e}")
        return jsonify({'success': False, 'error': f'Failed to create order: {str(e)}'}), 500

    rzp_order_id = order['id']
    save_transaction_record(rzp_order_id, {
        'user_id': user_id or None,
        'amount': price,
        'status': 'pending',
        'utr': rzp_order_id,
        'doc_id': doc_id,
        'client_ip': client_ip,
        'user_agent': user_agent,
        'admin_notes': ';'.join(admin_notes_parts)
    })

    invoice_id = f"INV-{rzp_order_id.replace('order_', '')}" if rzp_order_id.startswith('order_') else f"INV-{rzp_order_id}"
    return jsonify({
        'success': True,
        'app_name': os.getenv('APP_NAME', 'AbhiHub'),
        'app_id': os.getenv('APP_ID', 'com.abhihub.app'),
        'invoice_id': invoice_id,
        'key_id': os.getenv('RAZORPAY_KEY_ID', ''),
        'order_id': rzp_order_id,
        'amount': order['amount'],
        'currency': order.get('currency', currency),
        'prefill': {
            'name': user_name,
            'email': user_email,
            'contact': user_phone
        }
    })


@payments_bp.route('/api/verify-payment', methods=['POST'])
@payments_bp.route('/api/payment/verify', methods=['POST'])
@payments_bp.route('/api/payment/razorpay/verify', methods=['POST'])
def verify_payment():
    """Verifies HMAC-SHA256 signature of Razorpay payment and fulfills order."""
    from methods.razorpay_service import verify_payment_signature, hash_signature
    from data.transactions import get_transaction_record, is_order_completed
    from routes.webhooks import fulfill_order_transaction

    data = request.get_json(silent=True) or {}
    rzp_order_id = str(data.get('razorpay_order_id') or data.get('order_id') or '').strip()
    rzp_payment_id = str(data.get('razorpay_payment_id') or data.get('payment_id') or '').strip()
    rzp_signature = str(data.get('razorpay_signature') or data.get('signature') or '').strip()

    if not all([rzp_order_id, rzp_payment_id, rzp_signature]):
        return jsonify({'success': False, 'error': 'Missing required fields: order_id, payment_id, signature'}), 400

    rec = get_transaction_record(rzp_order_id)
    doc_id = rec.get('doc_id', '')
    if not doc_id:
        notes = rec.get('admin_notes', '')
        for part in notes.split(';'):
            if part.startswith('doc_id='):
                doc_id = part.replace('doc_id=', '').strip()

    if is_order_completed(rzp_order_id):
        return jsonify({
            'success': True,
            'message': 'Payment already verified',
            'redirect_url': f'/payment/receipt?order_id={rzp_order_id}&status=success&doc_id={doc_id}&amount={rec.get("amount", 0)}'
        }), 200

    if not verify_payment_signature(rzp_order_id, rzp_payment_id, rzp_signature):
        logging.error(f"[RZP] Signature mismatch: order={rzp_order_id} pay={rzp_payment_id}")
        try:
            client = init_supabase()
            if client:
                client.table('payment_errors').insert({
                    'user_id': rec.get('user_id'),
                    'order_id': rzp_order_id,
                    'payment_id': rzp_payment_id,
                    'reason': 'signature_mismatch',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }).execute()
        except Exception as err_log:
            logging.debug(f"[RZP] Could not log payment error to DB: {err_log}")
        return jsonify({'success': False, 'error': 'Signature verification failed'}), 400

    amount = float(rec.get('amount', 0))
    user_id = rec.get('user_id') or session.get('user', {}).get('uid', '')
    fulfill_order_transaction(rzp_order_id, amount, doc_id=doc_id, user_id=user_id, source='razorpay_verify')


    try:
        client = init_supabase()
        if client:
            client.table('credit_transactions').update({
                'payment_id': rzp_payment_id,
                'rzp_sig_hash': hash_signature(rzp_signature),
                'captured_at': datetime.now(timezone.utc).isoformat()
            }).eq('order_id', rzp_order_id).execute()
    except Exception as db_err:
        logging.debug(f"[RZP] credit_transactions sig update note: {db_err}")

    return jsonify({
        'success': True,
        'message': 'Payment verified successfully',
        'redirect_url': f'/payment/receipt?order_id={rzp_order_id}&status=success&doc_id={doc_id}&amount={amount}'
    }), 200



@payments_bp.route('/api/user/transactions', methods=['GET'])
@auth_required
def get_user_transactions_api():
    """Fetches recent payment and credit transactions for the logged-in user."""
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
            if not doc_title:
                doc_title = f"Document #{doc_id[:8]}"
        elif 'Credits-' in notes or 'pack=' in notes or 'credits' in notes.lower():
            pack = ''
            for part in notes.split(';'):
                if part.startswith('pack='):
                    pack = part.replace('pack=', '').strip()
                elif part.startswith('purpose=Credits-'):
                    try: pack = part.replace('purpose=Credits-', '').split('-')[0].strip()
                    except Exception: pass
            doc_title = f"Study Pass ({pack or 50} Views)"
        elif 'Tea' in notes or 'Chai' in notes or 'supporter' in notes.lower():
            doc_title = "Community Chai Support"
        else:
            doc_title = "AbhiHub Resource Access"

        status_val = tx.get('status', 'completed')
        is_success = status_val in ['completed', 'verified', 'captured']
        enriched.append({
            'order_id': tx.get('order_id'),
            'amount': tx.get('amount'),
            'status': status_val,
            'doc_id': doc_id,
            'doc_title': doc_title,
            'date': tx.get('updated_at') or tx.get('created_at'),
            'receipt_url': f"/payment/receipt?order_id={tx.get('order_id')}&status={'success' if is_success else 'failed'}&doc_id={doc_id}&amount={tx.get('amount')}"
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
    from methods.wallet_service import (
        get_creator_views_and_earnings,
        VIEW_EARNING_RATE_INR,
        is_creator_verified,
        get_creator_commission_pct,
    )
    from data.pricing import extract_document_pricing
    gate = get_feature_gate(user_id)
    is_rank_eligible = (gate.get('level') or '').lower() in ['contributor', 'power_contributor', 'community_leader']
    is_verified = is_creator_verified(user_id)
    total_views, raw_view_earnings = get_creator_views_and_earnings(user_id)
    view_earnings = raw_view_earnings if is_verified else 0.0
    view_rate = VIEW_EARNING_RATE_INR if is_verified else 0.0
    comm_info = get_creator_commission_pct(user_id)
    creator_share_ratio = comm_info['creator_pct'] / 100.0

    paid_docs = []
    try:
        # Check documents uploaded by creator
        docs_res = supabase.table('documents')\
            .select('id, title, description, is_paid, price, uploader_id, created_at')\
            .eq('uploader_id', str(user_id))\
            .execute()
        for d in (docs_res.data or []):
            p = extract_document_pricing(d)
            if p.get('is_paid') and float(p.get('price', 0) or 0) > 0:
                paid_docs.append({
                    'id': d['id'],
                    'title': d.get('title'),
                    'price': float(p.get('price', 0)),
                    'coupon_code': p.get('coupon_code', '')
                })
    except Exception as e:
        logging.error(f"[CREATOR_EARNINGS] Error loading documents: {e}")

    is_eligible = is_rank_eligible or (len(paid_docs) > 0)

    if not is_eligible:
        return jsonify({
            'success': True,
            'eligible': False,
            'level': gate.get('level'),
            'message': 'Reach Contributor rank to sell paid notes. Upload view earnings are active for verified creators.',
            'is_verified': is_verified,
            'is_view_monetized': is_verified,
            'total_views': total_views,
            'view_rate': view_rate,
            'view_earnings': view_earnings,
            'creator_commission_pct': comm_info['creator_pct'],
            'is_promo': comm_info.get('is_promo', False),
            'commission_status': comm_info.get('reason', ''),
            'paid_notes_count': 0,
            'total_sales': 0,
            'total_earnings': 0.0,
            'combined_earnings': view_earnings,
            'paid_notes': []
        })

    total_sales = 0
    total_earnings = 0.0
    for d in paid_docs:
        try:
            # Check sales in ledger first, fallback to credit_transactions
            ledger_res = supabase.table('wallet_ledger').select('amount, status').eq('doc_id', str(d['id'])).execute()
            if ledger_res.data:
                sales_count = len(ledger_res.data)
                earnings = sum(float(l.get('amount') or 0.0) for l in ledger_res.data)
                gross_amt = round(earnings / creator_share_ratio, 2) if creator_share_ratio > 0 else earnings
            else:
                tx_res = supabase.table('credit_transactions').select('amount, status').ilike('admin_notes', f"%{d['id']}%").execute()
                sales_count = len(tx_res.data or [])
                gross_amt = sum(float(t.get('amount', 0)) for t in (tx_res.data or []))
                earnings = round(gross_amt * creator_share_ratio, 2)

            d['sales_count'] = sales_count
            d['gross_amount'] = round(gross_amt, 2)
            d['earnings'] = round(earnings, 2)
            total_sales += sales_count
            total_earnings += earnings
        except Exception:
            d['sales_count'] = 0
            d['gross_amount'] = 0
            d['earnings'] = 0

    combined_earnings = round(total_earnings + view_earnings, 2)

    return jsonify({
        'success': True,
        'eligible': is_eligible,
        'level': gate.get('level'),
        'is_verified': is_verified,
        'is_view_monetized': is_verified,
        'paid_notes_count': len(paid_docs),
        'total_sales': total_sales,
        'total_earnings': round(total_earnings, 2),
        'total_views': total_views,
        'view_rate': view_rate,
        'view_earnings': view_earnings,
        'creator_commission_pct': comm_info['creator_pct'],
        'is_promo': comm_info.get('is_promo', False),
        'commission_status': comm_info.get('reason', ''),
        'combined_earnings': combined_earnings,
        'paid_notes': paid_docs
    })


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
    """Request a payout using KYC-verified payment details."""
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    amount = data.get('amount')

    # Automatically fetch verified payment details from KYC instead of asking user
    from methods.payment_engine import engine
    kyc = engine.get_kyc(user_id)
    if not kyc or not kyc.get('is_verified'):
        return jsonify({
            'success': False,
            'error': 'KYC verification required before requesting a payout. Please submit and verify your KYC details first.'
        }), 400

    payout_method = kyc.get('preferred_method', 'upi')
    payout_details = {
        'upi_id': kyc.get('upi_id'),
        'account_number': kyc.get('account_number'),
        'ifsc_code': kyc.get('ifsc_code'),
        'account_holder_name': kyc.get('full_name'),
        'bank_name': kyc.get('bank_name'),
        'pan_number': kyc.get('pan_number'),
    }

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


# ─── KYC & Passbook Endpoints ──────────────────────────────────────────────────

@payments_bp.route('/api/user/kyc/submit', methods=['POST'])
@auth_required
def submit_user_kyc():
    from methods.payment_engine import engine
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    ok, msg = engine.submit_kyc(user_id, data)
    return jsonify({'success': ok, 'message' if ok else 'error': msg}), (200 if ok else 400)


@payments_bp.route('/api/user/kyc/status', methods=['GET'])
@auth_required
def get_user_kyc_status():
    from methods.payment_engine import engine
    user_id = session.get('user', {}).get('uid')
    kyc = engine.get_kyc(user_id)
    return jsonify({'success': True, 'kyc': kyc})


@payments_bp.route('/api/user/passbook', methods=['GET'])
@auth_required
def get_user_passbook():
    from methods.payment_engine import engine
    user_id = session.get('user', {}).get('uid')
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = min(100, max(1, int(request.args.get('limit', 20))))
    except (ValueError, TypeError):
        page, limit = 1, 20
    res = engine.get_passbook(user_id, page=page, limit=limit)
    return jsonify(res), (200 if res.get('success') else 500)


@payments_bp.route('/api/user/passbook/download', methods=['GET'])
@auth_required
def download_user_passbook_csv():
    import csv
    import io
    from flask import Response
    from methods.payment_engine import engine
    user_id = session.get('user', {}).get('uid')
    res = engine.get_passbook(user_id, page=1, limit=500)
    if not res.get('success'):
        return jsonify(res), 500

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Description', 'Type', 'Currency', 'Amount', 'Status', 'Unlocks On', 'Reference ID', 'Balance After'])
    for e in res.get('entries', []):
        writer.writerow([
            e.get('date', ''),
            e.get('description', ''),
            e.get('type', ''),
            e.get('currency', ''),
            e.get('amount', ''),
            e.get('status', ''),
            e.get('unlocks_on', '') or '',
            e.get('ref_id', '') or '',
            e.get('balance_after', '') if e.get('balance_after') is not None else ''
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=passbook_{user_id[:8]}.csv'}
    )
