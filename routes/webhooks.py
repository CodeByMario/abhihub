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


# ─── Razorpay & Order Fulfillment ──────────────────────────────────────────

def fulfill_order_transaction(order_id: str, verified_amount: float, doc_id: str = '', user_id: str = '', source: str = 'razorpay'):
    """
    Secure & Idempotent Order Fulfillment:
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
        user_agent = 'Razorpay Webhook'


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
                    from methods.payment_engine import engine
                    from cache_manager import get_cache
                    new_q = engine.credit_views(
                        eff_uid,
                        pack_size,
                        reason='pack_purchase',
                        source='razorpay',
                        ref_id=order_id
                    )
                    if session:
                        session['paper_quota'] = {'credits': new_q, 'total_views': 0}
                        session.modified = True
                    cache = get_cache()
                    if cache and hasattr(cache, 'l1'):
                        cache.l1.delete(f"user:quota:{eff_uid}")
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
            from methods.payment_engine import engine
            engine.credit_creator(order_id, doc_id, verified_amount)
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

_fulfill_phonepe_transaction = fulfill_order_transaction


@webhooks_bp.route('/api/webhooks/razorpay', methods=['POST'])
def razorpay_webhook():
    """Webhook callback endpoint for Razorpay server-to-server notifications."""
    from methods.razorpay_service import verify_webhook_signature
    from data.transactions import get_transaction_record, save_transaction_record

    signature = request.headers.get('X-Razorpay-Signature', '')
    raw_payload = request.get_data().decode('utf-8', errors='replace')

    if not verify_webhook_signature(raw_payload, signature):
        logging.warning('[RZP WEBHOOK] Invalid signature — rejected')
        return jsonify({'error': 'Invalid signature'}), 400

    payload = request.get_json(silent=True) or {}
    event = payload.get('event')
    payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    order_id = payment_entity.get('order_id')
    payment_id = payment_entity.get('id')

    if event == 'payment.captured' and order_id:
        amount = (payment_entity.get('amount') or 0) / 100.0
        rec = get_transaction_record(order_id)
        doc_id = rec.get('doc_id', '')
        if not doc_id:
            notes = rec.get('admin_notes', '')
            for part in notes.split(';'):
                if part.startswith('doc_id='):
                    doc_id = part.replace('doc_id=', '').strip()
        user_id = rec.get('user_id', '')
        fulfill_order_transaction(order_id, amount, doc_id=doc_id, user_id=user_id, source="razorpay_webhook")
        logging.info(f'[RZP WEBHOOK] Captured order: {order_id} (pay_id={payment_id})')

    elif event == 'payment.failed' and order_id:
        save_transaction_record(order_id, {
            'status': 'failed',
            'admin_notes': f"failed_payment_id={payment_id}"
        })
        logging.info(f'[RZP WEBHOOK] Payment failed for order: {order_id}')

    return jsonify({'status': 'ok'}), 200

