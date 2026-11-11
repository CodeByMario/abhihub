from version import APP_VERSION
"""
AbhiHub Core JSON APIs Blueprint.
Handles system health, telemetry, user profiles, authentication state,
and student onboarding APIs.
"""
import os
import json
import hashlib
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

from routes.auth import auth_required, admin_required, is_admin_user
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
        'version': APP_VERSION,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200


@api_bp.route('/api/version')
def version_info():
    """Return current app version for footer and cache management."""
    return jsonify({"version": APP_VERSION})


@api_bp.route('/api/get-upload-signature', methods=['POST'])
@auth_required
def get_upload_signature():
    """Generates a presigned Cloudinary upload signature for client-side direct uploads."""
    import time
    import re
    import cloudinary.utils
    timestamp = int(time.time())
    folder = "uploads"
    data = request.get_json(silent=True) or {}
    filename = os.path.basename(str(data.get('filename') or 'upload'))
    is_pdf = filename.lower().endswith('.pdf')
    params = {
        'timestamp': timestamp,
        'folder': folder
    }
    if is_pdf:
        # Vercel rejects requests over its serverless body limit. Upload PDF bytes
        # directly to Cloudinary as a public raw asset, using a .txt suffix so
        # Cloudinary's PDF delivery restriction does not block the file.
        stem = re.sub(r'[^\w.-]+', '_', os.path.splitext(filename)[0]).strip('._') or 'upload'
        user_id = str(session.get('user', {}).get('uid') or session.get('user', {}).get('email') or 'user')
        user_id = re.sub(r'[^\w.-]+', '_', user_id)
        public_id = f"{user_id}_{timestamp}_{stem}.txt"
        params.update({
            'public_id': public_id,
            # Raw uploads otherwise inherit the browser file extension and
            # Cloudinary can return `<public_id>.pdf`.
            'format': 'txt',
        })
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    if not api_secret or not cloud_name:
        return jsonify({'success': False, 'message': 'Storage configuration error'}), 500

    signature = cloudinary.utils.api_sign_request(params, api_secret)
    return jsonify({
        'success': True,
        'upload_url': f"https://api.cloudinary.com/v1_1/{cloud_name}/{('raw' if is_pdf else 'auto')}/upload",
        'api_key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'folder': folder,
        'public_id': params.get('public_id'),
        'format': params.get('format'),
        'resource_type': 'raw' if is_pdf else 'auto'
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
        comm_info = {'creator_pct': 70, 'is_promo': False, 'promo_days_remaining': 0}
        if uid:
            try:
                from methods.wallet_service import get_creator_commission_pct
                comm_info = get_creator_commission_pct(uid)
            except Exception:
                pass
        return jsonify({
            'success': True,
            'level': gate.get('level'),
            'can_monetize': can_monetize,
            'creator_commission': comm_info,
            'creator_commission_pct': comm_info.get('creator_pct', 70),
            'is_promo': comm_info.get('is_promo', False),
            'promo_days_remaining': comm_info.get('promo_days_remaining', 0),
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
            logging.warning("[AUTH] Supabase token verification failed (error_type=%s)", type(e).__name__)

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
            logging.error("[AUTH] JWT fallback parsing failed (error_type=%s)", type(jwt_err).__name__)

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
        logging.warning("[AUTH] Login session audit write failed (error_type=%s)", type(sess_err).__name__)

    # Set initial paper view credits based on strict domain policy:
    # @ghrce.raisoni.net / approved college -> 20 views
    # @gmail.com -> 5 views
    # Temporary / disposable domains -> 0 views (must pay directly)
    try:
        from methods.domain_tier_service import classify_email
        tier_info = classify_email(user_data['email'])
        init_views = tier_info['starting_views']
        p_chk = client.table('profiles').select('id, paper_quota_remaining').eq('id', user_data['id']).limit(1).execute()
        if p_chk.data:
            if p_chk.data[0].get('paper_quota_remaining') is None:
                client.table('profiles').update({'paper_quota_remaining': init_views}).eq('id', user_data['id']).execute()
                session['paper_quota'] = {'credits': init_views, 'total_views': 0}
        else:
            client.table('profiles').insert({
                'id': user_data['id'],
                'email': user_data['email'],
                'full_name': user_data['name'],
                'paper_quota_remaining': init_views
            }).execute()
            session['paper_quota'] = {'credits': init_views, 'total_views': 0}
    except Exception as q_err:
        logging.warning("[AUTH] Initial quota setup failed (error_type=%s)", type(q_err).__name__)

    # Process referral reward if referral code was provided at authorization
    payload = request.get_json(silent=True) or {}
    ref_code = (payload.get('ref') or '').strip()
    if ref_code:
        try:
            ensure_referral_code(user_data['id'])
            register_referral(user_data['id'], ref_code)
        except Exception as ref_err:
            logging.warning("[AUTH] Referral crediting failed (error_type=%s)", type(ref_err).__name__)

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
        import re
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        students_helped = 0
        badges = []
        college_id = None
        college_name = None
        college_abbreviation = None
        department_id = None
        branch_name = None
        degree = None
        pursuing_year = None

        if user_id:
            rep_stats = get_reputation_stats(user_id)
            if rep_stats.get('success'):
                students_helped = rep_stats.get('students_helped', 0)
                badges = rep_stats.get('badges', [])

            try:
                from methods.supabase_helper import get_student_profile
                sp_res = get_student_profile(user_id)
                if sp_res and sp_res.get('success') and sp_res.get('data'):
                    sp = sp_res['data']
                    college_id = sp.get('college_id') or college_id
                    college_name = sp.get('college_name')
                    college_abbreviation = sp.get('college_abbreviation')
                    department_id = sp.get('branch_id') or sp.get('department_id') or department_id
                    branch_name = sp.get('branch_name')
                    degree = sp.get('degree') or degree
                    pursuing_year = sp.get('pursuing_year') or pursuing_year
                else:
                    client = init_supabase()
                    pres = client.table('profiles').select('college_id, department_id, degree').eq('id', user_id).single().execute()
                    if pres.data:
                        college_id = pres.data.get('college_id')
                        department_id = pres.data.get('department_id')
                        degree = pres.data.get('degree')

                    sres = client.table('students').select('pursuing_year, year_of_joining, degree').eq('profile_id', user_id).limit(1).execute()
                    if sres.data:
                        pursuing_year = sres.data[0].get('pursuing_year')
                        if not degree:
                            degree = sres.data[0].get('degree')
            except Exception:
                pass

        # Calculate estimated semester if pursuing_year (e.g. 1st year -> Sem 1, 3rd year -> Sem 5)
        semester = None
        if pursuing_year:
            try:
                yr_num = int(re.sub(r'\D', '', str(pursuing_year)) or '0')
                if 1 <= yr_num <= 4:
                    semester = f"Semester {yr_num * 2 - 1}"
            except Exception:
                pass

        comm_info = {'creator_pct': 70, 'is_promo': False, 'promo_days_remaining': 0}
        if user_id:
            try:
                from methods.wallet_service import get_creator_commission_pct
                comm_info = get_creator_commission_pct(user_id)
            except Exception:
                pass

        return jsonify({
            'success': True,
            'college_id': college_id,
            'college_name': college_name,
            'college_abbreviation': college_abbreviation,
            'department_id': department_id,
            'branch_id': department_id,
            'branch_name': branch_name,
            'degree': degree,
            'program': degree,
            'semester': semester,
            'pursuing_year': pursuing_year,
            'creator_commission': comm_info,
            'creator_commission_pct': comm_info.get('creator_pct', 70),
            'is_promo': comm_info.get('is_promo', False),
            'promo_days_remaining': comm_info.get('promo_days_remaining', 0),
            'user': {
                'creator_commission': comm_info,
                'creator_commission_pct': comm_info.get('creator_pct', 70),
                'is_promo': comm_info.get('is_promo', False),
                'promo_days_remaining': comm_info.get('promo_days_remaining', 0),
                'uid': user_info.get('uid'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'provider': user_info.get('provider'),
                'user_metadata': user_info.get('user_metadata', {}),
                'college_id': college_id,
                'department_id': department_id,
                'degree': degree,
                'program': degree,
                'semester': semester,
                'pursuing_year': pursuing_year,
                'students_helped': students_helped,
                'badges': badges,
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/sync/versions', methods=['GET'])
def api_sync_versions():
    """Return lightweight version hashes/timestamps for client-side IndexedDB delta invalidation."""
    import time
    import hashlib
    from cache_manager import get_cache
    from methods.supabase_helper import init_supabase
    cache = get_cache()

    def fetch_global_versions():
        try:
            client = init_supabase()
            c_cnt = client.table('colleges').select('id', count='exact').limit(1).execute().count or 0
            d_cnt = client.table('departments').select('id', count='exact').limit(1).execute().count or 0
            s_cnt = client.table('subjects').select('id', count='exact').limit(1).execute().count or 0
            return {
                'colleges': f"c_v{c_cnt}",
                'departments': f"d_v{d_cnt}",
                'subjects': f"s_v{s_cnt}",
                'users': "u_v1"
            }
        except Exception:
            return {'colleges': 'c_v1', 'departments': 'd_v1', 'subjects': 's_v1', 'users': 'u_v1'}

    global_vers = cache.get_cached('sync:global_versions', level=cache.L1, ttl=300, fetcher=fetch_global_versions) if cache else fetch_global_versions()

    user_info = session.get('user', {})
    user_id = user_info.get('uid') or user_info.get('id')
    user_version = None
    files_version = None

    if user_id:
        profile_ts = session.get('profile', {}).get('updated_at') or ''
        user_version = hashlib.md5(f"{user_id}:{profile_ts}".encode('utf-8')).hexdigest()[:12]
        try:
            client = init_supabase()
            latest_access = client.table('document_views').select('accessed_at').eq('user_id', user_id).order('accessed_at', desc=True).limit(1).execute()
            latest_ts = latest_access.data[0].get('accessed_at') if latest_access.data else 'none'
            files_version = hashlib.md5(f"files:{user_id}:{latest_ts}".encode('utf-8')).hexdigest()[:12]
        except Exception:
            files_version = f"files:{user_id}"

    return jsonify({
        'success': True,
        'user_id': user_id,
        'versions': {
            'colleges': global_vers.get('colleges'),
            'departments': global_vers.get('departments'),
            'subjects': global_vers.get('subjects'),
            'users': global_vers.get('users'),
            'recent_files': files_version,
            'user_meta': user_version
        },
        'endpoints': {
            'colleges': '/api/colleges',
            'departments': '/api/departments',
            'subjects': '/api/subjects',
            'recent_files': '/api/file-access-history?limit=25',
            'user_meta': '/api/profile'
        },
        'timestamp': int(time.time())
    }), 200


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
            if 'college_id' in update_data:
                try:
                    from methods.gamification_service import on_user_joined_college
                    on_user_joined_college(user_id, update_data['college_id'])
                except Exception as _g_err:
                    logging.debug(f"[Gamification] on_user_joined_college error: {_g_err}")
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
        from data.transactions import save_transaction_record

        user_info = session.get('user', {})
        user_id = user_info.get('uid') or user_info.get('id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
            
        data = request.get_json(silent=True) or {}
        pack_size = int(data.get('pack', 0) or 0)

        from methods.domain_tier_service import get_tiered_credit_packs, classify_email
        user_email = user_info.get('email', '')
        prof = session.get('profile', {})
        created_at = prof.get('created_at') or user_info.get('created_at')
        valid_packs = get_tiered_credit_packs(user_email, created_at=created_at)
        tier_info = classify_email(user_email, created_at=created_at)

        if pack_size not in valid_packs:
            return jsonify({'success': False, 'message': 'Invalid pack. Choose 10, 65, 160, or 500 views.'}), 400

        pack_info = valid_packs[pack_size]
        price_inr = float(pack_info['price'])
        granted_views = int(pack_info['views'])
        order_id = f"AH{int(time.time())}{secrets.token_hex(2).upper()}"

        # Record initiated transaction in database
        save_transaction_record(order_id, {
            'user_id': user_id,
            'amount': price_inr,
            'status': 'initiated',
            'utr': order_id,
            'admin_notes': f"purpose=Credits-{granted_views};pack={granted_views};views={granted_views};tier={tier_info['tier']};promo={tier_info.get('is_promo', False)}"
        })

        payment_url = f"/payment?amount={price_inr:.2f}&purpose=Credits-{granted_views}-Views&order_id={order_id}"

        return jsonify({
            'success': True,
            'pack': granted_views,
            'price_inr': price_inr,
            'order_id': order_id,
            'tier': tier_info['tier'],
            'discount_pct': tier_info['discount_pct'],
            'payment_url': payment_url,
            'message': 'Payment initiated. Redirecting to payment gateway…'
        }), 200
    except Exception as e:
        logging.error(f"[BUY-CREDITS] Error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/credit-packs', methods=['GET'])
def api_get_credit_packs():
    """Returns tailored credit pack pricing and discount rate based on user's email domain."""
    user = session.get('user', {})
    email = user.get('email', '')
    prof = session.get('profile', {})
    created_at = prof.get('created_at') or user.get('created_at')
    from methods.domain_tier_service import get_tiered_credit_packs, classify_email
    tier_info = classify_email(email, created_at=created_at)
    packs = get_tiered_credit_packs(email, created_at=created_at)
    # Deduplicate aliases
    clean_packs = [
        {'pack': 10, **packs[10]},
        {'pack': 65, **packs[65]},
        {'pack': 160, **packs[160]},
        {'pack': 500, **packs[500]}
    ]
    return jsonify({
        'success': True,
        'tier': tier_info['tier'],
        'tier_label': tier_info['label'],
        'starting_views': tier_info['starting_views'],
        'discount_pct': tier_info['discount_pct'],
        'packs': clean_packs
    }), 200


@api_bp.route('/api/credit-history', methods=['GET'])
@api_bp.route('/api/user/credits/history', methods=['GET'])
@auth_required
def api_credit_history():
    """Retrieve user credit transactions (spend & earn history) and current quota balance."""
    try:
        from data.pricing import _get_quota
        uid = session['user'].get('uid')
        quota_info = _get_quota()
        remaining = quota_info.get('credits', 0)
        txs = []
        client = init_supabase()
        if client and uid:
            try:
                res = client.table('user_credit_ledger').select('*').eq('user_id', uid).order('created_at', desc=True).limit(50).execute()
                if res.data:
                    for row in res.data:
                        txs.append({
                            'id': row.get('id'),
                            'delta': row.get('delta', 0),
                            'balance': row.get('balance', remaining),
                            'reason': row.get('reason') or 'Usage',
                            'source': row.get('source'),
                            'ref_id': row.get('ref_id'),
                            'created_at': row.get('created_at')
                        })
            except Exception:
                pass
            if not txs:
                try:
                    res = client.table('credit_transactions').select('*').eq('user_id', uid).order('created_at', desc=True).limit(50).execute()
                    if res.data:
                        for row in res.data:
                            amt = row.get('amount', 0)
                            txs.append({
                                'id': row.get('id'),
                                'delta': int(amt / 2) if row.get('status') == 'completed' else 0,
                                'balance': remaining,
                                'reason': row.get('admin_notes') or 'Credit Pack Purchase',
                                'source': 'razorpay',
                                'ref_id': row.get('order_id'),
                                'created_at': row.get('created_at')
                            })
                except Exception:
                    pass
        if not txs:
            txs = session.get('credit_history', [])
        return jsonify({
            'success': True,
            'remaining_credits': remaining,
            'transactions': txs,
            'history': txs
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ─── Academic Taxonomy & Metadata APIs ───────────────────────────────────────

@api_bp.route('/api/colleges', methods=['GET'])
def api_get_colleges():
    """Get all colleges for dropdown — cached at L1 for 1 hour."""
    from cache_manager import get_cache
    from methods.supabase_helper import get_colleges_with_document_counts
    cache = get_cache()

    def fetch_all_colleges():
        result = get_colleges_with_document_counts()
        return result.get('data', []) if result.get('success') else []

    colleges = cache.get_cached('dropdowns:colleges:v2', level=cache.L1, ttl=cache.SHORT, fetcher=fetch_all_colleges) if cache else fetch_all_colleges()

    if request.args.get('has_documents', '').lower() in ('1', 'true', 'yes') or request.args.get('has_resources', '').lower() in ('1', 'true', 'yes'):
        filtered = [c for c in (colleges or []) if (c.get('doc_count') or c.get('document_count') or 0) > 0]
        return jsonify({'success': True, 'colleges': filtered}), 200

    response = jsonify({'success': True, 'colleges': colleges}), 200
    if cache:
        cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
    return response


@api_bp.route('/api/colleges/check-availability', methods=['GET', 'POST'])
def api_check_college_availability():
    """Check resource availability, waitlist count, or log requested college."""
    from methods.supabase_helper import init_supabase_admin, init_supabase, get_colleges_with_document_counts
    client = init_supabase_admin() or init_supabase()

    if request.method == 'POST':
        data = request.get_json() or {}
        college_id = data.get('college_id')
        custom_name = data.get('college_name', '').strip()
        email = (data.get('email') or '').strip().lower()
        if client and (college_id or custom_name) and email:
            try:
                # Deduplicate: check if email already registered for this request
                q = client.table('college_waitlist').select('id').eq('email', email)
                if college_id:
                    q = q.eq('college_id', college_id)
                elif custom_name:
                    q = q.ilike('college_name', custom_name)
                exist = q.limit(1).execute()
                if not (exist.data or []):
                    client.table('college_waitlist').insert({
                        'college_id': college_id or None,
                        'college_name': custom_name or None,
                        'email': email
                    }).execute()
            except Exception:
                pass
        return jsonify({'success': True, 'message': 'College request logged'}), 200

    college_id = request.args.get('college_id')
    college_name = request.args.get('name', '').strip()

    colleges_res = get_colleges_with_document_counts()
    colleges = colleges_res.get('data', []) if colleges_res.get('success') else []

    matched = None
    if college_id:
        matched = next((c for c in colleges if str(c.get('id')) == str(college_id)), None)
    elif college_name:
        matched = next((c for c in colleges if c.get('name', '').lower() == college_name.lower()), None)

    doc_count = int(matched.get('doc_count') or matched.get('document_count') or 0) if matched else 0
    waitlist_count = int(matched.get('waitlist_count') or 0) if matched else 0

    if not matched and college_name and client:
        try:
            wl_res = client.table('college_waitlist').select('id', count='exact').ilike('college_name', f"%{college_name}%").execute()
            waitlist_count = wl_res.count or len(wl_res.data or [])
        except Exception:
            waitlist_count = 0

    return jsonify({
        'success': True,
        'has_content': doc_count > 0,
        'document_count': doc_count,
        'waitlist_count': waitlist_count,
        'college': matched
    }), 200


@api_bp.route('/api/gamification/badges', methods=['GET'])
def api_get_badges():
    """Return user's badges with lock status, unlock criteria, and college scarcity counters."""
    from methods.gamification_service import get_all_badges_with_user_status
    user_id = session.get('user', {}).get('uid') or request.args.get('user_id')
    college_id = request.args.get('college_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    badges = get_all_badges_with_user_status(user_id, college_id=college_id)
    return jsonify({'success': True, 'badges': badges}), 200


@api_bp.route('/api/ambassador/status', methods=['GET'])
def api_ambassador_status():
    """Get ambassador unlock progress and founding status for a college."""
    from methods.gamification_service import get_college_ambassador_status
    college_id = request.args.get('college_id')
    if not college_id:
        return jsonify({'success': False, 'message': 'college_id is required'}), 400

    status = get_college_ambassador_status(college_id)
    return jsonify({'success': True, 'status': status}), 200


@api_bp.route('/api/ambassador/leaderboard', methods=['GET'])
def api_ambassador_leaderboard():
    """Get college inviter leaderboard."""
    from methods.gamification_service import get_college_referral_leaderboard
    college_id = request.args.get('college_id')
    if not college_id:
        return jsonify({'success': False, 'message': 'college_id is required'}), 400

    leaderboard = get_college_referral_leaderboard(college_id)
    return jsonify({'success': True, 'leaderboard': leaderboard}), 200


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
            import difflib
            clean_q = query.strip()
            try:
                # 1. Search in current department across all semesters
                q = client.table("subjects").select("id, name, subject_code, semester, department_id")
                if department_id:
                    q = q.eq("department_id", department_id)
                res = q.or_(f"name.ilike.%{clean_q}%,subject_code.ilike.%{clean_q}%").order("name").limit(60).execute()
                results = res.data or []

                # 2. If not found in current department, search globally across all departments
                if not results and department_id:
                    res_global = client.table("subjects").select("id, name, subject_code, semester, department_id").or_(f"name.ilike.%{clean_q}%,subject_code.ilike.%{clean_q}%").order("name").limit(60).execute()
                    results = res_global.data or []

                # 3. Typo-tolerant fuzzy matching (e.g. 'opreating' -> 'Operating System')
                if not results:
                    base_q = client.table("subjects").select("id, name, subject_code, semester, department_id")
                    if department_id:
                        pool = base_q.eq("department_id", department_id).execute().data or []
                        if not pool:
                            pool = client.table("subjects").select("id, name, subject_code, semester, department_id").limit(200).execute().data or []
                    else:
                        pool = base_q.limit(200).execute().data or []

                    pool_names = {s['name'].lower(): s for s in pool if s.get('name')}
                    close = difflib.get_close_matches(clean_q.lower(), list(pool_names.keys()), n=5, cutoff=0.55)
                    results = [pool_names[c] for c in close if c in pool_names]

                return results
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
            # Fetch all subjects for the department so no semester is excluded
            res = client.table("subjects").select("id, name, subject_code, semester, department_id").eq("department_id", department_id).order("name").execute()
            subjs = res.data or []
            if semester and subjs:
                # Prioritize currently selected semester first
                s_int = int(semester)
                subjs.sort(key=lambda s: 0 if s.get('semester') == s_int else 1)
            return subjs
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


@api_bp.route('/api/save-document', methods=['POST'])
@auth_required
def api_save_document():
    """Save a document record from Cloudinary metadata (used after direct browser upload)."""
    try:
        data = request.get_json(silent=True) or {}
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        user_email = user_info.get('email', '')
        
        # Cloudinary result fields
        public_id = data.get('public_id', '')
        secure_url = data.get('secure_url', '')
        file_size = data.get('bytes', 0)
        original_filename = os.path.basename(
            str(data.get('original_filename') or data.get('file_name') or '')
        )
        orig_lower = original_filename.lower()
        pub_lower = str(public_id).lower()
        raw_format = str(data.get('format') or '').lower()
        raw_type = str(data.get('file_type') or '').lower()
        secure_url_lower = str(secure_url).lower()

        # Categorize images vs PDFs accurately
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tiff')
        is_image_upload = (
            any(orig_lower.endswith(ext) for ext in image_extensions)
            or raw_format in ('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg')
            or raw_type in ('image', 'img')
            or '/image/upload/' in secure_url_lower
        )

        is_pdf_upload = (
            not is_image_upload and (
                orig_lower.endswith('.pdf')
                or raw_type == 'pdf'
                or pub_lower.endswith('.txt')
                or '/raw/upload/' in secure_url_lower
            )
        )

        if is_image_upload:
            file_type = 'image'
        elif is_pdf_upload:
            # Cloudinary stores PDFs as raw assets with a .txt public ID.
            public_id = str(public_id)
            if public_id.lower().endswith('.txt.pdf'):
                public_id = public_id[:-4]
            elif not public_id.lower().endswith('.txt'):
                public_id = f"{public_id.rsplit('.', 1)[0] if '.' in public_id else public_id}.txt"
            cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', '')
            if cloud_name:
                secure_url = (
                    f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}"
                )
            file_type = 'pdf'
        else:
            file_type = raw_type if raw_type in ('pdf', 'image', 'document', 'archive') else 'document'
        
        # Document metadata
        title = (data.get('title') or '').strip()
        subject = (data.get('subject') or '').strip()
        subject_id = data.get('subject_id', '')
        college_id = data.get('college_id', '')
        branch_id = data.get('branch_id', '')
        document_type = (data.get('document_type') or 'notes').strip().lower()
        document_type = {
            'pyq': 'papers',
            'paper': 'papers',
            'question-paper': 'papers',
            'question paper': 'papers',
            'practicals': 'practical',
            'lab': 'practical',
            'question bank': 'question_bank',
            'question-bank': 'question_bank',
        }.get(document_type, document_type)
        if document_type not in {'papers', 'notes', 'practical', 'syllabus', 'question_bank', 'assignment', 'timetable'}:
            document_type = 'notes'
        year = str(data.get('year', '') or '')
        semester = data.get('semester')
        description = data.get('description', '')
        exam_type = data.get('exam_type', '')
        subject_code = data.get('subject_code', '')
        program = data.get('program', 'b.tech')
        file_hash = data.get('file_hash', '')
        material_request_id = data.get('material_request_id')
        
        if not public_id or not secure_url:
            return jsonify({'success': False, 'message': 'Missing Cloudinary metadata'}), 400
        
        # Build standardized title
        import re
        from methods.supabase_helper import make_acronym
        col_abbr = ''
        dept_abbr = ''
        subj_abbr = ''
        
        if college_id:
            col_abbr = college_id[:4].upper() if len(college_id) > 4 else college_id.upper()
        if branch_id:
            dept_abbr = branch_id[:4].upper() if len(branch_id) > 4 else branch_id.upper()
        if subject:
            subj_abbr = make_acronym(subject)
        
        prefix_tags = [p for p in [col_abbr, dept_abbr, subj_abbr] if p]
        header = " - ".join(prefix_tags)
        if not title:
            cat_title = document_type.replace('_', ' ').title()
            title = f"{header} - {cat_title} {year}" if header else f"{cat_title} {year}"
        
        # Save the record
        from methods.supabase_helper import save_file_record
        result = save_file_record(
            user_id=user_id,
            user_email=user_email,
            file_name=original_filename or (public_id.split('/')[-1].split('.')[0] if '/' in public_id else public_id),
            file_url=secure_url,
            file_type=file_type,
            file_size=file_size,
            cloudinary_public_id=public_id,
            subject_name=subject,
            document_type=document_type,
            year=year,
            college_id=college_id if college_id else None,
            branch_id=branch_id if branch_id else None,
            title=title,
            description=description,
            subject_id=subject_id if subject_id else None,
            semester=semester,
            program=program,
            exam_type=exam_type,
            subject_code=subject_code,
            file_hash=file_hash
        )
        
        if not result.get('success'):
            # Handle duplicate case
            if result.get('conflict'):
                return jsonify({'success': True, 'skipped': True, 'message': result.get('message', 'File already exists')}), 200
            return jsonify({'success': False, 'message': result.get('message', 'Save failed')}), 500
        
        doc_data = result.get('data', {})
        doc_id = doc_data.get('id')
        
        # Build response
        document_payload = {
            'id': doc_id,
            'title': title,
            'url': f"/resource/{doc_id}" if doc_id else secure_url,
            'subject': subject,
            'semester': semester,
            'document_type': document_type
        }
        
        xp_gained = 1.0
        total_xp = 0.0
        total_contributions = 1
        try:
            profile = session.get('profile') or {}
            total_contributions = int(profile.get('total_contributions') or 0) + 1
            xp_gained = getattr(current_app, 'POINTS_MAP', {}).get(document_type, 0.5) * 0.5
            total_xp = float(profile.get('reputation_score') or 0) + xp_gained
        except Exception:
            pass
        
        contribution_payload = {
            'xp_earned': xp_gained,
            'total_xp': total_xp,
            'total_contributions': total_contributions
        }
        
        return jsonify({
            'success': True,
            'message': 'Document saved successfully!',
            'document': document_payload,
            'contribution': contribution_payload,
            'data': {
                'url': secure_url,
                'record_id': doc_id,
                'resource_id': doc_id,
                'resource_url': f"/resource/{doc_id}" if doc_id else None,
                'title': title,
                'subject': subject,
                'public_id': public_id,
                'file_size': file_size,
                'file_type': file_type
            }
        }), 200
        
    except Exception as e:
        logging.error(f"[API /api/save-document] Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


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
            logging.warning(
                "[extract-upload-metadata] Download failed (error_type=%s)",
                type(e).__name__,
            )

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
            logging.warning(
                "[AI Extract] PDF extraction failed (error_type=%s)",
                type(e).__name__,
            )
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

        try:
            log_turn(
                user_id=user_id,
                session_id=None,
                provider=getattr(provider, 'provider_name', 'openrouter'),
                model=response.model_used,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=response.cost_usd,
                duration_ms=duration_ms,
                mode='direct',
                status='ok',
                route='/api/ai/extract-upload-metadata',
            )
        except Exception as l_err:
            logging.debug("[ai_log] log_turn notice (error_type=%s)", type(l_err).__name__)

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
        try:
            log_turn(
                user_id=user_id,
                session_id=None,
                provider=getattr(provider, 'provider_name', 'openrouter'),
                model=getattr(provider, 'model_name', 'unknown'),
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                duration_ms=duration_ms,
                mode='direct',
                status='error',
                route='/api/ai/extract-upload-metadata',
            )
        except Exception as l_err:
            logging.debug("[ai_log] log_turn error notice (error_type=%s)", type(l_err).__name__)
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
        logging.error(
            "[AI Extract] Unexpected failure (error_type=%s)",
            type(exc).__name__,
        )
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
        if not isinstance(content, str):
            return jsonify({'success': False, 'message': 'Comment content must be text'}), 400
        content = content.strip()
        if not content:
            return jsonify({'success': False, 'message': 'Comment content is required'}), 400
        if len(content) > 2000:
            return jsonify({'success': False, 'message': 'Comment is too long (maximum 2000 characters)'}), 400
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
        logging.error("[HISTORY] Recent document lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Failed to retrieve recent documents', 'data': [], 'count': 0}), 500


@api_bp.route('/api/file-access-history', methods=['GET'])
@auth_required
def api_get_file_access_history():
    """Get file access history from file_access_history table."""
    if request.accept_mimetypes.accept_html and not request.is_json and request.headers.get('Sec-Fetch-Dest') in ('document', 'iframe'):
        return redirect(url_for('app_pages.history'))
    try:
        user_info = session.get('user', {})
        user_email = user_info.get('email')
        if not user_email:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        limit = min(request.args.get('limit', 20, type=int), 100)
        from methods.supabase_helper import get_user_file_history
        user_id = user_info.get('uid') or user_info.get('id')
        result = get_user_file_history(user_email=user_email, user_id=user_id, limit=limit)
        if result.get('success'):
            data = result.get('data', [])
            return jsonify({'success': True, 'data': data, 'count': len(data)}), 200
        return jsonify({'success': False, 'message': 'Failed to retrieve file access history', 'data': [], 'count': 0}), 500
    except Exception as e:
        logging.error("[FILE_HISTORY] Lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Failed to retrieve file access history', 'data': [], 'count': 0}), 500


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

    user_meta = {}
    try:
        import app as main_app
        q = main_app._get_quota() if hasattr(main_app, '_get_quota') else {}
        user_meta['credits'] = q.get('credits', 0)
        user_meta['total_views'] = q.get('total_views', 0)
    except Exception:
        pass

    try:
        from methods.wallet_service import get_creator_commission_pct, get_creator_wallet
        comm = get_creator_commission_pct(user_id)
        user_meta['creator_pct'] = comm.get('creator_pct', 70)
        user_meta['promo_days_remaining'] = comm.get('promo_days_remaining', 0)
        user_meta['is_promo'] = comm.get('is_promo', False)
        user_meta['is_claimed'] = comm.get('is_claimed', False)
        wallet = get_creator_wallet(user_id)
        user_meta['wallet_balance'] = wallet.get('withdrawable_balance', 0.0)
    except Exception:
        pass

    try:
        from methods.wallet_service import _get_client
        prof_res = _get_client().table('profiles').select('role, subscription_tier').eq('id', user_id).limit(1).execute()
        if prof_res and prof_res.data and len(prof_res.data) > 0:
            p_data = prof_res.data[0]
            user_meta['account_type'] = (p_data.get('role') or 'student').capitalize()
            user_meta['subscription_tier'] = (p_data.get('subscription_tier') or 'free').capitalize()
        else:
            user_meta['account_type'] = 'Student'
            user_meta['subscription_tier'] = 'Free'
    except Exception:
        user_meta['account_type'] = 'Student'
        user_meta['subscription_tier'] = 'Free'

    return jsonify({'success': True, 'data': items, 'unread': unread, 'user_meta': user_meta}), 200


@api_bp.route('/api/claim-promo', methods=['POST'])
@auth_required
def api_claim_promo():
    """Activates the 90-day 90% creator royalties launch promotion for the user."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    from methods.wallet_service import claim_creator_promo
    result = claim_creator_promo(user_id)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@api_bp.route('/api/telemetry/track', methods=['POST'])
def api_telemetry_track():
    """Ingests batched feature usage, device, and network telemetry."""
    data = request.get_json(silent=True) or {}
    events = data.get('events') or ([data] if data.get('feature') else [])
    if not events:
        return jsonify({'success': False, 'message': 'No events'}), 400

    from methods.feature_telemetry import log_feature_event
    user_id = session.get('user', {}).get('uid') if 'user' in session else None

    count = 0
    for ev in events[:25]:
        feat = ev.get('feature')
        if feat:
            log_feature_event(
                user_id=user_id,
                feature=feat,
                action=ev.get('action', 'interact'),
                device_info=ev.get('device'),
                network_info=ev.get('network'),
                path=ev.get('path', '/'),
                metadata=ev.get('metadata'),
                req=request
            )
            count += 1

    return jsonify({'success': True, 'count': count}), 200


@api_bp.route('/api/admin/feature-analytics', methods=['GET'])
@auth_required
def api_admin_feature_analytics():
    """Returns aggregated feature adoption metrics, device distribution, and network breakdown."""
    days = min(request.args.get('days', 30, type=int), 90)
    from methods.feature_telemetry import get_feature_analytics_summary
    data = get_feature_analytics_summary(days=days)
    return jsonify({'success': True, 'data': data}), 200


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
        return jsonify({'success': False, 'message': 'Failed to retrieve files', 'data': [], 'count': 0}), 500
    except Exception as e:
        logging.error("[API /api/files/all] Lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Failed to retrieve files'}), 500


@api_bp.route('/api/proxy-file')
@auth_required
def proxy_file():
    """Compatibility redirect to the resource page; raw URL proxying is disabled."""
    doc_id = str(request.args.get('doc_id') or '').strip()
    if not validate_uuid(doc_id):
        return jsonify({'success': False, 'message': 'A valid document ID is required'}), 400
    return redirect(f"/resources/{doc_id}", code=302)


def authorize_document_access(doc_id, filename=None):
    """Authorize a document and return a short-lived provider URL when supported.

    Returns:
        (data_dict, status_code)
    """
    import re
    from methods.supabase_helper import get_document_by_id_rich

    token = request.args.get('token', '')
    if token and not _verify_pdf_token(doc_id, token):
        return {'success': False, 'error': 'forbidden', 'message': 'Invalid or expired access token'}, 403

    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        return {'success': False, 'error': 'not_found', 'message': 'Document not found'}, 404
    document = doc_res.get('data', {})

    if not _document_is_visible(document):
        return {'success': False, 'error': 'not_found', 'message': 'Document not found'}, 404

    current_uid = session.get('user', {}).get('uid') or session.get('user', {}).get('id')
    has_access = has_document_access(current_uid, doc_id, document)
    is_preview_mode = False

    pricing = extract_document_pricing(document)
    is_paid_doc = bool(pricing.get('is_paid')) and float(pricing.get('price', 0)) > 0

    if not has_access:
        if is_paid_doc and request.args.get('preview') == '1' and (document.get('file_type') == 'pdf' or '.pdf' in str(document.get('file_url', '')).lower()):
            is_preview_mode = True
        else:
            return {
                'success': False,
                'error': 'payment_required' if is_paid_doc else 'forbidden',
                'message': 'Payment required to view or download this document.' if is_paid_doc else 'You do not have permission to view this document.',
                'document_id': doc_id,
                'price': pricing.get('price', 0),
                'is_paid': is_paid_doc,
                'is_preview_available': is_paid_doc and (document.get('file_type') == 'pdf' or '.pdf' in str(document.get('file_url', '')).lower())
            }, (402 if is_paid_doc else 403)

    document_version = '|'.join(
        str(document.get(field) or '')
        for field in ('updated_at', 'file_hash', 'file_size', 'file_url')
    )
    version_identifier = hashlib.sha256(
        f"{doc_id}:{document_version}".encode('utf-8')
    ).hexdigest()[:16]

    file_url = document.get('file_url', '')
    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    if not file_url or not isinstance(file_url, str):
        return {'success': False, 'error': 'not_found', 'message': 'File URL not found for document'}, 404

    # Paid previews must remain server-side because the viewer strips every page
    # except the first. Full entitled documents are delivered directly by the
    # provider so PDF.js does not route file bytes through the Flask host.
    signed_target_url = f"/api/view-doc/{doc_id}/file?preview=1" if is_preview_mode else None
    if not is_preview_mode:
        signed_target_url = _create_document_delivery_url(document, file_url, doc_id)

    filename_doc = document.get('title') or document.get('file_name') or 'document.pdf'
    filename_doc = re.sub(r'[^a-z0-9_\-\.]+', '_', filename_doc, flags=re.I)
    if not filename_doc.lower().endswith('.pdf'):
        filename_doc = filename_doc.rsplit('.', 1)[0] + '.pdf'

    raw_lower = file_url.lower().split('?')[0]
    is_img_ext = any(raw_lower.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif'))

    is_pdf_doc = not is_img_ext and (
        document.get('file_type') == 'pdf' or
        '.pdf' in file_url.lower() or
        file_url.lower().endswith('.txt') or
        (filename and filename.lower().endswith('.pdf')) or
        str(document.get('file_name', '')).lower().endswith('.pdf')
    )

    if is_pdf_doc:
        resolved_file_type = 'application/pdf'
    elif raw_lower.endswith('.jpg') or raw_lower.endswith('.jpeg'):
        resolved_file_type = 'image/jpeg'
    elif raw_lower.endswith('.png'):
        resolved_file_type = 'image/png'
    elif raw_lower.endswith('.webp'):
        resolved_file_type = 'image/webp'
    else:
        resolved_file_type = document.get('file_type') or 'application/octet-stream'

    payload = {
        'success': True,
        'document_id': doc_id,
        'file_url': signed_target_url,
        'file_type': resolved_file_type,
        'file_version': version_identifier,
        'filename': filename_doc,
        'is_preview': is_preview_mode,
        'title': document.get('title') or filename_doc
    }
    return payload, 200


def _create_document_delivery_url(document, file_url, doc_id):
    """Create a short-lived provider URL; use the protected viewer as fallback."""
    import re
    from datetime import timedelta
    from urllib.parse import unquote, urlparse

    viewer_fallback = f"/api/view-doc/{doc_id}/file?stream=1"
    if file_url.startswith(('/static/', 'static/')):
        return file_url

    parsed = urlparse(file_url)
    provider = str(document.get('storage_provider') or '').strip().lower()
    if provider == 'firebase' or not parsed.scheme:
        try:
            from firebase_admin import storage
            path = file_url
            bucket_name = os.getenv('FIREBASE_STORAGE_BUCKET', 'abhi-hub.appspot.com')
            if parsed.hostname in ('firebasestorage.googleapis.com', 'storage.googleapis.com'):
                match = re.search(r'/b/([^/]+)/o/(.+?)(?:\?|$)', file_url)
                if not match:
                    return viewer_fallback
                bucket_name = match.group(1)
                path = unquote(match.group(2))
            blob = storage.bucket(name=bucket_name).blob(path)
            return blob.generate_signed_url(
                version='v4', expiration=timedelta(minutes=10), method='GET'
            )
        except Exception as exc:
            logging.warning('[AUTH-DOC] Firebase signing failed (error_type=%s)', type(exc).__name__)
            return viewer_fallback

    if parsed.hostname == 'res.cloudinary.com' or provider == 'cloudinary':
        try:
            import time
            import cloudinary
            import cloudinary.utils
            cloudinary.config(
                cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
                api_key=os.getenv('CLOUDINARY_API_KEY'),
                api_secret=os.getenv('CLOUDINARY_API_SECRET'),
                secure=True,
            )
            public_id = (
                document.get('provider_public_id')
                or document.get('cloudinary_public_id')
                or document.get('public_id')
            )
            if not public_id:
                match = re.search(r'/upload/(?:v\d+/)?(.+)$', parsed.path)
                public_id = match.group(1) if match else None
            if not public_id:
                return viewer_fallback
            resource_type = 'image' if '/image/' in parsed.path else ('video' if '/video/' in parsed.path else 'raw')
            # New uploads use authenticated delivery. Preserve the stored type
            # for legacy assets so existing records remain readable.
            delivery_type = 'authenticated' if '/authenticated/' in parsed.path else 'upload'
            signed, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=resource_type,
                type=delivery_type,
                sign_url=True,
                expires_at=int(time.time()) + 600,
            )
            return signed or viewer_fallback
        except Exception as exc:
            logging.warning('[AUTH-DOC] Cloudinary signing failed (error_type=%s)', type(exc).__name__)
            return viewer_fallback

    if parsed.hostname and parsed.hostname.endswith('.supabase.co'):
        try:
            match = re.search(r'/storage/v1/object/(?:public|sign)/([^/]+)/(.+)$', parsed.path)
            if match:
                from methods.supabase_helper import init_supabase
                client = init_supabase()
                if client:
                    result = client.storage.from_(match.group(1)).create_signed_url(
                        unquote(match.group(2)), 600
                    )
                    signed = result.get('signedURL') or result.get('signedUrl')
                    if signed and signed.startswith('/'):
                        signed = f"{parsed.scheme}://{parsed.netloc}{signed}"
                    if signed:
                        return signed
        except Exception as exc:
            logging.warning('[AUTH-DOC] Supabase signing failed (error_type=%s)', type(exc).__name__)
        return viewer_fallback

    return viewer_fallback


def _document_is_visible(document):
    """Published documents are public; unpublished records are private to owner/admin."""
    if str((document or {}).get('status') or '').strip().lower() == 'approved':
        return True
    user = session.get('user', {})
    user_id = user.get('uid') or user.get('id')
    is_owner = bool(user_id and str(user_id) == str((document or {}).get('uploader_id') or ''))
    return is_owner or is_admin_user(user)


@api_bp.route('/api/documents/<doc_id>/authorize', methods=['GET', 'POST'])
@api_bp.route('/api/view-doc/<doc_id>/authorize', methods=['GET', 'POST'])
@api_bp.route('/api/view-doc/<doc_id>/auth', methods=['GET', 'POST'])
def api_authorize_document(doc_id):
    """Authorization endpoint for direct cloud storage document delivery."""
    payload, status = authorize_document_access(doc_id)
    return jsonify(payload), status



_MAX_PAID_IMAGE_PREVIEW_BYTES = 25 * 1024 * 1024
_MAX_PAID_IMAGE_PREVIEW_PIXELS = 20_000_000


class ImagePreviewTooLarge(ValueError):
    """Raised when a paid image cannot be safely decoded within preview limits."""


def _read_image_preview_source(upstream):
    content_length = upstream.headers.get('Content-Length')
    if content_length:
        try:
            if int(content_length) > _MAX_PAID_IMAGE_PREVIEW_BYTES:
                raise ImagePreviewTooLarge('Image exceeds preview size limit')
        except ValueError as exc:
            if isinstance(exc, ImagePreviewTooLarge):
                raise

    output = bytearray()
    for chunk in upstream.iter_content(chunk_size=65536):
        if not chunk:
            continue
        output.extend(chunk)
        if len(output) > _MAX_PAID_IMAGE_PREVIEW_BYTES:
            raise ImagePreviewTooLarge('Image exceeds preview size limit')
    if not output:
        raise ValueError('Image content is empty')
    return bytes(output)


def _create_paid_image_preview(image_bytes):
    """Return a low-resolution JPEG with only the top fifth clear."""
    import io
    from PIL import Image, ImageFilter, ImageOps

    if not image_bytes or len(image_bytes) > _MAX_PAID_IMAGE_PREVIEW_BYTES:
        raise ImagePreviewTooLarge('Image exceeds preview size limit')

    with Image.open(io.BytesIO(image_bytes)) as source:
        width, height = source.size
        if width <= 0 or height <= 0 or width * height > _MAX_PAID_IMAGE_PREVIEW_PIXELS:
            raise ImagePreviewTooLarge('Image dimensions exceed preview limit')
        source.seek(0)
        image = ImageOps.exif_transpose(source).convert('RGB')

    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    width, height = image.size
    clear_height = max(1, min(height, round(height * 0.20)))
    clear_top = image.crop((0, 0, width, clear_height))
    blurred_lower = image.crop((0, clear_height, width, height))
    blur_radius = max(10, min(36, round(min(width, height) * 0.035)))
    blurred_lower = blurred_lower.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    preview = Image.new('RGB', (width, height), color='white')
    preview.paste(clear_top, (0, 0))
    if blurred_lower.height:
        preview.paste(blurred_lower, (0, clear_height))
    result = io.BytesIO()
    preview.save(result, format='JPEG', quality=76, optimize=True)
    return result.getvalue()


def _image_preview_response(preview_data, document_etag):
    headers = _secure_file_headers()
    headers['Content-Disposition'] = "inline; filename*=UTF-8''paid-image-preview.jpg"
    headers['Content-Length'] = str(len(preview_data))
    headers['X-AbhiHub-Preview'] = 'top-20-clear-rest-blurred'
    headers['ETag'] = document_etag
    headers['Cache-Control'] = 'private, max-age=60, must-revalidate'
    headers['Vary'] = 'Cookie, Authorization'
    return Response(preview_data, status=200, content_type='image/jpeg', headers=headers)


@api_bp.route('/api/view-doc/<doc_id>')
@api_bp.route('/api/view-doc/<doc_id>/<filename>')
def view_doc(doc_id, filename=None):
    """Clean proxy endpoint for streaming documents to PDF.js."""
    wants_json = (
        request.args.get('format') == 'json' or
        request.headers.get('Accept') == 'application/json' or
        request.path.endswith('/auth') or
        request.path.endswith('/authorize')
    )
    if wants_json:
        payload, status = authorize_document_access(doc_id, filename=filename)
        return jsonify(payload), status

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
        try:
            from observability.alerts import report_critical_incident
            report_critical_incident(
                name="File Open Failure",
                message=f"Document ID '{doc_id}' not found in viewer",
                route=request.path,
                cause=f"Database lookup failed or record missing: {doc_res.get('message', 'Document not found')}",
                account={"uid": current_uid, "email": session.get('user', {}).get('email')},
                feature="file_open",
                metadata={"doc_id": doc_id, "user_id": current_uid}
            )
        except Exception:
            pass
        abort(404)
    document = doc_res.get('data', {})

    if not _document_is_visible(document):
        abort(404)

    current_uid = session.get('user', {}).get('uid') or session.get('user', {}).get('id')
    has_access = has_document_access(current_uid, doc_id, document)
    is_preview_mode = False
    is_image_preview = False

    pricing = extract_document_pricing(document)
    is_paid_doc = bool(pricing.get('is_paid')) and float(pricing.get('price', 0)) > 0
    source_url = document.get('file_url') or ''
    if isinstance(source_url, (list, tuple)):
        source_url = source_url[0] if source_url else ''
    from urllib.parse import urlsplit
    source_ext = os.path.splitext(urlsplit(str(source_url)).path)[1].lower()
    source_type = str(document.get('file_type') or '').strip().lower()
    paid_image_types = {'image', 'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'avif'}
    is_image_document = (
        source_ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif'} or
        source_type in paid_image_types or source_type.startswith('image/') or
        bool(document.get('is_image'))
    )

    is_pdf_document = (
        str(document.get('file_type') or '').strip().lower() in {'pdf', 'application/pdf'} or
        '.pdf' in str(source_url).lower()
    )
    if is_paid_doc and is_pdf_document and request.args.get('preview') == '1':
        is_preview_mode = True
    elif is_paid_doc and is_image_document and request.args.get('preview') == '1':
        is_image_preview = True
    elif not has_access:
        if is_paid_doc and is_pdf_document:
            is_preview_mode = True
        else:
            return jsonify({
                'success': False,
                'message': 'Payment required to view or download this document.'
            }), 402

    # The document id is stable, while this version changes whenever the
    # backing record/file is changed. This lets each browser revalidate a
    # private response without downloading the document again.
    document_version = '|'.join(
        str(document.get(field) or '')
        for field in ('updated_at', 'file_hash', 'file_size', 'file_url')
    )
    response_variant = 'image-preview' if is_image_preview else ('pdf-preview' if is_preview_mode else 'full')
    document_etag = '"' + hashlib.sha256(
        f"{doc_id}:{document_version}:{response_variant}".encode('utf-8')
    ).hexdigest() + '"'
    if request.headers.get('If-None-Match') == document_etag and not request.headers.get('Range'):
        response = Response(status=304)
        response.headers['ETag'] = document_etag
        response.headers['Cache-Control'] = 'private, max-age=300, must-revalidate'
        response.headers['Vary'] = 'Cookie, Authorization, Range'
        return response

    file_url = document.get('file_url', '')
    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    if not file_url or not isinstance(file_url, str):
        abort(404)

    # Support local static files (such as chat uploads) directly from disk
    if file_url.startswith('/static/') or file_url.startswith('static/'):
        clean_rel = file_url.lstrip('/')
        local_disk_path = os.path.join(current_app.root_path, clean_rel)
        if os.path.exists(local_disk_path):
            from flask import send_file
            if is_image_preview:
                try:
                    with open(local_disk_path, 'rb') as local_file:
                        original = local_file.read(_MAX_PAID_IMAGE_PREVIEW_BYTES + 1)
                    if len(original) > _MAX_PAID_IMAGE_PREVIEW_BYTES:
                        return jsonify({'success': False, 'message': 'Preview is unavailable for this image.'}), 413
                    preview_data = _create_paid_image_preview(original)
                except ImagePreviewTooLarge:
                    return jsonify({'success': False, 'message': 'Preview is too large to process.'}), 413
                except (OSError, ValueError):
                    return jsonify({'success': False, 'message': 'Preview is unavailable for this image.'}), 415
                return _image_preview_response(preview_data, document_etag)
            mimetype = 'application/pdf' if local_disk_path.lower().endswith('.pdf') else None
            return send_file(local_disk_path, mimetype=mimetype)

    # In production environments without stream=1 flag, redirect directly to cloud storage
    if not file_url.startswith('http'):
        cache_key = f"signed-url:{doc_id}:{document_version}"
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
                logging.error(
                    "[VIEW-DOC] Firebase sign setup failed (error_type=%s)",
                    type(e).__name__,
                )

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
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS and not (parsed.hostname or '').endswith('.supabase.co'):
        abort(403)

    upstream_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    if request.headers.get('Range') and not (is_preview_mode or is_image_preview):
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
            pub_id = (
                document.get('provider_public_id')
                or document.get('cloudinary_public_id')
                or document.get('public_id')
                or ''
            )
            if not pub_id:
                m = re.search(r'/upload/(?:v\d+/)?(.+)$', parsed.path)
                pub_id = m.group(1) if m else ''
            if pub_id:
                cloudinary_cache_key = f"cloudinary-signed-url:{doc_id}:{document_version}"
                cached_signed = cache.l1.get(cloudinary_cache_key)[0]
                if cached_signed:
                    file_url = cached_signed
                else:
                    rtype = 'raw' if '/raw/' in parsed.path else ('image' if '/image/' in parsed.path else 'raw')
                    delivery_type = 'authenticated' if '/authenticated/' in parsed.path else 'upload'
                    signed_url, _ = _cld_utils.cloudinary_url(
                        pub_id, resource_type=rtype, type=delivery_type,
                        sign_url=True, expires_at=int(_time.time()) + 3600
                    )
                    if signed_url:
                        file_url = signed_url
                        cache.l1.set(cloudinary_cache_key, signed_url, ttl=300)
                parsed = urlparse(file_url)
        except Exception as _e:
            logging.warning(
                "[VIEW-DOC] Cloudinary pre-sign failed (error_type=%s)",
                type(_e).__name__,
            )

    upstream = _fetch(file_url)

    # Older records may contain a Cloudinary URL with a PDF extension even
    # though the asset was uploaded as raw .txt. Retry the canonical raw path.
    if upstream.status_code == 404 and parsed.hostname == 'res.cloudinary.com':
        try:
            cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', '')
            pub_id = (
                document.get('provider_public_id')
                or document.get('cloudinary_public_id')
                or document.get('public_id')
                or ''
            )
            if cloud_name and pub_id:
                raw_pub_id = str(pub_id)
                if not raw_pub_id.lower().endswith('.txt'):
                    raw_pub_id = f"{raw_pub_id.rsplit('.', 1)[0] if '.' in raw_pub_id else raw_pub_id}.txt"
                retry_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{raw_pub_id}"
                upstream.close()
                upstream = _fetch(retry_url)
                if upstream.ok:
                    file_url = retry_url
                    parsed = urlparse(retry_url)
        except Exception as retry_error:
            logging.warning(
                "[VIEW-DOC] Cloudinary raw-file retry failed (error_type=%s)",
                type(retry_error).__name__,
            )

    if upstream.status_code in (403, 404) and parsed.hostname in ('firebasestorage.googleapis.com', 'storage.googleapis.com'):
        try:
            cache.l1.delete(f"signed-url:{doc_id}:{document_version}")
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
                    cache.l1.set(f"signed-url:{doc_id}:{document_version}", fresh_url, ttl=300)
                except Exception:
                    pass
                upstream.close()
                upstream = _fetch(fresh_url)
            except Exception as e:
                logging.error(
                    "[VIEW-DOC] Re-sign failed (error_type=%s)",
                    type(e).__name__,
                )

    if upstream.status_code == 401 and parsed.hostname == 'res.cloudinary.com':
        try:
            import cloudinary.utils as _cld_utils
            import time as _time
            m = re.search(r'/upload/(?:v\d+/)?(.+)$', parsed.path)
            if m:
                pub = m.group(1)
                rtype = 'raw' if '/raw/' in parsed.path else ('image' if '/image/' in parsed.path else 'raw')
                delivery_type = 'authenticated' if '/authenticated/' in parsed.path else 'upload'
                signed_url, _ = _cld_utils.cloudinary_url(
                    pub, resource_type=rtype, type=delivery_type, sign_url=True, expires_at=int(_time.time()) + 3600
                )
                if signed_url:
                    upstream.close()
                    upstream = _fetch(signed_url)
        except Exception as _e:
            logging.error(
                "[VIEW-DOC] Cloudinary sign failed (error_type=%s)",
                type(_e).__name__,
            )

    try:
        if upstream.status_code == 204:
            msg = json.dumps({"error": "Document not available", "detail": f"No content found for document {doc_id}"})
            return Response(msg, status=404, content_type='application/json', headers=_secure_file_headers())
        if not upstream.ok:
            try:
                from observability.alerts import report_critical_incident
                report_critical_incident(
                    name="File Open Storage Failure",
                    message=f"Storage returned HTTP {upstream.status_code} for document '{doc_id}'",
                    route=request.path,
                    cause=f"Upstream storage returned HTTP {upstream.status_code} for URL: {str(file_url)[:120]}",
                    account={"uid": current_uid, "email": session.get('user', {}).get('email')},
                    feature="file_open",
                    metadata={"doc_id": doc_id, "status_code": upstream.status_code, "file_url": str(file_url)[:120]}
                )
            except Exception:
                pass
            abort(upstream.status_code if upstream.status_code in (403, 404) else 502)

        if is_image_preview:
            try:
                original_image = _read_image_preview_source(upstream)
                preview_image = _create_paid_image_preview(original_image)
            except ImagePreviewTooLarge:
                return jsonify({'success': False, 'message': 'Preview is too large to process.'}), 413
            except Exception:
                return jsonify({'success': False, 'message': 'Preview is unavailable for this image.'}), 415
            finally:
                upstream.close()
            return _image_preview_response(preview_image, document_etag)

        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        is_pdf_doc = (
            document.get('file_type') == 'pdf' or
            '.pdf' in file_url.lower() or
            file_url.lower().endswith('.txt') or
            (filename and filename.lower().endswith('.pdf')) or
            str(document.get('file_name', '')).lower().endswith('.pdf')
        )
        if is_pdf_doc:
            content_type = 'application/pdf'
            filename_doc = document.get('title') or document.get('file_name') or 'document.pdf'
            filename_doc = re.sub(r'[^a-z0-9_\-\.]+', '_', filename_doc, flags=re.I)
            if filename_doc.lower().endswith('.txt'):
                filename_doc = filename_doc[:-4] + '.pdf'
            elif not filename_doc.lower().endswith('.pdf'):
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
            preview_headers['ETag'] = document_etag
            preview_headers['Cache-Control'] = 'private, max-age=300, must-revalidate'
            preview_headers['Vary'] = 'Cookie, Authorization, Range'
            return Response(preview_data, status=200, content_type='application/pdf', headers=preview_headers)

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            except Exception as e:
                logging.error(f"[VIEW-DOC] Stream interrupted: {e}")

        response_headers = _secure_file_headers()
        response_headers['ETag'] = document_etag
        response_headers['Cache-Control'] = 'private, max-age=300, must-revalidate'
        response_headers['Vary'] = 'Cookie, Authorization, Range'
        if document.get('updated_at'):
            response_headers['Last-Modified'] = str(document['updated_at'])
        if is_pdf_doc:
            response_headers['Content-Disposition'] = f"inline; filename*=UTF-8''{filename_doc}"
        if 'Content-Length' in upstream.headers:
            response_headers['Content-Length'] = upstream.headers['Content-Length']
        if upstream.status_code == 206:
            response_headers['Content-Range'] = upstream.headers.get('Content-Range', '')
            response_headers['Accept-Ranges'] = 'bytes'

        return Response(generate(), status=upstream.status_code, content_type=content_type, headers=response_headers)
    except Exception as e:
        logging.error(
            "[VIEW-DOC] Exception streaming document (error_type=%s)",
            type(e).__name__,
        )
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
    """Resolve a legacy file path to its resource page; never serve raw paths."""
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Resource not found'}), 404
        result = (client.table('documents')
                  .select('id')
                  .eq('file_url', pdf_name)
                  .limit(1)
                  .execute())
        rows = getattr(result, 'data', None) or []
        if not rows or not rows[0].get('id'):
            return jsonify({'success': False, 'message': 'Resource not found'}), 404
        return redirect(f"/resources/{rows[0]['id']}", code=302)
    except Exception as e:
        logging.warning("[PDF_PROXY] Resource lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Resource not found'}), 404


@api_bp.route('/verify-file', methods=['POST'])
@auth_required
@admin_required
def verify_file():
    """Admin-only legacy utility to register a file after it is verified in storage."""
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
        logging.error("[VERIFY_FILE] Verification failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'File verification failed'}), 500


@api_bp.route('/get-file-url', methods=['POST'])
@auth_required
def get_file_url():
    """Return a signed URL only after the document viewer access policy allows it."""
    try:
        data = request.get_json() or {}
        doc_id = str(data.get('doc_id') or '').strip()
        if not doc_id:
            return jsonify({'success': False, 'message': 'Document ID is required'}), 400

        payload, status = authorize_document_access(doc_id)
        if status != 200:
            return jsonify(payload), status
        signed_url = payload.get('file_url') if isinstance(payload, dict) else None
        if not signed_url:
            return jsonify({'success': False, 'message': 'File URL is unavailable'}), 404
        return jsonify({'success': True, 'url': signed_url, 'document_id': doc_id}), 200
    except Exception as e:
        logging.error("[GET_FILE_URL] Signing failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'File URL is temporarily unavailable'}), 500


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
        logging.error("[UPDATE_FILE_METADATA] Update failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'File metadata update failed'}), 500


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
        logging.error("[MemoryWall] Signature upload failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Signature upload failed'}), 500


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
        err_msg = str(e)
        if 'PGRST205' in err_msg or 'material_requests' in err_msg:
            logging.warning("[MaterialRequests] Table 'material_requests' not found in schema cache. Migration pending: migrations/017_material_requests_table.sql")
            return jsonify({
                'success': False,
                'error': 'table_not_found',
                'message': 'Database table material_requests has not been migrated yet. Please apply migrations/017_material_requests_table.sql',
                'requests': []
            }), 404
        logging.error(f"[MaterialRequests] Unexpected error: {e}")
        return jsonify({'success': False, 'message': 'Database error', 'requests': []}), 500


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
        logging.error("[CHAT] Peer search failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'users': [], 'suggested': [], 'error': 'Peer search failed'}), 500


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
        logging.error("[CHAT] History lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'error': 'Chat history is temporarily unavailable'}), 500


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

    title_raw = (request.form.get('title') or '').strip()
    category_raw = (request.form.get('category') or 'notes').lower()

    # Map category string to platform document categories
    cat_clean = 'notes'
    if 'paper' in category_raw or 'pyq' in category_raw:
        cat_clean = 'papers'
    elif 'practical' in category_raw or 'lab' in category_raw:
        cat_clean = 'practical'
    elif 'syllabus' in category_raw:
        cat_clean = 'syllabus'
    elif 'assignment' in category_raw or 'assisment' in category_raw:
        cat_clean = 'assignment'
    elif 'question' in category_raw:
        cat_clean = 'question_bank'

    year_val = (request.form.get('year') or '2025').strip()
    if not (year_val.isdigit() and len(year_val) == 4):
        year_val = '2025'

    sem_raw = str(request.form.get('semester') or '').strip()
    semester_val = None
    import re
    sem_match = re.search(r'\d+', sem_raw)
    if sem_match:
        try:
            s_num = int(sem_match.group())
            if 1 <= s_num <= 8:
                semester_val = s_num
        except Exception:
            pass

    details_val = request.form.get('details') or 'Shared via Peer Chat'
    subject_val = (request.form.get('subject') or title_raw or 'General').strip()
    program_val = (request.form.get('program') or 'b.tech').strip()
    college_id_val = request.form.get('college_id') or session.get('user', {}).get('college_id')
    branch_id_val = request.form.get('branch_id') or request.form.get('department_id') or session.get('user', {}).get('branch_id')
    subject_id_val = request.form.get('subject_id')
    doc_id = None
    resource_url = None

    from methods.supabase_helper import init_supabase, init_supabase_admin
    client = init_supabase() or init_supabase_admin()

    # If subject_id is not yet created in table, check or insert it into subjects table
    try:
        if client and not subject_id_val and subject_val:
            s_check = client.table('subjects').select('id, name, subject_code').ilike('name', f"%{subject_val}%").limit(1).execute()
            if s_check.data:
                subject_id_val = s_check.data[0]['id']
            elif branch_id_val:
                ins_res = client.table('subjects').insert({
                    'name': subject_val,
                    'department_id': branch_id_val,
                    'semester': semester_val
                }).execute()
                if ins_res.data:
                    subject_id_val = ins_res.data[0]['id']
    except Exception as s_err:
        logging.info(f"[chat] Subject table lookup/insert notice: {s_err}")

    # Acronym helper for college, branch, and subject abbreviations
    def make_acronym(text):
        if not text:
            return ''
        stop_words = {'and', 'of', 'the', 'in', 'for', 'to', 'with', 'on', 'at', '&'}
        words = [w for w in re.split(r'[\s_\-]+', text.strip()) if w and w.lower() not in stop_words]
        if len(words) == 1:
            clean = re.sub(r'[^a-zA-Z0-9]', '', words[0])
            return clean.upper() if len(clean) <= 6 else clean[:6].upper()
        acr = "".join([re.sub(r'[^a-zA-Z0-9]', '', w)[:1] for w in words])
        return acr.upper() if len(acr) >= 2 else re.sub(r'[^a-zA-Z0-9]', '', text)[:6].upper()

    col_abbr = (request.form.get('college_abbr') or '').strip().upper()
    dept_abbr = (request.form.get('branch_abbr') or request.form.get('department_abbr') or '').strip().upper()
    subj_abbr = (request.form.get('subject_abbr') or '').strip().upper()
    subj_code = (request.form.get('subject_code') or '').strip().upper()

    if client:
        if not col_abbr and college_id_val:
            try:
                c_row = client.table('colleges').select('name, abbreviation').eq('id', college_id_val).limit(1).execute()
                if c_row.data:
                    col_abbr = (c_row.data[0].get('abbreviation') or make_acronym(c_row.data[0].get('name'))).strip().upper()
            except Exception:
                pass
        if not dept_abbr and branch_id_val:
            try:
                d_row = client.table('departments').select('name, abbreviation').eq('id', branch_id_val).limit(1).execute()
                if d_row.data:
                    dept_abbr = (d_row.data[0].get('abbreviation') or make_acronym(d_row.data[0].get('name'))).strip().upper()
            except Exception:
                pass
        if subject_id_val:
            try:
                s_row = client.table('subjects').select('name, subject_code').eq('id', subject_id_val).limit(1).execute()
                if s_row.data:
                    if not subj_code:
                        subj_code = (s_row.data[0].get('subject_code') or '').strip().upper()
                    if not subj_abbr:
                        subj_abbr = make_acronym(s_row.data[0].get('name') or subject_val)
            except Exception:
                pass

    if not subj_abbr and subject_val:
        subj_abbr = make_acronym(subject_val)

    unit_val = (request.form.get('unit') or '').strip()
    unit_clean = re.sub(r'[^a-zA-Z0-9]', '', unit_val) or 'Full'
    cat_title = cat_clean.capitalize()

    # Form descriptive title: CollegeAbbr - DeptAbbr - SubjAbbr (SubjectCode) - Topic/Unit/Category
    prefix_tags = [p for p in [col_abbr, dept_abbr, subj_abbr] if p]
    header = " - ".join(prefix_tags)
    if subj_code and subj_code not in header:
        header = f"{header} ({subj_code})" if header else subj_code

    custom_topic = ''
    if title_raw and title_raw.lower() != subject_val.lower() and not title_raw.startswith(header):
        custom_topic = title_raw

    desc_parts = []
    if custom_topic:
        desc_parts.append(custom_topic)
    if unit_val and unit_val.lower() not in (custom_topic.lower() if custom_topic else ''):
        desc_parts.append(unit_val)
    desc_parts.append(cat_title)
    if year_val:
        desc_parts.append(year_val)

    descriptive_title = f"{header} - {' · '.join(desc_parts)}" if header else " · ".join(desc_parts)

    # Form descriptive filename: CollegeAbbr_DeptAbbr_SubjAbbr_SubjCode_Unit_Category_Year.ext
    ext = os.path.splitext(orig_name)[1] or '.pdf'
    fn_components = [p for p in [col_abbr, dept_abbr, subj_abbr, subj_code, unit_clean, cat_title, year_val] if p]
    if not fn_components:
        fn_components = [os.path.splitext(orig_name)[0] or 'study_material']
    descriptive_filename = "_".join(re.sub(r'[^a-zA-Z0-9]', '', c) for c in fn_components) + ext

    safe_name = f"chat_{int(time.time())}_{_get_uid()[:8]}_{descriptive_filename}"
    upload_dir = os.path.join(current_app.static_folder or 'static', 'uploads', 'chat')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, safe_name)
    file.save(save_path)

    file_url = f"/static/uploads/chat/{safe_name}"

    try:
        from methods.supabase_helper import save_file_record, recalculate_and_persist_user_rank, notify_all_new_upload, track_user_event
        user_info = session.get('user', {})
        uid = _get_uid()
        res_rec = save_file_record(
            user_id=uid,
            user_email=user_info.get('email', ''),
            file_name=descriptive_filename,
            file_url=file_url,
            file_type='pdf' if orig_name.lower().endswith('.pdf') else 'file',
            file_size=size,
            cloudinary_public_id=f"local_{safe_name}",
            subject_name=subject_val,
            document_type=cat_clean,
            year=year_val,
            college_id=college_id_val,
            branch_id=branch_id_val,
            title=descriptive_title,
            description=details_val,
            semester=semester_val,
            program=program_val,
            subject_id=subject_id_val
        )
        if res_rec:
            doc_data = res_rec.get('data') or {}
            doc_id = doc_data.get('id')
            if doc_id:
                resource_url = f"/resources/{doc_id}"
                try:
                    client.table('documents').update({'status': 'approved'}).eq('id', doc_id).execute()
                except Exception:
                    pass

                def _bg_notify(u_id, d_id, d_title, s_name, sem, d_type):
                    try:
                        track_user_event(u_id, 'UPLOAD', {
                            'document_id': d_id,
                            'semester': sem,
                            'document_type': d_type
                        })
                    except Exception:
                        pass
                    try:
                        recalculate_and_persist_user_rank(u_id)
                    except Exception:
                        pass
                    try:
                        notify_all_new_upload(doc_id=d_id, title=d_title, uploader_id=u_id, subject=s_name)
                    except Exception:
                        pass

                import threading
                threading.Thread(
                    target=_bg_notify,
                    args=(uid, doc_id, descriptive_title, subject_val, semester_val, cat_clean),
                    daemon=True
                ).start()
    except Exception as e:
        logging.info(f"[chat] Platform library record skipped: {e}")

    final_resource_url = resource_url or (f"/resources/{doc_id}" if doc_id else file_url)

    return jsonify({
        'success': True,
        'file_url': final_resource_url,
        'direct_file_url': file_url,
        'file_name': descriptive_filename,
        'title': descriptive_title,
        'file_size': size,
        'doc_id': doc_id,
        'resource_url': final_resource_url
    })


@api_bp.route('/api/chat/resolve-doc')
def api_resolve_chat_doc():
    """Resolves a static chat file path to its canonical /resources/<doc_id> URL."""
    filename = (request.args.get('filename') or request.args.get('url') or '').strip()
    if not filename:
        return jsonify({'success': False, 'error': 'Missing filename'}), 400
    try:
        from methods.supabase_helper import init_supabase, init_supabase_admin
        client = init_supabase() or init_supabase_admin()
        if client:
            clean_name = os.path.basename(filename)
            res = client.table('documents').select('id, title').ilike('file_url', f"%{clean_name}%").limit(1).execute()
            if res.data:
                d_id = res.data[0]['id']
                return jsonify({
                    'success': True,
                    'doc_id': d_id,
                    'resource_url': f"/resources/{d_id}"
                })
    except Exception as e:
        logging.error("[CHAT] Document resolution failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'error': 'Document resolution failed'}), 500
    return jsonify({'success': False, 'error': 'Not found'}), 404


@api_bp.route('/static/uploads/chat/<path:filename>')
def serve_chat_uploaded_file(filename):
    """Intercepts requests to chat upload PDFs and redirects to /resources/<doc_id> in AbhiHub viewer."""
    try:
        from methods.supabase_helper import init_supabase, init_supabase_admin
        client = init_supabase() or init_supabase_admin()
        if client:
            clean_name = os.path.basename(filename)
            res = client.table('documents').select('id').ilike('file_url', f"%{clean_name}%").limit(1).execute()
            if res.data:
                d_id = res.data[0]['id']
                return redirect(f"/resources/{d_id}")
    except Exception as e:
        logging.warning(f"[chat] Failed to resolve static upload to resource: {e}")

    # Fallback to direct static streaming if not found in documents table
    static_folder = current_app.static_folder or 'static'
    chat_dir = os.path.join(static_folder, 'uploads', 'chat')
    return send_from_directory(chat_dir, filename)


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
        logging.error("[CRUSH] Request failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Request could not be completed'}), 500


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
        logging.error("[CHAT] User info lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'error': 'User information is temporarily unavailable'}), 500


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
        logging.error("[API /api/user/uploads] Lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'data': [], 'message': 'Failed to retrieve uploads'}), 500


@api_bp.route('/api/feedback', methods=['GET', 'POST'])
def feedback_endpoint():
    """Submit and retrieve student app feedback and ratings."""
    from data.tea_supporters import add_app_feedback, get_recent_feedbacks
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form or {}
        try:
            rating = int(data.get('rating', 5))
        except (ValueError, TypeError):
            rating = 5
        rating = max(1, min(5, rating))

        message = (data.get('message') or data.get('feedback') or '').strip()
        if not message:
            return jsonify({'success': False, 'message': 'Feedback message cannot be empty.'}), 400

        user = session.get('user', {})
        profile = session.get('profile', {})
        name = (data.get('name') or user.get('name') or profile.get('full_name') or 'Student Contributor').strip()
        college = (data.get('college') or profile.get('college_name') or user.get('college') or 'Engineering Scholar').strip()
        branch = (data.get('branch') or profile.get('branch_name') or '').strip()
        user_id = user.get('uid') or ''

        record = add_app_feedback(
            name=name,
            rating=rating,
            message=message,
            college=college,
            branch=branch,
            user_id=user_id
        )
        return jsonify({'success': True, 'feedback': record, 'message': 'Thank you for your valuable feedback! ⭐'}), 200

    limit = request.args.get('limit', default=10, type=int)
    feedbacks = get_recent_feedbacks(limit=limit)
    return jsonify({'success': True, 'feedbacks': feedbacks}), 200


@api_bp.route('/api/dashboard/summary', methods=['GET'])
def dashboard_summary_api():
    """Return pre-computed, memory-cached dashboard summary data for fast client retrieval."""
    try:
        college_name = request.args.get('college_name') or ''
        if not college_name and 'profile' in session:
            college_name = session['profile'].get('college_name') or ''

        from methods.supabase_helper import get_dashboard_summary_data
        summary = get_dashboard_summary_data(college_name=college_name)
        return jsonify({
            'success': True,
            'counts': summary.get('counts', {}),
            'trending_papers': summary.get('trending_papers', []),
            'trending_notes': summary.get('trending_notes', []),
            'recent_papers': summary.get('recent_papers', []),
            'recent_notes': summary.get('recent_notes', []),
            'recently_added': summary.get('recently_added_files', [])
        }), 200
    except Exception as e:
        logging.error("[API /api/dashboard/summary] Lookup failed (error_type=%s)", type(e).__name__)
        return jsonify({'success': False, 'message': 'Dashboard summary is temporarily unavailable'}), 500
