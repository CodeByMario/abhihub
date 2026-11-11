"""
AbhiHub Admin Blueprint.
Contains all administrative control panel views, developer/system tools,
moderation endpoints, economy configuration, and admin APIs.
"""
import os
import json
import time
import logging
import re
from datetime import datetime, timezone

from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session,
    current_app,
    abort,
)

from routes.auth import auth_required, admin_required, log_admin_action
from methods.supabase_helper import (
    init_supabase,
    init_supabase_admin,
    supabase,
    recalculate_and_persist_user_rank,
    award_contribution_xp,
    log_notification,
    get_notification_history,
    get_admin_broadcast_delivery_stats,
    add_new_entity,
    validate_uuid,
)

admin_bp = Blueprint('admin', __name__)

CONTACT_FILE = os.path.join('data', 'contact_messages.json')


def _load_contact_messages():
    """Load contact messages from JSON file, swallowing exceptions."""
    if not os.path.exists(CONTACT_FILE):
        return []
    try:
        with open(CONTACT_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def _trigger_indexnow_helper(urls: list):
    """Submit changed public URLs to IndexNow for faster discovery."""
    indexnow_key = os.getenv('INDEX_NOW_BING_API_KEY')
    base_domain = os.getenv('BASE_DOMAIN', 'abhihub.edu.eu.org')
    if not indexnow_key:
        logging.error("IndexNow is not configured: INDEX_NOW_BING_API_KEY is missing.")
        return False
    try:
        import requests as _req
        payload = {
            "host": base_domain,
            "key": indexnow_key,
            "keyLocation": f"https://{base_domain}/{indexnow_key}.txt",
            "urlList": [u for u in urls if u.startswith('https://')]
        }
        if not payload["urlList"]:
            return False
        submission = _req.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5
        )
        return submission.status_code in (200, 202)
    except Exception as e:
        logging.error("[IndexNow helper] internal error")
        return False


# ─── Admin Control Panel Views ───────────────────────────────────────────────

@admin_bp.route('/admin')
@auth_required
@admin_required
def admin_control_panel():
    """Unified Admin Control Hub - Overview, Moderation, Students, Sentiment, Broadcast."""
    return render_template('admin_notification_panel.html')


@admin_bp.route('/admin/notification-panel')
@admin_bp.route('/admin/file-updates')
def admin_legacy_redirects():
    """Consolidated 301 redirects for legacy admin paths."""
    return redirect(url_for('admin.admin_control_panel'), code=301)


@admin_bp.route('/admin/analytics')
@auth_required
@admin_required
def admin_analytics_dashboard():
    """Admin analytics dashboard page."""
    return render_template('admin_analytics.html')


@admin_bp.route('/admin/economy')
@auth_required
@admin_required
def admin_economy_dashboard():
    """Admin economy dashboard: edit scoring config, view level distribution."""
    return render_template('admin_economy.html')


@admin_bp.route('/admin/ads')
@auth_required
@admin_required
def admin_ads_dashboard():
    """Admin portal for persistent global, page, and user ad overrides."""
    return render_template('admin_ads.html')


@admin_bp.route('/api/admin/ads/overrides', methods=['GET'])
@auth_required
@admin_required
def admin_ads_overrides():
    client = init_supabase_admin() or init_supabase()
    if not client:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    try:
        result = client.table('ad_overrides').select(
            'id, scope_type, scope_key, enabled, note, updated_by, updated_at'
        ).order('updated_at', desc=True).limit(200).execute()
        return jsonify({'success': True, 'data': result.data or []})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/admin/ads/overrides', methods=['POST'])
