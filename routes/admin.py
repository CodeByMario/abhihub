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
)

from routes.auth import auth_required, admin_required, log_admin_action
from methods.supabase_helper import (
    init_supabase,
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
        logging.error(f"[IndexNow helper] {e}")
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


@admin_bp.route('/admin/developer')
@auth_required
@admin_required
def admin_developer_panel():
    """Admin Developer Panel: cloud stats, feature health, live logs."""
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

@admin_bp.route('/api/admin/payment/transactions', methods=['GET'])
@admin_required
def admin_get_payment_transactions():
    """Fetch recent payment transaction records for admin audit."""
    try:
        res = supabase.table('credit_transactions').select('*').order('created_at', desc=True).limit(50).execute()
        return jsonify({'success': True, 'transactions': res.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
    return jsonify({'success': True, 'message': f'Payout {action} successfully'})


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
                'paper_quota_remaining': p.get('paper_quota_remaining', 19),
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
        return jsonify({'success': False, 'error': str(e), 'wallets': []}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        logging.error(f"Error sending notification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/notification-history', methods=['GET'])
@auth_required
@admin_required
def get_admin_notification_history():
    """Get notification history (last 10 entries)."""
    try:
        history = get_notification_history()
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        logging.error(f"[admin broadcast-stats] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        logging.error(f"[admin system-health] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        result['cloudinary']['error'] = str(e)
    try:
        client = init_supabase()
        if client:
            res = client.rpc('get_db_size').execute()
            if res.data:
                result['supabase']['db_size_bytes'] = res.data
    except Exception as e:
        err_str = str(e)
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
            return {'name': name, 'status': 'error', 'latency_ms': round((time.time()-t0)*1000), 'error': str(e)[:120]}

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
                with open(lf, 'r', errors='replace') as f:
                    all_lines = f.readlines()
                lines = all_lines[-n:]
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


# ─── User Management & Admin Statistics ─────────────────────────────────────

@admin_bp.route('/api/admin/users', methods=['GET'])
@auth_required
@admin_required
def admin_get_users():
    """Get list of users with verification and academic details for admin dashboard."""
    try:
        client = init_supabase()
        sort_by = request.args.get('sort', 'recent')
        category = request.args.get('category', '').strip()
        search = request.args.get('q', '').strip()
        
        query = client.table('profiles')\
            .select('id, full_name, email, created_at, role, is_verified, verified_at, verified_by, reputation_score, abhihub_score, rank_title, access_level, degree, last_active_at, students_helped, college_id, department_id, phone_number, paper_quota_remaining, referral_credits')
        
        if search:
            query = query.or_(f"full_name.ilike.%{search}%,email.ilike.%{search}%")
        if category and category.lower() != 'all':
            query = query.ilike('degree', f"%{category}%")

        if sort_by == 'top':
            query = query.order('abhihub_score', desc=True).order('reputation_score', desc=True)
        elif sort_by == 'active':
            query = query.order('last_active_at', desc=True)
        elif sort_by == 'unverified':
            query = query.eq('is_verified', False).order('created_at', desc=True)
        else:
            query = query.order('created_at', desc=True)
            
        res = query.limit(300).execute()
        users = res.data or []

        top_students = sorted(
            users,
            key=lambda u: (u.get('abhihub_score') or 0, u.get('reputation_score') or 0, u.get('students_helped') or 0),
            reverse=True
        )[:10]

        return jsonify({
            'success': True,
            'users': users,
            'top_students': top_students,
            'total_count': len(users)
        })
    except Exception as e:
        logging.error(f"[admin_get_users] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/verify-user', methods=['POST'])
@auth_required
@admin_required
def admin_verify_user():
    """Verify or unverify a user profile."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        is_verified = bool(data.get('is_verified', True))
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        admin_user = session.get('user', {})
        admin_uid = admin_user.get('uid') or admin_user.get('id')

        update_payload = {
            'is_verified': is_verified,
            'verified_at': datetime.now(timezone.utc).isoformat() if is_verified else None,
            'verified_by': admin_uid if (is_verified and validate_uuid(admin_uid)) else None
        }

        res = client.table('profiles').update(update_payload).eq('id', user_id).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'User not found or update failed'}), 404

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

        log_admin_action('verify_user', target=user_id, details={'is_verified': is_verified})
        return jsonify({
            'success': True,
            'message': f"User successfully {'verified' if is_verified else 'unverified'}.",
            'profile': res.data[0]
        })
    except Exception as e:
        logging.error(f"[admin_verify_user] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/update-user-role', methods=['POST'])
@auth_required
@admin_required
def admin_update_user_role():
    """Update a user role (student, teacher, moderator, admin)."""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        new_role = (data.get('role') or '').lower().strip()
        valid_roles = {'student', 'teacher', 'moderator', 'admin'}
        if not user_id or new_role not in valid_roles:
            return jsonify({'success': False, 'error': f"Valid user_id and role ({', '.join(valid_roles)}) required"}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500

        res = client.table('profiles').update({'role': new_role}).eq('id', user_id).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'User not found or update failed'}), 404

        log_admin_action('update_user_role', target=user_id, details={'new_role': new_role})
        return jsonify({
            'success': True,
            'message': f"User role successfully updated to '{new_role}'.",
            'profile': res.data[0]
        })
    except Exception as e:
        logging.error(f"[admin_update_user_role] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        logging.error(f"[admin_update_user_level] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<user_id>/stats', methods=['GET'])
@auth_required
@admin_required
def admin_get_user_stats(user_id):
    """Get detailed stats for a specific user."""
    try:
        client = init_supabase()
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
            paper_quota = 19
        referral_credits = prof_data.get('referral_credits', 0) or 0
        access_level = prof_data.get('access_level') or 'explorer'
        rank_title = prof_data.get('rank_title') or 'Beginner'

        from methods.wallet_service import get_creator_wallet
        w_data = get_creator_wallet(user_id)
        wallet_info = w_data.get('wallet', {}) if w_data.get('success') else {}

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
                'wallet': wallet_info
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
                
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'approved_documents': approved_docs,
                'pending_documents': pending_docs,
                'total_views': total_views,
                'total_subscribers': total_subs,
                'total_messages': messages_count
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        logging.error(f'[pending-documents] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
            for table_name, col in [('search_documents', 'file_id'), ('document_views', 'document_id'), ('document_likes', 'document_id'), ('document_bookmarks', 'document_id'), ('viewer_failure_reports', 'doc_id')]:
                try:
                    client.table(table_name).delete().eq(col, doc_id).execute()
                except Exception:
                    pass
            client.table('documents').delete().eq('id', doc_id).execute()
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
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/file-reports')
@admin_required
def admin_file_reports():
    """API endpoint for admin to view all file reports and logs with full student profiles."""
    try:
        client = init_supabase()
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
        logging.error(f"Error fetching admin file reports: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/admin/file-reports/<report_id>/status', methods=['POST'])
@auth_required
@admin_required
def admin_update_file_report_status(report_id):
    """Update a failure report status (open, resolved, closed)."""
    try:
        data = request.get_json() or {}
        new_status = data.get('status', 'resolved').lower().strip()
        if new_status not in ['open', 'resolved', 'closed']:
            return jsonify({'success': False, 'message': 'Invalid status. Must be open, resolved, or closed'}), 400
            
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database client not initialized'}), 500
            
        admin_user = session.get('user', {})
        admin_email = admin_user.get('email', 'Admin')

        res = client.table('viewer_failure_reports').update({
            'status': new_status
        }).eq('id', report_id).execute()

        log_admin_action('update_file_report_status', target=report_id, details={'status': new_status, 'admin': admin_email})
        return jsonify({
            'success': True,
            'report_id': report_id,
            'status': new_status,
            'message': f"Report successfully marked as {new_status}."
        }), 200
    except Exception as e:
        logging.error(f"[admin_update_file_report_status] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


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
        return jsonify({'success': False, 'message': str(e)}), 500


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
        return jsonify({'success': False, 'message': str(e)}), 500


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
        return jsonify({'success': False, 'message': str(e)}), 500


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
        logging.info(f"[ECONOMY] admin set user {target_uid} access_level={level}")
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


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
        logging.error(f'[api_indexnow_submit] {e}')
        return jsonify({'success': False, 'message': str(e)}), 500
