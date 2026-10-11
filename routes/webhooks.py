"""
AbhiHub Webhooks Blueprint.
Handles third-party provider server callbacks and webhooks:
- Cloudinary async upload & post-processing webhook
- PhonePe payment server-to-server webhook & user redirect callback
"""
import os
import logging
import threading
from urllib.parse import urlparse

from flask import (
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    session,
)

webhooks_bp = Blueprint('webhooks', __name__)


# ─── Cloudinary Webhook Helpers & Route ──────────────────────────────────────

def _is_safe_storage_url(url_str: str) -> bool:
    """Validate that a URL is HTTPS and points strictly to trusted media storage CDNs."""
    if not url_str or not isinstance(url_str, str):
        return False
    try:
        parsed = urlparse(url_str)
        return parsed.scheme == 'https' and parsed.hostname in {
            'res.cloudinary.com',
            'storage.googleapis.com',
            'firebasestorage.googleapis.com',
            'abhi-hub.appspot.com',
            'abhihub-b94f6.appspot.com',
            'abhihub-b94f6.firebasestorage.app'
        }
    except Exception:
        return False


def _async_compress_and_update(public_id, secure_url, resource_type, filename):
    """Background worker task: downloads uploaded file, applies compression, and updates storage."""
    try:
        if not _is_safe_storage_url(secure_url):
            logging.warning(f"[SECURITY] Refusing to fetch unsafe/non-whitelisted URL in async worker: {secure_url}")
            return

        import requests
        from methods.cloudinary_upload import compress_image, compress_pdf, upload_file_to_cloudinary
        resp = requests.get(secure_url, timeout=30)
        if resp.status_code != 200:
            return
        
        file_bytes = resp.content
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        
        compressed_bytes = file_bytes
        if resource_type == 'image':
            compressed_bytes = compress_image(file_bytes, format='JPEG', quality=80)
        elif ext == 'pdf':
            compressed_bytes = compress_pdf(file_bytes)
            
        if len(compressed_bytes) < len(file_bytes):
            import io
            upload_file_to_cloudinary(
                io.BytesIO(compressed_bytes),
                filename,
                user_id="async_worker",
                folder="uploads",
                compress=False
            )
            logging.info(f"✓ Async background compression complete for {public_id}: {len(file_bytes)} ➔ {len(compressed_bytes)} bytes")
    except Exception as e:
        logging.error(f"Async post-upload worker error for {public_id}: {e}")


