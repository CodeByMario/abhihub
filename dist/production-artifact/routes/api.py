"""
AbhiHub Core JSON APIs Blueprint.
Handles system health, telemetry, user profiles, authentication state,
and student onboarding APIs.
"""
import os
import json
import logging
from datetime import datetime, timezone

from flask import (
    Blueprint,
    request,
    jsonify,
    session,
    current_app,
    make_response,
    Response,
    redirect,
    abort,
    send_from_directory,
    url_for,
)

from routes.auth import auth_required, admin_required
from methods.supabase_helper import (
    init_supabase,
    check_profile_completed,
    get_reputation_stats,
    validate_uuid,
    save_file_access,
    track_user_event,
    get_device_type,
    ensure_referral_code,
    register_referral,
    get_onboarding_status,
    mark_welcome_seen,
)

api_bp = Blueprint('api', __name__)

SUSPECTS_FILE = os.path.join('data', 'suspects.json')


# ─── System Health, Version & Telemetry ──────────────────────────────────────

@api_bp.route('/health')
@api_bp.route('/api/health')
def health_check():
    """Lightweight health check endpoint for monitoring without secret leakage."""
    return jsonify({
        'status': 'healthy',
        'service': 'abhihub',
        'version': '1.0.0',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200


@api_bp.route('/api/version')
def version_info():
    """Return current app version for footer and cache management."""
    return jsonify({"version": "1.0.0"})


@api_bp.route('/api/get-upload-signature', methods=['POST'])
@auth_required
def get_upload_signature():
    """Generates a presigned Cloudinary upload signature for client-side direct uploads."""
    import time
    import cloudinary.utils
    timestamp = int(time.time())
    folder = "uploads"
    params = {
        'timestamp': timestamp,
        'folder': folder
    }
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    if not api_secret or not cloud_name:
        return jsonify({'success': False, 'message': 'Storage configuration error'}), 500

    signature = cloudinary.utils.api_sign_request(params, api_secret)
    return jsonify({
        'success': True,
        'upload_url': f"https://api.cloudinary.com/v1_1/{cloud_name}/auto/upload",
        'api_key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'folder': folder
    }), 200


@api_bp.route('/api/cache-health', methods=['GET'])
def api_cache_health():
    """Cache system health check — returns stats for all cache layers."""
    app_cache = getattr(current_app, 'cache', None)
    stats = app_cache.stats() if app_cache and hasattr(app_cache, 'stats') else {}
    return jsonify({
        'status': 'ok',
        'cache': stats,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200


@api_bp.route('/api/quota', methods=['GET'])
@auth_required
def api_get_quota():
    """Return the current quota for the logged-in user."""
    import app as main_app
    q = main_app._get_quota() if hasattr(main_app, '_get_quota') else {}
    quota_per_upload = getattr(main_app, 'QUOTA_PER_UPLOAD', 5)
    return jsonify({
        'credits': q.get('credits', 0),
        'total_views': q.get('total_views', 0),
        'quota_per_upload': quota_per_upload
    }), 200


@api_bp.route('/api/widget-data')
def widget_data():
    """API endpoint for widget data updates."""
    try:
        data_file = os.path.join(current_app.root_path, 'static/premium/data.json')
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        latest = data[:2] if len(data) >= 2 else data
        return jsonify({
            "image1": "/static/images/android-chrome-192x192.png",
            "title1": latest[0].get('file-name', 'No documents') if latest else 'Welcome',
            "subtitle1": latest[0].get('subject', 'AbhiHub') if latest else 'Your study hub',
            "image2": "/static/images/android-chrome-192x192.png",
            "title2": latest[1].get('file-name', 'Start exploring') if len(latest) > 1 else 'Start exploring',
            "subtitle2": latest[1].get('subject', 'Notes & papers') if len(latest) > 1 else 'Notes & papers'
        })
    except Exception:
        return jsonify({
            "image1": "/static/images/android-chrome-192x192.png",
            "title1": "AbhiHub",
            "subtitle1": "Your study hub",
            "image2": "/static/images/android-chrome-192x192.png",
            "title2": "Open app",
            "subtitle2": "Browse materials"
        })


@api_bp.route('/api/my-access', methods=['GET'])
@auth_required
def api_my_access():
    """Current user's access level, feature gate limits, and ad density."""
    try:
        from methods.scoring_engine import get_feature_gate
        uid = session.get('user', {}).get('uid')
        gate = get_feature_gate(uid)
        quota = {'allowed': True, 'remaining': None}
        progress = None
        if uid:
            from methods.scoring_engine import check_upload_quota, get_access_progress
            quota = check_upload_quota(uid)
            progress = get_access_progress(uid)
        level = (gate.get('level') or '').lower()
        can_monetize = level in ['contributor', 'power_contributor', 'community_leader'] or session.get('user', {}).get('role') == 'admin' or session.get('is_admin', False)
        return jsonify({
            'success': True,
            'level': gate.get('level'),
            'can_monetize': can_monetize,
            'limits': {k: v for k, v in gate.items() if k != 'level'},
            'uploads_today_remaining': quota.get('remaining'),
            'progress': progress,
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/events', methods=['POST'])
@api_bp.route('/api/document-view', methods=['POST'])
@api_bp.route('/api/track-file-access', methods=['POST'])
@auth_required
def api_track_event():
    """Unified telemetry and event tracking endpoint."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        user_email = user_info.get('email', '')
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_type = (data.get('event_type') or '').upper().strip()

        if event_type in ('DOCUMENT_VIEW', 'VIEW') or request.path.endswith('/document-view'):
            document_id = data.get('document_id') or data.get('doc_id')
            if not document_id:
                return jsonify({'success': False, 'message': 'Missing document_id'}), 400
            if not user_id:
                return jsonify({'success': False, 'message': 'User not authenticated'}), 401

            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
            user_agent = request.headers.get('User-Agent', '')
            device_type = get_device_type(user_agent)

            from data.interactions import DocumentView
            result = DocumentView.log_view(
                user_id=user_id,
                document_id=document_id,
                ip_address=ip_address,
                device_type=device_type
            )
            if result.get('success'):
                try:
                    from methods.scoring_engine import process_event
                    is_owner = False
                    try:
                        _res = init_supabase().table('documents').select('uploader_id').eq('id', document_id).limit(1).execute()
                        if _res.data:
                            is_owner = (_res.data[0].get('uploader_id') == user_id)
                    except Exception:
                        pass
                    process_event(
                        user_id=user_id,
                        event_type='resource_viewed',
                        entity_id=document_id,
                        entity_type='document',
                        actor_is_owner=is_owner,
                        description='Viewed a resource',
                    )
                except Exception:
                    pass

                return jsonify({
                    'success': True,
                    'message': 'Document view recorded',
                    'data': result.get('view', {})
                }), 200
            else:
                return jsonify({'success': False, 'message': result.get('message', 'Failed to log document view')}), 500

        if event_type in ('FILE_ACCESS', 'TRACK_FILE_ACCESS') or request.path.endswith('/track-file-access'):
            file_name = data.get('file_name', '')
            file_type = data.get('file_type', 'unknown')
            file_path = data.get('file_path', '')
            file_url = data.get('file_url', '')
            if not file_name:
                return jsonify({'success': False, 'message': 'File name required'}), 400

            result = save_file_access(
                user_email=user_email,
                file_name=file_name,
                file_type=file_type,
                file_path=file_path,
                file_url=file_url
            )
            return jsonify(result), 200 if result.get('success') else 500

        track_user_event(user_id, event_type, data.get('metadata', {}))
        return jsonify({'success': True}), 200

    except Exception as e:
        logging.error(f"[EVENTS API ERROR] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── Auth, User Profiles & Accounts ──────────────────────────────────────────

@api_bp.route('/auth', methods=['POST'])
def authorize():
    """Client-side Supabase token authorization endpoint."""
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'success': False, 'message': 'Missing or invalid Authorization header'}), 401

    token = token[7:].strip()
    if not token:
        return jsonify({'success': False, 'message': 'Empty token provided'}), 401

    user_data = None
    client = init_supabase() or init_supabase_admin()

    # 1. Primary: Verify token against Supabase Auth API
    if client:
        try:
            res = client.auth.get_user(token)
            if res and res.user:
                u = res.user
                u_meta = u.user_metadata or {}
                app_meta = u.app_metadata or {}
                user_email = u.email or u_meta.get('email', '')
                user_name = u_meta.get('full_name') or u_meta.get('name') or (user_email.split('@')[0] if user_email else 'User')
                user_data = {
                    'id': u.id,
                    'email': user_email,
                    'name': user_name,
                    'provider': app_meta.get('provider', 'google'),
                    'user_metadata': u_meta
                }
        except Exception as e:
            logging.warning(f"[AUTH] client.auth.get_user failed: {e}")

    # 2. Fallback: Parse claims directly if JWT signature is valid or network was unreachable
    if not user_data:
        try:
            import jwt
            payload = jwt.decode(token, options={"verify_signature": False})
            uid = payload.get('sub') or payload.get('user_id')
            user_meta = payload.get('user_metadata') or {}
            email = payload.get('email') or user_meta.get('email', '')
            if uid and email:
                app_meta = payload.get('app_metadata') or {}
                user_name = user_meta.get('full_name') or user_meta.get('name') or (email.split('@')[0] if email else 'User')
                user_data = {
                    'id': uid,
                    'email': email,
                    'name': user_name,
                    'provider': app_meta.get('provider', 'google'),
                    'user_metadata': user_meta
                }
        except Exception as jwt_err:
            logging.error(f"[AUTH] JWT fallback parsing error: {jwt_err}")

    if not user_data or not user_data.get('email'):
        return jsonify({'success': False, 'message': 'Unauthorized: Invalid token or expired session'}), 401

    session['user'] = {
        'uid': user_data['id'],
        'email': user_data['email'],
        'name': user_data['name'],
        'provider': user_data['provider'],
        'user_metadata': user_data['user_metadata']
    }
    session.permanent = True

    try:
        from data.profiles import UserSession
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        device_type = get_device_type(user_agent)

        session_result = UserSession.log_login(
            user_id=user_data['id'],
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type
        )
        if session_result and session_result.get('success'):
            session['session_id'] = session_result.get('session_id')
    except Exception as sess_err:
        logging.warning(f"[AUTH] Logging login session failed: {sess_err}")

    # Process referral reward if referral code was provided at authorization
    payload = request.get_json(silent=True) or {}
    ref_code = (payload.get('ref') or '').strip()
    if ref_code:
        try:
            ensure_referral_code(user_data['id'])
            register_referral(user_data['id'], ref_code)
        except Exception as ref_err:
            logging.warning(f"[AUTH] Referral crediting failed: {ref_err}")

    return jsonify({'success': True, 'message': 'Authenticated', 'user': session['user']}), 200


@api_bp.route('/api/me', methods=['GET'])
def api_me():
    """Canonical current user endpoint returning auth state and profile info."""
    is_auth = 'user' in session and bool(session.get('user', {}).get('uid'))
    if not is_auth:
        return jsonify({
            'success': True,
            'authenticated': False,
            'profile_completed': False,
            'user': None
        }), 200

    user_info = session.get('user', {})
    user_id = user_info.get('uid')

    is_complete = False
    try:
        is_complete = check_profile_completed(user_id)
    except Exception:
        pass

    user_profile = {
        'uid': user_id,
        'email': user_info.get('email'),
        'name': user_info.get('name'),
        'provider': user_info.get('provider'),
        'user_metadata': user_info.get('user_metadata', {})
    }

    try:
        rep_stats = get_reputation_stats(user_id)
        if rep_stats.get('success'):
            user_profile['students_helped'] = rep_stats.get('students_helped', 0)
            user_profile['badges'] = rep_stats.get('badges', [])

        client = init_supabase()
        if client:
            pres = client.table('profiles').select('college_id, department_id').eq('id', user_id).single().execute()
            if pres.data:
                user_profile['college_id'] = pres.data.get('college_id')
                user_profile['department_id'] = pres.data.get('department_id')
    except Exception:
        pass

    return jsonify({
        'success': True,
        'authenticated': True,
        'profile_completed': is_complete,
        'user': user_profile
    }), 200


@api_bp.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated."""
    return jsonify({
        'authenticated': 'user' in session,
        'user': session.get('user', {}) if 'user' in session else None
    }), 200


@api_bp.route('/api/check-profile', methods=['GET'])
@auth_required
def api_check_profile():
    """Check if current user profile is completed."""
    user_id = session.get('user', {}).get('uid')
    is_completed = check_profile_completed(user_id) if user_id else False
    return jsonify({'profile_completed': is_completed}), 200


@api_bp.route('/api/profile-status')
@auth_required
def profile_status():
    """Lightweight endpoint returning profile completion state."""
    try:
        user_id = session.get('user', {}).get('uid')
        if not user_id:
            return jsonify({'profile_completed': False}), 200
        client = init_supabase()
        res = client.table('profiles').select('college_id, department_id').eq('id', user_id).single().execute()
        completed = bool(res.data and res.data.get('college_id') and res.data.get('department_id'))
        return jsonify({'profile_completed': completed}), 200
    except Exception:
        return jsonify({'profile_completed': False}), 200


@api_bp.route('/api/profile', methods=['GET'])
@auth_required
def get_profile():
    """Get current user profile with reputation and badges."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        students_helped = 0
        badges = []
        college_id = None
        department_id = None

        if user_id:
            rep_stats = get_reputation_stats(user_id)
            if rep_stats.get('success'):
                students_helped = rep_stats.get('students_helped', 0)
                badges = rep_stats.get('badges', [])

            try:
                client = init_supabase()
                pres = client.table('profiles').select('college_id, department_id').eq('id', user_id).single().execute()
                if pres.data:
                    college_id = pres.data.get('college_id')
                    department_id = pres.data.get('department_id')
            except Exception:
                pass

        return jsonify({
            'success': True,
            'user': {
                'uid': user_info.get('uid'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'provider': user_info.get('provider'),
                'user_metadata': user_info.get('user_metadata', {}),
                'college_id': college_id,
                'department_id': department_id,
                'students_helped': students_helped,
                'badges': badges,
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/profile/update', methods=['POST'])
@auth_required
def api_update_profile():
    """Update profile's default college and department selection."""
    try:
        user_id = session.get('user', {}).get('uid')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        data = request.get_json() or {}
        college_id = (data.get('college_id') or '').strip()
        department_id = (data.get('department_id') or '').strip()
        
        client = init_supabase()
        update_data = {}
        if validate_uuid(college_id):
            update_data['college_id'] = college_id
        if validate_uuid(department_id):
            update_data['department_id'] = department_id

        if update_data:
            client.table('profiles').update(update_data).eq('id', user_id).execute()
            return jsonify({'success': True}), 200
        
        return jsonify({'success': False, 'message': 'No valid fields provided'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/onboarding/status', methods=['GET'])
@auth_required
def api_onboarding_status():
    user_id = session.get('user', {}).get('uid')
    result = get_onboarding_status(user_id)
    return jsonify(result), 200 if result.get('success') else 500


@api_bp.route('/api/onboarding/welcome-seen', methods=['POST'])
@auth_required
def api_onboarding_welcome_seen():
    user_id = session.get('user', {}).get('uid')
    result = mark_welcome_seen(user_id)
    return jsonify(result), 200 if result.get('success') else 500


# ─── Unified Issue, Broken File & Suspect Reports ───────────────────────────

@api_bp.route('/api/reports', methods=['POST'])
@api_bp.route('/api/report-suspect', methods=['POST'])
@api_bp.route('/api/report-issue', methods=['POST'])
@api_bp.route('/api/report-broken-file', methods=['POST'])
def api_reports():
    """Unified report endpoint handling suspect events, broken files, and general issues."""
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        report_type = (data.get('type') or data.get('report_type') or '').lower().strip()

        if report_type == 'suspect' or request.path.endswith('/report-suspect'):
            user = session.get('user', {})
            action = data.get('action', 'unauthorized_access')
            user_email = user.get('email', 'unknown')
            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
            user_agent = request.headers.get('User-Agent', '')

            if 'screenshot' in action.lower():
                enum_action = 'screenshot_detected'
            elif 'right' in action.lower() or 'context' in action.lower():
                enum_action = 'right_click_prevented'
            elif 'dev' in action.lower() or 'inspect' in action.lower():
                enum_action = 'devtools_opened'
            else:
                enum_action = 'unauthorized_access'

            from methods.supabase_helper import log_security_audit_event
            res = log_security_audit_event(user_email, enum_action, ip_address, user_agent, {'frontend_action': action})
            return jsonify(res), 200 if res.get('success') else 500

        user = session.get('user') or {}
        user_email = user.get('email', 'guest')
        user_id = user.get('uid', None) or None

        file_id = data.get('file_id') or data.get('doc_id') or ''
        file_name = data.get('file_name') or data.get('doc_title') or 'Unknown document'
        file_url = data.get('file_url') or ''
        file_type = data.get('file_type', 'unknown')
        issue_type = data.get('issue_type') or ('Broken / unreadable file' if 'broken-file' in request.path or report_type == 'broken_file' else 'General issue')
        message = (data.get('message') or data.get('error_message') or '').strip()
        page_url = data.get('page_url') or data.get('doc_url') or request.referrer or ''
        viewer_type = data.get('viewer_type') or ('pdf' if 'broken-file' in request.path or report_type == 'broken_file' else 'in_viewer_report')

        if not message and not file_name and not file_id:
            return jsonify({'success': False, 'error': 'Please provide issue details.'}), 400

        report_data = {
            'doc_id': str(file_id) if file_id else file_name[:80],
            'file_name': file_name,
            'file_url': file_url,
            'file_type': file_type,
            'issue_type': issue_type,
            'error_msg': f"{issue_type}: {message}" if (message and issue_type != message) else (message or issue_type),
            'page_url': page_url,
            'reporter_email': user_email,
            'reporter_id': user_id,
            'viewer_type': viewer_type,
            'status': 'open',
        }

        client = None
        try:
            from methods.supabase_helper import init_supabase_admin
            client = init_supabase_admin() or init_supabase()
        except Exception:
            client = init_supabase()

        if not client:
            return jsonify({'success': False, 'error': 'Database client unavailable'}), 500

        try:
            result = client.table('viewer_failure_reports').insert(report_data).execute()
            report_id = result.data[0].get('id') if result.data else None
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

        return jsonify({'success': True, 'message': 'Report submitted successfully', 'report_id': report_id}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Referral & Credits APIs ─────────────────────────────────────────────────

@api_bp.route('/api/referral/register', methods=['POST'])
def api_referral_register():
    """Capture a referral code at signup and credit both sides."""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        payload = request.get_json(silent=True) or {}
        code = (payload.get('code') or '').strip()
        if not code:
            return jsonify({'success': False, 'message': 'No referral code provided'}), 400
        new_user_id = session['user'].get('uid') or session['user'].get('id')
        ensure_referral_code(new_user_id)
        result = register_referral(new_user_id, code)
        if result.get('success'):
            return jsonify({'success': True, 'credit_invitee': result.get('credit_invitee', 0)}), 200
        return jsonify({'success': False, 'message': result.get('message', 'Could not apply referral')}), 400
    except Exception as e:
        logging.error(f"[Referral] register endpoint failed: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500


@api_bp.route('/api/referral/my-code', methods=['GET'])
@auth_required
def api_referral_my_code():
    """Return the logged-in user's shareable referral code + link + progress."""
    try:
        uid = session['user'].get('uid')
        code = ensure_referral_code(uid)
        base = os.getenv('BASE_DOMAIN', 'abhihub.edu.eu.org')
        referral_count = 0
        referral_credits = 0
        try:
            client = init_supabase()
            if client:
                res = client.table('profiles').select('referral_count, referral_credits').eq('id', uid).limit(1).execute()
                if res.data:
                    referral_count = res.data[0].get('referral_count', 0) or 0
                    referral_credits = res.data[0].get('referral_credits', 0) or 0
        except Exception as e:
            logging.error(f"[Referral] my-code lookup failed: {e}")

        share_url = f"https://{base}/signup?ref={code}"
        return jsonify({
            'success': True,
            'code': code,
            'share_url': share_url,
            'referral_count': referral_count,
            'referral_credits': referral_credits
        }), 200
    except Exception as e:
        logging.error(f"[Referral] my-code endpoint failed: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500


@api_bp.route('/api/buy-credits', methods=['POST'])
@auth_required
def api_buy_credits():
    """Endpoint to initiate purchase for credit packs (50, 100, 500 views @ ₹2/view)."""
    try:
        import time
        import secrets
        from cache_manager import get_cache
        from data.pricing import log_credit_transaction
        from methods.phonepe_service import initiate_phonepe_payment
        from data.transactions import save_transaction_record

        user_info = session.get('user', {})
        user_id = user_info.get('uid') or user_info.get('id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
            
        data = request.get_json(silent=True) or {}
        pack_size = int(data.get('pack', 0) or 0)
        
        valid_packs = {50: 100, 100: 200, 500: 1000}
        if pack_size not in valid_packs:
            return jsonify({'success': False, 'message': 'Invalid pack. Choose 50, 100, or 500 views.'}), 400
            
        price_inr = float(valid_packs[pack_size])
        order_id = f"AH{int(time.time())}{secrets.token_hex(2).upper()}"

        base_url = request.host_url.rstrip('/')
        redirect_url = f"{base_url}/payment/phonepe/redirect?order_id={order_id}&pack={pack_size}&user_id={user_id}"
        callback_url = f"{base_url}/api/payment/phonepe/callback"

        # Record initiated transaction in database
        save_transaction_record(order_id, {
            'user_id': user_id,
            'amount': price_inr,
            'status': 'initiated',
            'utr': order_id,
            'admin_notes': f"purpose=Credits-{pack_size};pack={pack_size};views={pack_size}"
        })

        phonepe_res = initiate_phonepe_payment(
            order_id=order_id,
            amount_inr=price_inr,
            user_id=user_id,
            redirect_url=redirect_url,
            callback_url=callback_url
        )

        payment_url = None
        if phonepe_res.get('success') and phonepe_res.get('payment_url'):
            payment_url = phonepe_res['payment_url']
        else:
            # Fallback to checkout page with UPI QR & verification
            payment_url = f"/payment?amount={price_inr:.2f}&purpose=Credits-{pack_size}-Views&order_id={order_id}"

        return jsonify({
            'success': True,
            'pack': pack_size,
            'price_inr': price_inr,
            'order_id': order_id,
            'payment_url': payment_url,
            'message': 'Payment initiated. Redirecting to payment gateway…'
        }), 200
    except Exception as e:
        logging.error(f"[BUY-CREDITS] Error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/credit-history', methods=['GET'])
@auth_required
def api_credit_history():
    """Retrieve user credit transactions (spend & earn history) and current quota balance."""
    try:
        from data.pricing import _get_quota
        uid = session['user'].get('uid')
        quota_info = _get_quota()
        remaining = quota_info.get('credits', 19)
        txs = []
        client = init_supabase()
        if client:
            try:
                res = client.table('credit_transactions').select('*').eq('user_id', uid).order('created_at', desc=True).limit(50).execute()
                if res.data:
                    txs = res.data
            except Exception:
                pass
        if not txs:
            txs = session.get('credit_history', [])
        return jsonify({
            'success': True,
            'remaining_credits': remaining,
            'transactions': txs
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── Academic Taxonomy & Metadata APIs ───────────────────────────────────────

@api_bp.route('/api/colleges', methods=['GET'])
def api_get_colleges():
    """Get all colleges for dropdown — cached at L1 for 1 hour."""
    from cache_manager import get_cache
    from methods.supabase_helper import get_all_colleges
    cache = get_cache()

    def fetch_all_colleges():
        result = get_all_colleges()
        return result.get('data', []) if result.get('success') else []

    if cache:
        colleges = cache.get_cached('dropdowns:colleges', level=cache.L1, ttl=cache.LONG, fetcher=fetch_all_colleges)
        response = jsonify({'success': True, 'colleges': colleges}), 200
        cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
        return response
    return jsonify({'success': True, 'colleges': fetch_all_colleges()}), 200


@api_bp.route('/api/branches', methods=['GET'])
def api_get_branches():
    """Get all branches for dropdown — cached at L1 for 1 hour."""
    from cache_manager import get_cache
    from methods.supabase_helper import get_all_branches
    cache = get_cache()

    def fetch_all_branches():
        result = get_all_branches()
        return result.get('data', []) if result.get('success') else []

    if cache:
        branches = cache.get_cached('dropdowns:branches', level=cache.L1, ttl=cache.LONG, fetcher=fetch_all_branches)
        response = jsonify({'success': True, 'branches': branches}), 200
        cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
        return response
    return jsonify({'success': True, 'branches': fetch_all_branches()}), 200


@api_bp.route('/api/departments', methods=['GET'])
def api_get_departments():
    """Return departments for a college, or all departments if not filtered."""
    from cache_manager import get_cache
    from methods.supabase_helper import get_departments_by_college, get_all_branches
    cache = get_cache()
    college_id = request.args.get('college_id', '').strip()
    if college_id:
        result = get_departments_by_college(college_id)
        return jsonify({'success': result.get('success', False), 'departments': result.get('data', [])}), 200
    
    def fetch_all_depts():
        res = get_all_branches()
        return res.get('data', []) if res.get('success') else []
    
    if cache:
        depts = cache.get_cached("departments:all", level=cache.L1, ttl=cache.LONG, fetcher=fetch_all_depts)
        return jsonify({'success': True, 'departments': depts}), 200
    return jsonify({'success': True, 'departments': fetch_all_depts()}), 200


@api_bp.route('/api/semesters', methods=['GET'])
def api_get_semesters():
    """Return all semesters 1-8."""
    semesters = [{'id': str(i), 'name': f'Semester {i}'} for i in range(1, 9)]
    semesters.append({'id': '0', 'name': 'All Semesters'})
    return jsonify({'success': True, 'semesters': semesters}), 200


@api_bp.route('/api/subjects', methods=['GET'])
def api_get_subjects():
    """Return subjects for a department, or search through all subjects by keyword."""
    from cache_manager import get_cache
    cache = get_cache()
    department_id = request.args.get('department_id', '').strip()
    semester = request.args.get('semester', type=int)
    query = request.args.get('q', '').strip()

    from methods.supabase_helper import init_supabase, init_supabase_admin
    client = init_supabase() or init_supabase_admin()
    if not client:
        return jsonify({'success': False, 'subjects': []}), 200

    if query:
        cache_key = f"subjects_search:{query.lower()}:{department_id or 'all'}:{semester or 0}"
        def search_fetcher():
            try:
                q = client.table("subjects").select("id, name, subject_code, semester, department_id")
                if department_id:
                    q = q.eq("department_id", department_id)
                if semester:
                    q = q.or_(f"semester.eq.{semester},semester.is.null")
                res = q.or_(f"name.ilike.%{query}%,subject_code.ilike.%{query}%").order("name").limit(60).execute()
                return res.data or []
            except Exception:
                try:
                    res = client.table("subjects").select("id, name, subject_code, semester, department_id").ilike("name", f"%{query}%").order("name").limit(60).execute()
                    return res.data or []
                except Exception:
                    return []

        subjects = cache.get_cached(cache_key, level=cache.L1, ttl=cache.SHORT, fetcher=search_fetcher) if cache else search_fetcher()
        return jsonify({'success': True, 'subjects': subjects}), 200

    if not department_id:
        cache_key = "subjects:all_popular"
        def fetch_all():
            try:
                res = client.table("subjects").select("id, name, subject_code, semester, department_id").order("name").limit(200).execute()
                return res.data or []
            except Exception:
                return []
        subjects = cache.get_cached(cache_key, level=cache.L1, ttl=cache.LONG, fetcher=fetch_all) if cache else fetch_all()
        return jsonify({'success': True, 'subjects': subjects}), 200

    cache_key = f"subjects:{department_id}:{semester or 0}"
    def fetch_subjects():
        try:
            q = client.table("subjects").select("id, name, subject_code, semester, department_id").eq("department_id", department_id)
            if semester:
                res = q.or_(f"semester.eq.{semester},semester.is.null").order("name").execute()
            else:
                res = q.order("name").execute()
            return res.data or []
        except Exception:
            return []

    if cache:
        subjects = cache.get_cached(cache_key, level=cache.L1, ttl=cache.LONG, fetcher=fetch_subjects)
        response = jsonify({'success': True, 'subjects': subjects}), 200
        cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
        return response
    return jsonify({'success': True, 'subjects': fetch_subjects()}), 200


@api_bp.route('/api/subjects', methods=['POST'])
def api_add_subject(user_data=None):
    import re
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    code = (data.get('subject_code') or '').strip()
    dept_id = (data.get('department_id') or '').strip()
    semester = data.get('semester')
    
    if not name:
        return jsonify({'success': False, 'message': 'Subject name required'}), 400
    if len(name) > 80:
        return jsonify({'success': False, 'message': 'Subject name too long (max 80 chars)'}), 400
    if not dept_id:
        return jsonify({'success': False, 'message': 'Department ID required'}), 400
        
    try:
        sem_val = int(semester) if semester not in (None, '', 0, '0') else None
    except (ValueError, TypeError):
        sem_val = None

    client = init_supabase()
    try:
        insert_data = {
            'name': name,
            'subject_code': code or None,
            'department_id': dept_id
        }
        if sem_val is not None:
            insert_data['semester'] = sem_val
            
        res = client.table('subjects').insert(insert_data).execute()
        subj = res.data[0] if res.data else {}
        
        if subj and name:
            words = [w for w in re.split(r'\W+', name) if w and w.lower() not in ['and', 'of', 'the', '&']]
            acronym = "".join([w[0] for w in words]).lower()
            if len(acronym) > 1:
                try:
                    client.table('subject_aliases').insert({
                        'subject_id': subj['id'],
                        'alias': acronym,
                        'priority': 1
                    }).execute()
                except Exception:
                    pass
                    
        return jsonify({'success': True, 'subject': subj}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@api_bp.route('/api/colleges', methods=['POST'])
def api_add_college(user_data=None):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    abbr = (data.get('abbreviation') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'College name required'}), 400
    if len(name) > 200:
        return jsonify({'success': False, 'message': 'College name too long (max 200 chars)'}), 400
    client = init_supabase()
    try:
        res = client.table('colleges').insert({'name': name, 'abbreviation': abbr or None}).execute()
        college = res.data[0] if res.data else {}
        return jsonify({'success': True, 'college': college}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@api_bp.route('/api/departments', methods=['POST'])
def api_add_department(user_data=None):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    abbr = (data.get('abbreviation') or '').strip()
    college_id = (data.get('college_id') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Department name required'}), 400
    if len(name) > 120 or len(abbr) > 20:
        return jsonify({'success': False, 'message': 'Name too long (max 120) or abbreviation too long (max 20)'}), 400
    client = init_supabase()
    try:
        res = client.table('departments').insert({'name': name, 'abbreviation': abbr or None}).execute()
        dept = res.data[0] if res.data else {}
        dept_id = dept.get('id')
        if dept_id and college_id:
            client.table('college_departments').insert(
                {'college_id': college_id, 'department_id': dept_id}
            ).execute()
        return jsonify({'success': True, 'department': dept}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@api_bp.route('/api/check-duplicate', methods=['POST'])
@auth_required
def api_check_duplicate(user_data=None):
    data = request.get_json() or {}
    file_hash = data.get('file_hash')
    if not file_hash:
        return jsonify({'success': False, 'message': 'Missing file_hash'}), 400
        
    client = init_supabase()
    if not client: return jsonify({'success': False}), 500
    
    try:
        res = client.table('documents').select('id, title, status').eq('file_hash', file_hash).execute()
        if res.data and len(res.data) > 0:
            return jsonify({'success': True, 'is_duplicate': True, 'existing_file': res.data[0]}), 200
        return jsonify({'success': True, 'is_duplicate': False}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@api_bp.route('/api/ai/predict-metadata', methods=['POST'])
@auth_required
def api_predict_metadata(user_data=None):
    """Predict Subject, Type, and Unit from filename."""
    import re
    data = request.get_json() or {}
    filename = data.get('filename', '').lower()
    if not filename: return jsonify({'success': False})
    
    client = init_supabase()
    words = re.split(r'[\W_]+', filename.split('.')[0])
    prediction = {'subject_id': None, 'type': None, 'unit': None, 'year': str(datetime.now().year)}
    
    for w in words:
        if w in ['notes', 'note']: prediction['type'] = 'notes'
        elif w in ['cae1', 'cae2', 'cae3', 'ese']:
            prediction['type'] = 'papers'
            prediction['unit'] = w.upper()
        elif w in ['practical', 'lab']: prediction['type'] = 'practical'
        elif w in ['syllabus']: prediction['type'] = 'syllabus'
        if re.match(r'^202[0-9]$', w): prediction['year'] = w
            
    try:
        if client:
            alias_res = client.table('subject_aliases').select('subject_id, alias').execute()
            if alias_res.data:
                for record in alias_res.data:
                    alias = record.get('alias', '').lower()
                    if alias in words:
                        prediction['subject_id'] = record['subject_id']
                        break
    except Exception as e:
        logging.error(f"Prediction error: {e}")

    return jsonify({'success': True, 'prediction': prediction}), 200


@api_bp.route('/api/ai/extract-upload-metadata', methods=['POST'])
@auth_required
def api_extract_upload_metadata():
    """Extract metadata from uploaded file bytes."""
    import base64
    import time
    import app
    from methods.ai_provider import resolve_provider, ProviderError, RateLimitError, KeyInvalidError
    from methods.ai_usage import check_ceiling, log_turn, CostCeilingError
    from methods.ai_extract import build_extraction_prompt, validate_extracted_metadata
    from methods.supabase_helper import get_ai_profile, get_subjects_by_department

    file = request.files.get('upload_document') or request.files.get('file')
    file_url = request.form.get('file_url') or (request.get_json(silent=True) or {}).get('file_url')
    if not file and file_url:
        import requests, io
        try:
            r = requests.get(file_url, timeout=12)
            if r.status_code == 200:
                file_name = request.form.get('filename') or (request.get_json(silent=True) or {}).get('filename') or file_url.split('/')[-1].split('?')[0]
                file = io.BytesIO(r.content)
                file.filename = file_name
                file.mimetype = r.headers.get('content-type') or ('application/pdf' if file_name.endswith('.pdf') else 'image/jpeg')
        except Exception as e:
            logging.warning(f"[extract-upload-metadata] Download from url failed: {e}")

    if not file or not getattr(file, 'filename', None):
        return jsonify({'success': False, 'message': 'No file provided'}), 400

    filename = file.filename or request.form.get('filename', '')
    if not app.validate_file_content(file, filename):
        return jsonify({'success': False, 'message': 'File type not allowed or invalid content'}), 400

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > app.MAX_FILE_SIZE or file_size == 0:
        return jsonify({'success': False, 'message': 'Invalid file size'}), 400

    content_bytes = file.read()
    file.seek(0)

    branch_id = (request.form.get('branch_id') or '').strip() or None
    known_fields_raw = request.form.get('known_fields')
    known_fields = {}
    if known_fields_raw:
        try:
            known_fields = json.loads(known_fields_raw) if isinstance(known_fields_raw, str) else known_fields_raw
        except Exception:
            known_fields = {}

    user = session.get('user', {})
    user_id = user.get('uid') or user.get('email')

    if user_id:
        try:
            check_ceiling(user_id)
        except CostCeilingError:
            return jsonify({
                'success': True,
                'source': 'ceiling_reached',
                'metadata': {
                    'type': known_fields.get('type'),
                    'year': known_fields.get('year'),
                    'unit': known_fields.get('unit'),
                    'subject_id': known_fields.get('subject_id'),
                    'subject_name': known_fields.get('subject_name'),
                    'qb_tags': known_fields.get('qb_tags'),
                },
                'fields_filled': [k for k, v in known_fields.items() if v],
                'cost_usd': 0.0,
            }), 200

    ai_profile = get_ai_profile(user_id) if user_id else {}
    try:
        provider, _ = resolve_provider(ai_profile)
    except (KeyInvalidError, ProviderError):
        return jsonify({'success': True, 'source': 'heuristic_fallback', 'metadata': known_fields, 'fields_filled': []}), 200

    content_type = file.mimetype or 'application/octet-stream'
    is_pdf = app._looks_like_pdf(content_type, filename, content_bytes)

    extracted_text = ""
    img_bytes = None
    mime_type = None

    if is_pdf:
        try:
            pdf_text, pdf_img_bytes, pdf_img_mime = app.extract_pdf_info(content_bytes)
            if pdf_text and len(pdf_text.strip()) > 50:
                extracted_text = pdf_text.strip()
            elif pdf_img_bytes:
                img_bytes = pdf_img_bytes
                mime_type = pdf_img_mime or 'image/png'
        except Exception as e:
            logging.warning(f"[AI Extract] PDF extract info failed: {e}")
    else:
        img_bytes = content_bytes
        mime_type = content_type if content_type.startswith('image/') else 'image/jpeg'

    target_keys = ['type', 'year', 'unit', 'subject_match', 'qb_tags']
    missing_fields = [k for k in target_keys if not known_fields.get(k == 'subject_match' and 'subject_id' or k)]

    branch_subjects = None
    if branch_id:
        sub_res = get_subjects_by_department(branch_id)
        if sub_res.get('success'):
            branch_subjects = sub_res.get('data', [])

    system_prompt = build_extraction_prompt(missing_fields, known_fields, branch_subjects)

    source_tag = 'ai_text'
    if extracted_text:
        doc_slice = extracted_text[:2000]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Document Text Sample:\n{doc_slice}\n\nExtract the requested metadata JSON."}
        ]
    elif img_bytes:
        source_tag = 'ai_vision'
        b64_img = base64.b64encode(img_bytes).decode('utf-8')
        data_uri = f"data:{mime_type or 'image/png'};base64,{b64_img}"
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract metadata from this document image as JSON according to instructions."},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ]
    else:
        return jsonify({'success': True, 'source': 'empty', 'metadata': known_fields, 'fields_filled': []}), 200

    t0 = time.time()
    try:
        response = provider.complete(messages, max_tokens=300, temperature=0.1)
        duration_ms = int((time.time() - t0) * 1000)

        validated, s_flag = validate_extracted_metadata(response.text, branch_id=branch_id, known_fields=known_fields)

        log_turn(
            user_id=user_id,
            session_id=None,
            provider=getattr(provider, 'provider_name', 'openrouter'),
            model=response.model_used,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
            duration_ms=duration_ms,
            mode='upload_autofill',
            override_used=False,
            error_type=None,
            safety_flag=s_flag,
            finish_reason=response.finish_reason,
        )

        filled = [k for k, v in validated.items() if v]

        return jsonify({
            'success': True,
            'source': source_tag,
            'metadata': validated,
            'fields_filled': filled,
            'cost_usd': response.cost_usd,
        }), 200

    except (RateLimitError, ProviderError) as exc:
        duration_ms = int((time.time() - t0) * 1000)
        log_turn(
            user_id=user_id,
            session_id=None,
            provider=getattr(provider, 'provider_name', 'openrouter'),
            model=getattr(provider, 'model_name', 'unknown'),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            duration_ms=duration_ms,
            mode='upload_autofill',
            override_used=False,
            error_type='rate_limit' if isinstance(exc, RateLimitError) else 'provider_error',
            safety_flag=None,
            finish_reason='error',
        )
        return jsonify({
            'success': True,
            'source': 'heuristic_fallback',
            'metadata': {
                'type': known_fields.get('type'),
                'year': known_fields.get('year'),
                'unit': known_fields.get('unit'),
                'subject_id': known_fields.get('subject_id'),
                'subject_name': known_fields.get('subject_name'),
                'qb_tags': known_fields.get('qb_tags'),
            },
            'fields_filled': [k for k, v in known_fields.items() if v],
            'cost_usd': 0.0,
        }), 200
    except Exception as exc:
        logging.error(f"[AI Extract] Unexpected error: {exc}")
        return jsonify({'success': True, 'source': 'heuristic_fallback', 'metadata': known_fields, 'fields_filled': []}), 200


@api_bp.route('/api/subject-request', methods=['POST'])
@auth_required
def api_create_subject_request():
    """Create a pending_subject_requests row. Duplicate-safe via DB index."""
    from methods.supabase_helper import create_subject_request
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    subject_name = (data.get('subject_name') or '').strip()
    if not subject_name:
        return jsonify({'success': False, 'message': 'subject_name required'}), 400
    if len(subject_name) > 200:
        return jsonify({'success': False, 'message': 'Subject name too long (max 200 chars)'}), 400
    result = create_subject_request(
        user_id=user_id,
        college_id=data.get('college_id', ''),
        department_id=data.get('department_id', ''),
        subject_name=subject_name,
        subject_code=data.get('subject_code', ''),
        semester=data.get('semester') or None
    )
    if result.get('success'):
        track_user_event(user_id, 'SUBJECT_REQUEST', {'subject_name': subject_name})
    elif result.get('duplicate'):
        return jsonify({'success': False, 'message': result.get('message'), 'duplicate': True}), 409
    return jsonify(result), 200 if result.get('success') else 500


@api_bp.route('/api/waitlist/join', methods=['POST'])
def api_waitlist_join():
    """Public endpoint — join college waitlist. No auth required."""
    from methods.supabase_helper import join_college_waitlist
    data = request.get_json(silent=True) or {}
    college_id = (data.get('college_id') or '').strip()
    email = (data.get('email') or '').strip()
    name = (data.get('name') or '').strip()

    if not college_id or not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Valid email and college required'}), 400

    if not validate_uuid(college_id):
        return jsonify({'success': False, 'message': 'Invalid college'}), 400

    result = join_college_waitlist(college_id, email, name)
    return jsonify(result), 200


# ─── Document Interactions & User Activity ───────────────────────────────────

@api_bp.route('/api/like', methods=['POST'])
@api_bp.route('/api/interactions/like', methods=['POST'])
@auth_required
def api_toggle_like():
    from methods.supabase_helper import toggle_like
    data = request.json or {}
    doc_id = data.get('document_id')
    user_email = session.get('user', {}).get('email')
    if not doc_id or not user_email:
        return jsonify({'success': False, 'message': 'Missing document or user info'}), 400
    res = toggle_like(user_email, doc_id)
    return jsonify(res), 200 if res.get('success') else 500


@api_bp.route('/api/bookmark', methods=['POST'])
@api_bp.route('/api/interactions/bookmark', methods=['POST'])
@auth_required
def api_toggle_bookmark():
    from methods.supabase_helper import toggle_bookmark
    data = request.json or {}
    doc_id = data.get('document_id')
    user_email = session.get('user', {}).get('email')
    if not doc_id or not user_email:
        return jsonify({'success': False, 'message': 'Missing document or user info'}), 400
    res = toggle_bookmark(user_email, doc_id)
    return jsonify(res), 200 if res.get('success') else 500


@api_bp.route('/api/interactions/comments/<doc_id>', methods=['GET', 'POST'])
def api_comments(doc_id):
    from methods.supabase_helper import get_comments, add_comment
    if request.method == 'GET':
        res = get_comments(doc_id)
        return jsonify(res), 200 if res.get('success') else 500
    if request.method == 'POST':
        if 'user' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        data = request.json or {}
        content = data.get('content')
        user_email = session.get('user', {}).get('email')
        if not content:
            return jsonify({'success': False, 'message': 'Comment content is required'}), 400
        res = add_comment(user_email, doc_id, content)
        return jsonify(res), 200 if res.get('success') else 500


@api_bp.route('/api/recent-documents', methods=['GET'])
@auth_required
def api_get_recent_documents():
    """Get recently accessed documents for the logged-in user."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        if not user_id:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        limit = min(request.args.get('limit', 20, type=int), 100)
        from data.interactions import DocumentView
        result = DocumentView.get_recent_for_user(user_id=user_id, limit=limit)
        if result.get('success'):
            return jsonify({
                'success': True,
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 200
        return jsonify({
            'success': False,
            'message': result.get('message', 'Failed to retrieve recent documents'),
            'data': [],
            'count': 0
        }), 500
    except Exception as e:
        logging.error(f"[HISTORY] Exception retrieving recent documents: {e}")
        return jsonify({'success': False, 'message': str(e), 'data': [], 'count': 0}), 500


@api_bp.route('/api/file-access-history', methods=['GET'])
@auth_required
def api_get_file_access_history():
    """Get file access history from file_access_history table."""
    try:
        user_info = session.get('user', {})
        user_email = user_info.get('email')
        if not user_email:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        limit = min(request.args.get('limit', 20, type=int), 100)
        from methods.supabase_helper import get_user_file_history
        result = get_user_file_history(user_email=user_email, limit=limit)
        if result.get('success'):
            data = result.get('data', [])
            return jsonify({'success': True, 'data': data, 'count': len(data)}), 200
        return jsonify({'success': False, 'message': result.get('message', 'Failed'), 'data': [], 'count': 0}), 500
    except Exception as e:
        logging.error(f"[FILE_HISTORY] Exception: {e}")
        return jsonify({'success': False, 'message': str(e), 'data': [], 'count': 0}), 500


@api_bp.route('/api/my-notifications', methods=['GET'])
@auth_required
def api_get_my_notifications():
    """Return paginated notifications for the logged-in user."""
    from methods.supabase_helper import get_user_notifications
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    limit = min(request.args.get('limit', 20, type=int), 50)
    offset = request.args.get('offset', 0, type=int)
    items = get_user_notifications(user_id, limit=limit, offset=offset)
    unread = sum(1 for n in items if not n.get('is_read'))
    return jsonify({'success': True, 'data': items, 'unread': unread}), 200


@api_bp.route('/api/my-notifications/read', methods=['POST'])
@auth_required
def api_mark_notifications_read():
    """Mark all notifications as read for the logged-in user."""
    from methods.supabase_helper import mark_notifications_read
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    res = mark_notifications_read(user_id)
    return jsonify(res), 200 if res.get('success') else 500


@api_bp.route('/api/notifications/<notif_id>/read', methods=['POST'])
@auth_required
def api_mark_single_notification_read(notif_id):
    """Mark a single notification as read by its ID."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    try:
        client = init_supabase()
        if not client or not validate_uuid(notif_id):
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        res = client.table('notifications').update({'is_read': True}).eq('id', notif_id).eq('user_id', user_id).eq('is_read', False).execute()
        if res.data:
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    except Exception as e:
        logging.error(f"[api_mark_single_notification_read] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── File Serving Gateways & Streaming Proxies ───────────────────────────────

_ALLOWED_PROXY_HOSTS = {
    'storage.googleapis.com',
    'firebasestorage.googleapis.com',
    'res.cloudinary.com',
    'abhi-hub.appspot.com',
    'abhihub-b94f6.appspot.com',
    'abhihub-b94f6.firebasestorage.app',
}

_ALLOWED_CORS_ORIGINS = {
    'https://www.abhihub.edu.eu.org',
    'https://abhihub.edu.eu.org',
    'https://ai.abhihub.edu.eu.org',
}

def _get_safe_cors_origin():
    """Return a validated CORS origin with proper protocol scheme."""
    origin = (request.headers.get('Origin') or '').strip().rstrip('/')
    if origin in _ALLOWED_CORS_ORIGINS:
        return origin
    if os.getenv('FLASK_ENV', 'production').lower() == 'development':
        if origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:'):
            return origin
    return 'https://www.abhihub.edu.eu.org'

def _secure_file_headers(extra=None):
    """Build common no-store and anti-embedding headers for proxied files."""
    headers = {
        'Cache-Control': 'private, max-age=86400, stale-while-revalidate=604800',
        'Content-Disposition': 'inline',
        'Access-Control-Allow-Origin': _get_safe_cors_origin(),
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'Referrer-Policy': 'no-referrer',
        'X-Download-Options': 'noopen',
        'X-Permitted-Cross-Domain-Policies': 'none',
    }
    if extra:
        headers.update(extra)
    return headers

def extract_document_pricing(document):
    """Safely extract pricing metadata from document dict, description string, or nested payload."""
    if not isinstance(document, dict):
        return {}
    if isinstance(document.get('pricing'), dict):
        return document['pricing']
    desc_raw = document.get('description')
    if isinstance(desc_raw, dict):
        return desc_raw.get('pricing', {})
    if isinstance(desc_raw, str):
        trimmed = desc_raw.strip()
        if trimmed.startswith('{') and trimmed.endswith('}'):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict) and isinstance(parsed.get('pricing'), dict):
                    return parsed['pricing']
            except Exception:
                pass
    if document.get('is_paid'):
        try:
            p = float(document.get('price', 0))
        except (ValueError, TypeError):
            p = 0.0
        return {'is_paid': True, 'price': p, 'seller_id': document.get('uploader_id')}
    return {}

def has_document_access(user_id, doc_id, document=None):
    """Check if user has full access to a document (free, owner, admin, or purchased)."""
    from methods.supabase_helper import get_document_by_id_rich
    if not document:
        doc_res = get_document_by_id_rich(doc_id)
        if not doc_res.get('success'):
            return False
        document = doc_res.get('data', {})

    pricing = extract_document_pricing(document)
    is_paid = bool(pricing.get('is_paid')) and float(pricing.get('price', 0)) > 0
    if not is_paid:
        return True

    user = session.get('user', {})
    user_role = (user.get('role') or user.get('user_metadata', {}).get('role') or '').lower()
    if session.get('is_admin') or user_role == 'admin':
        return True

    u_uid = str(user_id or user.get('uid') or user.get('id') or '').strip()
    u_email = str(user.get('email') or '').strip().lower()
    seller_id = str(pricing.get('seller_id') or '').strip()
    uploader_id = str(document.get('uploader_id') or '').strip()
    uploader_email = str(document.get('uploader_email') or '').strip().lower()

    if u_uid and (u_uid == seller_id or u_uid == uploader_id):
        return True
    if u_email and uploader_email and u_email == uploader_email:
        return True

    if doc_id in session.get('purchased_documents', []):
        return True

    if u_uid or u_email:
        try:
            from data.transactions import TRANSACTIONS_FILE
            if os.path.exists(TRANSACTIONS_FILE):
                with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                    all_tx = json.load(f)
                    for tx in all_tx.values():
                        if tx.get('status') in ['completed', 'verified']:
                            tx_uid = str(tx.get('user_id') or '')
                            tx_notes = str(tx.get('admin_notes') or '') + ' ' + str(tx.get('purpose') or '')
                            if (not tx_uid or tx_uid == u_uid) and doc_id in tx_notes:
                                return True
        except Exception:
            pass

        try:
            res = supabase.table('credit_transactions').select('id, status').eq('user_id', u_uid).ilike('admin_notes', f'%{doc_id}%').execute()
            if res.data and any(t.get('status') in ['submitted', 'verified', 'completed'] for t in res.data):
                return True
        except Exception:
            pass

    return False

def _verify_pdf_token(doc_id, token):
    """Verify session-bound PDF token."""
    import time
    import hmac
    import hashlib
    if not token or ':' not in token:
        return False
    parts = token.split(':', 1)
    if len(parts) != 2:
        return False
    try:
        expiry = int(parts[0])
    except ValueError:
        return False
    if time.time() > expiry:
        return False
    user = session.get('user', {})
    user_id = user.get('uid', '')
    msg = f"{doc_id}:{user_id}:{expiry}".encode()
    expected_sig = hmac.new(current_app.secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts[1], expected_sig)


@api_bp.route('/api/files/all', methods=['GET'])
def get_all_files():
    """Get all documents exclusively from Supabase abhihub.documents table."""
    try:
        from methods.supabase_helper import get_all_files_merged
        user_info = session.get('user', {})
        current_user_id = user_info.get('uid')
        result = get_all_files_merged(include_file_records=True, current_user_id=current_user_id)
        if result.get('success'):
            return jsonify({'success': True, 'data': result.get('data', []), 'count': result.get('count', 0)}), 200
        return jsonify({'success': False, 'message': result.get('message', 'Failed'), 'data': [], 'count': 0}), 500
    except Exception as e:
        logging.error(f"[API /api/files/all] Exception: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/proxy-file')
@auth_required
def proxy_file():
    """Server-side proxy for Firebase/Cloudinary files to bypass browser CORS."""
    import requests
    file_url = request.args.get('url', '').strip()
    if not file_url:
        abort(400)
    from urllib.parse import urlparse
    parsed = urlparse(file_url)
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS:
        abort(403)
    try:
        upstream = requests.get(file_url, timeout=30, verify=True, headers={'User-Agent': 'AbhiHub-Proxy/1.0'})
        if not upstream.ok:
            abort(upstream.status_code if upstream.status_code in (403, 404) else 502)
        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        resp = make_response(upstream.content)
        resp.headers['Content-Type'] = content_type
        resp.headers.update(_secure_file_headers())
        return resp
    except Exception as e:
        logging.error(f"[PROXY] Error for {file_url}: {e}")
        abort(502)


@api_bp.route('/api/view-doc/<doc_id>')
@api_bp.route('/api/view-doc/<doc_id>/<filename>')
def view_doc(doc_id, filename=None):
    """Clean proxy endpoint for streaming documents to PDF.js."""
    import re
    import requests
    from datetime import timedelta
    from firebase_admin import storage
    from cache_manager import get_cache
    from methods.supabase_helper import get_document_by_id_rich
    cache = get_cache()

    token = request.args.get('token', '')
    if token and not _verify_pdf_token(doc_id, token):
        abort(403, description="Invalid or expired access token")

    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        abort(404)
    document = doc_res.get('data', {})

    current_uid = session.get('user', {}).get('uid') or session.get('user', {}).get('id')
    has_access = has_document_access(current_uid, doc_id, document)
    is_preview_mode = False

    pricing = extract_document_pricing(document)
    is_paid_doc = bool(pricing.get('is_paid')) and float(pricing.get('price', 0)) > 0

    if not has_access:
        if is_paid_doc and (document.get('file_type') == 'pdf' or '.pdf' in str(document.get('file_url', '')).lower()):
            is_preview_mode = True
        else:
            abort(402, description="Payment required to view or download this document.")

    file_url = document.get('file_url', '')
    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    if not file_url or not isinstance(file_url, str):
        abort(404)

    if not file_url.startswith('http'):
        cache_key = f"signed-url:{doc_id}"
        try:
            cached_url, _ = cache.l1.get(cache_key)
            if cached_url is not None:
                file_url = cached_url
            else:
                raise ValueError("Cache miss")
        except Exception:
            try:
                bucket = storage.bucket()
                blob = bucket.blob(file_url)
                signed = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
                file_url = signed[0] if isinstance(signed, (list, tuple)) else signed
                try:
                    cache.l1.set(cache_key, file_url, ttl=300)
                except Exception:
                    pass
            except Exception as e:
                logging.error(f"[VIEW-DOC] Firebase sign setup error for {doc_id}: {e}")

    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    file_url = str(file_url)

    if not file_url.startswith('http'):
        import urllib.parse
        bucket_name = os.getenv('FIREBASE_STORAGE_BUCKET', 'abhi-hub.appspot.com')
        encoded_path = urllib.parse.quote(file_url, safe='')
        file_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}?alt=media"

    from urllib.parse import urlparse
    parsed = urlparse(file_url)
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS:
        abort(403)

    upstream_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    if request.headers.get('Range') and not is_preview_mode:
        upstream_headers['Range'] = request.headers['Range']

    def _fetch(url):
        return requests.get(url, stream=True, timeout=30, verify=True, headers=upstream_headers)

    if parsed.hostname == 'res.cloudinary.com':
        try:
            import cloudinary
            import cloudinary.utils as _cld_utils
            import time as _time
            cloudinary.config(
                cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
                api_key=os.getenv('CLOUDINARY_API_KEY'),
                api_secret=os.getenv('CLOUDINARY_API_SECRET'),
                secure=True,
            )
            pub_id = document.get('cloudinary_public_id') or document.get('public_id') or ''
            if not pub_id:
                m = re.search(r'/upload/(?:v\d+/)?(.+)$', parsed.path)
                pub_id = m.group(1) if m else ''
            if pub_id:
                rtype = 'raw' if '/raw/' in parsed.path else ('image' if '/image/' in parsed.path else 'raw')
                signed_url, _ = _cld_utils.cloudinary_url(
                    pub_id, resource_type=rtype, type='upload', sign_url=True, expires_at=int(_time.time()) + 3600
                )
                if signed_url:
                    file_url = signed_url
                    parsed = urlparse(file_url)
        except Exception as _e:
            logging.warning(f"[VIEW-DOC] Cloudinary pre-sign failed for {doc_id}: {_e}")

    upstream = _fetch(file_url)

    if upstream.status_code in (403, 404) and parsed.hostname in ('firebasestorage.googleapis.com', 'storage.googleapis.com'):
        try:
            cache.l1.delete(f"signed-url:{doc_id}")
        except Exception:
            pass
        raw_path = document.get('file_url', '')
        if isinstance(raw_path, (list, tuple)):
            raw_path = raw_path[0] if raw_path else ''
        raw_path = str(raw_path or '')
        if raw_path.startswith('http'):
            from urllib.parse import unquote
            m = re.search(r'/v0/b/[^/]+/o/(.+?)(?:\?|$)', raw_path)
            raw_path = unquote(m.group(1)) if m else ''
        if raw_path and not raw_path.startswith('http'):
            try:
                bucket = storage.bucket()
                blob = bucket.blob(raw_path)
                signed = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
                fresh_url = signed[0] if isinstance(signed, (list, tuple)) else signed
                try:
                    cache.l1.set(f"signed-url:{doc_id}", fresh_url, ttl=300)
                except Exception:
                    pass
                upstream.close()
                upstream = _fetch(fresh_url)
            except Exception as e:
                logging.error(f"[VIEW-DOC] Re-sign failed for {doc_id}: {e}")

    if upstream.status_code == 401 and parsed.hostname == 'res.cloudinary.com':
        try:
            import cloudinary.utils as _cld_utils
            import time as _time
            m = re.search(r'/upload/(?:v\d+/)?(.+)$', parsed.path)
            if m:
                pub = m.group(1)
                rtype = 'raw' if '/raw/' in parsed.path else ('image' if '/image/' in parsed.path else 'raw')
                signed_url, _ = _cld_utils.cloudinary_url(
                    pub, resource_type=rtype, type='upload', sign_url=True, expires_at=int(_time.time()) + 3600
                )
                if signed_url:
                    upstream.close()
                    upstream = _fetch(signed_url)
        except Exception as _e:
            logging.error(f"[VIEW-DOC] Cloudinary sign failed for {doc_id}: {_e}")

    try:
        if upstream.status_code == 204:
            msg = json.dumps({"error": "Document not available", "detail": f"No content found for document {doc_id}"})
            return Response(msg, status=404, content_type='application/json', headers=_secure_file_headers())
        if not upstream.ok:
            abort(upstream.status_code if upstream.status_code in (403, 404) else 502)

        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        if document.get('file_type') == 'pdf' or '.pdf' in file_url.lower() or file_url.lower().endswith('.txt'):
            content_type = 'application/pdf'
            filename_doc = document.get('title') or 'document.pdf'
            filename_doc = re.sub(r'[^a-z0-9_\-\.]+', '_', filename_doc, flags=re.I)
            if not filename_doc.lower().endswith('.pdf'):
                filename_doc = filename_doc.rsplit('.', 1)[0] + '.pdf'

        if is_preview_mode:
            cache_preview_key = f"pdf_preview_p1:{doc_id}"
            cached_preview = cache.l1.get(cache_preview_key)
            preview_data = cached_preview[0] if (cached_preview and cached_preview[0]) else None
            if not preview_data:
                import io
                import pypdf
                try:
                    pdf_bytes = io.BytesIO(upstream.content)
                    reader = pypdf.PdfReader(pdf_bytes)
                    writer = pypdf.PdfWriter()
                    if len(reader.pages) > 0:
                        writer.add_page(reader.pages[0])
                    preview_io = io.BytesIO()
                    writer.write(preview_io)
                    preview_io.seek(0)
                    preview_data = preview_io.getvalue()
                    try:
                        cache.l1.set(cache_preview_key, preview_data, ttl=3600)
                    except Exception:
                        pass
                except Exception as e:
                    logging.error(f"[VIEW-DOC] Failed preview extraction: {e}")
                    abort(402, description="Payment required to view document.")

            preview_len = len(preview_data)
            preview_headers = _secure_file_headers()
            preview_headers['Content-Disposition'] = f"inline; filename*=UTF-8''preview_{filename_doc}"
            preview_headers['Accept-Ranges'] = 'bytes'
            preview_headers['X-AbhiHub-Preview'] = 'page-1-only'
            preview_headers['Content-Length'] = str(preview_len)
            return Response(preview_data, status=200, content_type='application/pdf', headers=preview_headers)

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            except Exception as e:
                logging.error(f"[VIEW-DOC] Stream interrupted: {e}")

        response_headers = _secure_file_headers()
        if document.get('file_type') == 'pdf' or '.pdf' in file_url.lower() or file_url.lower().endswith('.txt'):
            response_headers['Content-Disposition'] = f"inline; filename*=UTF-8''{filename_doc}"
        if 'Content-Length' in upstream.headers:
            response_headers['Content-Length'] = upstream.headers['Content-Length']
        if upstream.status_code == 206:
            response_headers['Content-Range'] = upstream.headers.get('Content-Range', '')
            response_headers['Accept-Ranges'] = 'bytes'

        return Response(generate(), status=upstream.status_code, content_type=content_type, headers=response_headers)
    except Exception as e:
        logging.error(f"[VIEW-DOC] Exception streaming {doc_id}: {e}")
        abort(502)


CONTACT_FILE = os.path.join('data', 'contact_messages.json')

def _load_contact_messages():
    if not os.path.exists(CONTACT_FILE):
        return []
    try:
        with open(CONTACT_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


@api_bp.route('/api/contact', methods=['POST'])
def api_contact():
    """Contact form submission with Cloudflare Turnstile bot verification."""
    import requests
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'})

    turnstile_token = data.get('turnstile_token', '')
    turnstile_secret = os.environ.get('TURNSTILE_SECRET', '')
    if not turnstile_secret:
        logging.warning('[Turnstile] TURNSTILE_SECRET not set')
        return jsonify({'success': False, 'error': 'Server misconfiguration'}), 500
    try:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
        ts_resp = requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data={'secret': turnstile_secret, 'response': turnstile_token, 'remoteip': client_ip},
            timeout=5
        )
        ts_resp.raise_for_status()
        ts_result = ts_resp.json()
    except Exception as e:
        logging.warning(f'[Turnstile] siteverify error: {e}')
        return jsonify({'success': False, 'error': 'Security check failed'}), 403

    if not ts_result.get('success'):
        return jsonify({'success': False, 'error': 'Security check failed'}), 403

    name = (data.get('name') or '').strip()[:100]
    email = (data.get('email') or '').strip()[:200]
    subject = (data.get('subject') or '').strip()[:200]
    message = (data.get('message') or '').strip()[:5000]

    if not name or not email or not message or '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'success': False, 'error': 'Invalid or missing fields'}), 400

    msg = {
        'name': name,
        'email': email,
        'subject': subject,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }
    os.makedirs('data', exist_ok=True)
    messages = _load_contact_messages()
    messages.insert(0, msg)
    try:
        with open(CONTACT_FILE, 'w') as f:
            json.dump(messages, f)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True})


@api_bp.route('/pdf-proxy/<path:pdf_name>')
@auth_required
def pdf_proxy(pdf_name):
    """Proxy PDF from Firebase Storage with inline disposition."""
    from firebase_admin import storage
    base_domain = os.getenv('BASE_DOMAIN', 'www.abhihub.edu.eu.org').strip().lower()
    referer = request.headers.get('Referer', '')
    if referer:
        ref_host = referer.split('/')[2] if len(referer.split('/')) > 2 else ''
        allowed = (ref_host == base_domain or ref_host.endswith('.' + base_domain) or
                   'localhost' in ref_host or '127.0.0.1' in ref_host or '0.0.0.0' in ref_host)
        if not allowed:
            abort(403, description="Access denied")
    try:
        if '..' in pdf_name or pdf_name.startswith('/'):
            abort(400, description="Invalid file path")
        if pdf_name.startswith(('http://', 'https://')):
            from urllib.parse import urlparse
            if urlparse(pdf_name).hostname not in _ALLOWED_PROXY_HOSTS:
                abort(403, description="Remote host not allowed")
            return redirect(pdf_name)

        bucket = storage.bucket()
        blob = bucket.blob(pdf_name)
        import mimetypes
        pdf_content = blob.download_as_bytes()
        file_size = len(pdf_content)
        content_type, _ = mimetypes.guess_type(pdf_name)
        if not content_type or pdf_name.lower().endswith('.txt'):
            content_type = 'application/pdf'

        range_header = request.headers.get('Range')
        if range_header:
            byte_range = range_header.replace('bytes=', '').split('-')
            start = int(byte_range[0]) if byte_range[0] else 0
            end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            end = min(end, file_size - 1)
            response = make_response(pdf_content[start:end+1])
            response.status_code = 206
            response.headers['Content-Type'] = content_type
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response.headers['Content-Length'] = str(end - start + 1)
        else:
            response = make_response(pdf_content)
            response.status_code = 200
            response.headers['Content-Type'] = content_type
            response.headers['Content-Length'] = str(file_size)

        response.headers['Access-Control-Allow-Origin'] = _get_safe_cors_origin()
        response.headers['Content-Disposition'] = f'inline; filename="{os.path.basename(pdf_name)}"'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers.update(_secure_file_headers())
        return response
    except Exception as e:
        logging.error(f"Error proxying PDF {pdf_name}: {e}")
        abort(404, description="PDF not found")


@api_bp.route('/verify-file', methods=['POST'])
def verify_file():
    """Verify a file and ensure it exists in Supabase documents."""
    try:
        from firebase_admin import storage
        data = request.get_json() or {}
        file_path = data.get('file_path')
        if not file_path:
            return jsonify({'success': False, 'message': 'File path is required'}), 400
        bucket = storage.bucket()
        blob = bucket.blob(file_path)
        if not blob.exists():
            return jsonify({'success': False, 'message': 'File does not exist in storage'}), 404

        info_temp = file_path.split('/')
        file_info = {
            'file-name': info_temp[-1].split('.')[0],
            'file-type': info_temp[-1].split('.')[1] if '.' in info_temp[-1] else '',
            'file-path': file_path,
            'verified': True,
            'verification_date': datetime.now().isoformat()
        }
        client = init_supabase()
        if client:
            res = client.table('documents').select('id').eq('file_url', file_path).execute()
            if not res.data:
                client.table('documents').insert({
                    'title': file_info.get('file-name', 'Unknown'),
                    'file_url': file_path,
                    'storage_provider': 'firebase',
                    'status': 'approved',
                    'document_category': 'Other',
                    'file_type': file_info.get('file-type', 'pdf'),
                }).execute()
        return jsonify({'success': True, 'message': 'File verified', 'file_info': file_info}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/get-file-url', methods=['POST'])
@auth_required
def get_file_url():
    """Generate a signed URL for a storage file without storing it."""
    try:
        from datetime import timedelta
        from firebase_admin import storage
        data = request.get_json() or {}
        file_path = (data.get('file_path') or '').strip()
        if not file_path or '..' in file_path or file_path.startswith('/'):
            return jsonify({'success': False, 'message': 'Valid file path is required'}), 400
        bucket = storage.bucket()
        blob = bucket.blob(file_path)
        if not blob.exists():
            return jsonify({'success': False, 'message': 'File does not exist in storage'}), 404
        url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1))
        return jsonify({'success': True, 'url': url}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/update-file-metadata', methods=['POST'])
@admin_required
def update_file_metadata_route():
    """Update file metadata in Supabase (Admin Only)."""
    try:
        from methods.supabase_helper import update_document_metadata
        data = request.get_json() or {}
        file_path = data.get('file-path')
        if not file_path:
            return jsonify({'success': False, 'message': 'File path is required'}), 400
        res = update_document_metadata(file_path, data)
        return jsonify(res), 200 if res.get('success') else 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── MemoryWall (know_me) APIs ───────────────────────────────────────────────

@api_bp.route('/api/memorywall/submit', methods=['POST'])
def api_memorywall_submit():
    """Public response submission — no auth, rate-limited by IP hash."""
    from methods.know_me import submit_response
    data = request.get_json(silent=True) or {}
    if data.get('_honey'):
        return jsonify({'success': False, 'message': 'rejected'}), 400

    wall_id = (data.get('wall_id') or '').strip()
    friend_name = (data.get('friend_name') or '').strip()
    word_1 = (data.get('word_1') or '').strip()
    word_2 = (data.get('word_2') or '').strip()
    word_3 = (data.get('word_3') or '').strip()
    message = (data.get('memory_message') or '').strip() or None
    emoji = (data.get('emoji') or '').strip() or None
    signature_url = (data.get('signature_url') or '').strip() or None

    if not all([wall_id, friend_name, word_1, word_2, word_3]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    if friend_name.lower() == 'anonymous':
        return jsonify({'success': False, 'message': 'Anonymous submissions are not allowed.'}), 400

    raw_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if raw_ip and ',' in raw_ip:
        raw_ip = raw_ip.split(',')[0].strip()

    result = submit_response(
        wall_id=wall_id, friend_name=friend_name,
        word_1=word_1, word_2=word_2, word_3=word_3,
        message=message, emoji=emoji, anonymous=False,
        raw_ip=raw_ip, signature_url=signature_url,
    )
    if result.get('message') == 'rate_limited':
        return jsonify({'success': False, 'message': 'Too many submissions. Try again later.'}), 429
    return jsonify(result), 200 if result.get('success') else 500


@api_bp.route('/api/memorywall/upload-signature', methods=['POST'])
def api_memorywall_upload_signature():
    """Upload a signature PNG to Firebase Storage. Returns public URL."""
    try:
        if 'signature' not in request.files:
            return jsonify({'success': False, 'message': 'No file'}), 400
        f = request.files['signature']
        if not f or f.content_type not in ('image/png', 'image/jpeg'):
            return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > 512 * 1024:
            return jsonify({'success': False, 'message': 'File too large'}), 400

        from PIL import Image as PILImage
        try:
            img = PILImage.open(f)
            img.verify()
            f.seek(0)
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid image'}), 400

        import uuid
        from firebase_admin import storage as fb_storage
        blob_name = f"know_me/signatures/{uuid.uuid4().hex}.png"
        bucket = fb_storage.bucket()
        blob = bucket.blob(blob_name)
        blob.upload_from_file(f, content_type='image/png')
        blob.make_public()
        return jsonify({'success': True, 'url': blob.public_url}), 200
    except Exception as e:
        logging.error(f"[MemoryWall] Signature upload error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/memorywall/stats/<wall_id>', methods=['GET'])
@auth_required
def api_memorywall_stats(wall_id):
    """Wall stats — auth required, owner only."""
    from methods.know_me import get_response_count, get_top_words, get_wall_by_user
    user = session.get('user', {})
    owner_check = get_wall_by_user(user.get('uid'))
    if not owner_check.get('success') or owner_check.get('data', {}).get('id') != wall_id:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403
    count = get_response_count(wall_id)
    words = get_top_words(wall_id)
    return jsonify({'success': True, 'response_count': count, 'top_words': words[:10]}), 200


# ─── Peer Sharing, Search & Chat HTTP APIs ───────────────────────────────────

def _get_uid():
    user = session.get('user', {})
    return user.get('uid') or user.get('id') or user.get('user_id')


def _getSuggestedPeers(client, uid):
    """Fetch up to 8 suggested peers from the same college as the user."""
    suggested = []
    try:
        my_prof = client.table('profiles').select('college_id').eq('id', uid).limit(1).execute()
        if not my_prof.data:
            return suggested
        my_college_id = my_prof.data[0].get('college_id')
        if my_college_id:
            sg = client.table('profiles').select(
                'id, full_name, email, rank_title, reputation_score, is_verified, colleges(name)'
            ).eq('college_id', my_college_id).neq('id', uid).order('reputation_score', desc=True).limit(8).execute()
            for s in (sg.data or []):
                col = s.get('colleges') or {}
                suggested.append({
                    'id': s.get('id'),
                    'full_name': s.get('full_name') or 'Student',
                    'email': s.get('email', ''),
                    'rank_title': s.get('rank_title', 'Student'),
                    'reputation_score': s.get('reputation_score', 0),
                    'college_name': col.get('name') or '',
                    'is_verified': s.get('is_verified', False)
                })
    except Exception as e:
        logging.error(f"[_getSuggestedPeers] {e}")
    return suggested


@api_bp.route('/api/users/search', methods=['GET'])
@auth_required
def api_search_users():
    """Search student profiles by query string."""
    from methods.supabase_helper import search_users_db
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': True, 'users': []})
    users = search_users_db(q)
    return jsonify({'success': True, 'users': users})


@api_bp.route('/api/user/<target_user_id>/materials', methods=['GET'])
@auth_required
def api_get_peer_materials(target_user_id):
    """Get target student's uploaded & referred study materials."""
    from methods.supabase_helper import get_user_peer_materials_db
    res = get_user_peer_materials_db(target_user_id)
    return jsonify(res)


@api_bp.route('/api/chat/peer/<target_user_id>/materials-summary', methods=['GET'])
@auth_required
def api_chat_peer_materials_summary(target_user_id):
    """Quick material summary for chat — uploads count + recent 5 viewed files."""
    from methods.supabase_helper import get_user_peer_materials_db
    res = get_user_peer_materials_db(target_user_id)
    if not res.get('success'):
        return jsonify({'success': False, 'message': 'User not found'}), 404
    return jsonify({
        'success': True,
        'user': res.get('user', {}),
        'uploads_count': len(res.get('uploads', [])),
        'recent_views': res.get('referred', [])[:5]
    })


@api_bp.route('/api/request-material', methods=['POST'])
@auth_required
def api_request_material():
    """Submit a material request to another student."""
    data = request.get_json() or {}
    target_user_id = data.get('target_user_id')
    subject = data.get('subject', '').strip()
    note_details = data.get('details', '').strip()
    if not target_user_id or not subject:
        return jsonify({'success': False, 'message': 'Missing target user or subject'}), 400
    sender_user = session.get('user', {})
    try:
        client = init_supabase()
        if client:
            client.table('material_requests').insert({
                'requester_id': sender_user.get('uid'),
                'target_user_id': target_user_id,
                'subject': subject,
                'details': note_details,
                'status': 'pending'
            }).execute()
    except Exception as e:
        logging.error(f"[RequestMaterial] DB insert error: {e}")
    return jsonify({'success': True, 'message': 'Request sent to the student'}), 200


@api_bp.route('/api/material-requests', methods=['GET'])
@auth_required
def api_get_material_requests():
    """Return pending material requests for the logged-in user."""
    user = session.get('user', {})
    uid = user.get('uid')
    if not uid:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'DB unavailable'}), 500
        try:
            res = client.table('material_requests').select(
                'id, requester_id, target_user_id, subject, details, status, created_at, profiles!material_requests_requester_id_fkey(full_name,email)'
            ).eq('target_user_id', uid).order('created_at', desc=True).execute()
        except Exception:
            res = client.table('material_requests').select(
                'id, requester_id, target_user_id, subject, details, status, created_at'
            ).eq('target_user_id', uid).order('created_at', desc=True).execute()
        items = []
        for r in (res.data or []):
            requester = r.get('profiles') or {}
            items.append({
                'id': r.get('id'),
                'requester_id': r.get('requester_id'),
                'requester_name': requester.get('full_name') or requester.get('name') or '',
                'requester_email': requester.get('email') or '',
                'subject': r.get('subject'),
                'details': r.get('details'),
                'status': r.get('status'),
                'created_at': str(r.get('created_at') or '')
            })
        return jsonify({'success': True, 'requests': items}), 200
    except Exception as e:
        return jsonify({'success': True, 'requests': []}), 200


@api_bp.route('/api/material-request/respond', methods=['POST'])
@auth_required
def api_respond_material_request():
    data = request.get_json() or {}
    req_id = data.get('id')
    action = data.get('action')
    message = data.get('message', '').strip()
    user = session.get('user', {})
    uid = user.get('uid')
    user_email = user.get('email', '')
    if not req_id or action not in ('accept', 'reject'):
        return jsonify({'success': False, 'message': 'Invalid parameters'}), 400
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'DB unavailable'}), 500
        upd = {
            'status': 'accepted' if action == 'accept' else 'rejected',
            'responder_id': uid,
            'responder_email': user_email,
            'response_message': message,
            'responded_at': 'now()'
        }
        client.table('material_requests').update(upd).eq('id', req_id).execute()
        return jsonify({'success': True, 'message': f'Request {action}ed'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500


@api_bp.route('/api/chat/search-peers', methods=['GET'])
@auth_required
def chat_search_peers():
    """Peer search for chat — available to all authenticated users."""
    q = request.args.get('q', '').strip()
    uid = _get_uid()
    if len(q) < 2:
        return jsonify({'success': True, 'users': [], 'suggested': []})
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'users': [], 'suggested': [], 'error': 'DB error'}), 500
        if q == '__suggested__':
            return jsonify({'success': True, 'users': [], 'suggested': _getSuggestedPeers(client, uid)})

        res = client.table('profiles').select(
            'id, full_name, email, rank_title, reputation_score, is_verified, college_id, colleges(name)'
        ).or_(f'full_name.ilike.%{q}%,email.ilike.%{q}%').limit(10).execute()
        users = []
        for u in (res.data or []):
            col = u.get('colleges') or {}
            users.append({
                'id': u.get('id'),
                'full_name': u.get('full_name') or 'Student',
                'email': u.get('email', ''),
                'rank_title': u.get('rank_title', 'Student'),
                'reputation_score': u.get('reputation_score', 0),
                'college_name': col.get('name') or '',
                'is_verified': u.get('is_verified', False),
            })
        return jsonify({'success': True, 'users': users, 'suggested': _getSuggestedPeers(client, uid)})
    except Exception as e:
        return jsonify({'success': False, 'users': [], 'suggested': [], 'error': str(e)}), 500


@api_bp.route('/api/chat/history/<peer_id>')
@auth_required
def api_chat_history(peer_id):
    """Retrieve chat message history for private room."""
    me = _get_uid()
    if not me or not validate_uuid(peer_id):
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    try:
        import app as main_app
        history_func = getattr(main_app, '_get_chat_history', None)
        history = history_func(me, peer_id) if history_func else []
        return jsonify({'success': True, 'messages': history})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/chat/messages', methods=['POST'])
@auth_required
def api_chat_send_message():
    """HTTP fallback when a network blocks WebSocket upgrades."""
    import app as main_app
    relay_func = getattr(main_app, '_relay_chat_message', None)
    payload = relay_func(_get_uid(), request.get_json(silent=True) or {}) if relay_func else None
    if not payload:
        return jsonify({'success': False, 'error': 'Invalid message'}), 400
    return jsonify({'success': True, 'message': payload})


@api_bp.route('/api/chat/upload-file', methods=['POST'])
@auth_required
def api_chat_upload_file():
    """Uploads a requested file in chat and returns its download URL."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file attached'}), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    import time
    from werkzeug.utils import secure_filename
    orig_name = secure_filename(file.filename) or f"file_{int(time.time())}.bin"

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 25 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File exceeds 25MB limit'}), 400

    safe_name = f"chat_{int(time.time())}_{_get_uid()[:8]}_{orig_name}"
    upload_dir = os.path.join(current_app.static_folder or 'static', 'uploads', 'chat')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, safe_name)
    file.save(save_path)

    file_url = f"/static/uploads/chat/{safe_name}"

    # Link with platform study library
    title = request.form.get('title') or orig_name
    category = request.form.get('category') or 'notes'
    year = request.form.get('year') or '2025'
    semester = request.form.get('semester') or None
    try:
        from methods.supabase_helper import save_file_record
        user_info = session.get('user', {})
        save_file_record(
            user_id=_get_uid(),
            user_email=user_info.get('email', ''),
            file_name=orig_name,
            file_url=file_url,
            file_type='pdf' if orig_name.lower().endswith('.pdf') else 'file',
            file_size=size,
            cloudinary_public_id=f"local_{safe_name}",
            subject_name=title,
            document_type=category.lower(),
            year=year,
            college_id=user_info.get('college_id'),
            branch_id=user_info.get('branch_id'),
            title=title,
            description=request.form.get('details', 'Shared via Peer Chat'),
            semester=int(semester) if semester and str(semester).isdigit() else None
        )
    except Exception as e:
        logging.info(f"[chat] Platform library record skipped: {e}")

    return jsonify({
        'success': True,
        'file_url': file_url,
        'file_name': orig_name,
        'file_size': size
    })


@api_bp.route('/api/chat/online')
@auth_required
def chat_online_users():
    """Returns currently online users for the dashboard widget."""
    import time
    import app as main_app
    uid = _get_uid()
    if uid:
        user = session.get('user', {})
        name = user.get('name') or (user.get('user_metadata') or {}).get('full_name') or user.get('email', 'Student')
        if hasattr(main_app, '_chat_online_http'):
            main_app._chat_online_http[uid] = {'time': time.time(), 'name': name}
        if hasattr(main_app, 'socketio'):
            safe_list = main_app._safe_online_list() if hasattr(main_app, '_safe_online_list') else []
            main_app.socketio.emit('chat_online_update', {'online': safe_list}, to='online-counter-room')

    all_users = main_app._get_merged_online_users() if hasattr(main_app, '_get_merged_online_users') else []
    users = [u for u in all_users if u.get('id') != uid]
    return jsonify({'success': True, 'online': users})


@api_bp.route('/api/chat/keys', methods=['GET', 'POST'])
@auth_required
def chat_keys():
    """Generate or retrieve user's NaCl key pair for E2E encryption."""
    from methods.encrypted_chat import generate_user_keys, store_user_keys, get_user_keys
    uid = _get_uid()
    if not uid:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        keys = get_user_keys(uid)
        if keys:
            return jsonify({'success': True, 'public_key': keys.get('public_key', '')})
        keys = generate_user_keys()
        if keys:
            store_user_keys(uid, keys['public_key'], keys['private_key'])
            return jsonify({'success': True, 'public_key': keys['public_key']})
        return jsonify({'success': False, 'error': 'Could not generate keys'}), 500
    data = request.get_json(silent=True) or {}
    public_key = data.get('public_key', '')
    if public_key:
        store_user_keys(uid, public_key, '')
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'public_key required'}), 400


@api_bp.route('/api/crush/<target_id>', methods=['POST'])
@auth_required
def api_crush_toggle(target_id):
    """Toggle a crush on target_id. Max 2 crushes per calendar year."""
    from methods.supabase_helper import init_supabase_admin
    me = session['user']['uid']
    if me == target_id:
        return jsonify({'success': False, 'message': 'Cannot crush yourself'}), 400
    year = datetime.utcnow().year
    try:
        if not validate_uuid(target_id):
            return jsonify({'success': False, 'message': 'Invalid user'}), 400
        client = init_supabase_admin()
        existing = client.table('user_crushes').select('id').eq('from_user', me).eq('to_user', target_id).eq('year', year).execute()
        if existing.data:
            client.table('user_crushes').delete().eq('from_user', me).eq('to_user', target_id).eq('year', year).execute()
            return jsonify({'success': True, 'action': 'removed', 'is_crush': False, 'is_match': False}), 200

        count_res = client.table('user_crushes').select('id', count='exact').eq('from_user', me).eq('year', year).execute()
        if (count_res.count or 0) >= 2:
            return jsonify({'success': False, 'message': 'You can only mark 2 crushes per year'}), 429

        client.table('user_crushes').insert({'from_user': me, 'to_user': target_id, 'year': year}).execute()
        mutual = client.table('user_crushes').select('id').eq('from_user', target_id).eq('to_user', me).eq('year', year).execute()
        is_match = bool(mutual.data)
        return jsonify({'success': True, 'action': 'added', 'is_crush': True, 'is_match': is_match}), 200
    except Exception as e:
        logging.error(f"[CRUSH] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/crush/status/<target_id>', methods=['GET'])
@auth_required
def api_crush_status(target_id):
    """Return crush/match state between current user and target."""
    from methods.supabase_helper import init_supabase_admin
    me = session['user']['uid']
    year = datetime.utcnow().year
    try:
        if not validate_uuid(target_id):
            return jsonify({'success': False}), 400
        client = init_supabase_admin()
        i_crushed = bool(client.table('user_crushes').select('id').eq('from_user', me).eq('to_user', target_id).eq('year', year).execute().data)
        they_crushed = bool(client.table('user_crushes').select('id').eq('from_user', target_id).eq('to_user', me).eq('year', year).execute().data)
        crushes_used = (client.table('user_crushes').select('id', count='exact').eq('from_user', me).eq('year', year).execute().count or 0)
        return jsonify({
            'success': True,
            'is_crush': i_crushed,
            'is_match': i_crushed and they_crushed,
            'crushes_used': crushes_used,
            'crushes_remaining': max(0, 2 - crushes_used)
        }), 200
    except Exception as e:
        return jsonify({'success': False}), 500


@api_bp.route('/api/chat/user-info/<user_id>')
@auth_required
def chat_user_info(user_id):
    """Returns profile context shown in chat message badges."""
    from methods.supabase_helper import get_student_profile
    try:
        prof = get_student_profile(user_id)
        if not prof or not prof.get('student_name'):
            return jsonify({'success': False, 'error': 'User not found'}), 404
        return jsonify({
            'success': True,
            'user': {
                'id': prof.get('student_id'),
                'name': prof.get('student_name'),
                'email': prof.get('student_email'),
                'rank_title': prof.get('rank_title') or 'Student',
                'reputation_score': prof.get('reputation_score') or 0,
                'year_of_joining': prof.get('year_of_joining'),
                'branch': prof.get('branch_name') or '',
                'college': prof.get('college_name') or '',
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Search API V2 & V3 (In-Memory Discovery + Autocomplete) ───────────────
from methods.search_api import search_v2_endpoint, search_analytics_endpoint, suggest_endpoint
api_bp.add_url_rule('/api/v2/search', view_func=search_v2_endpoint, methods=['GET'])
api_bp.add_url_rule('/api/v2/search/analytics', view_func=search_analytics_endpoint, methods=['POST'])
api_bp.add_url_rule('/api/v2/suggest', view_func=suggest_endpoint, methods=['GET'])


# ─── Interactive Guides API ───────────────────────────────────────────────
@api_bp.route('/api/guides/eligible', methods=['GET'])
def api_get_eligible_guides():
    from methods.guide_service import get_eligible_guides
    user_id = session.get('user', {}).get('uid') or session.get('user_id')
    screen = request.args.get('screen')
    eligible = get_eligible_guides(user_id=user_id, screen=screen)
    return jsonify({'success': True, 'guides': eligible}), 200


@api_bp.route('/api/guides/<guide_id>/progress', methods=['POST'])
def api_update_guide_progress(guide_id):
    from methods.guide_service import update_guide_progress
    user_id = session.get('user', {}).get('uid') or session.get('user_id') or 'guest'
    data = request.get_json(silent=True) or {}
    status = data.get('status', 'in_progress')
    current_step = data.get('current_step', 0)
    version = data.get('version', 1)
    ok = update_guide_progress(user_id, guide_id, status, current_step, version)
    return jsonify({'success': ok}), 200


@api_bp.route('/api/user/uploads', methods=['GET'])
@auth_required
def api_get_user_uploads():
    """Fetch files uploaded by the authenticated user with tracking info."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        user_email = user_info.get('email', '')

        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'data': [], 'message': 'Database unavailable'}), 500

        u_id = user_id
        if not u_id and user_email:
            p_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if p_res.data:
                u_id = p_res.data[0]['id']

        if not u_id:
            return jsonify({'success': True, 'data': [], 'count': 0}), 200

        res = client.table('documents').select(
            'id, title, document_category, file_type, file_size_bytes, status, view_count, like_count, is_paid, price, created_at, subjects(name)'
        ).eq('uploader_id', u_id).order('created_at', desc=True).limit(50).execute()

        raw_data = res.data or []
        items = []
        for r in raw_data:
            subj = (r.get('subjects') or {}).get('name') if isinstance(r.get('subjects'), dict) else ''
            items.append({
                'id': r.get('id'),
                'title': r.get('title') or 'Untitled Document',
                'category': (r.get('document_category') or 'notes').capitalize(),
                'subject': subj or 'General',
                'file_type': (r.get('file_type') or 'pdf').upper(),
                'status': r.get('status') or 'pending',
                'views': r.get('view_count') or 0,
                'likes': r.get('like_count') or 0,
                'is_paid': bool(r.get('is_paid')),
                'price': float(r.get('price') or 0),
                'created_at': r.get('created_at', '')
            })

        return jsonify({'success': True, 'data': items, 'count': len(items)}), 200
    except Exception as e:
        logging.error(f"[API /api/user/uploads] Error: {e}")
        return jsonify({'success': False, 'data': [], 'message': str(e)}), 500