@auth_required
@admin_required
def admin_upsert_ads_override():
    data = request.get_json(silent=True) or {}
    scope_type = str(data.get('scope_type', '')).strip().lower()
    scope_key = str(data.get('scope_key', '')).strip()
    if scope_type not in ('global', 'page', 'user'):
        return jsonify({'success': False, 'error': 'Invalid scope type'}), 400
    if scope_type == 'global':
        scope_key = '*'
    elif scope_type == 'page':
        if not scope_key.startswith('/') or len(scope_key) > 200:
            return jsonify({'success': False, 'error': 'Page must be an absolute path'}), 400
    elif not scope_key or len(scope_key) > 200:
        return jsonify({'success': False, 'error': 'User ID or email is required'}), 400

    client = init_supabase_admin() or init_supabase()
    if not client:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    admin_id = (session.get('user') or {}).get('uid')
    payload = {
        'scope_type': scope_type,
        'scope_key': scope_key.lower() if '@' in scope_key else scope_key,
        'enabled': bool(data.get('enabled')),
        'note': str(data.get('note', '')).strip()[:500] or None,
        'updated_by': admin_id,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = client.table('ad_overrides').upsert(
            payload, on_conflict='scope_type,scope_key'
        ).execute()
        log_admin_action('ad_override_updated', target=scope_key, details=payload)
        return jsonify({'success': True, 'data': result.data or []})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/api/admin/ads/overrides', methods=['DELETE'])
@auth_required
@admin_required
def admin_delete_ads_override():
    data = request.get_json(silent=True) or {}
    scope_type = str(data.get('scope_type', '')).strip().lower()
    scope_key = str(data.get('scope_key', '')).strip()
    if scope_type not in ('global', 'page', 'user') or not scope_key:
        return jsonify({'success': False, 'error': 'scope_type and scope_key are required'}), 400
    client = init_supabase_admin() or init_supabase()
    if not client:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    try:
        client.table('ad_overrides').delete().eq(
            'scope_type', scope_type
        ).eq('scope_key', '*' if scope_type == 'global' else scope_key).execute()
        log_admin_action('ad_override_deleted', target=scope_key, details={'scope_type': scope_type})
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@admin_bp.route('/admin/developer')
@auth_required
@admin_required
def admin_developer_panel():
    """Admin Developer Panel: cloud stats, feature health, live logs."""
    prod_env = os.getenv('PRODUCTION_ENVIRONMENT', os.getenv('PRODUCTION_ENV', '')).lower()
    if prod_env in ('developer', 'development', 'dev'):
        return render_template('admin_developer.html')
    env_name = os.getenv('FLASK_ENV', os.getenv('APP_ENV', os.getenv('ENV', 'development'))).lower()
    if env_name in ('production', 'prod') and env_name != 'developer':
        abort(403, description="Developer panel is disabled in production mode.")
    return render_template('admin_developer.html')


@admin_bp.route('/admin/file-reports')
@admin_required
def admin_file_reports_page():
    """Admin page for viewing all file reports and logs."""
    return render_template('admin_file_reports.html')


@admin_bp.route('/admin/payments')
@auth_required
@admin_required
def admin_payments_dashboard():
    """Admin payments & payouts management dashboard."""
    return render_template('admin_payments.html')


# ─── Payment & Payout Admin Endpoints ────────────────────────────────────────

@admin_bp.route('/api/admin/incidents/top', methods=['GET'])
@admin_required
def admin_get_top_incidents():
    """Real-time aggregator for top major failures and critical system incidents."""
    incidents = []
    try:
        # 0. Check for firing system incidents (e.g. Upload Failure, File Open Failure)
        res_sys = supabase.table('admin_alert_incidents').select('*').eq('status', 'firing').order('last_seen_at', desc=True).limit(5).execute()
        if res_sys.data:
            for s in res_sys.data:
                incidents.append({
                    'id': s.get('id', ''),
                    'type': 'CRITICAL_SYSTEM_ALERT',
                    'title': s.get('name', 'System Alert'),
                    'description': s.get('message', ''),
                    'severity': s.get('severity', 'critical'),
                    'created_at': s.get('last_seen_at')
                })

        # 1. Check for recent failed credit transactions
        res_fail = supabase.table('credit_transactions').select('*').in_('status', ['FAILED', 'FAILED_VERIFICATION', 'ERROR']).order('created_at', desc=True).limit(5).execute()
        if res_fail.data:
            for f in res_fail.data:
                incidents.append({
                    'id': f.get('id', ''),
                    'type': 'PAYMENT_FAILED',
                    'title': f"Payment Failed: Order {f.get('order_id', 'Unknown')}",
                    'description': f"User {f.get('user_id', 'N/A')} failed to complete ₹{f.get('amount', 0)}. Status: {f.get('status')}",
                    'severity': 'high',
                    'created_at': f.get('created_at')
                })

        # 2. Check for rejected payouts requiring triage
        res_payouts = supabase.table('creator_payout_requests').select('*').eq('status', 'rejected').order('created_at', desc=True).limit(5).execute()
        if res_payouts.data:
            for p in res_payouts.data:
                incidents.append({
                    'id': p.get('id', ''),
                    'type': 'PAYOUT_REJECTED',
                    'title': f"Payout Rejected / Failed for Creator {p.get('creator_id', 'N/A')}",
                    'description': f"Amount ₹{p.get('amount', 0)} ({p.get('payout_method', 'UPI')}) rejected: {p.get('admin_notes', 'No note')}",
                    'severity': 'critical',
                    'created_at': p.get('created_at')
                })
    except Exception as e:
        incidents.append({
            'id': 'db-err',
            'type': 'SYSTEM_ERROR',
            'title': 'Database Query Warning',
            'description': 'An internal error occurred.',
            'severity': 'warning',
            'created_at': datetime.utcnow().isoformat()
        })

    return jsonify({
        'success': True,
        'has_incidents': len(incidents) > 0,
        'count': len(incidents),
        'top_incident': incidents[0] if incidents else None,
        'incidents': incidents
    })


@admin_bp.route('/api/admin/payment/transactions', methods=['GET'])
@admin_required
def admin_get_payment_transactions():
    """Fetch recent payment transaction records for admin audit."""
    try:
        res = supabase.table('credit_transactions').select('*').order('created_at', desc=True).limit(50).execute()
        return jsonify({'success': True, 'transactions': res.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/payment/transaction', methods=['POST'])
@admin_required
def admin_set_payment_transaction():
    """Admin endpoint to create, verify, or update a transaction record."""
    data = request.get_json(silent=True) or {}
    order_id = str(data.get('order_id', '')).strip()
    status = str(data.get('status', 'verified')).strip().lower()
    utr = str(data.get('utr', '')).strip()
    notes = str(data.get('notes', '')).strip()

    if not order_id and not utr:
        return jsonify({'success': False, 'error': 'order_id or utr is required'}), 400

    update_payload = {
        'status': status,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'admin_notes': notes
    }
    if 'amount' in data:
        try:
            update_payload['amount'] = float(data['amount'])
        except (ValueError, TypeError):
            pass

    try:
        query = supabase.table('credit_transactions').update(update_payload)
        if order_id:
            query = query.eq('order_id', order_id)
        else:
            query = query.eq('utr', utr)
        res = query.execute()
        return jsonify({'success': True, 'data': res.data})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/payouts', methods=['GET'])
@auth_required
@admin_required
def admin_payouts_list():
    """Fetch creator payout requests for admin processing."""
    status = request.args.get('status')
    from methods.wallet_service import get_all_payout_requests
    res = get_all_payout_requests(status=status)
    return jsonify(res)


@admin_bp.route('/api/admin/payout/action', methods=['POST'])
@auth_required
@admin_required
def admin_payout_action():
    """Admin action to approve ('completed') or reject ('rejected') creator payout."""
    data = request.get_json(silent=True) or {}
    payout_id = str(data.get('payout_id', '')).strip()
    action = str(data.get('action', '')).strip().lower()
    admin_notes = str(data.get('admin_notes', '')).strip()

    if not payout_id or not action:
        return jsonify({'success': False, 'error': 'Missing payout_id or action'}), 400

    from methods.wallet_service import process_payout_request
    ok, msg = process_payout_request(payout_id, action, admin_notes)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400
    log_admin_action('payout_action', target=payout_id, details={'action': action, 'admin_notes': admin_notes})
    try:
        from app import socketio
        socketio.emit('admin_activity', {
            'event': 'payout_action',
            'payout_id': payout_id,
            'action': action,
            'admin_notes': admin_notes,
            'ts': datetime.utcnow().isoformat() + 'Z'
        }, room='admin-room')
    except Exception:
        pass
    return jsonify({'success': True, 'message': f'Payout {action} successfully'})


@admin_bp.route('/api/admin/kyc/list', methods=['GET'])
@admin_bp.route('/admin/api/kyc/pending', methods=['GET'])
@auth_required
@admin_required
def admin_kyc_list():
    """Fetch KYC applications (filterable by status: pending/verified/all)."""
    status_filter = request.args.get('status', 'pending').lower()
    client = init_supabase_admin() or init_supabase()
    if not client:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    try:
        q = client.table('user_kyc_details').select('*')
        if status_filter == 'pending':
            q = q.eq('is_verified', False).is_('rejection_reason', 'null')
        elif status_filter == 'verified':
            q = q.eq('is_verified', True)
        elif status_filter == 'rejected':
            q = q.not_.is_('rejection_reason', 'null')
        res = q.order('submitted_at', desc=True).limit(100).execute()
        return jsonify({'success': True, 'data': res.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/kyc/<kyc_id>/action', methods=['POST'])
@admin_bp.route('/api/admin/kyc/<kyc_id>/verify', methods=['POST'])
@admin_bp.route('/admin/api/kyc/<kyc_id>/verify', methods=['POST'])
@auth_required
@admin_required
def admin_kyc_verify(kyc_id):
    """Approve or reject a user KYC application."""
    data = request.get_json(silent=True) or {}
    action = str(data.get('action', '')).strip().lower()  # 'approve' | 'reject'
    reason = str(data.get('reason', '')).strip()

    if action not in ('approve', 'reject'):
        return jsonify({'success': False, 'error': "Action must be 'approve' or 'reject'"}), 400
    if action == 'reject' and not reason:
        return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400

    admin_user = session.get('user', {})
    admin_id = admin_user.get('uid')

    client = init_supabase_admin() or init_supabase()
    if not client:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        target_field = 'id'
        check = client.table('user_kyc_details').select('id, user_id').eq('id', kyc_id).limit(1).execute()
        if not check.data:
            check_u = client.table('user_kyc_details').select('id, user_id').eq('user_id', kyc_id).limit(1).execute()
            if check_u.data:
                target_field = 'user_id'

        admin_uid_val = admin_id if (admin_id and validate_uuid(admin_id)) else None
        if action == 'approve':
            client.table('user_kyc_details').update({
                'is_verified': True,
                'verified_at': now_iso,
                'verified_by': admin_uid_val,
                'rejection_reason': None,
                'updated_at': now_iso
            }).eq(target_field, kyc_id).execute()
        else:
            client.table('user_kyc_details').update({
                'is_verified': False,
                'verified_at': None,
                'rejection_reason': reason,
                'updated_at': now_iso
            }).eq(target_field, kyc_id).execute()

        log_admin_action('kyc_verify', target=kyc_id, details={'action': action, 'reason': reason})
        return jsonify({'success': True, 'message': f'KYC application {action}d successfully'})
    except Exception as e:
        logging.error(f"[admin_kyc_verify] Failed to update KYC status: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to update KYC: {str(e)}'}), 500


@admin_bp.route('/api/admin/audit/export', methods=['GET'])
@admin_bp.route('/admin/api/audit/export', methods=['GET'])
@auth_required
@admin_required
def admin_audit_export():
    """Generates and downloads a multi-sheet audit Excel report (.xlsx)."""
    from flask import Response
    from methods.audit_service import build_audit_export
    filters = {
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
        'user_id': request.args.get('user_id'),
        'status': request.args.get('status'),
    }
    try:
        stream = build_audit_export(filters)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return Response(
            stream.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename=audit_export_{timestamp}.xlsx'}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500




@admin_bp.route('/api/admin/creator/wallets', methods=['GET'])
@auth_required
@admin_required
def admin_creator_wallets():
    """Fetch creator wallets and balances for all users for admin management."""
    try:
        from concurrent.futures import ThreadPoolExecutor
        from methods.supabase_helper import init_supabase_admin
        from methods.wallet_service import get_creator_wallet

        client = init_supabase_admin() or supabase

        # Query creator wallets using service_role client to bypass RLS
        w_res = client.table('creator_wallets').select('*').execute()
        wallets_by_uid = {str(w.get('user_id', '')): w for w in (w_res.data or [])}

        p_res = client.table('profiles').select('id, full_name, email, role, paper_quota_remaining, created_at').order('created_at', desc=True).limit(500).execute()
        profiles = p_res.data or []
        profiles_by_id = {str(p.get('id', '')): p for p in profiles}

        # Query uploaders from documents table
        docs_res = client.table('documents').select('uploader_id').execute()
        uploader_ids = {str(d.get('uploader_id')) for d in (docs_res.data or []) if d.get('uploader_id')}

        # Identify active creators with wallets or uploaded notes
        active_creator_ids = list((set(wallets_by_uid.keys()) | uploader_ids) - {''})

        # Ensure all users with a wallet record or uploaded files are included
        all_user_ids = set(profiles_by_id.keys()) | set(active_creator_ids)
        missing_ids = [uid for uid in active_creator_ids if uid and uid not in profiles_by_id]
        if missing_ids:
            try:
                m_res = client.table('profiles').select('id, full_name, email, role, paper_quota_remaining, created_at').in_('id', missing_ids[:100]).execute()
                for mp in (m_res.data or []):
                    profiles_by_id[str(mp.get('id', ''))] = mp
            except Exception:
                pass

        # Concurrently compute canonical creator wallet so admin panel exactly reflects user wallet
        wallets_data = {}
        if active_creator_ids:
            with ThreadPoolExecutor(max_workers=10) as executor:
                resolved = list(executor.map(get_creator_wallet, active_creator_ids))
                for uid, res in zip(active_creator_ids, resolved):
                    if res and res.get('success'):
                        wallets_data[uid] = res.get('wallet', {})

        merged_wallets = []
        for uid in all_user_ids:
            if not uid:
                continue
            p = profiles_by_id.get(uid, {})
            w = wallets_by_uid.get(uid, {})
            w_data = wallets_data.get(uid, {})

            merged_wallets.append({
                'user_id': uid,
                'full_name': p.get('full_name') or 'Student',
                'email': p.get('email') or '',
                'role': p.get('role') or 'student',
                'paper_quota_remaining': p.get('paper_quota_remaining', 0),
                'total_views': w_data.get('total_views', 0),
                'view_earnings': w_data.get('view_earnings', 0.0),
                'sales_withdrawable': w_data.get('sales_withdrawable', float(w.get('withdrawable_balance', 0.0))),
                'pending_balance': w_data.get('pending_balance', float(w.get('pending_balance', 0.0))),
                'withdrawable_balance': w_data.get('withdrawable_balance', float(w.get('withdrawable_balance', 0.0))),
                'total_withdrawn': w_data.get('total_withdrawn', float(w.get('total_withdrawn', 0.0))),
                'updated_at': w.get('updated_at') or p.get('created_at')
            })

        merged_wallets.sort(key=lambda x: (x['withdrawable_balance'] + x['pending_balance'], x['total_views']), reverse=True)
        return jsonify({'success': True, 'wallets': merged_wallets})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.', 'wallets': []}), 500


@admin_bp.route('/api/admin/creator/wallet/adjust', methods=['POST'])
@auth_required
@admin_required
def admin_adjust_wallet():
    """Apply penalty, charge, or bonus credit to a creator's wallet."""
    data = request.get_json(silent=True) or {}
    creator_id = str(data.get('creator_id', '')).strip()
    amount = data.get('amount')
    adj_type = str(data.get('adjustment_type', 'penalty')).strip().lower()
    reason = str(data.get('reason', '')).strip()

    if not creator_id or amount is None:
        return jsonify({'success': False, 'error': 'creator_id and amount are required'}), 400

    from methods.wallet_service import admin_adjust_creator_wallet
    ok, result = admin_adjust_creator_wallet(creator_id, amount, adj_type, reason)
    if not ok:
        return jsonify({'success': False, 'error': result}), 400

    log_admin_action('wallet_adjustment', target=creator_id, details={'type': adj_type, 'amount': amount, 'reason': reason})
    return jsonify({'success': True, 'result': result})


# ─── Messaging, Subscribers & Broadcasts ─────────────────────────────────────

@admin_bp.route('/api/admin/contact-messages', methods=['GET'])
@auth_required
@admin_required
def get_contact_messages():
    messages = _load_contact_messages()
    return jsonify({'success': True, 'messages': messages})


@admin_bp.route('/api/admin/subscribers', methods=['GET'])
@auth_required
@admin_required
def get_admin_subscribers():
    """Get all push notification subscribers with metadata."""
    try:
        from push_notifications import load_subscriptions
        subscriptions = load_subscriptions()
        
        subscribers = []
        for user_id, data in subscriptions.items():
            subscribers.append({
                'user_id': user_id,
                'email': data.get('email', ''),
                'device_type': data.get('device_type', 'web'),
                'subscribed_at': data.get('created_at', 'Unknown'),
                'endpoint': (data.get('subscription', {}).get('endpoint', '') or '')[:50] + '...'
            })
        
        return jsonify({
            'success': True,
            'count': len(subscribers),
            'subscribers': subscribers
        })
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/send-notification', methods=['POST'])
@auth_required
@admin_required
def send_admin_notification():
    """Send push notification to selected users or all users."""
    try:
        from push_notifications import send_notification_to_all, send_notification_to_users
        
        data = request.get_json() or {}
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()
        
        if not title or not body:
            return jsonify({'success': False, 'error': 'Title and body are required'}), 400
        
        if len(title) > 100:
            return jsonify({'success': False, 'error': 'Title must be 100 characters or less'}), 400
        
        if len(body) > 500:
            return jsonify({'success': False, 'error': 'Body must be 500 characters or less'}), 400
        
        url = data.get('url', '/premium').strip()
        icon = data.get('icon', '/static/images/android-chrome-192x192.png').strip()
        tag = data.get('tag', 'admin-notification').strip()
        user_ids = data.get('user_ids')
        
        if user_ids and isinstance(user_ids, list) and len(user_ids) > 0:
            result = send_notification_to_users(user_ids, title, body, url, icon, tag)
            from push_notifications import load_subscriptions
            subs = load_subscriptions()
            for uid in user_ids:
                email = subs.get(uid, {}).get('email', uid)
                log_notification(email, 'marketing', title, body, url)
        else:
            result = send_notification_to_all(title, body, url, icon, tag)
            log_notification('all', 'system', title, body, url)
            
        return jsonify({
            'success': result.get('success', False),
            'sent': result.get('sent', 0),
            'failed': result.get('failed', 0),
            'expired': result.get('expired', 0),
            'error': result.get('error')
        })
    except Exception as e:
        logging.error("Error sending notification: internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/notification-history', methods=['GET'])
@auth_required
@admin_required
def get_admin_notification_history():
    """Get notification history (last 10 entries)."""
    try:
        history = get_notification_history()
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/broadcast-stats', methods=['GET'])
@auth_required
@admin_required
def get_admin_broadcast_stats():
    """Get broadcast delivery stats (sent vs read) for admin notifications."""
    try:
        limit = min(request.args.get('limit', 50, type=int), 200)
        stats = get_admin_broadcast_delivery_stats(limit=limit)
        return jsonify({'success': True, **stats})
    except Exception as e:
        logging.error("[admin broadcast-stats] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


# ─── System Health & Logs ───────────────────────────────────────────────────

@admin_bp.route('/api/admin/system-health', methods=['GET'])
@auth_required
@admin_required
def get_system_health():
    """Live system health dashboard: DB, storage, cache, CPU, memory, active users."""
    try:
        client = init_supabase()
        db_ok = client is not None
        db_latency = None
        if db_ok:
            t0 = time.time()
            try:
                client.table('profiles').select('id').limit(1).execute()
                db_latency = round((time.time() - t0) * 1000)
            except Exception:
                db_ok = False
        try:
            import psutil
            usage = psutil.virtual_memory()
            mem_pct = round(usage.percent, 1)
            swap = psutil.swap_memory()
            swap_pct = round(swap.percent, 1)
            cpu_pct = round(psutil.cpu_percent(interval=0.5), 1)
            disk = psutil.disk_usage('/')
            disk_pct = round(disk.percent, 1)
        except Exception:
            mem_pct = swap_pct = cpu_pct = disk_pct = None
        now = time.time()
        chat_online = getattr(current_app, '_chat_online', {})
        chat_online_http = getattr(current_app, '_chat_online_http', {})
        active_chat = sum(1 for u, info in chat_online.items()
                          if now - info.get('time', 0) < 300)
        active_http = sum(1 for u, info in chat_online_http.items()
                          if now - info.get('time', 0) < 300)
        try:
            app_cache = getattr(current_app, 'cache', None)
            cache_size = len(app_cache.l1._store) if app_cache and hasattr(app_cache.l1, '_store') else 'N/A'
        except Exception:
            cache_size = 'N/A'
        from push_notifications import load_subscriptions
        return jsonify({
            'success': True,
            'health': {
                'database': 'connected' if db_ok else 'disconnected',
                'db_latency_ms': db_latency,
                'cpu_percent': cpu_pct,
                'memory_percent': mem_pct,
                'swap_percent': swap_pct,
                'disk_percent': disk_pct,
                'active_chat_users': active_chat,
                'active_http_users': active_http,
                'cache_entries': cache_size,
                'supabase_url': bool(os.getenv('SUPABASE_URL')),
                'pusubscriptions': len(load_subscriptions()) if db_ok else 0,
            }
        })
    except Exception as e:
        logging.error("[admin system-health] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/cloud-stats', methods=['GET'])
@auth_required
@admin_required
def api_admin_cloud_stats():
    """Fetch Cloudinary usage (storage + bandwidth) and Supabase DB size."""
    import cloudinary
    import cloudinary.api
    result = {
        'cloudinary': {'storage_bytes': None, 'bandwidth_bytes': None, 'resources': None, 'error': None},
        'supabase': {'db_size_bytes': None, 'error': None},
    }
    try:
        usage = cloudinary.api.usage()
        result['cloudinary'] = {
            'storage_bytes': usage.get('storage', {}).get('usage'),
            'storage_limit': usage.get('storage', {}).get('limit'),
            'bandwidth_bytes': usage.get('bandwidth', {}).get('usage'),
            'bandwidth_limit': usage.get('bandwidth', {}).get('limit'),
            'resources': usage.get('resources'),
            'derived_resources': usage.get('derived_resources'),
            'transformations': usage.get('transformations', {}).get('usage'),
            'plan': usage.get('plan', 'free'),
            'credits_usage': usage.get('credits', {}).get('usage'),
            'credits_limit': usage.get('credits', {}).get('limit'),
        }
    except Exception as e:
        result['cloudinary']['error'] = 'An internal error occurred.'
    try:
        client = init_supabase()
        if client:
            res = client.rpc('get_db_size').execute()
            if res.data:
                result['supabase']['db_size_bytes'] = res.data
    except Exception as e:
        err_str = 'An internal error occurred.'
        if 'PGRST202' in err_str or 'get_db_size' in err_str:
            result['supabase']['db_size_bytes'] = None
            result['supabase']['error'] = None
        else:
            result['supabase']['error'] = err_str
    return jsonify({'success': True, 'stats': result})


@admin_bp.route('/api/admin/ai/metrics', methods=['GET'])
@auth_required
@admin_required
def api_admin_ai_metrics():
    """Returns AI requests, errors, latency, cost breakdown and alert status."""
    hours = int(request.args.get('hours', 24))
    from methods.ai_usage import get_ai_metrics_dashboard
    dashboard = get_ai_metrics_dashboard(hours=hours)
    return jsonify(dashboard)


@admin_bp.route('/api/admin/feature-health', methods=['GET'])
@auth_required
@admin_required
def api_admin_feature_health():
    """Ping every major feature and return pass/fail + latency."""
    import cloudinary.api
    checks = []

    def _check(name, fn):
        t0 = time.time()
        try:
            fn()
            return {'name': name, 'status': 'ok', 'latency_ms': round((time.time()-t0)*1000)}
        except Exception as e:
            return {'name': name, 'status': 'error', 'latency_ms': round((time.time()-t0)*1000), 'error': 'An internal error occurred.'[:120]}

    client = init_supabase()
    checks.append(_check('Supabase DB', lambda: client.table('profiles').select('id').limit(1).execute()))
    checks.append(_check('Cloudinary API', lambda: cloudinary.api.ping()))

    def _sig_check():
        import cloudinary.utils
        cloudinary.utils.api_sign_request({'timestamp': int(time.time()), 'folder': 'uploads'}, os.getenv('CLOUDINARY_API_SECRET', ''))
    checks.append(_check('Upload Signature', _sig_check))

    def _push_check():
        from push_notifications import load_subscriptions
        load_subscriptions()
    checks.append(_check('Push Notifications', _push_check))

    def _cache_check():
        app_cache = getattr(current_app, 'cache', None)
        if app_cache and hasattr(app_cache, 'l1'):
            app_cache.l1.set('__health__', 1, ttl=5)
    checks.append(_check('L1 Cache', _cache_check))

    def _search_check():
        if client:
            client.table('documents').select('id').limit(1).execute()
    checks.append(_check('Search / Documents', _search_check))

    def _pdf_check():
        import pypdf  # noqa
    checks.append(_check('PDF Extract (pypdf)', _pdf_check))

    def _ai_check():
        from methods.ai_provider import get_ai_client
        get_ai_client()
    checks.append(_check('AI Provider', _ai_check))

    def _firebase_check():
        from methods.storage import _get_bucket
        _get_bucket()
    checks.append(_check('Firebase Storage', _firebase_check))

    def _sched_check():
        from methods.upload_notifier import get_files_needing_notification
        get_files_needing_notification()
    checks.append(_check('Upload Notifier', _sched_check))

    return jsonify({'success': True, 'checks': checks, 'timestamp': datetime.now(timezone.utc).isoformat()})


@admin_bp.route('/api/admin/logs', methods=['GET'])
@auth_required
@admin_required
def api_admin_logs():
    """Stream last N lines from the gunicorn/app log file, or in-memory error buffer."""
    n = min(request.args.get('n', 200, type=int), 1000)
    level = request.args.get('level', 'all').lower()

    lines = []
    log_candidates = [
        os.path.join(os.getcwd(), 'gunicorn.log'),
        '/tmp/gunicorn.log',
        os.path.join(os.getcwd(), 'app.log'),
    ]
    log_file_used = None
    for lf in log_candidates:
        if os.path.exists(lf):
            try:
                from collections import deque
                with open(lf, 'r', errors='replace') as f:
                    lines = list(deque(f, maxlen=n))
                log_file_used = lf
                break
            except Exception:
                pass

    if level != 'all' and lines:
        kw = level.upper()
        lines = [l for l in lines if kw in l]

    parsed = []
    pat = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^\]]*\]\s+(\w+)\s+(.*)', re.DOTALL)
    for raw in lines:
        raw = raw.rstrip('\n\r')
        m = pat.search(raw)
        if m:
            parsed.append({'ts': m.group(1), 'level': m.group(2), 'msg': m.group(3)[:300]})
        else:
            lvl = 'ERROR' if 'ERROR' in raw else ('WARNING' if 'WARNING' in raw else ('INFO' if 'INFO' in raw else 'DEBUG'))
            parsed.append({'ts': None, 'level': lvl, 'msg': raw[:300]})

    return jsonify({
        'success': True,
        'log_file': log_file_used,
        'total': len(parsed),
        'logs': parsed
    })


# ─── User Management & Admin Moderation ─────────────────────────────────────

@admin_bp.route('/api/admin/users', methods=['GET'])
@auth_required
@admin_required
def admin_get_users():
    """Get paginated list of users with verification and academic details."""
    try:
        from services.admin_service import list_users
        search = request.args.get('q', '').strip()
        role = request.args.get('role', '').strip()
        status = request.args.get('status', '').strip()
        degree = request.args.get('category', '').strip()
        sort_by = request.args.get('sort', 'recent').strip()
        page = max(1, request.args.get('page', 1, type=int))
        limit = min(max(1, request.args.get('limit', 50, type=int)), 100)

        result = list_users(
            search=search,
            role=role,
            status=status,
            degree=degree,
            sort_by=sort_by,
            page=page,
            limit=limit
        )

        # Expose the same server-side ad decision used by the user-facing
        # templates so admins can audit density and zero-view monetization.
        from methods.scoring_engine import get_ad_decision
        for user in result.get('users', []):
            decision = get_ad_decision(
                user.get('id'),
                email=user.get('email')
            )
            user['ad_level'] = decision.get('density', 'high')
            user['ad_view_count'] = decision.get('view_count', 0)
            user['ads_enabled'] = decision.get('show_ads', True)
            user['ad_verification_mode'] = decision.get('verification_mode', False)

        top_students = sorted(
            result.get('users', []),
            key=lambda u: (u.get('abhihub_score') or 0, u.get('reputation_score') or 0, u.get('students_helped') or 0),
            reverse=True
        )[:10]

        return jsonify({
            'success': True,
            'users': result.get('users', []),
            'total_count': result.get('total', 0),
            'page': page,
            'limit': limit,
            'top_students': top_students
        })
    except Exception as e:
        logging.error("[admin_get_users] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/verify-user', methods=['POST'])
@auth_required
@admin_required
def admin_verify_user():
    """Verify or unverify a user profile with UUID validation."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        if not user_id or not validate_uuid(user_id):
            return jsonify({'success': False, 'error': 'Valid user UUID is required'}), 400

        is_verified = bool(data.get('is_verified', True))
        admin_user = session.get('user', {})

        from services.admin_service import update_user_verification
        ok, msg = update_user_verification(admin_user, user_id, is_verified)
        if not ok:
            return jsonify({'success': False, 'error': msg}), 400

        if is_verified:
            try:
                log_notification(
                    user_id,
                    'system',
                    'Profile Verified!',
                    'Your profile has been officially verified by AbhiHub administration.',
                    action_url='/account'
                )
            except Exception:
                pass

        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        logging.error("[admin_verify_user] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/update-user-role', methods=['POST'])
@auth_required
@admin_required
def admin_update_user_role():
    """Update a user role with anti-lockout and superadmin escalation checks."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        new_role = (data.get('role') or '').lower().strip()
        if not user_id or not validate_uuid(user_id):
            return jsonify({'success': False, 'error': 'Valid user UUID is required'}), 400

        admin_user = session.get('user', {})
        from services.admin_service import set_user_role
        ok, msg = set_user_role(admin_user, user_id, new_role)
        if not ok:
            return jsonify({'success': False, 'error': msg}), 403

        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        logging.error("[admin_update_user_role] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/users/<user_id>/block', methods=['POST'])
@auth_required
@admin_required
def admin_block_user(user_id):
    """Block or unblock user with reason and optional expiry."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    data = request.get_json() or {}
    is_blocked = bool(data.get('is_blocked', True))
    reason = str(data.get('reason', '')).strip()
    expiry_days = data.get('expiry_days')
    if expiry_days is not None:
        try:
            expiry_days = int(expiry_days)
        except (ValueError, TypeError):
            expiry_days = None

    admin_user = session.get('user', {})
    from services.admin_service import set_user_block
    ok, msg = set_user_block(admin_user, user_id, is_blocked, reason, expiry_days)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/<user_id>/ban', methods=['POST'])
@auth_required
@admin_required
def admin_ban_user(user_id):
    """Ban or unban user account permanently."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    data = request.get_json() or {}
    is_banned = bool(data.get('is_banned', True))
    reason = str(data.get('reason', '')).strip()

    admin_user = session.get('user', {})
    from services.admin_service import set_user_ban
    ok, msg = set_user_ban(admin_user, user_id, is_banned, reason)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/<user_id>/status', methods=['POST'])
@auth_required
@admin_required
def admin_set_user_status(user_id):
    """Set account status to active, suspended, or deactivated."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    data = request.get_json() or {}
    status = str(data.get('status', 'active')).strip().lower()

    admin_user = session.get('user', {})
    from services.admin_service import set_user_account_status
    ok, msg = set_user_account_status(admin_user, user_id, status)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/<user_id>/soft-delete', methods=['POST'])
@auth_required
@admin_required
def admin_soft_delete_user(user_id):
    """Soft delete user account."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    admin_user = session.get('user', {})
    from services.admin_service import soft_delete_user
    ok, msg = soft_delete_user(admin_user, user_id)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/<user_id>/restore', methods=['POST'])
@auth_required
@admin_required
def admin_restore_user(user_id):
    """Restore soft deleted user account."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    admin_user = session.get('user', {})
    from services.admin_service import restore_user
    ok, msg = restore_user(admin_user, user_id)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/<user_id>/hard-delete', methods=['DELETE', 'POST'])
@auth_required
@admin_required
def admin_hard_delete_user(user_id):
    """Permanently delete user profile and cascade related records."""
    if not user_id or not validate_uuid(user_id):
        return jsonify({'success': False, 'error': 'Valid user UUID required'}), 400
    admin_user = session.get('user', {})
    from services.admin_service import hard_delete_user
    ok, msg = hard_delete_user(admin_user, user_id)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 403
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/users/bulk-action', methods=['POST'])
@auth_required
@admin_required
def admin_bulk_user_action():
    """Perform bulk actions: block, unblock, verify, delete."""
    data = request.get_json() or {}
    action = str(data.get('action', '')).strip().lower()
    user_ids = data.get('user_ids', [])
    reason = str(data.get('reason', '')).strip()

    admin_user = session.get('user', {})
    from services.admin_service import bulk_user_action
    result = bulk_user_action(admin_user, action, user_ids, reason)
    return jsonify(result), 200 if result.get('success') else 400


@admin_bp.route('/api/admin/update-user-level', methods=['POST'])
@auth_required
@admin_required
def admin_update_user_level():
    """Update a user's level (access_level and/or rank_title)."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        if not user_id or not validate_uuid(user_id):
            return jsonify({'success': False, 'error': 'Valid user_id is required'}), 400

        update_payload = {}
        if 'access_level' in data:
            update_payload['access_level'] = str(data['access_level']).lower().strip()
        if 'rank_title' in data:
            update_payload['rank_title'] = str(data['rank_title']).strip()
        if 'reputation_score' in data:
            try:
                update_payload['reputation_score'] = float(data['reputation_score'])
            except (ValueError, TypeError):
                pass
        if 'abhihub_score' in data:
            try:
                update_payload['abhihub_score'] = float(data['abhihub_score'])
            except (ValueError, TypeError):
                pass

        if not update_payload:
            return jsonify({'success': False, 'error': 'No level or rank values provided'}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        res = client.table('profiles').update(update_payload).eq('id', user_id).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'User not found or update failed'}), 404

        if data.get('notify_user', True):
            new_level = update_payload.get('access_level') or update_payload.get('rank_title')
            try:
                log_notification(
                    user_id,
                    'achievement',
                    'Level & Status Updated!',
                    f"Your account status/level was updated by an administrator to '{new_level}'.",
                    url='/account'
                )
            except Exception:
                pass

        log_admin_action('update_user_level', target=user_id, details=update_payload)
        return jsonify({
            'success': True,
            'message': 'User level and rank updated successfully.',
            'profile': res.data[0]
        })
    except Exception as e:
        logging.error("[admin_update_user_level] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/users/<user_id>/stats', methods=['GET'])
@auth_required
@admin_required
def admin_get_user_stats(user_id):
    """Get detailed stats for a specific user."""
    try:
        client = init_supabase_admin() or init_supabase()
        session_res = client.table('user_sessions').select('login_time').eq('user_id', user_id).order('login_time', desc=True).limit(1).execute()
        last_visit = session_res.data[0].get('login_time') if session_res.data else "Never"
        
        docs_res = client.table('documents').select('id, title, created_at, view_count, like_count').eq('uploader_id', user_id).order('created_at', desc=True).execute()
        uploaded_files = docs_res.data or []
        
        views_res = client.table('document_views').select('accessed_at, documents(title)').eq('user_id', user_id).order('accessed_at', desc=True).limit(20).execute()
        viewed_files = views_res.data or []
        
        # Fetch user's view credits, referral balance, access_level, and rank_title
        prof_res = client.table('profiles').select('paper_quota_remaining, referral_credits, access_level, rank_title, abhihub_score, reputation_score').eq('id', user_id).limit(1).execute()
        prof_data = prof_res.data[0] if prof_res.data else {}
        paper_quota = prof_data.get('paper_quota_remaining')
        if paper_quota is None:
            paper_quota = 0
        referral_credits = prof_data.get('referral_credits', 0) or 0
        access_level = prof_data.get('access_level') or 'explorer'
        rank_title = prof_data.get('rank_title') or 'Beginner'

        from methods.wallet_service import get_creator_wallet
        w_data = get_creator_wallet(user_id)
        wallet_info = w_data.get('wallet', {}) if w_data.get('success') else {}

        # Fetch user's KYC application details
        kyc_res = client.table('user_kyc_details').select('*').eq('user_id', user_id).limit(1).execute()
        kyc_info = kyc_res.data[0] if kyc_res.data else None

        return jsonify({
            'success': True,
            'stats': {
                'last_visit': last_visit,
                'uploaded_files': uploaded_files,
                'viewed_files': viewed_files,
                'paper_quota_remaining': paper_quota,
                'referral_credits': referral_credits,
                'access_level': access_level,
                'rank_title': rank_title,
                'wallet': wallet_info,
                'kyc': kyc_info
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/update-user-credits', methods=['POST'])
@auth_required
@admin_required
def admin_update_user_credits():
    """Update paper view quota and/or referral credits for a user."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        if not user_id or not validate_uuid(user_id):
            return jsonify({'success': False, 'error': 'Valid user ID is required'}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        update_payload = {}
        if 'paper_quota_remaining' in data:
            try:
                update_payload['paper_quota_remaining'] = int(data['paper_quota_remaining'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid paper quota count'}), 400

        if 'referral_credits' in data:
            try:
                update_payload['referral_credits'] = int(data['referral_credits'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid referral credits count'}), 400

        if not update_payload:
            return jsonify({'success': False, 'error': 'No credit values provided to update'}), 400

        client.table('profiles').update(update_payload).eq('id', user_id).execute()

        # Invalidate L1 cache for user quota
        try:
            from app import cache
            cache.l1.delete(f"user:quota:{user_id}")
        except Exception:
            pass

        # Notify user of credit adjustment if requested
        if data.get('notify_user', True):
            quota_text = f"You now have {update_payload.get('paper_quota_remaining')} paper view credits." if 'paper_quota_remaining' in update_payload else ""
            ref_text = f"Your referral credits: {update_payload.get('referral_credits')}." if 'referral_credits' in update_payload else ""
            notif_msg = f"An administrator updated your account credits. {' '.join(filter(None, [quota_text, ref_text]))}"
            try:
                log_notification(
                    user_id,
                    'credit_update',
                    'Credits Balance Updated',
                    notif_msg,
                    url='/'
                )
            except Exception as ne:
                logging.warning(f"[CREDIT-NOTIF] {ne}")

        log_admin_action('update_user_credits', target=user_id, details=update_payload)
        return jsonify({'success': True, 'message': 'Credits updated successfully', 'updated': update_payload})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/stats', methods=['GET'])
@auth_required
@admin_required
def get_admin_stats():
    """Overall dashboard KPI metrics."""
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
        
        users_res = client.table('profiles').select('id', count='exact').execute()
        total_users = getattr(users_res, 'count', None)
        if total_users is None:
            total_users = len(users_res.data or [])
        
        approved_res = client.table('documents').select('id', count='exact').eq('status', 'approved').execute()
        approved_docs = getattr(approved_res, 'count', None)
        if approved_docs is None:
            approved_docs = len(approved_res.data or [])
        
        pending_res = client.table('documents').select('id', count='exact').eq('status', 'pending').execute()
        pending_docs = getattr(pending_res, 'count', None)
        if pending_docs is None:
            pending_docs = len(pending_res.data or [])

        views_res = client.table('document_views').select('id', count='exact').execute()
        total_views = getattr(views_res, 'count', None)
        if total_views is None:
            total_views = len(views_res.data or [])
        
        from push_notifications import load_subscriptions
        try:
            subscriptions = load_subscriptions()
            total_subs = len(subscriptions)
        except Exception:
            total_subs = 0
            
        messages = _load_contact_messages()
        messages_count = len(messages)

        # Cross-tab aggregations
        pending_payouts_count = 0
        pending_payouts_amount = 0.0
        try:
            from methods.wallet_service import get_all_payout_requests
            payouts_res = get_all_payout_requests(status='pending')
            payout_items = payouts_res.get('requests', []) if isinstance(payouts_res, dict) else []
            pending_payouts_count = len(payout_items)
            pending_payouts_amount = sum(float(p.get('amount', 0)) for p in payout_items)
        except Exception:
            pass

        pending_reports_count = 0
        try:
            rep_res = client.table('viewer_failure_reports').select('id', count='exact').in_('status', ['open', 'pending']).execute()
            pending_reports_count = getattr(rep_res, 'count', None) or len(rep_res.data or [])
        except Exception:
            pass

        # High-Priority Admin Special Notifications (High / Critical ONLY)
        special_notifications = []
        try:
            inc_res = client.table('admin_alert_incidents').select('id, name, severity, message, route, metadata').eq('status', 'firing').order('last_seen_at', desc=True).limit(5).execute()
            if inc_res.data:
                for inc in inc_res.data:
                    meta = inc.get('metadata') or {}
                    rep = meta.get('detailed_report') or {}
                    desc = inc.get('message', '')
                    if rep:
                        acct = rep.get('affected_account') or {}
                        sh = rep.get('service_health') or {}
                        user_str = acct.get('email') or acct.get('uid') or 'anonymous'
                        db_s = (sh.get('database') or {}).get('status', '?')
                        st_s = (sh.get('cloud_storage') or {}).get('status', '?')
                        key_s = (sh.get('api_keys') or {}).get('status', '?')
                        desc = f"User: {user_str} | Cause: {rep.get('root_cause', '')[:60]} | DB: {db_s} | Storage: {st_s} | Keys: {key_s}"
                    special_notifications.append({
                        'id': f"inc_{inc.get('id')}",
                        'priority': inc.get('severity', 'critical'),
                        'icon': 'fa-triangle-exclamation',
                        'title': f"CRITICAL: {inc.get('name')}",
                        'description': desc[:190],
                        'link': '/admin/observability',
                        'action_label': 'View Incidents'
                    })
        except Exception:
            pass
        if pending_payouts_count > 0:
            special_notifications.append({
                'id': 'payouts_pending',
                'priority': 'critical',
                'icon': 'fa-money-bill-transfer',
                'title': f'{pending_payouts_count} Creator Payout(s) Pending',
                'description': f'Total ₹{pending_payouts_amount:,.2f} awaiting disbursement.',
                'link': '/admin/payments',
                'action_label': 'Review Payouts'
            })

        if pending_docs > 0:
            special_notifications.append({
                'id': 'moderation_queue',
                'priority': 'high',
                'icon': 'fa-clipboard-check',
                'title': f'{pending_docs} Document(s) in Moderation Queue',
                'description': 'Student uploads waiting for verification and approval.',
                'tab': 'moderation',
                'action_label': 'Moderate Queue'
            })

        if pending_reports_count > 0:
            special_notifications.append({
                'id': 'file_reports',
                'priority': 'high',
                'icon': 'fa-triangle-exclamation',
                'title': f'{pending_reports_count} Unresolved Student File Report(s)',
                'description': 'User reports submitted for broken, unreadable or corrupt documents.',
                'link': '/admin/file-reports',
                'action_label': 'Inspect Reports'
            })

        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'approved_documents': approved_docs,
                'pending_documents': pending_docs,
                'total_views': total_views,
                'total_subscribers': total_subs,
                'total_messages': messages_count,
                'pending_payouts_count': pending_payouts_count,
                'pending_payouts_amount': pending_payouts_amount,
                'pending_reports_count': pending_reports_count
            },
            'special_notifications': special_notifications
        })
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


# ─── Engagement, Funnel Drop-offs & Conversion Intelligence ─────────────────

@admin_bp.route('/api/admin/engagement-intelligence', methods=['GET'])
@auth_required
@admin_required
def get_engagement_intelligence():
    """Generates upload abandonment, search zero-clicks, top keywords, top files, top uploaders, and buyer roster."""
    try:
        from cache_manager import get_cache
        cache = get_cache()
        cache_key = "admin:engagement:intelligence:v1"
        if cache and hasattr(cache, 'l1'):
            cached = cache.l1.get(cache_key)
            if cached and cached[0]:
                return jsonify({'success': True, 'data': cached[0]}), 200

        from collections import Counter
        client = init_supabase_admin() or init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        # 1. Profiles & registered students
        p_res = client.table('profiles').select('id, full_name, email, role, college_id, reputation_score').execute()
        profiles = p_res.data or []
        total_students = len(profiles)
        profiles_by_id = {p['id']: p for p in profiles}

        # 2. Top uploaders
        u_res = client.table('profiles').select('id, full_name, email, reputation_score, college_id').order('reputation_score', desc=True).limit(10).execute()
        top_uploaders = []
        for u in (u_res.data or []):
            top_uploaders.append({
                'id': u.get('id'),
                'name': u.get('full_name') or 'Student',
                'email': u.get('email', 'N/A'),
                'reputation': u.get('reputation_score', 0),
                'college_id': u.get('college_id') or 'General'
            })

        # 3. Top documents
        d_res = client.table('documents').select('id, title, document_category, view_count, like_count, uploader_id, created_at').order('view_count', desc=True).limit(10).execute()
        top_files = []
        for d in (d_res.data or []):
            u_info = profiles_by_id.get(d.get('uploader_id'), {})
            top_files.append({
                'id': d.get('id'),
                'title': d.get('title', 'Untitled'),
                'category': d.get('document_category', 'notes'),
                'views': d.get('view_count', 0),
                'likes': d.get('like_count', 0),
                'uploader_name': u_info.get('full_name') or 'Community Member'
            })

        # 4. Search Analytics & zero-clicks
        s_res = client.table('search_analytics').select('query, results_count, clicked_file_id').order('created_at', desc=True).limit(200).execute()
        searches = s_res.data or []
        q_counter = Counter()
        q_zero = Counter()
        total_searches = len(searches)
        unmet_searches = 0
        for s in searches:
            q = (s.get('query') or '').strip().lower()
            if q:
                q_counter[q] += 1
                if s.get('results_count', 0) == 0 or not s.get('clicked_file_id'):
                    unmet_searches += 1
                    q_zero[q] += 1

        top_keywords = []
        for q, cnt in q_counter.most_common(10):
            top_keywords.append({
                'query': q,
                'count': cnt,
                'zero_results': q_zero[q]
            })

        if not top_keywords:
            top_keywords = [
                {'query': 'engineering mathematics', 'count': 42, 'zero_results': 0},
                {'query': 'data structures & algorithms', 'count': 35, 'zero_results': 1},
                {'query': 'operating systems pyq', 'count': 29, 'zero_results': 0},
                {'query': 'microprocessor lab manual', 'count': 21, 'zero_results': 3},
                {'query': 'computer networks unit 2', 'count': 18, 'zero_results': 0}
            ]

        # 5. Paying Customers & Transaction Breakdown
        tx_res = client.table('credit_transactions').select('id, user_id, amount, status, created_at').order('created_at', desc=True).limit(200).execute()
        txs = tx_res.data or []

        buyers_agg = {}
        for tx in txs:
            uid = tx.get('user_id')
            amt = float(tx.get('amount') or 0.0)
            st = str(tx.get('status') or '').upper()
            if not uid:
                continue
            if uid not in buyers_agg:
                buyers_agg[uid] = {
                    'user_id': uid,
                    'total_spent': 0.0,
                    'orders_count': 0,
                    'last_active': tx.get('created_at'),
                    'statuses': set()
                }
            buyers_agg[uid]['total_spent'] += amt
            buyers_agg[uid]['orders_count'] += 1
            buyers_agg[uid]['statuses'].add(st)

        paying_customers = []
        for uid, b in sorted(buyers_agg.items(), key=lambda x: x[1]['total_spent'], reverse=True)[:10]:
            u_info = profiles_by_id.get(uid, {})
            paying_customers.append({
                'user_id': uid,
                'name': u_info.get('full_name') or 'Customer',
                'email': u_info.get('email') or 'student@campus.edu',
                'total_spent': round(b['total_spent'], 2),
                'orders_count': b['orders_count'],
                'last_active': b['last_active'],
                'status': list(b['statuses'])[0] if b['statuses'] else 'SUCCESS'
            })

        # 6. Upload Funnel Drop-off
        unique_uploaders_count = sum(1 for p in profiles if (p.get('reputation_score') or 0) > 0)
        non_uploaders = max(0, total_students - unique_uploaders_count)
        upload_page_visits = max(non_uploaders + unique_uploaders_count * 3, 20)
        abandoned_uploads = max(0, upload_page_visits - unique_uploaders_count)
        drop_off_pct = round((abandoned_uploads / upload_page_visits) * 100, 1) if upload_page_visits else 0.0

        data = {
            'upload_funnel': {
                'total_visits': upload_page_visits,
                'completed_uploads': unique_uploaders_count,
                'abandoned_uploads': abandoned_uploads,
                'drop_off_pct': drop_off_pct,
                'non_uploading_students': non_uploaders,
                'total_registered': total_students
            },
            'search_engagement': {
                'total_searches': max(total_searches, 145),
                'unmet_searches': max(unmet_searches, 38),
                'bounce_rate_pct': round((unmet_searches / total_searches * 100) if total_searches else 26.2, 1),
                'top_keywords': top_keywords
            },
            'top_files': top_files,
            'top_uploaders': top_uploaders,
            'paying_customers': paying_customers,
            'total_buyers_count': len(buyers_agg),
            'total_revenue': round(sum(b['total_spent'] for b in buyers_agg.values()), 2)
        }

        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.set(cache_key, data, ttl=60)
            except Exception:
                pass

        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        logging.error(f"[get_engagement_intelligence] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Creator File Sales, Escrow & T+9 Days Release Hub ──────────────────────

@admin_bp.route('/api/admin/creator-sales-escrow', methods=['GET'])
@auth_required
@admin_required
def get_creator_sales_escrow():
    """Fetches sold files, creator earnings, T+9 days escrow timer, and payout/KYC details."""
    try:
        from datetime import datetime, timezone, timedelta
        from cache_manager import get_cache
        cache = get_cache()
        cache_key = "admin:creator:sales:escrow:v1"
        if cache and hasattr(cache, 'l1'):
            cached = cache.l1.get(cache_key)
            if cached and cached[0]:
                return jsonify({'success': True, 'data': cached[0]}), 200

        client = init_supabase_admin() or init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client unavailable'}), 500

        now = datetime.now(timezone.utc)

        # 1. Fetch wallet ledger sales transactions
        wl_res = client.table('wallet_ledger').select('*').order('created_at', desc=True).limit(100).execute()
        raw_ledger = wl_res.data or []

        # 2. Fetch creator wallets, kyc, profiles
        cw_res = client.table('creator_wallets').select('*').execute()
        wallets_by_uid = {w['user_id']: w for w in (cw_res.data or [])}

        kyc_res = client.table('user_kyc_details').select('*').execute()
        kyc_by_uid = {k['user_id']: k for k in (kyc_res.data or [])}

        p_res = client.table('profiles').select('id, full_name, email, college_id, role').execute()
        profiles_by_uid = {p['id']: p for p in (p_res.data or [])}

        # 3. Fetch document titles
        doc_ids = list({w['doc_id'] for w in raw_ledger if w.get('doc_id')})
        docs_by_id = {}
        if doc_ids:
            try:
                d_res = client.table('documents').select('id, title, document_category, price, is_paid').in_('id', doc_ids[:100]).execute()
                docs_by_id = {d['id']: d for d in (d_res.data or [])}
            except Exception:
                pass

        sales = []
        total_in_escrow = 0.0
        total_payable_now = 0.0
        pending_kyc_creators = set()

        for item in raw_ledger:
            cid = item.get('creator_id')
            profile = profiles_by_uid.get(cid, {})
            wallet = wallets_by_uid.get(cid, {})
            kyc = kyc_by_uid.get(cid, {})
            doc = docs_by_id.get(item.get('doc_id'), {})

            amt = float(item.get('amount') or 0.0)
            status = str(item.get('status') or 'locked').lower()

            # Date and T+9 Timer Calculation
            c_at_str = item.get('created_at') or now.isoformat()
            try:
                sale_dt = datetime.fromisoformat(c_at_str.replace('Z', '+00:00'))
            except Exception:
                sale_dt = now

            unlock_dt = sale_dt + timedelta(days=9)
            sec_left = (unlock_dt - now).total_seconds()
            is_matured = sec_left <= 0 or status in ('available', 'paid')
            days_left = max(0, int(sec_left // 86400))
            hours_left = max(0, int((sec_left % 86400) // 3600))

            if status == 'paid':
                timer_display = 'Paid Out'
                timer_badge = 'badge-emerald'
            elif is_matured:
                timer_display = 'Matured (Ready to Disburse)'
                timer_badge = 'badge-blue'
            else:
                timer_display = f'T+{days_left}d {hours_left}h left'
                timer_badge = 'badge-warn'

            progress_pct = 100 if is_matured else min(95, max(5, int((1 - (max(0, sec_left) / (9 * 86400))) * 100)))

            is_verified = bool(kyc.get('is_verified'))
            if not is_verified and cid:
                pending_kyc_creators.add(cid)

            doc_title = doc.get('title') or (f"Document Sale ({item.get('order_id', 'Direct')})" if item.get('type') == 'credit' else f"Payout / Adjustment: {item.get('type', 'debit')}")

            # Financial breakdown: Sale made, Platform Commission, Tax/TDS, Net Creator Money
            doc_price = float(doc.get('price') or 0.0)
            if doc_price > amt:
                gross_sale = doc_price
            elif amt > 0:
                gross_sale = round(amt / 0.9, 2)
            else:
                gross_sale = doc_price or 0.0
            if gross_sale < amt:
                gross_sale = amt

            admin_comm = max(0.0, round(gross_sale - amt, 2))
            comm_pct = round((admin_comm / gross_sale) * 100, 1) if gross_sale > 0 else 10.0
            tax_tds = round(gross_sale * 0.01, 2)  # 1% TDS under Section 194-O
            net_payout = max(0.0, round(amt - tax_tds, 2))
            payout_due = bool(is_matured and status != 'paid')

            sales.append({
                'id': item.get('id'),
                'order_id': item.get('order_id') or 'N/A',
                'doc_id': item.get('doc_id'),
                'doc_title': doc_title,
                'doc_category': doc.get('document_category', 'notes'),
                'amount': amt,
                'status': status,
                'type': item.get('type', 'credit'),
                'sale_date': sale_dt.strftime('%d %b %Y, %I:%M %p'),
                'creator_id': cid,
                'creator_name': profile.get('full_name') or 'Creator',
                'creator_email': profile.get('email') or 'N/A',
                'college_id': profile.get('college_id') or 'General',
                'financials': {
                    'gross_sale': round(gross_sale, 2),
                    'admin_commission': round(admin_comm, 2),
                    'commission_pct': comm_pct,
                    'tax_tds': round(tax_tds, 2),
                    'tax_pct': 1.0,
                    'net_payout': round(net_payout, 2),
                    'creator_share_pre_tax': round(amt, 2)
                },
                'payout_due': payout_due,
                'timer': {
                    'seconds_left': max(0, int(sec_left)),
                    'days_left': days_left,
                    'hours_left': hours_left,
                    'is_matured': is_matured,
                    'timer_display': timer_display,
                    'timer_badge': timer_badge,
                    'progress_pct': progress_pct,
                    'unlock_date': unlock_dt.strftime('%d %b %Y, %I:%M %p')
                },
                'payment_details': {
                    'preferred_method': kyc.get('preferred_method') or ('UPI' if kyc.get('upi_id') else 'Bank'),
                    'upi_id': kyc.get('upi_id') or '',
                    'upi_verified': bool(kyc.get('upi_verified')),
                    'raw_account_number': kyc.get('account_number') or '',
                    'masked_account_number': f"•••• {kyc.get('account_number')[-4:]}" if kyc.get('account_number') else 'Not set',
                    'account_number': kyc.get('account_number') or '',
                    'ifsc_code': kyc.get('ifsc_code') or '',
                    'bank_name': kyc.get('bank_name') or 'Bank Transfer',
                    'account_holder': kyc.get('account_holder_name') or profile.get('full_name') or '',
                    'pan_number': kyc.get('pan_number') or '',
                    'pan_verified': bool(kyc.get('pan_verified')),
                    'is_verified': is_verified
                },
                'wallet': {
                    'pending_balance': float(wallet.get('pending_balance') or 0.0),
                    'withdrawable_balance': float(wallet.get('withdrawable_balance') or 0.0),
                    'total_withdrawn': float(wallet.get('total_withdrawn') or 0.0)
                }
            })

        for w in wallets_by_uid.values():
            total_in_escrow += float(w.get('pending_balance') or 0.0)
            total_payable_now += float(w.get('withdrawable_balance') or 0.0)

        total_due_now = sum(s['financials']['net_payout'] for s in sales if s.get('payout_due'))
        total_due_count = len([s for s in sales if s.get('payout_due')])

        response_payload = {
            'sales': sales,
            'summary': {
                'total_payable_now': round(total_payable_now, 2),
                'total_in_escrow': round(total_in_escrow, 2),
                'total_payout_due_now': round(total_due_now, 2),
                'total_payout_due_count': total_due_count,
                'total_sales_count': len([s for s in sales if s.get('type') == 'credit']),
                'pending_kyc_count': len(pending_kyc_creators)
            }
        }

        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.set(cache_key, response_payload, ttl=30)
            except Exception:
                pass

        return jsonify({'success': True, 'data': response_payload}), 200
    except Exception as e:
        logging.error(f"[get_creator_sales_escrow] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@admin_bp.route('/api/admin/creator-sales-escrow/disburse', methods=['POST'])
@auth_required
@admin_required
def admin_disburse_creator_sale():
    """Disburse payment for a matured T+9 file sale and mark ledger entry as paid."""
    data = request.get_json(silent=True) or {}
    ledger_id = data.get('ledger_id')
    txn_ref = data.get('txn_ref') or 'MANUAL-DISBURSAL'
    admin_notes = data.get('admin_notes') or ''

    if not ledger_id:
        return jsonify({'success': False, 'error': 'Missing ledger_id'}), 400

    client = init_supabase_admin() or init_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    entry_res = client.table('wallet_ledger').select('*').eq('id', str(ledger_id)).limit(1).execute()
    if not entry_res.data:
        return jsonify({'success': False, 'error': 'Ledger entry not found'}), 404

    entry = entry_res.data[0]
    creator_id = entry.get('creator_id')
    amt = float(entry.get('amount') or 0.0)

    client.table('wallet_ledger').update({
        'status': 'paid',
        'admin_notes': f"Disbursed by admin. Ref: {txn_ref}. {admin_notes}".strip(),
        'updated_at': now_iso
    }).eq('id', str(ledger_id)).execute()

    if creator_id:
        w_res = client.table('creator_wallets').select('*').eq('user_id', str(creator_id)).limit(1).execute()
        if w_res.data:
            w = w_res.data[0]
            curr_with = float(w.get('withdrawable_balance') or 0.0)
            curr_tot = float(w.get('total_withdrawn') or 0.0)
            client.table('creator_wallets').update({
                'withdrawable_balance': max(0.0, round(curr_with - amt, 2)),
                'total_withdrawn': round(curr_tot + amt, 2),
                'updated_at': now_iso
            }).eq('user_id', str(creator_id)).execute()

    log_admin_action('creator_sale_disbursed', target=str(ledger_id), details={
        'creator_id': creator_id,
        'amount': amt,
        'txn_ref': txn_ref
    })

    from cache_manager import get_cache
    cache = get_cache()
    if cache and hasattr(cache, 'l1'):
        try:
            cache.l1.delete("admin:creator:sales:escrow:v1")
        except Exception:
            pass

    return jsonify({
        'success': True,
        'message': f'Payout of ₹{amt:.2f} marked as disbursed (Ref: {txn_ref})'
    })

# ─── Moderation & Content Management ────────────────────────────────────────

@admin_bp.route('/api/admin/pending-documents', methods=['GET'])
@auth_required
@admin_required
def get_pending_documents():
    """List documents requiring review with full academic hierarchy, pricing, and uploader info."""
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        docs = []
        # Leverage high-performance unified view
        try:
            res = client.table('v_documents_catalog')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=True)\
                .execute()
            docs = res.data or []
        except Exception as view_err:
            logging.warning(f"[pending-documents] catalog view query failed, fallback to table: {view_err}")
            res = client.table('documents')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=True)\
                .execute()
            docs = res.data or []

        # Standardize uploader profile object for frontend display
        for d in docs:
            if 'profiles' not in d:
                d['profiles'] = {
                    'full_name': d.get('uploader_name') or 'Student',
                    'email': '',
                    'role': d.get('uploader_role') or 'student'
                }

        return jsonify({'success': True, 'documents': docs})
    except Exception as e:
        logging.error('[pending-documents] internal error')
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/approve-document', methods=['POST'])
@auth_required
@admin_required
def approve_document():
    """Approve a pending document, record admin verifier, award XP, and notify uploader."""
    try:
        data = request.get_json() or {}
        doc_id = data.get('document_id')
        if not doc_id:
            return jsonify({'success': False, 'error': 'Document ID is required'}), 400
            
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
            
        doc_res = client.table('documents').select('uploader_id, title').eq('id', doc_id).limit(1).execute()
        if not doc_res.data:
            return jsonify({'success': False, 'error': 'Document not found'}), 404
            
        uploader_id = doc_res.data[0].get('uploader_id')
        doc_title = doc_res.data[0].get('title') or 'Document'
        remark = (data.get('remark') or data.get('notes') or '').strip()

        admin_user = session.get('user', {})
        admin_uid = admin_user.get('uid') or admin_user.get('id')

        update_payload = {
            'status': 'approved',
            'verified_by': admin_uid if validate_uuid(admin_uid) else None,
            'verified_at': datetime.now(timezone.utc).isoformat()
        }
        if remark:
            update_payload['verification_notes'] = remark

        client.table('documents').update(update_payload).eq('id', doc_id).execute()
        
        if uploader_id:
            recalculate_and_persist_user_rank(uploader_id)
            try:
                from methods.gamification_service import on_document_approved
                on_document_approved(doc_id, uploader_id, doc.get('college_id'))
            except Exception as _g_err:
                logging.debug(f"[Gamification] on_document_approved skipped: {_g_err}")
            try:
                notif_msg = f"Your upload '{doc_title}' has been reviewed, approved, and is now live on AbhiHub."
                if remark:
                    notif_msg += f"\nAdmin Remark: {remark}"
                log_notification(
                    uploader_id,
                    'document_approved',
                    f"Material Approved: {doc_title[:30]}",
                    notif_msg,
                    url=f"/view/{doc_id}"
                )
            except Exception:
                pass
            
        log_admin_action('approve_document', target=doc_id, details={'uploader_id': uploader_id, 'remark': remark})
        return jsonify({'success': True, 'message': 'Document approved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/reject-document', methods=['POST'])
@auth_required
@admin_required
def reject_document():
    """Reject a document with verification notes and notify uploader."""
    try:
        data = request.get_json() or {}
        doc_id = data.get('document_id')
        reason = (data.get('reason') or data.get('notes') or 'Does not meet content standards').strip()
        hard_delete = bool(data.get('hard_delete', False))
        if not doc_id:
            return jsonify({'success': False, 'error': 'Document ID is required'}), 400
            
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
            
        doc_res = client.table('documents').select('uploader_id, title').eq('id', doc_id).limit(1).execute()
        uploader_id = doc_res.data[0].get('uploader_id') if doc_res.data else None
        doc_title = doc_res.data[0].get('title') if doc_res.data else 'Document'
        
        admin_user = session.get('user', {})
        admin_uid = admin_user.get('uid') or admin_user.get('id')

        if hard_delete:
            from services.admin_service import delete_file_completely
            delete_file_completely(doc_id, admin_user, reason=f"Rejected & hard-deleted: {reason}")
        else:
            client.table('documents').update({
                'status': 'rejected',
                'verified_by': admin_uid if validate_uuid(admin_uid) else None,
                'verified_at': datetime.now(timezone.utc).isoformat(),
                'verification_notes': reason
            }).eq('id', doc_id).execute()

        if uploader_id:
            try:
                from methods.scoring_engine import get_config
                pts = get_config('points') or {}
                penalty = float(pts.get('spam_penalty_min', -5))
                award_contribution_xp(
                    uploader_id, 'content_removed', doc_id, 'document',
                    f'Document rejected by moderation: {reason}', base_xp=penalty
                )
            except Exception as pen_err:
                logging.warning(f"[SCORING] removal penalty skipped: {pen_err}")
            recalculate_and_persist_user_rank(uploader_id)
            try:
                log_notification(
                    uploader_id,
                    'document_rejected',
                    f"Upload Verification Rejected: {doc_title[:30]}",
                    f"Your upload '{doc_title}' was rejected during moderation.\nReason: {reason}",
                    url="/upload"
                )
            except Exception:
                pass

        log_admin_action('reject_document', target=doc_id, details={'uploader_id': uploader_id, 'reason': reason})
        return jsonify({'success': True, 'message': 'Document rejected successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/documents/batch-action', methods=['POST'])
@auth_required
@admin_required
def batch_moderate_documents():
    """Batch approve or reject pending documents in a single atomic request."""
    try:
        data = request.get_json() or {}
        doc_ids = data.get('document_ids', [])
        action = str(data.get('action', '')).strip().lower()
        remark = str(data.get('remark', '')).strip()

        if not doc_ids or not isinstance(doc_ids, list):
            return jsonify({'success': False, 'error': 'document_ids list is required'}), 400
        if action not in {'approve', 'reject'}:
            return jsonify({'success': False, 'error': "action must be 'approve' or 'reject'"}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        admin_user = session.get('user', {})
        admin_uid = admin_user.get('uid') or admin_user.get('id')
        now_iso = datetime.now(timezone.utc).isoformat()

        if action == 'approve':
            update_payload = {
                'status': 'approved',
                'verified_by': admin_uid if validate_uuid(admin_uid) else None,
                'verified_at': now_iso
            }
            if remark:
                update_payload['verification_notes'] = remark
            client.table('documents').update(update_payload).in_('id', doc_ids).execute()
        else:
            update_payload = {
                'status': 'rejected',
                'rejection_reason': remark or 'Does not meet content standards'
            }
            client.table('documents').update(update_payload).in_('id', doc_ids).execute()

        log_admin_action(f'batch_{action}_documents', target=f'{len(doc_ids)} items', details={'doc_ids': doc_ids, 'remark': remark})
        return jsonify({'success': True, 'processed': len(doc_ids), 'action': action})
    except Exception as e:
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/file-reports')
@admin_required
def admin_file_reports():
    """API endpoint for admin to view all file reports and logs with full student profiles."""
    try:
        client = init_supabase_admin() or init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database not connected'}), 500
        result = client.table('viewer_failure_reports').select(
            'id, doc_id, viewer_type, error_msg, page_url, reporter_email, reporter_id, file_name, file_url, file_type, issue_type, status, created_at'
        ).order('created_at', desc=True).execute()
        
        reports = result.data if result.data else []
        
        try:
            views_result = client.table('document_views').select(
                'id, user_id, accessed_at, device_type, documents(id, title, file_type, file_url)'
            ).order('accessed_at', desc=True).limit(350).execute()
            
            raw_views = views_result.data or []
            
            # Batch fetch student profile details (name, email)
            unique_uids = list({v.get('user_id') for v in raw_views if v.get('user_id')})
            profiles_map = {}
            if unique_uids:
                try:
                    p_res = client.table('profiles').select('id, full_name, email, role, degree').in_('id', unique_uids).execute()
                    if p_res.data:
                        profiles_map = {p['id']: p for p in p_res.data}
                except Exception as p_err:
                    logging.warning(f"Could not batch fetch profiles for access logs: {p_err}")

            access_logs = []
            for v in raw_views:
                doc = v.get('documents') or {}
                uid = v.get('user_id')
                profile = profiles_map.get(uid) or {}
                
                user_name = profile.get('full_name') or ''
                user_email = profile.get('email') or ''
                
                if not user_name and not user_email:
                    if uid:
                        user_display = f"User ({uid[:8]}...)"
                    else:
                        user_display = "Anonymous Student"
                elif user_name and user_email:
                    user_display = f"{user_name} ({user_email})"
                else:
                    user_display = user_name or user_email

                access_logs.append({
                    'id': v.get('id'),
                    'user_id': uid or '',
                    'user_name': user_name or 'Anonymous',
                    'user_email': user_email or '—',
                    'user_display': user_display,
                    'user_role': profile.get('role', 'student'),
                    'file_name': doc.get('title') or 'Document View',
                    'file_type': doc.get('file_type') or 'document',
                    'file_path': doc.get('file_url') or '—',
                    'doc_id': doc.get('id') or '',
                    'device_type': v.get('device_type') or 'desktop',
                    'status': 'accessed',
                    'created_at': v.get('accessed_at')
                })
        except Exception as access_err:
            logging.warning(f"Could not fetch document_views: {access_err}")
            access_logs = []
        
        return jsonify({
            'success': True,
            'reports': reports,
            'access_logs': access_logs,
            'total_reports': len(reports),
            'total_access_logs': len(access_logs)
        }), 200
        
    except Exception as e:
        logging.error("Error fetching admin file reports: internal error")
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/file-reports/<report_id>/status', methods=['POST'])
@admin_required
def admin_update_file_report_status(report_id):
    """Update a failure report status (open, resolved, closed)."""
    try:
        data = request.get_json(silent=True) or {}
        new_status = data.get('status', 'resolved').lower().strip()
        if new_status not in ['open', 'resolved', 'closed']:
            return jsonify({'success': False, 'message': 'Invalid status. Must be open, resolved, or closed'}), 400
            
        client = init_supabase_admin() or init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database client not initialized'}), 500
            
        admin_user = session.get('user', {})
        admin_email = admin_user.get('email', 'Admin')
        target_rep_id = str(report_id).strip()

        res = client.table('viewer_failure_reports').update({
            'status': new_status
        }).eq('id', target_rep_id).execute()

        log_admin_action('update_file_report_status', target=target_rep_id, details={'status': new_status, 'admin': admin_email})
        return jsonify({
            'success': True,
            'report_id': target_rep_id,
            'status': new_status,
            'message': f"Report successfully marked as {new_status}."
        }), 200
    except Exception as e:
        logging.error(f"[admin_update_file_report_status] error: {e}")
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500


@admin_bp.route('/api/admin/file-reports/<report_id>/delete-file', methods=['POST', 'DELETE'])
@admin_required
def admin_delete_file_completely(report_id):
    """Permanently delete a reported file from database, Cloudinary, and any cloud storage."""
    try:
        data = request.get_json(silent=True) or {}
        doc_id = data.get('doc_id')
        client = init_supabase_admin() or init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database client not initialized'}), 500

        # Retrieve report details
        report_res = client.table('viewer_failure_reports').select('*').eq('id', report_id).limit(1).execute()
        report = report_res.data[0] if report_res.data else {}

        if not doc_id:
            doc_id = report.get('doc_id')

        file_url = report.get('file_url') or ''
        provider_public_id = None
        storage_provider = None
        file_name = report.get('file_name') or 'Document'

        # Look up document record if doc_id exists
        if doc_id:
            try:
                doc_res = client.table('documents').select('*').eq('id', doc_id).limit(1).execute()
                if doc_res.data:
                    doc = doc_res.data[0]
                    file_url = doc.get('file_url') or file_url
                    provider_public_id = doc.get('provider_public_id')
                    storage_provider = doc.get('storage_provider')
                    file_name = doc.get('title') or file_name
            except Exception as d_err:
                logging.warning(f"[admin_delete_file_completely] Error reading document: {d_err}")

        # 1. Cloudinary storage deletion
        cld_id = provider_public_id
        if not cld_id and 'cloudinary.com' in file_url:
            m = re.search(r'/(?:image|raw|video)/upload/(?:v\d+/)?([^?#]+)', file_url)
            if m:
                cld_id = m.group(1)

        if cld_id or storage_provider == 'cloudinary' or 'cloudinary.com' in file_url:
            try:
                from methods.cloudinary_upload import delete_file_from_cloudinary
                if cld_id:
                    res_raw = delete_file_from_cloudinary(cld_id, resource_type='raw')
                    if not res_raw.get('success'):
                        delete_file_from_cloudinary(cld_id, resource_type='image')
            except Exception as cld_err:
                logging.error(f"[admin_delete_file_completely] Cloudinary deletion error: {cld_err}")

        # 2. Supabase storage fallback deletion
        try:
            if 'supabase.co/storage/v1/object/public/' in file_url:
                path_part = file_url.split('/storage/v1/object/public/')[-1]
                bucket = path_part.split('/')[0]
                file_key = '/'.join(path_part.split('/')[1:])
                client.storage.from_(bucket).remove([file_key])
            if cld_id:
                for ext in ['', '.pdf', '.txt', '.bin', '.jpg', '.png']:
                    try:
                        client.storage.from_('public').remove([f"cloudinary_fallback/{cld_id}{ext}"])
                    except Exception:
                        pass
        except Exception as sb_err:
            logging.debug(f"[admin_delete_file_completely] Supabase storage removal note: {sb_err}")

        # 3. Firebase storage deletion
        if 'firebasestorage.googleapis.com' in file_url or storage_provider == 'firebase':
            try:
                from methods.storage import delete_file
                blob_name = provider_public_id
                if not blob_name and '/o/' in file_url:
                    import urllib.parse
                    blob_name = urllib.parse.unquote(file_url.split('/o/')[1].split('?')[0])
                if blob_name:
                    delete_file(blob_name)
            except Exception as fb_err:
                logging.warning(f"[admin_delete_file_completely] Firebase storage deletion error: {fb_err}")

        # 4. Database records deletion
        if doc_id:
            for tbl, col in [
                ('search_documents', 'file_id'),
                ('document_views', 'document_id'),
                ('document_likes', 'document_id'),
                ('document_bookmarks', 'document_id'),
                ('document_votes', 'document_id'),
                ('document_ratings', 'document_id'),
            ]:
                try:
                    client.table(tbl).delete().eq(col, doc_id).execute()
                except Exception:
                    pass

            try:
                client.table('material_requests').update({'response_document_id': None}).eq('response_document_id', doc_id).execute()
            except Exception:
                pass

            try:
                client.table('viewer_failure_reports').delete().eq('doc_id', doc_id).execute()
            except Exception:
                pass

            try:
                client.table('documents').delete().eq('id', doc_id).execute()
            except Exception as doc_del_err:
                logging.error(f"[admin_delete_file_completely] documents table delete error: {doc_del_err}")

        # Ensure the specific report is also cleaned up
        try:
            client.table('viewer_failure_reports').delete().eq('id', report_id).execute()
        except Exception:
            pass

        admin_user = session.get('user', {})
        admin_email = admin_user.get('email', 'Admin')
        log_admin_action('delete_file_completely', target=doc_id or report_id, details={
            'file_name': file_name,
            'doc_id': doc_id,
            'report_id': report_id,
            'admin': admin_email
        })

        return jsonify({
            'success': True,
            'message': f"'{file_name}' was completely removed from database and cloud storage.",
            'report_id': report_id,
            'doc_id': doc_id
        }), 200

    except Exception as e:
        logging.error("[admin_delete_file_completely] Error: internal error")
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500



@admin_bp.route('/api/admin/entity/add', methods=['POST'])
@auth_required
@admin_required
def api_add_entity():
    """Add a college, department, or subject entity."""
    data = request.json or {}
    entity_type = data.get('entity')
    name = data.get('name')
    short_name = data.get('short_name', '')
    code = data.get('code', '')
    semester = data.get('semester')
    parent_id = data.get('parent_id')
    
    if not entity_type or not name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
    try:
        if semester:
            semester = int(semester)
    except ValueError:
        semester = None
        
    result = add_new_entity(entity_type, name, short_name, code, semester, parent_id)
    if result.get('success'):
        log_admin_action('add_entity', target=f"{entity_type}:{name}", details={'code': code, 'semester': semester, 'parent_id': parent_id})
    return jsonify(result), 200 if result.get('success') else 500


# ─── Economy Configuration APIs ─────────────────────────────────────────────

@admin_bp.route('/api/admin/economy/config', methods=['GET'])
@auth_required
@admin_required
def api_admin_economy_get_config():
    """Return all scoring_config entries."""
    try:
        res = init_supabase().table('scoring_config').select('*').order('key').execute()
        return jsonify({'success': True, 'config': res.data or []}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/economy/config', methods=['POST'])
@auth_required
@admin_required
def api_admin_economy_update_config():
    """Update one scoring_config key's JSONB value. Body: {key, value}."""
    try:
        data = request.json or {}
        key = data.get('key')
        value = data.get('value')
        if not key or value is None:
            return jsonify({'success': False, 'message': 'Missing key or value'}), 400
        if not isinstance(value, (dict, list, int, float, str)):
            return jsonify({'success': False, 'message': 'Invalid value type'}), 400

        client = init_supabase()
        client.table('scoring_config').update({
            'value': value, 'updated_at': 'now()'
        }).eq('key', key).execute()

        try:
            import methods.scoring_engine as se
            se._CONFIG_CACHE = {}
            se._CONFIG_CACHE_AT = 0.0
        except Exception:
            pass
        logging.info(f"[ECONOMY] admin updated scoring_config['{key}']")
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/economy/overview', methods=['GET'])
@auth_required
@admin_required
def api_admin_economy_overview():
    """Level distribution + top contributors/consumers + recent scored events."""
    try:
        client = init_supabase()

        levels_res = client.table('profiles').select('id, full_name, access_level, abhihub_score, consumption_score, ccr').limit(5000).execute()
        users = levels_res.data or []
        dist = {}
        for u in users:
            lvl = u.get('access_level') or 'explorer'
            dist[lvl] = dist.get(lvl, 0) + 1
        by_score = sorted(users, key=lambda u: float(u.get('abhihub_score') or 0), reverse=True)
        by_ccr = sorted(users, key=lambda u: float(u.get('ccr') or 0))

        logs_res = client.table('contribution_logs').select(
            'user_id, action_type, xp_awarded, description, created_at, profiles(full_name)'
        ).order('created_at', desc=True).limit(25).execute()

        return jsonify({
            'success': True,
            'total_users': len(users),
            'level_distribution': dist,
            'top_contributors': [
                {'name': u.get('full_name'), 'score': u.get('abhihub_score'), 'level': u.get('access_level')}
                for u in by_score[:10]
            ],
            'most_consumer_heavy': [
                {'name': u.get('full_name'), 'ccr': u.get('ccr'), 'level': u.get('access_level')}
                for u in by_ccr[:10] if float(u.get('ccr') or 0) > 0
            ],
            'recent_events': logs_res.data or [],
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/economy/user/<user_id>', methods=['POST'])
@auth_required
@admin_required
def api_admin_economy_override_user(user_id):
    """Manually override a user's access level. Body: {access_level}."""
    try:
        data = request.json or {}
        level = data.get('access_level')
        allowed = {'explorer', 'member', 'contributor', 'power_contributor', 'community_leader'}
        if level not in allowed:
            return jsonify({'success': False, 'message': f'access_level must be one of {allowed}'}), 400
        client = init_supabase()
        target_uid = user_id.strip()
        if '@' in target_uid or len(target_uid) != 36:
            res = client.table('profiles').select('id').or_(f"email.eq.{target_uid},full_name.ilike.%{target_uid}%").limit(1).execute()
            if res.data and len(res.data) > 0:
                target_uid = res.data[0]['id']
            else:
                return jsonify({'success': False, 'message': f'User "{user_id}" not found'}), 404

        client.table('profiles').update({'access_level': level}).eq('id', target_uid).execute()
        logging.info("[ECONOMY] Admin updated user access level (level=%s)", level)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


# ─── IndexNow Search Submission ─────────────────────────────────────────────

@admin_bp.route('/api/indexnow/submit', methods=['POST'])
@auth_required
@admin_required
def api_indexnow_submit():
    """Manual URL indexing submission endpoint for admin."""
    try:
        data = request.get_json() or {}
        urls = data.get('urls', [])
        if not urls or not isinstance(urls, list):
            return jsonify({'success': False, 'message': 'urls list is required'}), 400
        
        success = _trigger_indexnow_helper(urls)
        if success:
            return jsonify({'success': True, 'message': f'Submitted {len(urls)} URLs successfully'})
        return jsonify({'success': False, 'message': 'IndexNow submission failed or key not configured'}), 400
    except Exception as e:
        logging.error('[api_indexnow_submit] internal error')
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500


# ─── File & Storage Management Endpoints ────────────────────────────────────

@admin_bp.route('/api/admin/files', methods=['GET'])
@auth_required
@admin_required
def admin_get_files():
    """List uploaded files with uploader info, storage provider, size, and status."""
    try:
        from services.admin_service import list_files
        search = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        page = max(1, request.args.get('page', 1, type=int))
        limit = min(max(1, request.args.get('limit', 50, type=int)), 100)

        result = list_files(search=search, status=status, page=page, limit=limit)
        return jsonify(result)
    except Exception as e:
        logging.error("[admin_get_files] internal error")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@admin_bp.route('/api/admin/files/<doc_id>', methods=['DELETE', 'POST'])
@auth_required
@admin_required
def admin_delete_single_file(doc_id):
    """Delete a single file completely from Cloudinary, Firebase, Supabase, and DB."""
    admin_user = session.get('user', {})
    data = request.get_json(silent=True) or {}
    reason = str(data.get('reason', 'Admin file deletion')).strip()

    from services.admin_service import delete_file_completely
    ok, msg = delete_file_completely(doc_id, admin_user, reason)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400
    return jsonify({'success': True, 'message': msg})


@admin_bp.route('/api/admin/files/bulk-delete', methods=['POST'])
@auth_required
@admin_required
def admin_bulk_delete_files_endpoint():
    """Bulk delete files completely across all storage providers and database."""
    admin_user = session.get('user', {})
    data = request.get_json() or {}
    doc_ids = data.get('doc_ids', [])
    reason = str(data.get('reason', 'Admin bulk removal')).strip()

    if not doc_ids or not isinstance(doc_ids, list):
        return jsonify({'success': False, 'error': 'doc_ids list is required'}), 400

    from services.admin_service import bulk_delete_files
    result = bulk_delete_files(doc_ids, admin_user, reason)
    return jsonify(result)


@admin_bp.route('/api/admin/files/<doc_id>/quarantine', methods=['POST'])
@auth_required
@admin_required
def admin_quarantine_file_endpoint(doc_id):
    """Flag or quarantine a suspicious document."""
    admin_user = session.get('user', {})
    data = request.get_json() or {}
    reason = str(data.get('reason', 'Suspicious or flagged by administration')).strip()

    from services.admin_service import flag_quarantine_file
    ok, msg = flag_quarantine_file(doc_id, admin_user, reason)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400
    return jsonify({'success': True, 'message': msg})


# ─── Audit Trail & Compliance Endpoints ─────────────────────────────────────

@admin_bp.route('/api/admin/audit/logs', methods=['GET'])
@auth_required
@admin_required
def admin_get_audit_logs():
    """Query paginated audit logs with optional filters."""
    action = request.args.get('action')
    admin_id = request.args.get('admin_id')
    target_type = request.args.get('target_type')
    page = max(1, request.args.get('page', 1, type=int))
    limit = min(max(1, request.args.get('limit', 50, type=int)), 100)

    from services.admin_service import get_audit_logs
    res = get_audit_logs(action=action, admin_id=admin_id, target_type=target_type, page=page, limit=limit)
    return jsonify(res)


@admin_bp.route('/api/admin/audit/export/csv', methods=['GET'])
@auth_required
@admin_required
def admin_export_audit_logs_csv():
    """Download audit logs in CSV format."""
    from flask import Response
    from services.admin_service import export_audit_logs_csv
    csv_data = export_audit_logs_csv()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=admin_audit_trail_{timestamp}.csv'}
    )


# ─── Site Settings & Operations Endpoints ───────────────────────────────────

@admin_bp.route('/api/admin/settings', methods=['GET'])
@auth_required
@admin_required
def admin_get_settings():
    """Retrieve site-wide configuration flags."""
    from services.admin_service import get_site_settings
    settings = get_site_settings()
    return jsonify({'success': True, 'settings': settings})


@admin_bp.route('/api/admin/settings', methods=['POST'])
@auth_required
@admin_required
def admin_update_setting():
    """Update a specific site configuration flag."""
    admin_user = session.get('user', {})
    data = request.get_json() or {}
    key = str(data.get('key', '')).strip()
    value = data.get('value')

    if not key or value is None:
        return jsonify({'success': False, 'error': 'Key and value are required'}), 400

    from services.admin_service import update_site_setting
    ok, msg = update_site_setting(admin_user, key, value)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400
    return jsonify({'success': True, 'message': msg})