@webhooks_bp.route('/api/webhooks/cloudinary-upload', methods=['POST'])
def webhook_cloudinary_upload():
    """Webhook triggered on storage upload completion to run async background compression."""
    webhook_secret = os.getenv('CLOUDINARY_WEBHOOK_SECRET')
    if webhook_secret:
        auth_hdr = request.headers.get('X-Webhook-Secret') or request.headers.get('Authorization', '')
        if auth_hdr.replace('Bearer ', '').strip() != webhook_secret.strip():
            return jsonify({'success': False, 'message': 'Unauthorized webhook call'}), 401

    data = request.get_json(silent=True) or request.form.to_dict()
    public_id = data.get('public_id')
    secure_url = data.get('secure_url') or data.get('url')
    resource_type = data.get('resource_type', 'raw')
    filename = data.get('original_filename') or f"{public_id}.pdf"
    
    if not public_id or not secure_url:
        return jsonify({'success': False, 'message': 'Missing upload payload'}), 400
        
    if not _is_safe_storage_url(secure_url):
        return jsonify({'success': False, 'message': 'Invalid storage URL'}), 400

    thread = threading.Thread(
        target=_async_compress_and_update,
        args=(public_id, secure_url, resource_type, filename)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Async compression queued'}), 200


# ─── PhonePe Webhook & Redirect Route ────────────────────────────────────────

def _fulfill_phonepe_transaction(order_id: str, verified_amount: float, doc_id: str = '', user_id: str = '', source: str = 'redirect'):
    """
    Secure & Idempotent PhonePe Order Fulfillment:
    1. Checks if transaction was already completed (prevents replay attacks & duplicate wallet credit).
    2. Persists transaction to safe local store + Supabase sync.
    3. Credits creator wallet via `credit_creator_for_purchase` (guaranteed once).
    4. Records Tea Supporter on public wall if community contribution.
    5. Unlocks doc_id in session if running in request context.
    """
    from data.transactions import save_transaction_record, is_order_completed, get_transaction_record

    is_already_completed = is_order_completed(order_id)
    rec = get_transaction_record(order_id)
    admin_notes_prev = rec.get('admin_notes', '')
    saved_user_id = rec.get('user_id', '')

    eff_uid = user_id or saved_user_id or (session.get('user', {}).get('uid') if session else None) or (session.get('user', {}).get('id') if session else None)

    try:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        user_agent = request.headers.get('User-Agent', '')[:255]
    except Exception:
        client_ip = ''
        user_agent = 'PhonePe Webhook'

    save_transaction_record(order_id, {
        'user_id': eff_uid or None,
        'amount': verified_amount,
        'status': 'completed',
        'utr': order_id,
        'client_ip': client_ip,
        'user_agent': user_agent,
        'admin_notes': f"{admin_notes_prev};verified_via={source}".strip(';')
    })

    is_credits = 'Credits-' in admin_notes_prev or 'pack=' in admin_notes_prev or 'credits' in admin_notes_prev.lower()
    if is_credits:
        if not is_already_completed:
            pack_size = 0
            for part in admin_notes_prev.split(';'):
                if part.startswith('pack='):
                    try: pack_size = int(part.replace('pack=', '').strip())
                    except: pass
                elif part.startswith('purpose=Credits-'):
                    try: pack_size = int(part.replace('purpose=Credits-', '').split('-')[0].strip())
                    except: pass
            if pack_size <= 0:
                pack_size = int(verified_amount / 2) if verified_amount > 0 else 50

            if eff_uid:
                try:
                    from data.db import get_client
                    from cache_manager import get_cache
                    from data.pricing import log_credit_transaction
                    db = get_client()
                    if db:
                        prof_res = db.table('profiles').select('paper_quota_remaining').eq('id', eff_uid).execute()
                        curr_q = 19
                        if prof_res.data:
                            curr_q = prof_res.data[0].get('paper_quota_remaining')
                            if curr_q is None:
                                curr_q = 19
                        new_q = curr_q + pack_size
                        db.table('profiles').update({'paper_quota_remaining': new_q}).eq('id', eff_uid).execute()

                        if session and 'paper_quota' in session and isinstance(session['paper_quota'], dict):
                            session['paper_quota']['credits'] = new_q
                        elif session:
                            session['paper_quota'] = {'credits': new_q, 'total_views': 0}
                        if session:
                            session.modified = True

                        cache = get_cache()
                        if cache and hasattr(cache, 'l1'):
                            cache.l1.delete(f"user:quota:{eff_uid}")
                        log_credit_transaction(eff_uid, pack_size, 'earn', f"Bought {pack_size} Views Pack (₹{verified_amount})")
                        logging.info(f"[_fulfill_phonepe_transaction] Added {pack_size} credits to user {eff_uid}. New quota: {new_q}")
                except Exception as cred_err:
                    logging.error(f"[_fulfill_phonepe_transaction] Error crediting quota: {cred_err}")
    elif not doc_id and not is_credits:
        try:
            from data.tea_supporters import add_tea_supporter
            s_name = ''
            s_msg = ''
            for part in admin_notes_prev.split(';'):
                if part.startswith('name='):
                    s_name = part.replace('name=', '').strip()
                elif part.startswith('msg='):
                    s_msg = part.replace('msg=', '').strip()

            if not s_name and session and 'user' in session:
                s_name = session.get('user', {}).get('name', '')

            add_tea_supporter(order_id, s_name or 'Generous Friend', verified_amount, s_msg, user_id=eff_uid)
        except Exception as e:
            logging.warning(f"[_fulfill_phonepe_transaction] Tea supporter recording: {e}")

    if doc_id and not is_already_completed:
        try:
            from methods.wallet_service import credit_creator_for_purchase
            credit_creator_for_purchase(order_id, doc_id, verified_amount)
        except Exception as e:
            logging.error(f"[_fulfill_phonepe_transaction] Creator credit error: {e}")

    if doc_id and session is not None:
        try:
            purchased = session.get('purchased_documents', [])
            if doc_id not in purchased:
                purchased.append(doc_id)
                session['purchased_documents'] = purchased
                session.modified = True
        except Exception:
            pass

    return True


@webhooks_bp.route('/api/payment/phonepe/callback', methods=['POST'])
def payment_phonepe_callback():
    """Webhook callback endpoint for PhonePe server-to-server notifications."""
    from methods.phonepe_service import parse_phonepe_callback_data, check_phonepe_status
    from data.transactions import get_transaction_record

    raw_data = request.get_json(silent=True) or request.form.to_dict() or {}
    cb_data = parse_phonepe_callback_data(raw_data)

    order_id = (
        cb_data.get('data', {}).get('merchantOrderId')
        or cb_data.get('data', {}).get('merchantTransactionId')
        or cb_data.get('merchantOrderId')
        or request.args.get('order_id', '')
    )

    if order_id:
        status_res = check_phonepe_status(order_id)
        if status_res.get('is_paid'):
            amount = (status_res.get('data', {}).get('amount') or 0) / 100.0
            doc_id = ''
            rec = get_transaction_record(order_id)
            notes = rec.get('admin_notes') or ''
            for part in notes.split(';'):
                if part.startswith('doc_id='):
                    doc_id = part.replace('doc_id=', '').strip()
            _fulfill_phonepe_transaction(order_id, amount, doc_id=doc_id, source="webhook_callback")

    return jsonify({"status": "SUCCESS"}), 200


@webhooks_bp.route('/payment/phonepe/redirect', methods=['GET', 'POST'])
def payment_phonepe_redirect():
    """User redirect destination upon returning from PhonePe payment gateway."""
    order_id = (
        request.args.get('order_id')
        or request.args.get('merchantOrderId')
        or request.form.get('merchantOrderId')
        or request.form.get('transactionId')
        or request.form.get('merchantTransactionId', '')
    )
    doc_id = request.args.get('doc_id', '').strip()
    url_user_id = request.args.get('user_id', '').strip()
    session_user_id = (session.get('user', {}).get('uid') or session.get('user', {}).get('id', '')) if session else ''
    user_id = url_user_id or session_user_id

    from methods.phonepe_service import check_phonepe_status
    from data.transactions import save_transaction_record, get_transaction_record
    status_res = check_phonepe_status(order_id)

    if status_res.get('is_paid'):
        amount = (status_res.get('data', {}).get('amount') or 0) / 100.0
        _fulfill_phonepe_transaction(order_id, amount, doc_id=doc_id, user_id=user_id, source="redirect")
        rec = get_transaction_record(order_id)
        admin_notes = rec.get('admin_notes', '')
        is_credits = 'Credits-' in admin_notes or 'pack=' in admin_notes or 'credits' in admin_notes.lower()
        if is_credits:
            pack_size = 0
            for part in admin_notes.split(';'):
                if part.startswith('pack='):
                    try: pack_size = int(part.replace('pack=', '').strip())
                    except: pass
                elif part.startswith('purpose=Credits-'):
                    try: pack_size = int(part.replace('purpose=Credits-', '').split('-')[0].strip())
                    except: pass
            return redirect(url_for('site.payment_receipt_page', order_id=order_id, status='success', is_credits=1, pack=pack_size, amount=f"{amount:.2f}"))
        return redirect(url_for('site.payment_receipt_page', order_id=order_id, status='success', doc_id=doc_id, amount=f"{amount:.2f}"))

    save_transaction_record(order_id, {
        'status': 'failed',
        'admin_notes': f"doc_id={doc_id};error={status_res.get('message')}"
    })
    error_msg = status_res.get('message') or "Payment was not completed."
    return redirect(url_for('site.payment_receipt_page', order_id=order_id, status='failed', doc_id=doc_id, error=error_msg))
