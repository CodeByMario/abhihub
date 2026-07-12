from flask import Flask, redirect, render_template, request, make_response, session, abort, jsonify, url_for, send_file, send_from_directory, flash, Response
import secrets
from functools import wraps
from push_api import init_push_api

import os
import io
import requests
import json
from datetime import timedelta, datetime
import logging
from dotenv import load_dotenv
from supabase import create_client, ClientOptions

# Load environment variables
load_dotenv()

# Initialize Supabase client for authentication
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="abhihub"))

# Initialize Firebase Admin SDK for storage only
import firebase_admin
from firebase_admin import credentials, storage

# Try to load Firebase credentials from environment variable first, fallback to file
firebase_service_account = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
if firebase_service_account:
    # Load from environment variable (recommended for production)
    cred_dict = json.loads(firebase_service_account)
    cred = credentials.Certificate(cred_dict)
else:
    # Fallback to file (for local development only)
    # IMPORTANT: This file should NOT be committed to Git!
    cred = credentials.Certificate("firebase-auth.json")

firebase_admin.initialize_app(cred, {
    'storageBucket': 'abhi-hub.appspot.com'
})

# --- Advanced Search helpers (add after imports) ---
import re
from rapidfuzz import fuzz as _fuzz

# Tunable weights (subject hits matter most; then file-name; then type/author)
FIELD_WEIGHTS = {
    "subject": 4.0,
    "file-name": 3.0,
    "type": 2.5,
    "author": 1.5,
    "exam": 1.25,
    "year": 1.0,
    "all": 0.75,  # generic JSON text match
}

# Lightweight synonym map (extend as needed)
SYNONYMS = {
    "pyq": ["paper", "papers"],
    "paper": ["pyq", "papers"],
    "papers": ["pyq", "paper"],
    "imp": ["important"],
    "important": ["imp"],
    "prac": ["practical", "lab"],
    "practical": ["prac", "lab"],
    "notes": ["note"],
    "dbms": ["database"],
}

_ALNUM = re.compile(r"[A-Za-z0-9]+")

def _normalize(text: str) -> str:
    return (text or "").lower()

def _tokenize(text: str) -> list[str]:
    return _ALNUM.findall(_normalize(text))

def _similar(a: str, b: str) -> float:
    """Fuzzy similarity (0..1) — rapidfuzz C++ backend (~10x faster than difflib)."""
    return _fuzz.ratio(a, b) / 100.0

def _parse_query(q: str) -> tuple[list[str], dict]:
    """
    Parse query into free-text tokens and field filters:
    Supports: type:, subject:, author:, year:, exam:
    Example: "type:notes subject:dbms year:2024"
    """
    if not q:
        return [], {}
    filters, tokens = {}, []
    for part in q.strip().split():
        if ":" in part:
            k, v = part.split(":", 1)
            k, v = k.lower().strip(), v.lower().strip()
            if k in {"type", "subject", "author", "year", "exam"} and v:
                filters[k] = v
            else:
                tokens.append(part.lower())
        else:
            tokens.append(part.lower())

    # synonym expansion
    expanded = set(tokens)
    for t in tokens:
        for s in SYNONYMS.get(t, []):
            expanded.add(s)
    return list(expanded), filters

def _field_text(item: dict, field: str) -> str:
    # map field names in your JSON
    return _normalize(str(item.get(field, "")))

def _token_match_score(text: str, tokens: list[str], weight: float) -> float:
    if not text or not tokens:
        return 0.0
    words = _tokenize(text)
    score = 0.0
    for t in tokens:
        # exact substring (phrase) boost
        if t in text:
            score += 2.0 * weight
            continue
        # token-level exact match
        if t in words:
            score += 1.5 * weight
            continue
        # fuzzy match against each word
        if any(_similar(t, w) >= 0.82 for w in words):
            score += 0.75 * weight
    return score

def _recent_year_boost(item: dict) -> float:
    """
    Favor recent items slightly. Uses 'year' or year-like in 'date'.
    """
    now_year = datetime.now().year
    year_str = item.get("year") or str(item.get("date", ""))[:4]
    try:
        y = int(year_str)
        # newer year -> larger boost, but capped
        return max(0.0, 1.0 - (max(0, now_year - y) * 0.08))
    except Exception:
        return 0.0

def _apply_filters(item: dict, filters: dict) -> bool:
    for k, v in filters.items():
        field_text = _field_text(item, k)
        # allow partial contains for filters (e.g., year:2024 matches "2024-05")
        if v not in field_text:
            return False
    return True

def _score_item(item: dict, tokens: list[str]) -> float:
    s = 0.0
    s += _token_match_score(_field_text(item, "subject"), tokens, FIELD_WEIGHTS["subject"])
    s += _token_match_score(_field_text(item, "file-name"), tokens, FIELD_WEIGHTS["file-name"])
    s += _token_match_score(_field_text(item, "type"), tokens, FIELD_WEIGHTS["type"])
    s += _token_match_score(_field_text(item, "author"), tokens, FIELD_WEIGHTS["author"])
    s += _token_match_score(_field_text(item, "exam"), tokens, FIELD_WEIGHTS["exam"])
    s += _token_match_score(_field_text(item, "year"), tokens, FIELD_WEIGHTS["year"])
    # generic fallback across the whole record
    s += _token_match_score(_normalize(json.dumps(item)), tokens, FIELD_WEIGHTS["all"])
    # small boost for verified
    if item.get("verified") is True:
        s += 0.35
    # recency boost
    s += _recent_year_boost(item)
    return s

from flask_compress import Compress

# Initialize Flask app
app = Flask(__name__)
Compress(app)

import mimetypes
mimetypes.add_type('application/javascript', '.mjs')

AI_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
    "nvidia/nemotron-3.5-content-safety:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
    "nvidia/nemotron-nano-12b-v2-vl:free"
]
ai_model_errors = {m: 0 for m in AI_MODELS}

def get_best_ai_model():
    return min(ai_model_errors, key=ai_model_errors.get)

# Security Configuration - Load from environment variables
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Configure session cookie settings
# SESSION_COOKIE_SECURE should be True in production (HTTPS), False in development (HTTP)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# CSRF Protection
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour expiry on CSRF tokens

from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
app.config['WTF_CSRF_CHECK_DEFAULT'] = False

@app.before_request
def check_csrf():
    if request.method not in ['GET', 'HEAD', 'OPTIONS', 'TRACE']:
        if request.path.startswith('/api/') or request.path.startswith('/auth') or request.path.startswith('/store-room/api/'):
            return
        csrf.protect()


# Redirect old Heroku domain to new custom domain (301 permanent redirect)
@app.before_request
def redirect_to_custom_domain():
    """Redirect traffic from old Heroku domain to new custom domain for SEO"""
    if request.host == "abhi-hub-06bba7f4101d.herokuapp.com":
        return redirect("https://app.abhihub.run.place" + request.full_path, code=301)

init_push_api(app)

# Initialize background scheduler for upload notifications
try:
    from scheduled_tasks import init_scheduler
    init_scheduler(app)
    logging.info("✅ Background task scheduler initialized")
except Exception as e:
    logging.error(f"⚠️ Failed to initialize background scheduler: {e}")
    logging.error("Upload notifications will not be sent automatically")


# File Upload Security Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg'
}

def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False  # no extension — rejected
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal and other attacks"""
    # Remove path components
    filename = os.path.basename(filename)
    # Remove any potentially dangerous characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename

def get_device_type(user_agent: str) -> str:
    """Detect device type from user agent string."""
    ua = (user_agent or '').lower()
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        return 'mobile'
    if 'tablet' in ua or 'ipad' in ua:
        return 'tablet'
    return 'desktop'

########################
#-------function-------#
from methods.storage import upload_file, list_files, download_file, delete_file


########################################
""" Authentication and Authorization """

# Decorator for routes that require authentication
def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if 'user' not in session:
            if request.path.startswith('/api/') or request.path.startswith('/store-room/api/'):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        
        else:
            return f(*args, **kwargs)
        
    return decorated_function

# Admin emails from environment variable (comma-separated)
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'abhijeetshende4053@gmail.com')
ADMIN_EMAILS = [e.strip().lower() for e in os.getenv('ADMIN_EMAILS', 'abhijeetshende4053@gmail.com,codebymario@gmail.com').split(',') if e.strip()]

# Decorator for admin-only routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated first
        user = session.get('user')
        if not user:
            return redirect(url_for('login'))
            
        # Check if user email matches admin email
        user_email = user.get('email', '').lower()
        if user_email not in ADMIN_EMAILS:
            abort(403)  # Forbidden
            
        return f(*args, **kwargs)
    return decorated_function

# ─── Paper Access Quota ──────────────────────────────────────────────────────
# Each upload grants QUOTA_PER_UPLOAD paper opens.
# Admins and unauthenticated users are not affected (unauthenticated is blocked
# by @auth_required anyway).
QUOTA_PER_UPLOAD = 19

def _get_quota():
    """Return the current quota dict from session, synced with backend, processing monthly resets."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return {'credits': 19, 'total_views': 0}

    # Fetch from Supabase
    res = supabase.table('profiles').select('paper_quota_remaining, last_quota_reset').eq('id', user_id).execute()
    db_quota = 19
    _default_month = datetime.utcnow().strftime('%Y-%m')
    last_reset = _default_month
    if res.data:
        db_quota = res.data[0].get('paper_quota_remaining')
        if db_quota is None:
            db_quota = 19
        last_reset = res.data[0].get('last_quota_reset') or _default_month

    current_month = datetime.utcnow().strftime('%Y-%m')
    if last_reset != current_month:
        db_quota = 19
        last_reset = current_month
        supabase.table('profiles').update({
            'paper_quota_remaining': db_quota,
            'last_quota_reset': last_reset
        }).eq('id', user_id).execute()

    q = {'credits': db_quota, 'total_views': session.get('paper_quota', {}).get('total_views', 0)}
    session['paper_quota'] = q
    session.modified = True
    return q

def _grant_upload_credits():
    """Award +1 reputation score to the user after a successful upload."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return
    
    # Fetch current rep
    res = supabase.table('profiles').select('reputation_score').eq('id', user_id).execute()
    if res.data:
        curr_rep = res.data[0].get('reputation_score') or 0
        supabase.table('profiles').update({'reputation_score': curr_rep + 1}).eq('id', user_id).execute()
        logging.info(f"[REWARD] Granted +1 reputation to {user.get('email')} -> {curr_rep + 1}")

def _consume_credit():
    """
    Deduct 1 credit for a paper open.
    Returns True if the open is allowed, False if quota is exhausted.
    Admins always pass.
    """
    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    user_id = user.get('uid')
    
    # Admins bypass the gate
    if user_email in ADMIN_EMAILS:
        return True
        
    q = _get_quota()
    if q.get('credits', 0) <= 0:
        return False
        
    new_credits = q['credits'] - 1
    q['credits'] = new_credits
    q['total_views'] = q.get('total_views', 0) + 1
    session['paper_quota'] = q
    session.modified = True
    
    # Update backend
    if user_id:
        supabase.table('profiles').update({'paper_quota_remaining': new_credits}).eq('id', user_id).execute()
        
    return True

@app.route('/api/quota', methods=['GET'])
@auth_required
def api_get_quota():
    """Return the current quota for the logged-in user."""
    q = _get_quota()
    return jsonify({
        'credits': q.get('credits', 0),
        'total_views': q.get('total_views', 0),
        'quota_per_upload': QUOTA_PER_UPLOAD
    }), 200
# ─────────────────────────────────────────────────────────────────────────────

from PIL import Image
import jwt

# Configure logging
logging.basicConfig(level=logging.DEBUG)


@app.route('/static/<path:filename>')
def static_files(filename):
    if filename.endswith(".mjs"):
        return send_from_directory("static", filename, mimetype="application/javascript")
    return send_from_directory("static", filename)


@app.route('/auth', methods=['POST'])
def authorize():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        logging.debug("Missing or incorrect Authorization header")
        return "Unauthorized", 401

    token = token[7:]  # Strip off 'Bearer ' to get the actual token
    logging.debug(f"Received token: {token}")

    try:
        # Get user from Supabase using the token
        user = supabase.auth.get_user(token)
        
        # Verify token by checking user existence
        if not user or not user.user:
            logging.debug("Token verification failed: No user found")
            return "Unauthorized", 401
            
        user_data = user.user
        
        # Store user info in session
        session['user'] = {
            'uid': user_data.id,
            'email': user_data.email,
            'name': user_data.user_metadata.get('name', user_data.email.split('@')[0]),
            'provider': user_data.app_metadata.get('provider', 'email'),
            'user_metadata': user_data.user_metadata
        }
        session.permanent = True  # Make the session permanent
        
        # Log the user session
        from data.profiles import UserSession
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        
        # Simple device type detection
        device_type = get_device_type(user_agent)
            
        session_result = UserSession.log_login(
            user_id=user_data.id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type
        )
        
        if session_result.get('success'):
            session['session_id'] = session_result.get('session_id')
        
        logging.debug(f"User authenticated: {user_data.email}")
        return jsonify({'success': True, 'message': 'Authenticated'}), 200
    
    except Exception as e:
        logging.debug(f"Token verification failed: {e}")
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

@app.route('/auth-callback')
def auth_callback():
    """Handle OAuth callback from Supabase"""
    try:
        # Get the session from the callback
        fragment = request.args.get('fragment', '')
        
        # The client should handle setting the session, but this endpoint
        # can be used to confirm the authentication
        if 'user' in session:
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('login'))
    except Exception as e:
        logging.debug(f"Auth callback failed: {e}")
        return redirect(url_for('login'))

@app.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    else:
        return render_template('p_login.html')

@app.route('/signup')
def signup():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    else:
        return render_template('p_signup.html')


@app.route('/reset-password')
def reset_password():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    else:
        return render_template('forgot_password.html')

@app.route('/reset-password-confirm')
def reset_password_confirm():
    """Handle password reset confirmation from Supabase email link"""
    try:
        # The password reset link from Supabase contains a token in the URL fragment
        # The client will handle the actual password update
        return render_template('reset_password_form.html')
    except Exception as e:
        logging.debug(f"Password reset confirm failed: {e}")
        return redirect(url_for('reset_password'))

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/ads.txt')
def ads_txt():
    return "google.com, pub-8274846157272362, DIRECT, f08c47fec0942fa0", 200, {'Content-Type': 'text/plain'}

@app.route('/<key>.txt')
def index_now_key(key):
    expected_key = os.getenv('INDEX_NOW_BING_API_KEY', '31d61c30c86d4fc7a7bb3584a4d225c9').strip()
    if key == expected_key:
        return expected_key, 200, {'Content-Type': 'text/plain'}
    return abort(404)

@app.route('/sitemap.xml')
def sitemap():
    from methods.supabase_helper import get_sitemap_urls
    import re
    
    # 1. Fetch raw data
    sitemap_res = get_sitemap_urls()
    data = sitemap_res.get('data', {}) if sitemap_res.get('success') else {}
    
    colleges = data.get('colleges', [])
    departments = data.get('departments', [])
    subjects = data.get('subjects', [])
    documents = data.get('documents', [])
    
    urls = []
    base_url = "https://app.abhihub.run.place"
    
    def slugify(text):
        return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
        
    # Standard static URLs
    for static_route in ['/', '/pyq', '/contact', '/features-tour', '/about']:
        priority = "1.00" if static_route == '/' else ("0.95" if static_route == '/pyq' else "0.80")
        urls.append({"loc": f"{base_url}{static_route}", "priority": priority})
        
    # Colleges + popular_name alias/brand URLs
    seen_brands = set()
    for c in colleges:
        c_slug = slugify(c.get('abbreviation') or c.get('name'))
        urls.append({"loc": f"{base_url}/college/{c_slug}", "lastmod": c.get('created_at'), "priority": "0.90"})
        # Add brand page URL (one per unique popular_name)
        popular = c.get('popular_name')
        if popular:
            p_slug = slugify(popular)
            if p_slug not in seen_brands:
                seen_brands.add(p_slug)
                urls.append({"loc": f"{base_url}/college/{p_slug}", "lastmod": c.get('created_at'), "priority": "0.92"})
        
        # Departments (Nested under colleges)
        for d in departments:
            d_slug = slugify(d.get('abbreviation') or d.get('name'))
            urls.append({"loc": f"{base_url}/college/{c_slug}/{d_slug}", "lastmod": d.get('created_at'), "priority": "0.85"})
            
    # Subjects (Unique)
    seen_subjects = set()
    for s in subjects:
        s_slug = slugify(s.get('name'))
        if s_slug and s_slug not in seen_subjects:
            seen_subjects.add(s_slug)
            urls.append({"loc": f"{base_url}/subject/{s_slug}", "lastmod": s.get('created_at'), "priority": "0.90"})
            
    # Resources
    for doc in documents:
        college_data = doc.get('college') or {}
        dept_data = doc.get('department') or {}
        subj_data = doc.get('subject') or {}
        
        c_slug = slugify(college_data.get('abbreviation') or college_data.get('name') or 'college')
        d_slug = slugify(dept_data.get('abbreviation') or dept_data.get('name') or 'dept')
        s_slug = slugify(subj_data.get('name') or 'subject')
        t_slug = slugify(doc.get('title') or 'file')
        
        canonical_slug = f"{c_slug}-{d_slug}-{s_slug}-{t_slug}-{doc.get('id')}"
        urls.append({"loc": f"{base_url}/resource/{canonical_slug}", "lastmod": doc.get('updated_at') or doc.get('created_at'), "priority": "0.75"})
        
    response = make_response(render_template('sitemap.xml', urls=urls))
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/help')
def help_center():
    return render_template('help.html')

@app.route('/logout')
def logout():
    # Log out the user session if it exists
    session_id = session.get('session_id')
    if session_id:
        from data.profiles import UserSession
        UserSession.log_logout(session_id)
        session.pop('session_id', None)
        
    session.pop('user', None)  # Remove the user from session
    response = make_response(redirect(url_for('login')))
    response.set_cookie('session', '', expires=0)  # Optionally clear the session cookie
    return response

@app.route('/api/profile-status')
@auth_required
def profile_status(user_data=None):
    """Lightweight endpoint for access-gates.js — returns profile completion state."""
    try:
        user_id = session.get('user', {}).get('uid')
        if not user_id:
            return jsonify({'profile_completed': False}), 200
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        res = client.table('profiles').select('college_id, department_id').eq('id', user_id).single().execute()
        completed = bool(res.data and res.data.get('college_id') and res.data.get('department_id'))
        return jsonify({'profile_completed': completed}), 200
    except Exception:
        return jsonify({'profile_completed': False}), 200


@app.route('/api/profile', methods=['GET'])
@auth_required
def get_profile(user_data=None):
    """Get current user profile"""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')

        # Get reputation stats
        students_helped = 0
        badges = []
        college_id = None
        department_id = None

        if user_id:
            from methods.supabase_helper import get_reputation_stats, init_supabase
            rep_stats = get_reputation_stats(user_id)
            if rep_stats.get('success'):
                students_helped = rep_stats.get('students_helped', 0)
                badges = rep_stats.get('badges', [])

            # Fetch college_id + department_id from profiles table
            try:
                client = init_supabase()
                pres = client.table('profiles') \
                    .select('college_id, department_id') \
                    .eq('id', user_id).single().execute()
                if pres.data:
                    college_id    = pres.data.get('college_id')
                    department_id = pres.data.get('department_id')
            except Exception:
                pass  # non-fatal — form remains editable
                
            timeline = []
            try:
                from methods.supabase_helper import get_contribution_timeline
                t_res = get_contribution_timeline(user_id)
                if t_res.get('success'):
                    timeline = t_res.get('timeline', [])
            except Exception:
                pass

        return jsonify({
            'success': True,
            'user': {
                'uid':          user_info.get('uid'),
                'email':        user_info.get('email'),
                'name':         user_info.get('name'),
                'provider':     user_info.get('provider'),
                'user_metadata': user_info.get('user_metadata', {}),
                'college_id':   college_id,
                'department_id': department_id,
                'students_helped': students_helped,
                'badges':       badges,
                'timeline':     timeline
            }
        }), 200
    except Exception as e:
        logging.error(f"Error getting profile: {e}")
        return jsonify({'success': False, 'message': 'Failed to get profile'}), 500


@app.route('/api/profile/update', methods=['POST'])
@auth_required
def api_update_profile(user_data=None):
    """Update profile's default college and department selection."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        data = request.get_json() or {}
        college_id = (data.get('college_id') or '').strip()
        department_id = (data.get('department_id') or '').strip()
        
        from methods.supabase_helper import init_supabase, validate_uuid
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Supabase client unavailable'}), 500

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
        logging.error(f"Error updating profile: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    return jsonify({
        'authenticated': 'user' in session,
        'user': session.get('user', {}) if 'user' in session else None
    }), 200


# ─── Security: Suspect Reporting ───────────────────────────────────────────
SUSPECTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'suspects.json')

@app.route('/api/report-suspect', methods=['POST'])
def report_suspect():
    """Log a suspect action (screenshot / screen-record attempt) to Supabase."""
    try:
        user = session.get('user', {})
        data = request.get_json(silent=True) or {}
        action = data.get('action', 'unauthorized_access')

        user_email = user.get('email', 'unknown')
        ip_address = request.remote_addr
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

        logging.info(f"[SUSPECT] {user_email} | {enum_action}")
        return jsonify(res), 200 if res.get('success') else 500

    except Exception as e:
        logging.error(f"[SUSPECT ERROR] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# ────────────────────────────────────────────────────────────────────────────


# File Records System API Endpoints
@app.route('/api/colleges', methods=['GET'])
def api_get_colleges():
    """Get all colleges for dropdown"""
    from methods.supabase_helper import get_all_colleges
    
    result = get_all_colleges()
    if result.get('success'):
        return jsonify({
            'success': True,
            'colleges': result.get('data', [])
        }), 200
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', 'Failed to fetch colleges'),
            'colleges': []
        }), 500


@app.route('/api/branches', methods=['GET'])
def api_get_branches():
    """Get all branches for dropdown"""
    from methods.supabase_helper import get_all_branches
    
    result = get_all_branches()
    if result.get('success'):
        return jsonify({
            'success': True,
            'branches': result.get('data', [])
        }), 200
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', 'Failed to fetch branches'),
            'branches': []
        }), 500


# T1 — Cascading dropdowns
@app.route('/api/departments', methods=['GET'])
def api_get_departments():
    """Return departments for a college (cascading dropdown, T1/T8)."""
    college_id = request.args.get('college_id', '').strip()
    if not college_id:
        return jsonify({'success': False, 'departments': [], 'message': 'college_id required'}), 400
    from methods.supabase_helper import get_departments_by_college
    result = get_departments_by_college(college_id)
    return jsonify({'success': result.get('success', False), 'departments': result.get('data', [])}), 200


@app.route('/api/semesters', methods=['GET'])
def api_get_semesters():
    """Return semesters for a department (unified API)."""
    department_id = request.args.get('department_id', '').strip()
    if not department_id:
        return jsonify({'success': False, 'semesters': [], 'message': 'department_id required'}), 400
    
    semesters = [{'id': str(i), 'name': f'Semester {i}'} for i in range(1, 9)]
    semesters.append({'id': '0', 'name': 'All Semesters'})
    return jsonify({'success': True, 'semesters': semesters}), 200


@app.route('/api/subjects', methods=['GET'])
def api_get_subjects():
    """Return subjects for a department, optionally filtered by semester."""
    department_id = request.args.get('department_id', '').strip()
    semester = request.args.get('semester', type=int)  # optional
    if not department_id:
        return jsonify({'success': False, 'subjects': [], 'message': 'department_id required'}), 400
    from methods.supabase_helper import get_subjects_by_department
    result = get_subjects_by_department(department_id, semester=semester)
    return jsonify({'success': result.get('success', False), 'subjects': result.get('data', [])}), 200


# Direct-insert: new subject
@app.route('/api/subjects', methods=['POST'])
@auth_required
def api_add_subject(user_data=None):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    code = (data.get('subject_code') or '').strip()
    dept_id = (data.get('department_id') or '').strip()
    semester = data.get('semester')
    
    if not name:
        return jsonify({'success': False, 'message': 'Subject name required'}), 400
    if not dept_id:
        return jsonify({'success': False, 'message': 'Department ID required'}), 400
        
    try:
        sem_val = int(semester) if semester not in (None, '', 0, '0') else None
    except (ValueError, TypeError):
        sem_val = None

    from methods.supabase_helper import init_supabase
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
        
        # Auto-generate and store acronym alias (e.g. Transform Numerical Method -> tnm)
        if subj and name:
            import re
            words = [w for w in re.split(r'\W+', name) if w and w.lower() not in ['and', 'of', 'the', '&']]
            acronym = "".join([w[0] for w in words]).lower()
            if len(acronym) > 1:
                try:
                    client.table('subject_aliases').insert({
                        'subject_id': subj['id'],
                        'alias': acronym,
                        'priority': 1
                    }).execute()
                except Exception as e:
                    print(f"Failed to save alias {acronym} for subject: {e}")
                    
        return jsonify({'success': True, 'subject': subj}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# Direct-insert: new college
@app.route('/api/colleges', methods=['POST'])
@auth_required
def api_add_college(user_data=None):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    abbr = (data.get('abbreviation') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'College name required'}), 400
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    try:
        res = client.table('colleges').insert({'name': name, 'abbreviation': abbr or None}).execute()
        college = res.data[0] if res.data else {}
        return jsonify({'success': True, 'college': college}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/check-duplicate', methods=['POST'])
@auth_required
def api_check_duplicate(user_data=None):
    data = request.get_json() or {}
    file_hash = data.get('file_hash')
    if not file_hash:
        return jsonify({'success': False, 'message': 'Missing file_hash'}), 400
        
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if not client: return jsonify({'success': False}), 500
    
    try:
        res = client.table('documents').select('id, title, status').eq('file_hash', file_hash).execute()
        if res.data and len(res.data) > 0:
            return jsonify({'success': True, 'is_duplicate': True, 'existing_file': res.data[0]}), 200
        return jsonify({'success': True, 'is_duplicate': False}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/ai/predict-metadata', methods=['POST'])
@auth_required
def api_predict_metadata(user_data=None):
    """
    Phase 5: AI Metadata Prediction.
    Takes a filename (e.g. 'tnm_cae2.pdf') and returns predicted Subject, Type, and Unit.
    """
    data = request.get_json() or {}
    filename = data.get('filename', '').lower()
    if not filename: return jsonify({'success': False})
    
    from methods.supabase_helper import init_supabase
    import re
    client = init_supabase()
    
    words = re.split(r'[\W_]+', filename.split('.')[0])
    prediction = {'subject_id': None, 'type': None, 'unit': None, 'year': '2025'}
    
    # 1. Predict Category / Unit
    for w in words:
        if w in ['notes', 'note']: prediction['type'] = 'notes'
        elif w in ['cae1', 'cae2', 'cae3', 'ese']:
            prediction['type'] = 'papers'
            prediction['unit'] = w.upper()
        elif w in ['practical', 'lab']: prediction['type'] = 'practical'
        elif w in ['syllabus']: prediction['type'] = 'syllabus'
        
        # Detect Year
        if re.match(r'^202[0-9]$', w): prediction['year'] = w
            
    # 2. Predict Subject via Aliases
    try:
        if client:
            alias_res = client.table('subject_aliases').select('subject_id, alias').execute()
            if alias_res.data:
                # Find longest matching alias in filename
                best_match = None
                for record in alias_res.data:
                    alias = record.get('alias', '').lower()
                    if alias in words:
                        best_match = record['subject_id']
                        break
                if best_match:
                    prediction['subject_id'] = best_match
    except Exception as e:
        print("Prediction error:", e)

    return jsonify({'success': True, 'prediction': prediction}), 200

# Direct-insert: new department + map to college
@app.route('/api/departments', methods=['POST'])
@auth_required
def api_add_department(user_data=None):
    data = request.get_json() or {}
    name      = (data.get('name') or '').strip()
    abbr      = (data.get('abbreviation') or '').strip()
    college_id = (data.get('college_id') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Department name required'}), 400
    if len(name) > 120 or len(abbr) > 20:
        return jsonify({'success': False, 'message': 'Name too long (max 120) or abbreviation too long (max 20)'}), 400
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    try:
        res = client.table('departments').insert({'name': name, 'abbreviation': abbr or None}).execute()
        dept = res.data[0] if res.data else {}
        dept_id = dept.get('id')
        # Map to college if provided
        if dept_id and college_id:
            client.table('college_departments').insert(
                {'college_id': college_id, 'department_id': dept_id}
            ).execute()
        return jsonify({'success': True, 'department': dept}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# T2 — Missing subject request
@app.route('/api/subject-request', methods=['POST'])
@auth_required
def api_create_subject_request():
    """Create a pending_subject_requests row (T2). Duplicate-safe via DB index."""
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    subject_name = (data.get('subject_name') or '').strip()
    if not subject_name:
        return jsonify({'success': False, 'message': 'subject_name required'}), 400
    if len(subject_name) > 200:
        return jsonify({'success': False, 'message': 'Subject name too long (max 200 chars)'}), 400
    from methods.supabase_helper import create_subject_request, track_user_event
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


@app.route('/api/waitlist/join', methods=['POST'])
def api_waitlist_join():
    """Public endpoint — join college waitlist. No auth required."""
    data = request.get_json(silent=True) or {}
    college_id = (data.get('college_id') or '').strip()
    email = (data.get('email') or '').strip()
    name = (data.get('name') or '').strip()

    if not college_id or not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Valid email and college required'}), 400

    from methods.supabase_helper import join_college_waitlist, validate_uuid
    if not validate_uuid(college_id):
        return jsonify({'success': False, 'message': 'Invalid college'}), 400

    result = join_college_waitlist(college_id, email, name)
    return jsonify(result), 200


# T4 — Onboarding status
@app.route('/api/onboarding/status', methods=['GET'])
@auth_required
def api_onboarding_status():
    user_id = session.get('user', {}).get('uid')
    from methods.supabase_helper import get_onboarding_status
    result = get_onboarding_status(user_id)
    return jsonify(result), 200 if result.get('success') else 500


@app.route('/api/onboarding/welcome-seen', methods=['POST'])
@auth_required
def api_onboarding_welcome_seen():
    user_id = session.get('user', {}).get('uid')
    from methods.supabase_helper import mark_welcome_seen
    result = mark_welcome_seen(user_id)
    return jsonify(result), 200 if result.get('success') else 500


# T7 — Analytics event tracking
@app.route('/api/events', methods=['POST'])
@auth_required
def api_track_event():
    """Tracks only UPLOAD, DOWNLOAD, SUBJECT_REQUEST. Returns 200 always."""
    user_id = session.get('user', {}).get('uid')
    data = request.get_json(silent=True) or {}
    event_type = (data.get('event_type') or '').upper().strip()
    # track_user_event already filters to 3 allowed types
    from methods.supabase_helper import track_user_event
    track_user_event(user_id, event_type, data.get('metadata', {}))
    return jsonify({'success': True}), 200


@app.route('/store-room/api/label', methods=['POST'])
@auth_required
def label_store_room_paper():
    """
    Label a paper from store room and save to file_records table.
    Expects JSON with: filename, url, college_name, subject_name, branch, year, exam_type, etc.
    """
    try:
        # Get user info from session
        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        user_email = user_info.get('email', '')
        
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Extract fields — IDs come directly from the cascade dropdowns (same as upload route)
        filename = data.get('filename', '')
        file_url = data.get('url', '')
        college_id = data.get('college_id', '').strip() or None
        branch_id = data.get('branch_id', '').strip() or None
        subject_id = data.get('subject_id', '').strip() or None
        subject_name = data.get('subject_name', '')
        subject_code = data.get('subject_code', '')
        year_raw = data.get('year', '')
        year = str(year_raw)
        try:
            year_int = int(year_raw)
            from datetime import datetime
            current_year = datetime.now().year
            if year_int < 1900 or year_int > current_year + 1:
                return jsonify({'success': False, 'message': 'Invalid year provided'}), 400
        except Exception:
            return jsonify({'success': False, 'message': 'Year must be a number'}), 400

        custom_title = data.get('title', '')
        document_category = data.get('document_category', 'papers')
        custom_description = data.get('description', '')
        exam_type = data.get('exam_type', '')
        semester_raw = data.get('semester')
        semester = int(semester_raw) if semester_raw and str(semester_raw).isdigit() and 1 <= int(semester_raw) <= 8 else None

        missing_fields = []
        if not filename: missing_fields.append('filename')
        if not file_url: missing_fields.append('url')
        if not subject_name: missing_fields.append('subject_name')
        if not year: missing_fields.append('year')

        if missing_fields:
            print(f"[DEBUG] Missing required fields: {missing_fields}")
            return jsonify({'success': False, 'message': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        if not subject_id:
            return jsonify({'success': False, 'message': 'Subject selection is required'}), 400

        # Validate the academic hierarchy
        from methods.supabase_helper import verify_hierarchy
        if not verify_hierarchy(college_id, branch_id, subject_id):
            return jsonify({'success': False, 'message': 'Invalid academic hierarchy (mismatched college/branch/subject)'}), 400

        allowed_categories = ['papers', 'notes', 'practical', 'syllabus', 'assisment', 'timetable']
        if document_category not in allowed_categories:
            document_category = 'papers'

        print(f"[STORE_ROOM_LABEL] User: {user_email}, File: {filename}")
        print(f"[STORE_ROOM_LABEL] College:{college_id} Branch:{branch_id} Subject:{subject_id} Sem:{semester}")

        # Extract cloudinary_public_id from URL
        cloudinary_public_id = filename
        if 'cloudinary.com' in file_url:
            parts = file_url.split('/')
            if 'upload' in parts:
                idx = parts.index('upload')
                if idx + 1 < len(parts):
                    p_id_ext = '/'.join(parts[idx + 1:])
                    cloudinary_public_id = p_id_ext.rsplit('.', 1)[0]

        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
        file_type = 'pdf' if file_ext == 'pdf' else 'image'

        from methods.supabase_helper import save_file_record

        result = save_file_record(
            user_id=user_id or user_email.split('@')[0],
            user_email=user_email,
            file_name=filename,
            file_url=file_url,
            file_type=file_type,
            file_size=0,
            cloudinary_public_id=cloudinary_public_id,
            subject_name=subject_name,
            document_type=document_category,
            year=year,
            college_id=college_id,
            branch_id=branch_id,
            subject_id=subject_id,
            subject_code=subject_code,
            semester=semester,
            title=custom_title or subject_name,
            description=custom_description,
            exam_type=exam_type
        )
        
        if result.get('success'):
            print(f"[STORE_ROOM_LABEL] SUCCESS: Saved to file_records")
            
            # 1. Update storage_assets status to LABELED
            from methods.supabase_helper import mark_storage_asset_labeled, log_label_audit
            storage_provider = 'cloudinary' if cloudinary_public_id else 'firebase'
            if cloudinary_public_id:
                mark_storage_asset_labeled(storage_provider, cloudinary_public_id)
            
            # 2. Log audit entry
            doc_id = result.get('data', {}).get('id')
            if doc_id:
                log_label_audit(
                    user_id=user_id or user_email.split('@')[0], 
                    document_id=doc_id, 
                    action='LABELED_FROM_QUEUE', 
                    details={'subject_id': subject_id, 'branch_id': branch_id, 'college_id': college_id}
                )
            
            # Invalidate the unlabeled files cache
            global _unlabeled_cache
            _unlabeled_cache['data'] = None
            
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data', {})
            }), 200
        else:
            print(f"[STORE_ROOM_LABEL] ERROR: {result.get('message')}")
            status_code = 409 if result.get('conflict') else 500
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save label')
            }), status_code
    
    except Exception as e:
        print(f"[STORE_ROOM_LABEL] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error labeling paper: {str(e)}'
        }),  500


@app.route('/api/interactions/like', methods=['POST'])
@auth_required
def api_toggle_like():
    data = request.json
    doc_id = data.get('document_id')
    user_email = session.get('user', {}).get('email')
    
    if not doc_id or not user_email:
        return jsonify({'success': False, 'message': 'Missing document or user info'}), 400
        
    from methods.supabase_helper import toggle_like
    res = toggle_like(user_email, doc_id)
    return jsonify(res), 200 if res.get('success') else 500

@app.route('/api/interactions/bookmark', methods=['POST'])
@auth_required
def api_toggle_bookmark():
    data = request.json
    doc_id = data.get('document_id')
    user_email = session.get('user', {}).get('email')
    
    if not doc_id or not user_email:
        return jsonify({'success': False, 'message': 'Missing document or user info'}), 400
        
    from methods.supabase_helper import toggle_bookmark
    res = toggle_bookmark(user_email, doc_id)
    return jsonify(res), 200 if res.get('success') else 500

@app.route('/api/interactions/comments/<doc_id>', methods=['GET', 'POST'])
def api_comments(doc_id):
    from methods.supabase_helper import add_comment, get_comments
    
    if request.method == 'GET':
        res = get_comments(doc_id)
        return jsonify(res), 200 if res.get('success') else 500
        
    if request.method == 'POST':
        # Must be logged in to comment
        if 'user' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
        data = request.json
        content = data.get('content')
        user_email = session.get('user', {}).get('email')
        
        if not content:
            return jsonify({'success': False, 'message': 'Comment content is required'}), 400
            
        res = add_comment(user_email, doc_id, content)
        return jsonify(res), 200 if res.get('success') else 500


@app.route('/api/document-view', methods=['POST'])
@auth_required
def api_log_document_view():
    """
    Log a document view to track file access history.
    Records every time a user accesses a document.
    """
    try:
        data = request.json or {}
        document_id = data.get('document_id') or data.get('doc_id')
        
        if not document_id:
            return jsonify({'success': False, 'message': 'Missing document_id'}), 400
        
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        
        # Extract device info from request
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        
        # Detect device type
        device_type = 'desktop'
        user_agent_lower = user_agent.lower()
        if 'mobile' in user_agent_lower or 'android' in user_agent_lower or 'iphone' in user_agent_lower:
            device_type = 'mobile'
        elif 'tablet' in user_agent_lower or 'ipad' in user_agent_lower:
            device_type = 'tablet'
        
        # Log the view using DocumentView class
        from data.interactions import DocumentView
        result = DocumentView.log_view(
            user_id=user_id,
            document_id=document_id,
            ip_address=ip_address,
            device_type=device_type
        )
        
        if result.get('success'):
            logging.info(f"[HISTORY] Document view logged - User: {user_id}, Doc: {document_id}")
            return jsonify({
                'success': True,
                'message': 'Document view recorded',
                'data': result.get('view', {})
            }), 200
        else:
            logging.error(f"[HISTORY] Failed to log view - {result.get('message')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to log document view')
            }), 500
            
    except Exception as e:
        logging.error(f"[HISTORY] Exception in document view logging: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error logging document view: {str(e)}'
        }), 500


@app.route('/api/recent-documents', methods=['GET'])
@auth_required
def api_get_recent_documents():
    """
    Get recently accessed documents for the logged-in user.
    Returns a list of documents the user has viewed recently.
    """
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        
        # Get optional limit parameter (default 20)
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 100)  # Cap at 100 to prevent excessive queries
        
        from data.interactions import DocumentView
        result = DocumentView.get_recent_for_user(user_id=user_id, limit=limit)
        
        if result.get('success'):
            logging.info(f"[HISTORY] Retrieved recent documents for user: {user_id} - Count: {result.get('count', 0)}")
            return jsonify({
                'success': True,
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 200
        else:
            logging.warning(f"[HISTORY] Failed to retrieve recent documents: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to retrieve recent documents'),
                'data': [],
                'count': 0
            }), 500
            
    except Exception as e:
        logging.error(f"[HISTORY] Exception retrieving recent documents: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error retrieving recent documents: {str(e)}',
            'data': [],
            'count': 0
        }), 500


@app.route('/api/file-access-history', methods=['GET'])
@auth_required
def api_get_file_access_history():
    """
    Get file access history for the logged-in user.
    Retrieves from file_access_history table for "Previously Accessed Files" UI.
    """
    try:
        user_info = session.get('user', {})
        user_email = user_info.get('email')
        
        if not user_email:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401
        
        # Get optional limit parameter (default 20)
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 100)  # Cap at 100
        
        from methods.supabase_helper import get_user_file_history
        result = get_user_file_history(user_email=user_email, limit=limit)
        
        if result.get('success'):
            data = result.get('data', [])
            logging.info(f"[FILE_HISTORY] Retrieved {len(data)} file access records for user: {user_email}")
            return jsonify({
                'success': True,
                'data': data,
                'count': len(data)
            }), 200
        else:
            logging.warning(f"[FILE_HISTORY] Failed to retrieve history: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to retrieve file access history'),
                'data': [],
                'count': 0
            }), 500
            
    except Exception as e:
        logging.error(f"[FILE_HISTORY] Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error retrieving file access history: {str(e)}',
            'data': [],
            'count': 0
        }), 500


@app.route('/api/my-notifications', methods=['GET'])
@auth_required
def api_get_my_notifications():
    """Return paginated notifications for the logged-in user."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    limit  = min(request.args.get('limit', 20, type=int), 50)
    offset = request.args.get('offset', 0, type=int)
    from methods.supabase_helper import get_user_notifications
    items = get_user_notifications(user_id, limit=limit, offset=offset)
    unread = sum(1 for n in items if not n.get('is_read'))
    return jsonify({'success': True, 'data': items, 'unread': unread}), 200


@app.route('/api/my-notifications/read', methods=['POST'])
@auth_required
def api_mark_notifications_read():
    """Mark all notifications as read for the logged-in user."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    from methods.supabase_helper import mark_notifications_read
    res = mark_notifications_read(user_id)
    return jsonify(res), 200 if res.get('success') else 500


@app.route('/api/files/all', methods=['GET'])
def get_all_files():
    """
    API endpoint to get all files exclusively from the abhihub.documents table.
    Returns unified JSON array of all files.
    """
    try:
        print("[API /api/files/all] Request received")
        
        from methods.supabase_helper import get_all_files_merged
        
        # Check if user is logged in to return personalized interactions
        user_info = session.get('user', {})
        current_user_id = user_info.get('uid')
        
        result = get_all_files_merged(include_file_records=True, current_user_id=current_user_id)

        
        if result.get('success'):
            print(f"[API /api/files/all] Returning {result.get('count', 0)} files")
            return jsonify({
                'success': True,
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 200
        else:
            print(f"[API /api/files/all] ERROR: {result.get('message', 'Unknown error')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to load files'),
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 500
    
    except Exception as e:
        print(f"[API /api/files/all] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500




@app.route('/upload', methods=['GET', 'POST'])
@auth_required
def upload():
    if request.method == 'POST':
        # Security: Check if file is present
        if 'upload_document' not in request.files:
            return jsonify(success=False, message="No file provided"), 400
        
        file = request.files['upload_document']
        
        # Security: Check if a file was selected
        if file.filename == '':
            return jsonify(success=False, message="No file selected"), 400
        
        # Security: Validate file extension
        if not allowed_file(file.filename):
            return jsonify(success=False, message="File type not allowed. Allowed types: PDF, DOC, DOCX, TXT, PPT, PPTX, XLS, XLSX, PNG, JPG, JPEG, GIF, WEBP, SVG, ZIP, RAR, 7Z"), 400
        
        # Security: Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > MAX_FILE_SIZE:
            return jsonify(success=False, message=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"), 400
        
        if file_size == 0:
            return jsonify(success=False, message="File is empty"), 400
        
        try:
            # Get user info and form data
            user_info = session['user']
            user_id = user_info.get('uid', '')
            user_email = user_info.get('email', '')
            user_name = user_info.get('name', '')
            
            subject = request.form.get('subject', '')
            year = request.form.get('Year', '')
            doc_type = request.form.get('type', 'Other')

            # Build metadata-aware filename: {type}_{subject}_{unit}_{year}.ext
            _ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
            _unit = request.form.get('unit', '')
            _doc = (request.form.get('document_type') or doc_type or 'file').strip()
            _parts = [p.strip() for p in [_doc, subject, _unit, year] if p.strip()]
            _base = '_'.join(_parts).replace(' ', '_')
            _base = re.sub(r'[^a-zA-Z0-9_-]', '', _base).lower() or 'upload'
            original_filename = f"{_base}.{_ext}"

            # Determine file type for categorization
            ext = _ext
            file_type_category = {
                'pdf': 'pdf',
                'doc': 'document', 'docx': 'document', 'txt': 'document',
                'ppt': 'presentation', 'pptx': 'presentation',
                'xls': 'spreadsheet', 'xlsx': 'spreadsheet',
                'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'webp': 'image',
                'zip': 'archive', 'rar': 'archive', '7z': 'archive'
            }.get(ext, 'file')
            
            # Determine Cloudinary folder based on document category
            folder_map = {
                'papers': 'pyq',
                'notes': 'notes',
                'practical': 'practicals',
                'syllabus': 'other',
                'assisment': 'other',
                'timetable': 'other'
            }
            cloudinary_folder = folder_map.get(doc_type, 'uploads')
            
            # Upload to Cloudinary with compression
            from methods.cloudinary_upload import upload_file_to_cloudinary
            
            upload_result = upload_file_to_cloudinary(
                file_data=file,
                filename=original_filename,
                user_id=user_id or user_name.replace(' ', '_'),
                folder=cloudinary_folder,
                compress=True
            )
            
            if not upload_result.get('success'):
                return jsonify(
                    success=False,
                    message=f"Upload failed: {upload_result.get('error', 'Unknown error')}"
                ), 500
            
            # Resolve metadata from form
            college_id = request.form.get('college_id', '').strip()
            branch_id = request.form.get('branch_id', '').strip()
            subject_id = request.form.get('subject_id', '').strip()
            semester_raw = request.form.get('semester', '').strip()
            semester = int(semester_raw) if semester_raw.isdigit() and 1 <= int(semester_raw) <= 8 else None
            document_type = request.form.get('document_type') or request.form.get('type') or 'Other'
            subject_name = subject.strip()
            unit = request.form.get('unit', '')
            practical_num = request.form.get('practical', '')
            practical_type = request.form.get('practical-type', '')

            # Guard: reject uploads with no subject selected
            if not subject_id or subject_id == '__other__':
                print(f"[UPLOAD REJECTED] Reason:Missing subject_id Uploader:{user_id} File:{original_filename}")
                return jsonify(
                    success=False,
                    message="Subject selection is required. Please select a subject from the dropdown."
                ), 400


            print(f"[UPLOAD] Uploader:{user_id} College:{college_id} Branch:{branch_id} Semester:{semester} Subject:{subject_name!r} SubjectID:{subject_id}")
            
            # Save to file_records table (Supabase abhihub.documents)
            from methods.supabase_helper import save_file_record
            
            file_record_result = save_file_record(
                user_id=user_id,
                user_email=user_email,
                file_name=original_filename,
                file_url=upload_result['secure_url'],
                file_type=file_type_category,
                file_size=file_size,
                cloudinary_public_id=upload_result['public_id'],
                subject_name=subject_name,
                document_type=document_type.lower(),
                year=year,
                college_id=college_id if college_id else None,
                branch_id=branch_id if branch_id else None,
                title=subject_name if subject_name else original_filename,
                subject_id=subject_id if subject_id else None,
                semester=semester
            )
            
            if not file_record_result.get('success'):
                print(f"[UPLOAD ERROR] Supabase record creation failed: {file_record_result.get('message')}")
                # We still return success if Cloudinary succeeded, but with a warning? 
                # Actually, the user wants a record in abhihub.documents, so this is a failure for the task.
                return jsonify(
                    success=False,
                    message=f"File uploaded to Cloudinary, but database record creation failed: {file_record_result.get('message')}"
                ), 500
            
            print(f"[UPLOAD SUCCESS] Document ID: {file_record_result.get('data', {}).get('id')}")

            # ── Track UPLOAD event (non-blocking) ───────────────────────
            try:
                from methods.supabase_helper import track_user_event
                track_user_event(user_id, 'UPLOAD', {
                    'document_id': file_record_result.get('data', {}).get('id'),
                    'subject_id': subject_id or None,
                    'semester': semester,
                    'document_type': document_type.lower()
                })
            except Exception:
                pass

            _grant_upload_credits()

            # ── IndexNow: fast-track indexing of new resource ────────────
            try:
                doc_id = file_record_result.get('data', {}).get('id', '')
                _trigger_indexnow([
                    f"https://{BASE_DOMAIN}/pyq",
                    f"https://{BASE_DOMAIN}/resource/{doc_id}" if doc_id else None,
                ])
            except Exception:
                pass

            # ── Recalculate & persist reputation score in DB ────────
            xp_gained = 0.0
            new_score = 0.0
            try:
                from methods.supabase_helper import recalculate_and_persist_user_rank, POINTS_MAP, DEFAULT_POINTS
                # XP for this specific upload (before persist)
                cat = document_type.lower()
                raw_pts = POINTS_MAP.get(cat, DEFAULT_POINTS)
                xp_gained = round(raw_pts * 0.5, 2)  # pending = half pts initially
                result_rank = recalculate_and_persist_user_rank(user_id)
                new_score = result_rank.get('score', 0.0)
            except Exception as rank_err:
                logging.warning(f"[UPLOAD] Rank recalc failed (non-critical): {rank_err}")

            return jsonify(
                success=True,
                message="File uploaded and recorded successfully! 🎉",
                data={
                    'url': upload_result['secure_url'],
                    'record_id': file_record_result.get('data', {}).get('id'),
                    'public_id': upload_result['public_id'],
                    'file_size': upload_result['bytes'],
                    'file_type': file_type_category,
                    'compressed': upload_result.get('resource_type') == 'image',
                    'credits_granted': QUOTA_PER_UPLOAD,
                    'credits_remaining': _get_quota().get('credits', 0),
                    'xp_gained': xp_gained,
                    'new_score': new_score
                }
            ), 200
            
        except Exception as e:
            print(f"[UPLOAD EXCEPTION] Upload error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify(
                success=False,
                message=f"Upload failed: {str(e)}"
            ), 500

    # GET request - show upload form
    # GET request - show upload form
    if 'user' in session:
        return render_template('p_upload.html')
    else:
        return render_template('p_login.html')

@app.route('/preview')
@auth_required
def preview():
    file_url = request.args.get('file_path')
    if not file_url:
        abort(404)
        
    record_id = request.args.get('record_id')
    if record_id:
        return redirect(url_for('resource_landing', slug=f"legacy-redirect-{record_id}"), code=301)


    # ── Quota gate ────────────────────────────────────────────────────────
    if not _consume_credit():
        q = _get_quota()
        return redirect(url_for('upload_gate',
                                next=request.url,
                                credits=q.get('credits', 0)))
    # ─────────────────────────────────────────────────────────────────────

    # Log file access
    if 'user' in session:
        user_email = session['user'].get('email', '')
        file_basename = os.path.basename(file_url)
        
        # Determine file type from extension
        file_ext = os.path.splitext(file_basename)[1].lower()
        file_type_map = {
            '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.gif': 'image', '.webp': 'image',
            '.pdf': 'pdf',
            '.doc': 'document', '.docx': 'document', '.txt': 'document',
            '.xls': 'spreadsheet', '.xlsx': 'spreadsheet',
            '.ppt': 'presentation', '.pptx': 'presentation'
        }
        file_type = file_type_map.get(file_ext, 'file')
        
        record_id = request.args.get('record_id')
        save_file_access(
            user_email=user_email,
            file_name=file_basename,
            file_type=file_type,
            file_path=file_url,
            file_url=file_url,
            record_id=record_id
        )
    
    if file_url.startswith('http'):
        return render_template('preview.html', file=file_url)
    
    try:
        bucket = storage.bucket()
        blob = bucket.blob(file_url)
        signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
        return render_template('preview.html', file=signed_url)
    except Exception as e:
        logging.error(f"Error generating signed URL for {file_url}: {e}")
        return render_template('preview.html', file=file_url)


@app.route('/pdf-viewer')
@auth_required
def pdf_viewer():
    file_url = request.args.get('file')
    if not file_url:
        abort(404, description="File URL is required")

    # ── Quota gate ────────────────────────────────────────────────────────
    if not _consume_credit():
        q = _get_quota()
        return redirect(url_for('upload_gate',
                                next=request.url,
                                credits=q.get('credits', 0)))
    # ─────────────────────────────────────────────────────────────────────

    # Log file access
    if 'user' in session:
        user_email = session['user'].get('email', '')
        file_basename = os.path.basename(file_url)
        record_id = request.args.get('record_id')
        save_file_access(
            user_email=user_email,
            file_name=file_basename,
            file_type='pdf',
            file_path=file_url,
            file_url=request.url,
            record_id=record_id
        )
    
    import urllib.parse
    safe_file_url = urllib.parse.unquote(file_url).replace('\\', '/')
    
    if '..' in safe_file_url or safe_file_url.startswith('/'):
        abort(400, description="Invalid file path")
        
    base_dir = os.path.abspath('data')
    local_path = os.path.abspath(os.path.join(base_dir, safe_file_url))
    
    if not local_path.startswith(base_dir + os.sep):
        abort(400, description="Invalid file path")
        
    if not os.path.exists(local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        bucket = storage.bucket()
        blob = bucket.blob(safe_file_url)
        blob.download_to_filename(local_path)
    
    return send_file(local_path, mimetype='application/pdf')


@app.route('/upload-gate')
@auth_required
def upload_gate():
    """Shown when a user has exhausted their paper-access credits."""
    q = _get_quota()
    next_url = request.args.get('next', url_for('dashboard'))
    return render_template('p_upload_gate.html',
                           credits=q.get('credits', 0),
                           quota_per_upload=QUOTA_PER_UPLOAD,
                           next_url=next_url)


##############################################
""" Private Routes (Require authorization) """
@app.route("/logo")
def logo():
    return send_file('static/images/logo.png', mimetype='image/png')


_ALLOWED_PROXY_HOSTS = {
    'storage.googleapis.com',
    'firebasestorage.googleapis.com',
    'res.cloudinary.com',
}

@app.route('/api/proxy-file')
@auth_required
def proxy_file():
    """Server-side proxy for Firebase/Cloudinary files to bypass browser CORS."""
    file_url = request.args.get('url', '').strip()
    if not file_url:
        abort(400)

    from urllib.parse import urlparse
    parsed = urlparse(file_url)
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS:
        abort(403)

    try:
        upstream = requests.get(
            file_url,
            timeout=30,
            verify=True,
            headers={'User-Agent': 'AbhiHub-Proxy/1.0'}
        )
        if not upstream.ok:
            logging.error(f"[PROXY] Upstream returned {upstream.status_code} for {file_url}")
            abort(upstream.status_code if upstream.status_code in (403, 404) else 502)

        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        resp = make_response(upstream.content)
        resp.headers['Content-Type'] = content_type
        resp.headers['Cache-Control'] = 'private, max-age=86400'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Disposition'] = 'inline'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except requests.exceptions.RequestException as e:
        logging.error(f"[PROXY] Request failed for {file_url}: {e}")
        abort(502)
    except Exception as e:
        logging.error(f"[PROXY] Unexpected error for {file_url}: {e}")
        abort(502)


@app.route('/api/view-doc/<doc_id>')
@app.route('/api/view-doc/<doc_id>/<filename>')
def view_doc(doc_id, filename=None):
    """Clean proxy endpoint for viewing docs — no URL encoding needed in PDF.js file= param."""
    from methods.supabase_helper import get_document_by_id_rich
    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        abort(404)
    document = doc_res.get('data', {})
    file_url = document.get('file_url', '')
    if not file_url:
        abort(404)

    # Resolve Firebase storage paths to signed URLs
    if not file_url.startswith('http'):
        try:
            bucket = storage.bucket()
            blob = bucket.blob(file_url)
            file_url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
        except Exception as e:
            logging.error(f"[VIEW-DOC] Signed URL error for {doc_id}: {e}")
            abort(500)

    from urllib.parse import urlparse
    parsed = urlparse(file_url)
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS:
        abort(403)

    try:
        upstream = requests.get(file_url, stream=True, timeout=30, verify=True, headers={'User-Agent': 'AbhiHub-Proxy/1.0'})
        if not upstream.ok:
            abort(upstream.status_code if upstream.status_code in (403, 404) else 502)
            
        content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        if document.get('file_type') == 'pdf' or '.pdf' in file_url.lower():
            content_type = 'application/pdf'
            
        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            except Exception as e:
                logging.error(f"[VIEW-DOC] Stream interrupted for {doc_id}: {e}")
                
        return Response(generate(),
                        status=upstream.status_code,
                        content_type=content_type,
                        headers={
                            'Cache-Control': 'private, max-age=86400',
                            'Content-Disposition': 'inline',
                            'Access-Control-Allow-Origin': '*'
                        })
    except Exception as e:
        logging.error(f"[VIEW-DOC] Proxy error for {doc_id}: {e}")
        abort(502)



def get_all_files_unified():
    """
    Get all active documents from Supabase `abhihub.documents`.
    """
    from methods.supabase_helper import get_all_files_merged
    
    # Check if we have an active session to pass the user_id for like/bookmark status
    current_user_id = None
    if getattr(request, 'endpoint', None) and 'user' in session:
        current_user_id = session['user'].get('uid')
        
    result = get_all_files_merged(current_user_id=current_user_id)
    files = result.get('data', [])
    
    logging.info(f"Fetched {len(files)} files directly from Supabase documents.")
    
    return files


@app.route('/dashboard')
def dashboard():
    # Get all files from both sources
    files = get_all_files_unified()
    
    # Extract SEO data
    all_subjects = list(set([f.get('subject', '') for f in files if f.get('subject', '').strip()]))
    top_subjects = sorted(all_subjects)[:8]
    paper_count = len([f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')])
    notes_count = len([f for f in files if f.get('type', '').lower() in ('notes', 'imp questions', 'imp_questions')])
    
    seo_keywords = "AbhiHub, GHRCE papers, engineering papers, " + ", ".join(top_subjects) + ", exam resources, study materials"
    
    # User-specific personalization data
    user_data = None
    file_history = []
    if 'user' in session:
        user_info = session['user']
        user_name = user_info.get('name', '')
        user_email = user_info.get('email', '')
        user_id = user_info.get('uid', '')
        
        # Get user's uploaded files (from both sources)
        user_files = [f for f in files if f.get('author', '') == user_name or f.get('author_email', '') == user_email]
        
        # Calculate user statistics
        user_uploads_count = len(user_files)
        user_notes_count = len([f for f in user_files if f.get('type', '').lower() == 'notes'])
        user_papers_count = len([f for f in user_files if f.get('type', '').lower() in ['pyq', 'papers']])
        user_practicals_count = len([f for f in user_files if f.get('type', '').lower() == 'practical'])
        
        # Get unique subjects user has contributed to
        user_subjects = list(set([f.get('subject', '') for f in user_files if f.get('subject', '').strip()]))
        
        # Get file access history
        history_result = get_user_file_history(user_email, limit=10)
        if history_result.get('success'):
            file_history = history_result.get('data', [])
            
        # Get user profile + college data
        from methods.supabase_helper import get_student_profile, calculate_user_ranks
        profile_res = get_student_profile(user_id)
        profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}
        student_res = profile_res  # same call reuse result
        student_data = profile_data  # already fetched above
        
        # Enforce profile completion
        if not student_data or not student_data.get('college_id'):
            flash("Welcome to AbhiHub! Please complete your profile to access all personalized features.", "warning")
            return redirect(url_for('account'))
            
        college_name = student_data.get('college_name') or ''
        
        # Calculate global rank and live score
        # Match by uploader_id (UUID) — avoids fragile full_name string comparison
        rank_list = calculate_user_ranks()
        global_rank = '-'
        computed_score = 0
        for i, entry in enumerate(rank_list):
            if entry.get('uploader_id') == user_id:
                global_rank = str(i + 1)
                computed_score = entry.get('points', 0)
                break
        
        # Get detailed reputation stats (students helped, badges)
        from methods.supabase_helper import get_reputation_stats
        rep_stats = get_reputation_stats(user_id)
        students_helped = rep_stats.get('students_helped', 0) if rep_stats.get('success') else 0
        badges = rep_stats.get('badges', []) if rep_stats.get('success') else []
        
        user_data = {
            'name': user_name,
            'email': user_info.get('email', ''),
            'uploads_count': user_uploads_count,
            'notes_count': user_notes_count,
            'papers_count': user_papers_count,
            'practicals_count': user_practicals_count,
            'subjects_contributed': len(user_subjects),
            'user_files': user_files[:10],  # Latest 10 user files for "Your Files" section
            'role': profile_data.get('role', 'student'),
            'reputation_score': max(computed_score, profile_data.get('reputation_score', 0)),
            'rank_title': profile_data.get('rank_title', 'Beginner'),
            'is_verified': profile_data.get('is_verified', False),
            'subscription_tier': profile_data.get('subscription_tier', 'free'),
            'global_rank': global_rank,
            'students_helped': students_helped,
            'badges': badges,
            'paper_quota_remaining': _get_quota().get('credits', 19),
            'college_name': college_name
        }
    
    promo_context = {
        'remaining_views': user_data.get('paper_quota_remaining', 19) if user_data else 19,
        'students_helped': user_data.get('students_helped', 0) if user_data else 0,
        'reputation_score': user_data.get('reputation_score', 0) if user_data else 0,
        'upload_goal_month': 'May'
    }

    # ── Personalized & trending papers ──────────────────────────────────────
    all_papers = [f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')]
    all_papers_by_views = sorted(all_papers, key=lambda f: f.get('view_count', 0), reverse=True)

    # Personalized: same college, sorted by views
    user_college = user_data.get('college_name', '') if user_data else ''
    if user_college:
        relevant_papers = [f for f in all_papers_by_views if f.get('college', '') == user_college][:8]
    else:
        relevant_papers = all_papers_by_views[:8]

    # Trending: top viewed overall (may overlap with relevant but that's fine)
    trending_papers = all_papers_by_views[:8]

    # Recent papers: newest first
    recent_papers = sorted(all_papers, key=lambda f: f.get('date', ''), reverse=True)[:8]

    return render_template('p_index.html',
                         data=files,
                         seo_keywords=seo_keywords,
                         top_subjects=top_subjects,
                         paper_count=paper_count,
                         notes_count=notes_count,
                         user_data=user_data,
                         file_history=file_history,
                         now=datetime.now(),
                         promo_context=promo_context,
                         relevant_papers=relevant_papers,
                         trending_papers=trending_papers,
                         recent_papers=recent_papers)


@app.route('/profile')
@auth_required
def profile():
    from methods.supabase_helper import get_student_profile, get_user_uploaded_files, get_papo_meter_data
    
    user_info = session['user']
    user_id = user_info.get('uid')
    user_email = user_info.get('email', '')
    
    # Get student profile info
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    
    # Get user's specifically uploaded files
    uploaded_files_result = get_user_uploaded_files(user_email, limit=50)
    uploaded_files = uploaded_files_result.get('data', []) if uploaded_files_result.get('success') else []
    
    # Map uploaded files to our unified format if necessary (though get_user_uploaded_files should return raw docs)
    # Actually, p_profile.html expects the unified format for the file cards
    from methods.supabase_helper import _doc_to_json, get_contribution_timeline
    
    # Phase 18: Contribution Timeline
    timeline_result = get_contribution_timeline(user_id)
    timeline = timeline_result.get('timeline', []) if timeline_result.get('success') else []
    formatted_uploads = [_doc_to_json(f, user_id) for f in uploaded_files]
    
    # Get Papo Meter data
    papo_meter = get_papo_meter_data(user_id)
    
    return render_template('p_profile.html', data={
        'user': user_info,
        'uploaded_files': formatted_uploads,
        'profile': profile,
        'papo_meter': papo_meter,
        'timeline': timeline
    })

@app.route('/dashboard/profile')
@auth_required
def p_profile_redirect():
    return redirect(url_for('profile'))

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    """Phase 19: Global Gamification Leaderboard"""
    from methods.supabase_helper import get_leaderboard_data
    
    # Optional filter by college if requested
    college_id = request.args.get('college_id')
    
    lb_result = get_leaderboard_data(college_id=college_id, limit=50)
    leaderboard_data = lb_result.get('data', []) if lb_result.get('success') else []
    
    # Get current user for personalization in the template
    user_info = session.get('user')
    
    return render_template('leaderboard.html', 
                           leaderboard=leaderboard_data,
                           current_user=user_info)


@app.route('/account', methods=['GET'])
@auth_required
def account():
    """Display account management page"""
    from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
    
    user_info = session['user']
    user_id = user_info.get('uid')
    
    # Get student profile
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    
    # Get colleges and branches for dropdowns
    colleges_result = get_all_colleges()
    branches_result = get_all_branches()
    
    colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
    branches = branches_result.get('data', []) if branches_result.get('success') else []
    
    return render_template('p_account.html', 
                         user=user_info, 
                         profile=profile,
                         colleges=colleges,
                         branches=branches)


@app.route('/account/update', methods=['POST'])
@auth_required
def update_account():
    """Handle account profile updates"""
    from methods.supabase_helper import create_or_update_student_profile
    
    user_info = session['user']
    user_id = user_info.get('uid')
    user_email = user_info.get('email')
    
    # Collect form data
    profile_data = {
        'student_name': request.form.get('student_name'),
        'student_email': user_email,  # Use auth email, don't allow override
        'student_moblie_number': request.form.get('student_moblie_number'),
        'college_id': request.form.get('college_id'),
        'branch_id': request.form.get('branch_id'),
        'user_role': request.form.get('user_role'),
        'year_of_joining': request.form.get('year_of_joining'),
        'pursuing_year': request.form.get('pursuing_year') if request.form.get('pursuing_year') else None,
        'registration_number': request.form.get('registration_number')
    }
    
    # Fetch static form data ONCE (colleges/branches are now cached)
    from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
    colleges = get_all_colleges().get('data', [])
    branches = get_all_branches().get('data', [])

    # Save profile
    result = create_or_update_student_profile(user_id, profile_data)

    # Re-fetch profile after save to reflect updated data
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    
    msg_type = 'success' if result.get('success') else 'error'
    msg = result.get('message') or ('Profile updated!' if result.get('success') else 'Failed to update profile')

    return render_template('p_account.html',
                         user=user_info,
                         profile=profile,
                         colleges=colleges,
                         branches=branches,
                         message=msg,
                         message_type=msg_type)


@app.route('/api/check-profile', methods=['GET'])
@auth_required
def api_check_profile():
    """API endpoint to check if profile is complete"""
    from methods.supabase_helper import check_profile_completed
    
    user_info = session.get('user', {})
    user_id = user_info.get('uid')
    
    is_complete = check_profile_completed(user_id)
    
    return jsonify({
        'success': True,
        'profile_completed': is_complete
    }), 200




@app.route('/settings')
@auth_required
def settings():
    return render_template('settings.html')


@app.route('/support')
@auth_required
def support():
    return render_template('p_support.html')

# Public pages
@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/')
def features():
    """Root route - handles OAuth callbacks and home page"""
    # If user is already authenticated, send to dashboard
    if 'user' in session:
        return redirect(url_for('dashboard'))
    
    # If there's an OAuth token in the hash (from Supabase redirect),
    # load the login page which will extract and process the token
    # Otherwise show the features page
    return render_template('p_landing.html')

@app.route('/features-tour')
def features_tour():
    return render_template('features.html')
@app.route('/pyq')
def pyq_landing():
    """SEO landing page targeting 'PYQ' and '[college] PYQ' searches"""
    from methods.supabase_helper import get_all_colleges, init_supabase
    import re
    colleges_res = get_all_colleges()
    colleges = colleges_res.get('data', [])
    # Attach doc count to each college
    try:
        client = init_supabase()
        if client:
            counts = client.table('documents').select('college_id', count='exact').execute()
            # Build per-college count via grouped query
            raw = client.table('documents').select('college_id').execute()
            count_map = {}
            for row in (raw.data or []):
                cid = row.get('college_id')
                if cid:
                    count_map[cid] = count_map.get(cid, 0) + 1
            for c in colleges:
                c['doc_count'] = count_map.get(c.get('id'), 0)
    except Exception:
        pass
    return render_template('pyq_landing.html', colleges=colleges)


@app.route('/college/<college_slug>')
def college_landing(college_slug):
    """Dynamic SEO-optimized college landing page.
    Priority: brand group page > individual college page > 404
    """
    import re
    from methods.supabase_helper import (
        get_colleges_by_brand, get_college_by_slug,
        get_college_stats, get_recent_college_files, get_all_branches
    )

    def slugify(text):
        return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')

    # 1. Check if slug matches a brand group (popular_name shared by 2+ colleges)
    brand_res = get_colleges_by_brand(college_slug)
    if brand_res.get('success'):
        brand_colleges = brand_res.get('data', [])
        brand_name = brand_res.get('brand_name', college_slug.capitalize())
        if len(brand_colleges) > 1:
            return render_template('brand.html', colleges=brand_colleges, brand_name=brand_name)
        elif len(brand_colleges) == 1:
            c = brand_colleges[0]
            canonical_slug = slugify(c.get('abbreviation') or c.get('name'))
            if college_slug != canonical_slug:
                return redirect(f"/college/{canonical_slug}", code=301)
            # Else fall through to normal college resolution

    # 2. Resolve as individual college slug
    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)

    college = college_res.get('data')
    college_id = college.get('id')

    # 3. If accessed via alias (not canonical abbr), 301-redirect
    canonical_slug = slugify(college.get('abbreviation') or college.get('name'))
    if college_slug != canonical_slug:
        return redirect(f"/college/{canonical_slug}", code=301)

    # 4. Check doc count — show coming soon if empty
    COMING_SOON_THRESHOLD = 1  
    stats = get_college_stats(college_id).get('data', {})
    total_docs = stats.get('total_documents', 0)

    if total_docs < COMING_SOON_THRESHOLD:
        from methods.supabase_helper import get_waitlist_count
        waitlist_count = get_waitlist_count(college_id)
        return render_template('college_coming_soon.html',
                               college=college,
                               waitlist_count=waitlist_count)

    # 5. Enough material — render full college page
    recent_files = get_recent_college_files(college_id, limit=6).get('data', [])
    departments = get_all_branches().get('data', [])

    return render_template('college.html',
                           college=college,
                           stats=stats,
                           recent_files=recent_files,
                           departments=departments)

@app.route('/college/<college_slug>/<department_slug>')
def department_landing(college_slug, department_slug):
    """Dynamic SEO-optimized department landing page"""
    from methods.supabase_helper import get_college_by_slug, get_department_by_slug, get_department_stats, get_recent_department_files
    
    # 1. Resolve college
    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)
    college = college_res.get('data')
    college_id = college.get('id')
    
    # 2. Resolve department
    dept_res = get_department_by_slug(department_slug)
    if not dept_res.get('success'):
        abort(404)
    department = dept_res.get('data')
    dept_id = department.get('id')
    
    # 3. Fetch stats and recent files
    stats = get_department_stats(college_id, dept_id).get('data', {})
    recent_files = get_recent_department_files(college_id, dept_id, limit=6).get('data', [])
    
    return render_template('department.html', 
                           college=college,
                           department=department,
                           stats=stats, 
                           recent_files=recent_files)

@app.route('/subject/<subject_slug>')
def subject_landing(subject_slug):
    """Dynamic SEO-optimized subject landing page (aggregated across colleges)"""
    from methods.supabase_helper import get_subjects_by_slug, get_subject_stats, get_recent_subject_files
    
    # 1. Resolve subject slug to a list of DB IDs
    subject_res = get_subjects_by_slug(subject_slug)
    if not subject_res.get('success'):
        abort(404)
        
    subject_data = subject_res.get('data')
    subject_ids = subject_data.get('ids')
    subject_name = subject_data.get('name')
    
    # 2. Fetch aggregate stats and recent files
    stats = get_subject_stats(subject_ids).get('data', {})
    recent_files = get_recent_subject_files(subject_ids, limit=12).get('data', [])
    
    return render_template('subject.html', 
                           subject_name=subject_name,
                           stats=stats, 
                           recent_files=recent_files)

@app.route('/resource/<path:slug>')
def resource_landing(slug):
    """Dynamic SEO-optimized resource landing page"""
    from methods.supabase_helper import get_document_by_id_rich
    import re
    
    # Extract UUID from the end of the slug
    # A standard UUID is 36 chars long (e.g. 847afaa6-cec4-48db-9016-2218c169bb87)
    # The slug format is something like ghrce-ai-dbms-pyq-<uuid>
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    match = re.search(uuid_pattern, slug.lower())
    if not match:
        abort(404)
        
    doc_id = match.group(0)
    
    # Fetch rich document data
    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        abort(404)
        
    document = doc_res.get('data')
    
    # Rewrite file URL through same-origin proxy to avoid CORS issues
    file_url = document.get('file_url', '')
    if file_url:
        ext = ''
        if document.get('file_type') == 'pdf':
            ext = '.pdf'
        elif '.' in file_url.split('/')[-1]:
            ext = '.' + file_url.split('/')[-1].split('.')[-1].split('?')[0]
        
        # Use clean path-based route for proxying
        document['file_url'] = f'/api/view-doc/{doc_id}/file{ext}'

    

    # Construct canonical slug
    college_data = document.get('college') or {}
    dept_data = document.get('department') or {}
    subj_data = document.get('subject') or {}
    
    college_abbr = (college_data.get('abbreviation') or college_data.get('name') or 'college').lower()
    dept_abbr = (dept_data.get('abbreviation') or dept_data.get('name') or 'dept').lower()
    subj_name = (subj_data.get('name') or 'subject').lower()
    title = (document.get('title') or 'file').lower()
    
    raw_slug = f"{college_abbr}-{dept_abbr}-{subj_name}-{title}"
    canonical_prefix = re.sub(r'[^a-z0-9]+', '-', raw_slug).strip('-')
    canonical_slug = f"{canonical_prefix}-{doc_id}"
    
    # 301 Redirect to canonical if mismatch
    if slug.lower() != canonical_slug:
        return redirect(url_for('resource_landing', slug=canonical_slug), code=301)
        
    document['is_liked'] = False
    document['is_bookmarked'] = False
    
    current_user_id = session.get('user', {}).get('uid')
    if current_user_id:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if client:
            like_check = client.table('document_votes').select('*').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
            document['is_liked'] = bool(like_check.data)
            
            bm_check = client.table('bookmarks').select('*').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
            document['is_bookmarked'] = bool(bm_check.data)
            
    # Track view
    from methods.supabase_helper import save_file_access
    user_email = session.get('user', {}).get('email')
    save_file_access(
        user_email=user_email,
        file_name=title,
        file_type=document.get('file_type'),
        file_path=document.get('file_url'),
        file_url=document.get('file_url'),
        record_id=doc_id
    )
        
    # Fetch Suggested Documents
    suggested_docs = []
    store_room_docs = []
    try:
        subj_id = document.get('subject_id')
        subj_name = document.get('subject', {}).get('name', '') if document.get('subject') else ''
        
        # 1. Exact subject_id
        if subj_id:
            sug_res = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').eq('subject_id', subj_id).neq('id', doc_id).limit(4).execute()
            suggested_docs = sug_res.data or []
            
        # 2. Exact same subject name (if not enough)
        similar_subj_ids = []
        if len(suggested_docs) < 4 and subj_name:
            name_res = client.table('subjects').select('id').ilike('name', subj_name.strip()).execute()
            similar_subj_ids = [s['id'] for s in name_res.data if s['id'] != subj_id] if name_res.data else []
            if similar_subj_ids:
                sug_res2 = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').in_('subject_id', similar_subj_ids).neq('id', doc_id).limit(4 - len(suggested_docs)).execute()
                if sug_res2.data:
                    suggested_docs.extend(sug_res2.data)
        
        # 3. Fuzzy matching subject name
        if len(suggested_docs) < 4 and subj_name:
            subj_kws = [w for w in subj_name.lower().split() if len(w) > 3]
            if subj_kws:
                or_cond = ','.join([f'name.ilike.*{kw}*' for kw in subj_kws[:2]])
                fuzzy_name_res = client.table('subjects').select('id').or_(or_cond).execute()
                fuzzy_subj_ids = [s['id'] for s in fuzzy_name_res.data if s['id'] != subj_id and s['id'] not in similar_subj_ids] if fuzzy_name_res.data else []
                if fuzzy_subj_ids:
                    sug_res3 = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').in_('subject_id', fuzzy_subj_ids).neq('id', doc_id).limit(4 - len(suggested_docs)).execute()
                    if sug_res3.data:
                        suggested_docs.extend(sug_res3.data)
            
        if title:
            # Simple keyword extraction (words > 3 chars) to find store room matches
            keywords = [w for w in title.split() if len(w) > 3]
            if keywords:
                or_cond = ",".join([f"filename.ilike.*{kw}*" for kw in keywords[:2]])
                sr_res = client.table('storage_assets').select('id, provider_public_id, filename').eq('status', 'PENDING').or_(or_cond).limit(4).execute()
                store_room_docs = sr_res.data or []
    except Exception as e:
        print(f"[Supabase] Error fetching suggestions: {e}")

    return render_template('resource.html', document=document, ai_models=AI_MODELS, best_model=get_best_ai_model(), suggested_docs=suggested_docs, store_room_docs=store_room_docs)

@app.route('/join')
def join_team():
    """Collaborator recruitment landing page"""
    return render_template('join.html')

@app.route('/team')
def team():
    """Team page"""
    return render_template('team.html')

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

import json
import os
CONTACT_FILE = os.path.join('data', 'contact_messages.json')

@app.route('/api/contact', methods=['POST'])
def api_contact():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'})
    
    msg = {
        'name': data.get('name'),
        'email': data.get('email'),
        'subject': data.get('subject'),
        'message': data.get('message'),
        'timestamp': datetime.now().isoformat()
    }
    
    os.makedirs('data', exist_ok=True)
    messages = []
    if os.path.exists(CONTACT_FILE):
        try:
            with open(CONTACT_FILE, 'r') as f:
                messages = json.load(f)
        except Exception:
            pass
    
    messages.insert(0, msg)
    
    try:
        with open(CONTACT_FILE, 'w') as f:
            json.dump(messages, f)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
        
    return jsonify({'success': True})

@app.route('/delete-account')
def delete_account():
    """Account deletion request page"""
    return render_template('delete_account.html')

@app.route('/register')
def register():
    """Register page (alias for signup)"""
    return redirect(url_for('signup'))

# Premium features
@app.route('/dashboard')
@auth_required
def premium():
    # Use unified documents from database
    from methods.supabase_helper import get_all_file_records_formatted
    user_info = session.get('user', {})
    current_user_id = user_info.get('uid')
    files = get_all_file_records_formatted(current_user_id=current_user_id)
    
    # Extract SEO data
    all_subjects = list(set([f.get('subject', '') for f in files if f.get('subject', '').strip()]))
    top_subjects = sorted(all_subjects)[:8]
    paper_count = len([f for f in files if f.get('type', '').lower() == 'pyq'])
    notes_count = len([f for f in files if f.get('type', '').lower() == 'notes'])
    
    seo_keywords = "AbhiHub, GHRCE papers, engineering papers, " + ", ".join(top_subjects) + ", exam resources, study materials"
    
    # User-specific personalization data
    user_data = None
    if 'user' in session:
        user_info = session['user']
        user_name = user_info.get('name', '')
        
        # Get user's uploaded files
        user_files = [f for f in files if f.get('author', '') == user_name]
        
        # Calculate user statistics
        user_uploads_count = len(user_files)
        user_notes_count = len([f for f in user_files if f.get('type', '').lower() == 'notes'])
        user_papers_count = len([f for f in user_files if f.get('type', '').lower() in ['pyq', 'papers']])
        user_practicals_count = len([f for f in user_files if f.get('type', '').lower() == 'practical'])
        
        # Get unique subjects user has contributed to
        user_subjects = list(set([f.get('subject', '') for f in user_files if f.get('subject', '').strip()]))
        
        user_data = {
            'name': user_name,
            'email': user_info.get('email', ''),
            'uploads_count': user_uploads_count,
            'notes_count': user_notes_count,
            'papers_count': user_papers_count,
            'practicals_count': user_practicals_count,
            'subjects_contributed': len(user_subjects),
            'user_files': user_files[:10],
            'role': 'student'
        }
        
    if user_data is None:
        user_data = {}
        
    user_data.setdefault('paper_quota_remaining', _get_quota().get('credits', 19))
    user_data.setdefault('students_helped', 0)
    user_data.setdefault('reputation_score', 0)
    user_data.setdefault('badges', [])
    user_data.setdefault('global_rank', '-')
    user_data.setdefault('rank_title', 'Beginner')
    user_data.setdefault('is_verified', False)
    
    promo_context = {
        'remaining_views': user_data.get('paper_quota_remaining', 19) if user_data else 19,
        'students_helped': user_data.get('students_helped', 0) if user_data else 0,
        'reputation_score': user_data.get('reputation_score', 0) if user_data else 0,
        'upload_goal_month': 'May'
    }

    return render_template('p_index.html', 
                         data=files,
                         seo_keywords=seo_keywords,
                         top_subjects=top_subjects,
                         paper_count=paper_count,
                         notes_count=notes_count,
                         user_data=user_data,
                         now=datetime.now(),
                         promo_context=promo_context)

def cors_headers(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        resp = f(*args, **kwargs)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp
    return decorated_function

def get_pdf_list():
    try:
        bucket = storage.bucket()
        blobs = bucket.list_blobs()
        return [blob.name for blob in blobs if blob.name.lower().endswith('.pdf')]
    except Exception as e:
        app.logger.error(f"Error getting PDF list: {e}")
        return []

def get_pdf_content(pdf_name):
    try:
        bucket = storage.bucket()
        blob = bucket.blob(pdf_name)
        return blob.download_as_bytes()
    except Exception as e:
        app.logger.error(f"Error getting PDF content: {e}")
        return None

@app.route('/abhijeetupdate')
@auth_required
def abhijeet_updae():
    data = list_files('Documents')
    
    # Sort data: New files first, then unverified, then verified
    def sort_key(item):
        verified = item.get('verified', False)
        has_last_updated = bool(item.get('last_updated'))
        
        # Priority order: new files (no last_updated), unverified, verified
        if not has_last_updated:
            return 0  # New files first
        elif not verified:
            return 1  # Unverified files second
        else:
            return 2  # Verified files last
    
    sorted_data = sorted(data, key=sort_key)
    return render_template('abhijeetupdate.html', data=sorted_data)

@app.route('/view_pdf')
@auth_required
def view_pdf():
    pdf_name = request.args.get('pdf_name', '')
    if not pdf_name:
        abort(400, description="PDF name is required")

    try:
        record_id = request.args.get('record_id')
        if record_id:
            # 301 redirect to the new SEO URL structure
            return redirect(url_for('resource_landing', slug=f"legacy-redirect-{record_id}"), code=301)


        # Log file access
        if 'user' in session:
            user_email = session['user'].get('email', '')
            file_basename = os.path.basename(pdf_name)
            save_file_access(
                user_email=user_email,
                file_name=file_basename,
                file_type='pdf',
                file_path=pdf_name,
                file_url=url_for('pdf_proxy', pdf_name=pdf_name, _external=True),
                record_id=record_id
            )
        
        # Use proxy URL to avoid CORS issues with Adobe PDF viewer
        if pdf_name.startswith('http'):
            proxy_url = pdf_name
        else:
            proxy_url = url_for('pdf_proxy', pdf_name=pdf_name, _external=True)

        # Fetch document metadata for info panel
        file_meta = {}
        if record_id:
            try:
                from methods.supabase_helper import init_supabase, _doc_to_json, validate_uuid
                if validate_uuid(record_id):
                    client = init_supabase()
                    if client:
                        res = client.table('documents') \
                            .select('*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name, subject_code)') \
                            .eq('id', record_id).limit(1).execute()
                        if res.data:
                            file_meta = _doc_to_json(res.data[0])
            except Exception as meta_err:
                logging.warning(f"Could not fetch metadata for {record_id}: {meta_err}")

        return render_template('p_pdf_reader.html',
                               pdf_name=pdf_name,
                               pdf_url=proxy_url,
                               file_meta=file_meta)

    except Exception as e:
        logging.error(f"Error generating proxy URL for {pdf_name}: {e}")
        abort(404, description="PDF not found or error generating access URL")


@app.route('/pdf-proxy/<path:pdf_name>')
@auth_required
def pdf_proxy(pdf_name):
    """Proxy PDF from Firebase Storage or redirect if absolute URL"""
    try:
        if pdf_name.startswith('http'):
            return redirect(pdf_name)

        # Get PDF from Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(pdf_name)
        
        import mimetypes
        
        # Download PDF content
        pdf_content = blob.download_as_bytes()
        file_size = len(pdf_content)
        
        # Determine content type dynamically based on file extension
        content_type, _ = mimetypes.guess_type(pdf_name)
        if not content_type:
            content_type = 'application/pdf'  # Fallback
            
        # Handle Range requests for progressive PDF loading
        range_header = request.headers.get('Range')
        
        if range_header:
            # Parse Range header (e.g., "bytes=0-1023")
            byte_range = range_header.replace('bytes=', '').split('-')
            start = int(byte_range[0]) if byte_range[0] else 0
            end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            
            # Ensure valid range
            end = min(end, file_size - 1)
            length = end - start + 1
            
            # Create partial content response (206)
            response = make_response(pdf_content[start:end+1])
            response.status_code = 206
            response.headers['Content-Type'] = content_type
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response.headers['Content-Length'] = str(length)
        else:
            # Full content response (200)
            response = make_response(pdf_content)
            response.headers['Content-Type'] = content_type
            response.headers['Content-Length'] = str(file_size)
        
        # Common headers for both full and partial responses
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type, Content-Range'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'
        response.headers['Content-Disposition'] = f'inline; filename="{os.path.basename(pdf_name)}"'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        return response
        
    except Exception as e:
        logging.error(f"Error proxying PDF {pdf_name}: {e}")
        abort(404, description="PDF not found")



# @app.route('/get_pdf/<path:pdf_name>')
# def get_pdf(pdf_name):
    
#     pdf_content = get_pdf_content(pdf_name)
#     if pdf_content is None:
#         abort(404, description="PDF not found")
    
#     # Save the PDF content to the data folder
#     local_path = os.path.join('static', pdf_name)
#     os.makedirs(os.path.dirname(local_path), exist_ok=True)
#     with open(local_path, 'wb') as f:
#         f.write(pdf_content)
    
#     return send_file(
#         io.BytesIO(pdf_content),
#         mimetype='application/pdf',
#         as_attachment=False,
#         download_name=pdf_name
#     )

INDEXNOW_KEY = '358beb4ba88947458503f632b81ca8cf'
BASE_DOMAIN = 'app.abhihub.run.place'

def _trigger_indexnow(urls: list):
    """Submit a list of URLs to IndexNow for fast Google indexing. Fire-and-forget."""
    try:
        import requests as _req
        payload = {
            "host": BASE_DOMAIN,
            "key": INDEXNOW_KEY,
            "keyLocation": f"https://{BASE_DOMAIN}/{INDEXNOW_KEY}.txt",
            "urlList": [u for u in urls if u.startswith('https://')]
        }
        _req.post("https://api.indexnow.org/indexnow", json=payload, timeout=5)
    except Exception:
        pass  # non-critical

@app.route('/indexnow', methods=['POST'])
def indexnow():
    urls = [
        f"https://{BASE_DOMAIN}/",
        f"https://{BASE_DOMAIN}/pyq",
        # Add more URLs as needed
    ]
    
    indexnow_url = "https://api.indexnow.org/indexnow"
    
    payload = {
        "host": BASE_DOMAIN,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{BASE_DOMAIN}/{INDEXNOW_KEY}.txt",
        "urlList": urls
    }
    
    response = requests.post(indexnow_url, json=payload)
    
    if response.status_code == 200:
        return jsonify({"message": "URLs submitted successfully"}), 200
    else:
        return jsonify({"message": "Failed to submit URLs"}), response.status_code



# -----------------Permium Section----------------- #
# _________________________________________________ #
# Load data once and cache it
# --- Premium data cache (keep your original globals) ---
data_cache = []
search_query = [None,]

def load_data(search_query=search_query[-1]):
    """
    Loads all files from unified sources (data.json + uploaded_files + file_records),
    then performs advanced search using fuzzy matching, field filters, and ranking.
    """
    global data_cache

    # load once - now using unified file list
    if not data_cache:
        try:
            # Use get_all_files_unified() to include all file sources
            data_cache = get_all_files_unified()
            logging.info(f"Loaded {len(data_cache)} files from unified sources for search cache")
        except Exception as e:
            logging.error(f"Error loading unified files for search: {e}")
            data_cache = []

    # no query -> return all (unchanged behavior)
    if not search_query:
        return data_cache

    # advanced parsing + scoring
    tokens, filters = _parse_query(search_query)
    scored = []
    for item in data_cache:
        if not _apply_filters(item, filters):
            continue
        score = _score_item(item, tokens)
        if score > 0.0:
            scored.append((score, item))

    # if nothing matched, fall back to original contains logic
    if not scored:
        q = _normalize(search_query)
        fallback = [
            item for item in data_cache
            if q in _normalize(json.dumps(item)) or q == _field_text(item, "subject")
        ]
        return fallback

    # sort by score desc, then by verified desc, then by file-name asc
    scored.sort(key=lambda x: (x[0], bool(x[1].get("verified")), x[1].get("file-name", "")), reverse=True)
    return [item for _, item in scored]

@app.route('/dashboard/suggest')
@auth_required
def suggest():
    q = request.args.get('q', '').strip().lower()
    if not q or not data_cache:
        return jsonify({"subjects": [], "types": [], "authors": []})

    subjects = {}
    types = {}
    authors = {}

    for item in data_cache:
        s = item.get("subject", "")
        t = item.get("type", "")
        a = item.get("author", "")
        if q in _normalize(s):
            subjects[s] = subjects.get(s, 0) + 1
        if q in _normalize(t):
            types[t] = types.get(t, 0) + 1
        if q in _normalize(a):
            authors[a] = authors.get(a, 0) + 1

    # top 5 of each
    top_subjects = [k for k, _ in sorted(subjects.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    top_types    = [k for k, _ in sorted(types.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    top_authors  = [k for k, _ in sorted(authors.items(), key=lambda kv: kv[1], reverse=True)[:5]]

    return jsonify({"subjects": top_subjects, "types": top_types, "authors": top_authors})

@app.route('/dashboard/')
@auth_required
def index():
    search_query = request.args.get('search_query')
    data = load_data(search_query)
    
    # Calculate counts for template
    paper_count = sum(1 for item in data if item.get('type') == 'Papers')
    notes_count = sum(1 for item in data if item.get('type') == 'Notes')
    
    return render_template('p_index.html', data=data, paper_count=paper_count, notes_count=notes_count, user_data=None)

@app.route('/dashboard/search', methods=['POST', 'GET'])
@auth_required
def search():
    search_query = request.form.get('search')
    if not search_query:
        return "Search query is missing", 400
    data = load_data(search_query)
    
    # Calculate counts for template
    paper_count = sum(1 for item in data if item.get('type') == 'Papers')
    notes_count = sum(1 for item in data if item.get('type') == 'Notes')
    
    return render_template('p_index.html', data=data, paper_count=paper_count, notes_count=notes_count, user_data=None)

@app.route('/dashboard/view', methods=['POST', 'GET'])
@auth_required
def view():
    """Handle file viewing - supports both form POST and file handler GET"""
    if request.method == 'GET':
        # File handler API integration - receives files opened from device
        # The files are already uploaded to temp storage by the browser
        return render_template('p_file_receiver.html')
    
    # Original POST handling for form submissions
    file_name = request.form.get('file_name')
    subject = request.form.get('subject')
    date = request.form.get('date')
    section = request.form.get('section')
    url = request.form.get('url')
    file_data = {
        'file_name': file_name,
        'subject': subject,
        'date': date,
        'section': section,
        'url':url
    }
    return render_template('p_view.html', file=file_data)

@app.route('/dashboard/share-receiver', methods=['POST', 'GET'])
@auth_required
def share_receiver():
    """
    Handle shared files from other apps via PWA share_target.
    Accepts multipart/form-data with files.
    """
    if request.method == 'GET':
        # User navigated directly to this page
        return render_template('p_share_receiver.html', files=[], message="Share files using your device's share menu")
    
    # Handle POST with shared files
    title = request.form.get('title', '')
    text = request.form.get('text', '')
    url = request.form.get('url', '')
    files = request.files.getlist('files')
    
    received_files = []
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf'}
    max_file_size = 50 * 1024 * 1024  # 50MB max
    
    for file in files:
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            
            # Validate file extension
            if ext not in allowed_extensions:
                continue
                
            # Validate file size (check content length)
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            file.seek(0)  # Seek back to start
            
            if size > max_file_size:
                continue
            
            # Save to temp folder for preview
            temp_path = os.path.join('temp_uploads', file.filename)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            file.save(temp_path)
            
            received_files.append({
                'name': file.filename,
                'type': file.content_type,
                'size': size,
                'path': temp_path
            })
    
    return render_template('p_share_receiver.html', 
                          files=received_files, 
                          title=title,
                          text=text,
                          url=url,
                          message=f"Received {len(received_files)} file(s)")

@app.route('/dashboard/about')
@auth_required
def premium_about():
    return render_template('p_about.html')

@app.route('/dashboard/profile/old')
@auth_required
def p_profile_deprecated():
    return redirect(url_for('profile'))
@app.route('/dashboard/setting')
def p_setting():
    return render_template('settings.html')


@app.route('/dashboard/static/search.json')
@auth_required
def search_in():
    search_file = os.path.join(app.root_path, 'premium/static/search.json')
    try:
        with open(search_file, 'r') as f:
            searches = json.load(f)
        return jsonify(searches), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

@app.route('/dashboard/save_search', methods=['POST'])
@auth_required
def save_search():
    search_data = request.get_json()
    search_query = search_data.get('searchquery')
    if search_query:
        search_file = os.path.join(app.root_path, 'premium/static/search.json')
        search_entry = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'searchquery': search_query
        }
        try:
            if os.path.exists(search_file):
                with open(search_file, 'r') as f:
                    searches = json.load(f)
            else:
                searches = []
            searches.append(search_entry)
            with open(search_file, 'w') as f:
                json.dump(searches, f, indent=4)
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            return jsonify({'status': 'error'}), 500
    return jsonify({'status': 'error'}), 400

@app.route('/sw.js')
def service_worker_root():
    """Serve service worker from root with proper headers"""
    response = make_response(send_file('static/sw.js', mimetype='application/javascript'))
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/manifest.json')
def premium_manifest():
    return send_file('static/manifest.json', mimetype='application/manifest+json')

@app.route('/api/widget-data')
def widget_data():
    """
    API endpoint for widget data updates.
    Returns latest documents for home screen widget display.
    """
    try:
        data_file = os.path.join(app.root_path, 'static/premium/data.json')
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        # Get latest 2 items for widget display
        latest = data[:2] if len(data) >= 2 else data
        
        widget_data = {
            "image1": "/static/images/android-chrome-192x192.png",
            "title1": latest[0].get('file-name', 'No documents') if latest else 'Welcome',
            "subtitle1": latest[0].get('subject', 'AbhiHub') if latest else 'Your study hub',
            "image2": "/static/images/android-chrome-192x192.png",
            "title2": latest[1].get('file-name', 'Start exploring') if len(latest) > 1 else 'Start exploring',
            "subtitle2": latest[1].get('subject', 'Notes & papers') if len(latest) > 1 else 'Notes & papers'
        }
        
        return jsonify(widget_data)
    except Exception as e:
        return jsonify({
            "image1": "/static/images/android-chrome-192x192.png",
            "title1": "AbhiHub",
            "subtitle1": "Your study hub",
            "image2": "/static/images/android-chrome-192x192.png",
            "title2": "Open app",
            "subtitle2": "Browse materials"
        })

@app.route('/favicon.ico')
def favicon():
    return send_file('static/images/favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/sw.js')
def service_worker():
    """Serve service worker from root scope so push notifications work."""
    response = make_response(send_file('static/sw.js', mimetype='application/javascript'))
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

########################
# Admin Control Panel #
########################

@app.route('/admin/controle')
@auth_required
@admin_required
def admin_control_panel():
    """Admin notification control panel - restricted to admin email only"""
    return render_template('admin_notification_panel.html')

@app.route('/api/admin/contact-messages', methods=['GET'])
@auth_required
@admin_required
def get_contact_messages():
    messages = []
    if os.path.exists(CONTACT_FILE):
        try:
            with open(CONTACT_FILE, 'r') as f:
                messages = json.load(f)
        except Exception:
            pass
    return jsonify({'success': True, 'messages': messages})

@app.route('/api/admin/subscribers', methods=['GET'])
@auth_required
@admin_required
def get_admin_subscribers():
    """Get all push notification subscribers with metadata"""
    try:
        from push_notifications import load_subscriptions
        subscriptions = load_subscriptions()  # keyed by UUID
        
        subscribers = []
        for user_id, data in subscriptions.items():
            subscribers.append({
                'user_id': user_id,
                'email': data.get('email', ''),  # populated by get_all_push_subscriptions
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

@app.route('/api/admin/send-notification', methods=['POST'])
@auth_required
@admin_required
def send_admin_notification():
    """Send push notification to selected users or all users"""
    try:
        from push_notifications import send_notification_to_all, send_notification_to_users
        from methods.supabase_helper import log_notification
        
        data = request.get_json() or {}
        
        # Input validation
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()
        
        if not title or not body:
            return jsonify({'success': False, 'error': 'Title and body are required'}), 400
        
        if len(title) > 100:
            return jsonify({'success': False, 'error': 'Title must be 100 characters or less'}), 400
        
        if len(body) > 500:
            return jsonify({'success': False, 'error': 'Body must be 500 characters or less'}), 400
        
        # Optional parameters
        url = data.get('url', '/premium').strip()
        icon = data.get('icon', '/static/images/android-chrome-192x192.png').strip()
        tag = data.get('tag', 'admin-notification').strip()
        user_ids = data.get('user_ids')  # None = all users, or list of user IDs
        
        # Send notification
        if user_ids and isinstance(user_ids, list) and len(user_ids) > 0:
            # Send to specific users (user_ids are UUIDs from subscriber list)
            result = send_notification_to_users(user_ids, title, body, url, icon, tag)
            # Log notification using email resolved from subscription metadata
            from push_notifications import load_subscriptions
            subs = load_subscriptions()
            for uid in user_ids:
                email = subs.get(uid, {}).get('email', uid)  # fall back to uid if no email
                log_notification(email, 'marketing', title, body, url)
        else:
            # Send to all users
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

@app.route('/api/admin/notification-history', methods=['GET'])
@auth_required
@admin_required
def get_admin_notification_history():
    """Get notification history (last 10 entries)"""
    try:
        from methods.supabase_helper import get_notification_history
        history = get_notification_history()
        return jsonify({'success': True, 'history': history})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@auth_required
@admin_required
def admin_get_users():
    """Get list of users for admin dashboard"""
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        res = client.table('profiles').select('id, full_name, email, created_at, role, reputation_score').order('created_at', desc=True).limit(500).execute()
        return jsonify({'success': True, 'users': res.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/users/<user_id>/stats', methods=['GET'])
@auth_required
@admin_required
def admin_get_user_stats(user_id):
    """Get detailed stats for a specific user"""
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        
        # Last visit (from user_sessions)
        session_res = client.table('user_sessions').select('login_time').eq('user_id', user_id).order('login_time', desc=True).limit(1).execute()
        last_visit = session_res.data[0].get('login_time') if session_res.data else "Never"
        
        # Files uploaded
        docs_res = client.table('documents').select('id, title, created_at, view_count, like_count').eq('uploader_id', user_id).order('created_at', desc=True).execute()
        uploaded_files = docs_res.data or []
        
        # Files viewed
        views_res = client.table('document_views').select('accessed_at, documents(title)').eq('user_id', user_id).order('accessed_at', desc=True).limit(20).execute()
        viewed_files = views_res.data or []
        
        return jsonify({
            'success': True,
            'stats': {
                'last_visit': last_visit,
                'uploaded_files': uploaded_files,
                'viewed_files': viewed_files
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/prepair/<subject>')
def exam_prep(subject="HE"):
    with open('static/premium/data.json', 'r') as f:
        data = json.load(f)
    prepair = [item for item in data if item.get('subject', '').lower().startswith(subject.lower())]
    return render_template('exam_page.html', data = prepair)

@app.route('/UHV')
def uhv_notes():
    return render_template('video_page.html')

@app.route('/rank')
def calculate_rank():
    try:
        from methods.supabase_helper import calculate_user_ranks
        rank_list = calculate_user_ranks()
        return jsonify({
            'status': 'success',
            'count': len(rank_list),
            'rank': rank_list
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/show_rank')
def show_rank():
    """Legacy route: redirect to new leaderboard"""
    return redirect(url_for('leaderboard'))

@app.route('/verify-file', methods=['POST'])
def verify_file():
    """
    Verify a file and ensure it's properly added to data.json
    """
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'success': False, 'message': 'File path is required'}), 400
        
        # Check if file exists in Firebase Storage
        from firebase_admin import storage
        bucket = storage.bucket()
        blob = bucket.blob(file_path)
        
        if not blob.exists():
            return jsonify({'success': False, 'message': 'File does not exist in storage'}), 404
        
        # Parse file metadata based on the file path structure
        info_temp = file_path.split('/')
        
        # Handle different file path styles
        if "AbhiHub" in info_temp:
            # Format: Documents/AbhiHub/Papers/subject_exam_year.filetype
            file_name_parts = info_temp[-1].split('_')
            file_info = {
                'file-name': file_name_parts[0] if file_name_parts else info_temp[-1].split('.')[0],
                'file-type': info_temp[-1].split('.')[1] if '.' in info_temp[-1] else '',
                'file-path': file_path,
                'author': 'AbhiHub',
                'type': info_temp[2] if len(info_temp) > 2 else '',
                'subject': file_name_parts[0] if len(file_name_parts) > 0 else '',
                'exam': file_name_parts[1] if len(file_name_parts) > 1 else '',
                'year': file_name_parts[2].split('.')[0] if len(file_name_parts) > 2 else '',
                'verified': True,
                'verification_date': datetime.now().isoformat()
            }
        else:
            # Format: Documents/AUTHOR/Type/year/subject/filename.filetype
            file_info = {
                'file-name': info_temp[-1].split('.')[0],
                'file-type': info_temp[-1].split('.')[1] if '.' in info_temp[-1] else '',
                'file-path': file_path,
                'author': info_temp[1] if len(info_temp) > 1 else '',
                'type': info_temp[2] if len(info_temp) > 2 else '',
                'year': info_temp[3] if len(info_temp) > 3 else '',
                'subject': info_temp[4] if len(info_temp) > 4 else '',
                'verified': True,
                'verification_date': datetime.now().isoformat()
            }
        
        # Insert into Supabase directly instead of data.json
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if client:
            res = client.table('documents').select('id').eq('file_url', file_path).execute()
            if not res.data:
                client.table('documents').insert({
                    'title': file_info.get('file-name', 'Unknown'),
                    'file_url': file_path,
                    'storage_provider': 'firebase',
                    'status': 'approved',
                    'document_category': file_info.get('type', 'Other'),
                    'file_type': file_info.get('file-type', 'pdf'),
                    'description': json.dumps({'author': file_info.get('author', ''), 'subject': file_info.get('subject', ''), 'year': file_info.get('year', '')})
                }).execute()
        
        return jsonify({
            'success': True, 
            'message': 'File verified and added to database successfully',
            'file_info': file_info
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get-file-url', methods=['POST'])
def get_file_url():
    """
    Generate a signed URL for a file without storing it
    """
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'success': False, 'message': 'File path is required'}), 400
        
        # Check if file exists in Firebase Storage
        from firebase_admin import storage
        bucket = storage.bucket()
        blob = bucket.blob(file_path)
        
        if not blob.exists():
            return jsonify({'success': False, 'message': 'File does not exist in storage'}), 404
        
        # Generate signed URL
        url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1))
        
        return jsonify({
            'success': True, 
            'url': url
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update-file-metadata', methods=['POST'])
@admin_required
def update_file_metadata():
    """
    Update file metadata in Supabase (Admin Only)
    """
    try:
        from methods.supabase_helper import update_document_metadata
        data = request.get_json()
        file_path = data.get('file-path')
        
        if not file_path:
            return jsonify({'success': False, 'message': 'File path is required'}), 400
            
        res = update_document_metadata(file_path, data)
        if res.get('success'):
            return jsonify({'success': True, 'message': 'File metadata updated successfully'}), 200
        else:
            return jsonify({'success': False, 'message': res.get('message', 'Update failed')}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================================================
# Store Room Routes - Cloudinary & Supabase Integration
# ================================================

from methods.cloudinary_helper import (
    fetch_all_files, search_files, sort_files, filter_files,
    get_unique_formats, get_unique_folders
)
from methods.supabase_helper import (
    save_labeled_paper, get_labeled_papers, check_if_labeled,
    save_file_access, get_user_file_history
)
import time

_unlabeled_cache = {
    'data': None,
    'labeled_count': 0,
    'timestamp': 0,
    'ttl': 60  # Cache for 60 seconds
}

def get_cached_unlabeled_files():
    now = time.time()
    if _unlabeled_cache['data'] is not None and (now - _unlabeled_cache['timestamp'] < _unlabeled_cache['ttl']):
        return _unlabeled_cache['data'], _unlabeled_cache['labeled_count']
        
    from methods.supabase_helper import get_pending_storage_assets
    pending_assets = get_pending_storage_assets()
    
    unlabeled_files = []
    for f in pending_assets:
        # Standardize format for frontend
        unlabeled_files.append({
            'storage_provider': f.get('provider'),
            'storage_id': f.get('provider_public_id'),
            'filename': f.get('filename'),
            'url': f.get('public_url'),
            'path': f.get('public_url'),
            'created_at': f.get('uploaded_at'),
            'size': 'Unknown',  # Consider adding size to storage_assets if needed
            'format': (f.get('mime') or 'unknown').split('/')[-1],
            'record_id': None,
            'verified': False,
            'verification_status': None,
            'like_count': 0,
            'bookmark_count': 0,
            'comment_count': 0,
            'view_count': 0
        })
        
    _unlabeled_cache['data'] = unlabeled_files
    _unlabeled_cache['labeled_count'] = 0 # Can be fetched separately if needed
    _unlabeled_cache['timestamp'] = now
    
    return unlabeled_files, 0

@app.route('/store-room')
@auth_required
def store_room():
    """
    Store Room page - displays unsorted papers from Cloudinary
    Only loads initial batch for performance
    """
    try:
        # Get cached files (O(1) instead of O(N+M) on every request)
        unlabeled_files, sorted_papers = get_cached_unlabeled_files()
        all_files = unlabeled_files

        # Calculate statistics
        total_papers = len(unlabeled_files) + sorted_papers
        remaining_papers = len(unlabeled_files)
        
        # Get unique formats and folders for filters
        formats = get_unique_formats(all_files)
        folders = get_unique_folders(all_files)
        
        # Only send first 20 files initially for better performance
        initial_batch_size = 20
        initial_files = all_files[:initial_batch_size]
        
        return render_template('p_store_room.html', 
                             files=initial_files,
                             total_papers=total_papers,
                             sorted_papers=sorted_papers,
                             remaining_papers=remaining_papers,
                             formats=formats,
                             folders=folders,
                             initial_batch_size=initial_batch_size)
    
    except Exception as e:
        logging.error(f"Error loading store room: {e}")
        return render_template('p_error.html', error=str(e)), 500

@app.route('/store-room/api/sync', methods=['POST'])
@auth_required
def store_room_api_sync():
    """
    Triggers a manual synchronization from physical storage to the storage_assets table.
    """
    try:
        from methods.storage_providers import CloudinaryProvider
        provider = CloudinaryProvider()
        result = provider.sync()
        
        if result.get('success'):
            # Invalidate cache
            global _unlabeled_cache
            _unlabeled_cache['data'] = None
            return jsonify({'success': True, 'message': f"Synced {result.get('upserted', 0)} assets successfully."}), 200
        else:
            return jsonify({'success': False, 'message': result.get('message', 'Sync failed')}), 500
    except Exception as e:
        logging.error(f"Error syncing storage: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/store-room/api/unlabeled', methods=['GET'])
@auth_required
def store_room_api_unlabeled():
    """
    API endpoint for fetching unlabeled queue files
    Query params: search, sort_by, order, format, folder, offset, limit
    """
    try:
        # Get query parameters
        search_query = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'created_at')
        order = request.args.get('order', 'desc')
        format_filter = request.args.get('format', '')
        folder_filter = request.args.get('folder', '')
        
        # Pagination parameters
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 20))
        
        # Get cached unlabeled files
        unlabeled_files, sorted_papers = get_cached_unlabeled_files()
        all_files = unlabeled_files
        
        # Apply search
        if search_query:
            all_files = search_files(all_files, search_query)
        
        # Apply filters
        if format_filter or folder_filter:
            all_files = filter_files(all_files, format_filter, folder_filter)
        
        # Apply sorting
        all_files = sort_files(all_files, sort_by, order)
        
        # Calculate statistics
        total_papers = len(unlabeled_files) + sorted_papers
        remaining_papers = len(unlabeled_files)
        
        # Apply pagination
        paginated_files = all_files[offset:offset + limit]
        has_more = (offset + limit) < total_papers
        
        return jsonify({
            'success': True,
            'files': paginated_files,
            'statistics': {
                'total': total_papers,
                'sorted': sorted_papers,
                'remaining': remaining_papers
            },
            'pagination': {
                'offset': offset,
                'limit': limit,
                'has_more': has_more,
                'total': total_papers
            }
        })
    
    except Exception as e:
        logging.error(f"Error fetching files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/store-room/api/rename-file', methods=['POST'])
@auth_required
def store_room_api_rename_file():
    """
    API endpoint for renaming files with metadata in filename
    """
    try:
        data = request.get_json()
        
        # Get original filename
        original_filename = data.get('filename', '')
        if not original_filename:
            return jsonify({
                'success': False,
                'message': 'Filename required'
            }), 400
        
        # Extract metadata from form
        college = data.get('college_name', '').strip()[:3].upper()  # First 3 chars
        subject_code = data.get('subject_code', '').strip() or data.get('subject_name', '')[:4].upper()
        exam_type = data.get('exam_type', 'unknown')[0].upper()  # S, W, V
        year = data.get('year', '')
        branch = data.get('branch', '').strip()[:3].upper()  # First 3 chars
        semesters = data.get('semesters', [])
        sem = '-'.join(str(s) for s in semesters) if semesters else 'UNK'
        
        # Get file extension
        file_ext = os.path.splitext(original_filename)[1]
        
        # Create new filename with metadata
        # Format: College_SubjectCode_ExamType_Year_Branch_Sem.ext
        new_filename = f"{college}_{subject_code}_{exam_type}_{year}_{branch}_{sem}{file_ext}"
        
        # Remove/replace invalid characters for filenames
        new_filename = "".join(c for c in new_filename if c.isalnum() or c in ('_', '.'))
        
        return jsonify({
            'success': True,
            'message': 'File renamed successfully',
            'new_filename': new_filename,
            'original_filename': original_filename
        })
    
    except Exception as e:
        logging.error(f"Error renaming file: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/store-room/api/verify', methods=['POST'])
@auth_required
def store_room_api_verify():
    """
    API endpoint for verifying a labeled paper
    """
    try:
        data = request.get_json()
        labeled_paper_id = data.get('paper_id')
        
        if not labeled_paper_id:
            return jsonify({
                'success': False,
                'message': 'Paper ID required'
            }), 400
        
        # Get user email
        user_email = session.get('user', {}).get('email', '')
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        # Save verification record to Supabase
        from methods.supabase_helper import add_paper_verification
        result = add_paper_verification(labeled_paper_id, user_email)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error verifying paper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/store-room/api/verification-queue', methods=['GET'])
@auth_required
def store_room_api_verification_queue():
    """
    API endpoint to get papers pending verification
    """
    try:
        from methods.supabase_helper import get_pending_verification_papers
        result = get_pending_verification_papers()
        
        return jsonify(result), 200 if result.get('success') else 400
    
    except Exception as e:
        logging.error(f"Error adding verification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/track-file-access', methods=['POST'])
@auth_required
def track_file_access_api():
    """
    API endpoint for tracking file access from client-side JavaScript
    """
    try:
        if 'user' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        data = request.get_json()
        user_email = session['user'].get('email', '')
        
        file_name = data.get('file_name', '')
        file_type = data.get('file_type', 'unknown')
        file_path = data.get('file_path', '')
        file_url = data.get('file_url', '')
        
        if not file_name:
            return jsonify({'success': False, 'message': 'File name required'}), 400
        
        # Log the file access
        result = save_file_access(
            user_email=user_email,
            file_name=file_name,
            file_type=file_type,
            file_path=file_path,
            file_url=file_url
        )
        
        return jsonify(result), 200 if result.get('success') else 500
    
    except Exception as e:
        logging.error(f"Error tracking file access: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# Flask CLI command for Heroku Scheduler (alternative to APScheduler)
@app.cli.command('send-upload-notifications')
def send_upload_notifications_command():
    """
    Flask CLI command to process upload notifications.
    Can be run manually or via Heroku Scheduler:
    $ heroku run flask send-upload-notifications -a abhi-hub
    Or schedule in Heroku Scheduler dashboard with: flask send-upload-notifications
    """
    from scheduled_tasks import run_upload_notifications_task
    
    print("=== Running upload notifications task ===")
    result = run_upload_notifications_task()
    print(f"Complete: {result['sent']} sent, {result['failed']} failed, {result['total']} total")
    return result



# Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('p_error.html', error="Page Not Found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('p_error.html', error="Internal Server Error"), 500

@app.route('/offline')
def offline_page():
    return render_template('offline.html')

# ─── AI Paper Q&A ───────────────────────────────────────────────────────────
@app.route('/api/ask-paper', methods=['POST'])
@auth_required
def api_ask_paper():
    """Ask a question about a paper image using NVIDIA Gemma vision model."""
    try:
        data = request.get_json(silent=True) or {}
        doc_id = (data.get('doc_id') or data.get('document_id') or '').strip()
        question = (data.get('question') or '').strip()
        selected_model = data.get('model')
        if not selected_model:
            selected_model = get_best_ai_model()
        logging.info(f"[AI] ask-paper using model: {selected_model}")

        if not doc_id or not question:
            return jsonify({'success': False, 'message': 'doc_id/document_id and question required'}), 400

        from methods.supabase_helper import get_document_by_id_rich
        doc_res = get_document_by_id_rich(doc_id)
        if not doc_res.get('success'):
            return jsonify({'success': False, 'message': 'Document not found'}), 404

        document = doc_res.get('data', {})
        file_url = document.get('file_url', '')

        # Resolve proxy URL to actual image URL for the AI
        if file_url.startswith('/api/view-doc/'):
            # Fetch the actual upstream URL
            from methods.supabase_helper import init_supabase
            client = init_supabase()
            raw = client.table('documents').select('file_url').eq('id', doc_id).single().execute()
            file_url = raw.data.get('file_url', '') if raw.data else ''

        if not file_url or not file_url.startswith('http'):
            return jsonify({'success': False, 'message': 'Image URL not available'}), 400

        # Encode image as base64
        import base64
        img_resp = requests.get(file_url, timeout=15)
        if not img_resp.ok:
            return jsonify({'success': False, 'message': 'Could not fetch image'}), 502

        b64_image = base64.b64encode(img_resp.content).decode('utf-8')
        content_type = img_resp.headers.get('Content-Type', 'image/jpeg').split(';')[0]

        openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()
        if not openrouter_key:
            return jsonify({'success': False, 'message': 'API key not configured'}), 500
            
        # Extract document info for the AI
        title = document.get('title', 'Unknown Title')
        doc_type = document.get('type', 'Unknown Type')
        subject_data = document.get('subject') or {}
        subject_name = subject_data.get('name', 'Unknown Subject')
        paper_info = f"Document Title: {title}\nSubject: {subject_name}\nType: {doc_type}"

        headers = {
            'Authorization': f'Bearer {openrouter_key}',
            'Content-Type': 'application/json'
        }
        
        system_prompt = (
            f"You are a helpful AI assistant for AbhiHub. Answer questions based only on the provided authentic source image.\n\n"
            f"Context Information about this paper:\n{paper_info}\n\n"
            f"Provide clear, accurate, and properly formatted answers."
        )

        payload = {
            'model': selected_model,
            'messages': [
                {
                    'role': 'system',
                    'content': system_prompt
                },
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': question},
                        {'type': 'image_url', 'image_url': {'url': f'data:{content_type};base64,{b64_image}'}}
                    ]
                }
            ],
            'max_tokens': 512,
            'temperature': 0.20,
            'top_p': 0.70,
            'stream': False
        }

        ai_resp = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers, json=payload, timeout=90
        )

        if not ai_resp.ok:
            ai_model_errors[selected_model] = ai_model_errors.get(selected_model, 0) + 1
            logging.error(f"[AI] OpenRouter API error: {ai_resp.status_code} {ai_resp.text}")
            return jsonify({'success': False, 'message': 'We are experiencing high demand. Please try after some time.'}), 502

        answer = ai_resp.json()['choices'][0]['message']['content']
        return jsonify({'success': True, 'answer': answer}), 200

    except Exception as e:
        logging.error(f"[AI] ask-paper error: {e}")
        return jsonify({'success': False, 'message': 'We are experiencing high demand. Please try after some time.'}), 500

@app.route('/api/extract-ocr', methods=['POST'])
@auth_required
def api_extract_ocr():
    """Extract OCR text from a paper image using the vision model."""
    try:
        data = request.get_json(silent=True) or {}
        doc_id = (data.get('doc_id') or '').strip()
        selected_model = data.get('model')
        if not selected_model:
            selected_model = get_best_ai_model()
        logging.info(f"[AI] extract-ocr using model: {selected_model}")
        if not doc_id:
            return jsonify({'success': False, 'message': 'doc_id required'}), 400

        from methods.supabase_helper import init_supabase
        client = init_supabase()
        raw = client.table('documents').select('file_url').eq('id', doc_id).single().execute()
        file_url = raw.data.get('file_url', '') if raw.data else ''

        if not file_url or not file_url.startswith('http'):
            return jsonify({'success': False, 'message': 'Image URL not available'}), 400

        import base64
        img_resp = requests.get(file_url, timeout=15)
        if not img_resp.ok:
            return jsonify({'success': False, 'message': 'Could not fetch image'}), 502

        b64_image = base64.b64encode(img_resp.content).decode('utf-8')
        content_type = img_resp.headers.get('Content-Type', 'image/jpeg').split(';')[0]

        openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()
        if not openrouter_key:
            return jsonify({'success': False, 'message': 'API key not configured'}), 500

        headers = {
            'Authorization': f'Bearer {openrouter_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': selected_model,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'Extract all text, math equations, and tables from this image perfectly. Return ONLY the raw transcript without any conversational filler or formatting outside of what is in the image.'},
                        {'type': 'image_url', 'image_url': {'url': f'data:{content_type};base64,{b64_image}'}}
                    ]
                }
            ],
            'max_tokens': 1024,
            'temperature': 0.10,
            'top_p': 0.70,
            'stream': False
        }

        ai_resp = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=payload, timeout=90)
        if not ai_resp.ok:
            ai_model_errors[selected_model] = ai_model_errors.get(selected_model, 0) + 1
            return jsonify({'success': False, 'message': 'We are experiencing high demand. Please try after some time.'}), 502

        ocr_text = ai_resp.json()['choices'][0]['message']['content']
        return jsonify({'success': True, 'ocr_text': ocr_text}), 200

    except Exception as e:
        logging.error(f"[AI] extract-ocr error: {e}")
        return jsonify({'success': False, 'message': 'We are experiencing high demand. Please try after some time.'}), 500
# ─────────────────────────────────────────────────────────────────────────────


# ─── Social Interactions: Like, Bookmark, Comment ─────────────────────────
@app.route('/api/like', methods=['POST'])
@auth_required
def toggle_like_route():
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        document_id = data.get('document_id')
        
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import toggle_like
        user_email = user.get('email')
        res = toggle_like(user_email, document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bookmark', methods=['POST'])
@auth_required
def toggle_bookmark_route():
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        document_id = data.get('document_id')
        
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import toggle_bookmark
        user_email = user.get('email')
        res = toggle_bookmark(user_email, document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/interactions/comments/<document_id>', methods=['POST'])
@auth_required
def add_comment_route(document_id):
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        content = data.get('content')
        
        if not document_id or not content:
            return jsonify({'success': False, 'message': 'document_id and content are required'}), 400
            
        from methods.supabase_helper import add_comment
        user_email = user.get('email')
        res = add_comment(user_email, document_id, content)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/interactions/comments/<document_id>', methods=['GET'])
def get_comments_route(document_id):
    try:
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import get_comments
        res = get_comments(document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
# ────────────────────────────────────────────────────────────────────────────


# ─── MemoryWall (know_me) ─────────────────────────────────────────────────────

@app.route('/memorywall')
@auth_required
def memorywall_dashboard():
    """Creator dashboard — shows wall status, share link, stats, and recent activity."""
    from methods.know_me import get_wall_by_user, get_recent_responses, get_dashboard_metrics
    user = session.get('user', {})
    user_id = user.get('uid')
    wall_result = get_wall_by_user(user_id)
    wall = wall_result.get('data') if wall_result.get('success') else None

    dashboard_data = None
    recent_responses = []
    if wall:
        dashboard_data = get_dashboard_metrics(wall['id'])
        recent_responses = get_recent_responses(wall['id'], limit=5)

    return render_template(
        'know_me/dashboard.html',
        wall=wall,
        user=user,
        dashboard_data=dashboard_data,
        recent_responses=recent_responses
    )



@app.route('/memorywall/create', methods=['GET', 'POST'])
@auth_required
def memorywall_create():
    """Create a new MemoryWall."""
    from methods.know_me import get_wall_by_user, create_wall
    user = session.get('user', {})
    user_id = user.get('uid')

    # Already has a wall — redirect to dashboard
    existing = get_wall_by_user(user_id)
    if existing.get('success') and existing.get('data'):
        return redirect(url_for('memorywall_dashboard'))

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:80]
        college = (request.form.get('college') or '').strip()[:100]
        branch = (request.form.get('branch') or '').strip()[:100]
        try:
            grad_year = int(request.form.get('graduation_year') or 0) or None
        except ValueError:
            grad_year = None

        if not title:
            return render_template('know_me/create.html', error='Please enter a title.', user=user)

        result = create_wall(user_id, title, college, branch, grad_year)
        if result.get('success'):
            logging.info(f"[MemoryWall] Wall created for {user.get('email')}")
            return redirect(url_for('memorywall_dashboard'))
        elif result.get('message') == 'already_exists':
            return redirect(url_for('memorywall_dashboard'))
        else:
            return render_template('know_me/create.html',
                                   error='Something went wrong. Please try again.', user=user)

    return render_template('know_me/create.html', user=user)


@app.route('/m/<slug>')
def memorywall_public(slug):
    """Public submission page — no auth required."""
    from methods.know_me import get_wall_by_slug
    result = get_wall_by_slug(slug)
    if not result.get('success') or not result.get('data'):
        abort(404)
    wall = result['data']
    if wall.get('status') == 'closed':
        return render_template('know_me/closed.html', wall=wall), 410
    return render_template('know_me/public_wall.html', wall=wall)


@app.route('/memorywall/reveal/<wall_id>')
@auth_required
def memorywall_reveal(wall_id):
    """Reveal page — authenticated wall owner only."""
    from methods.know_me import reveal_wall, get_wall_by_user, get_dashboard_metrics, generate_personality_summary
    from methods.know_me_generator import generate_wordcloud, generate_signature_wall, upload_to_firebase

    user = session.get('user', {})
    user_id = user.get('uid')

    # Verify ownership
    owner_check = get_wall_by_user(user_id)
    if not owner_check.get('success') or not owner_check.get('data'):
        abort(403)
    if owner_check['data']['id'] != wall_id:
        abort(403)

    data = reveal_wall(wall_id)
    responses = data.get('responses', [])
    word_list = data.get('word_list', [])
    words = data.get('words', [])

    # Track reveal view
    try:
        from methods.know_me import increment_view_count
        increment_view_count(wall_id)
    except Exception:
        pass

    # Dashboard metrics (top_traits, most_loved_trait)
    metrics = get_dashboard_metrics(wall_id)

    # Template-based AI personality summary
    personality_summary = generate_personality_summary(metrics)

    # Generate assets
    wc_path = generate_wordcloud(word_list, wall_id)
    sig_urls = [
        r['signature'][0]['signature_url']
        for r in responses
        if r.get('signature') and r['signature'][0].get('signature_url')
    ]
    sw_path = generate_signature_wall(sig_urls, wall_id)

    # Upload to Firebase (non-blocking best-effort)
    wc_firebase = ""
    sw_firebase = ""
    try:
        if wc_path:
            wc_firebase = upload_to_firebase(wc_path, f"know_me/{wall_id}/wordcloud.png")
        if sw_path:
            sw_firebase = upload_to_firebase(sw_path, f"know_me/{wall_id}/signature_wall.png")
    except Exception as e:
        logging.warning(f"[MemoryWall] Firebase upload skipped: {e}")

    wall = owner_check['data']
    return render_template('know_me/reveal.html',
                           wall=wall, user=user,
                           responses=responses,
                           words=words,
                           wc_path=wc_path,
                           sw_path=sw_path,
                           wc_firebase=wc_firebase,
                           sw_firebase=sw_firebase,
                           metrics=metrics,
                           personality_summary=personality_summary)


# ── MemoryWall API Endpoints ──────────────────────────────────────────────────

@app.route('/api/memorywall/submit', methods=['POST'])
def api_memorywall_submit():
    """Public response submission — no auth, rate-limited by IP hash."""
    from methods.know_me import submit_response, get_wall_by_slug

    # Honeypot check
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
    anonymous = False
    signature_url = (data.get('signature_url') or '').strip() or None

    if not all([wall_id, friend_name, word_1, word_2, word_3]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if friend_name.lower() == 'anonymous':
        return jsonify({'success': False, 'message': 'Anonymous submissions are not allowed. Please enter your name.'}), 400


    raw_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if raw_ip and ',' in raw_ip:
        raw_ip = raw_ip.split(',')[0].strip()

    result = submit_response(
        wall_id=wall_id,
        friend_name=friend_name,
        word_1=word_1, word_2=word_2, word_3=word_3,
        message=message, emoji=emoji,
        anonymous=anonymous,
        raw_ip=raw_ip,
        signature_url=signature_url,
    )

    if result.get('message') == 'rate_limited':
        return jsonify({'success': False, 'message': 'Too many submissions. Try again later.'}), 429

    return jsonify(result), 200 if result.get('success') else 500


@app.route('/api/memorywall/upload-signature', methods=['POST'])
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
        if size > 512 * 1024:  # 512 KB limit
            return jsonify({'success': False, 'message': 'File too large'}), 400

        # Validate it's a real image
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


@app.route('/api/memorywall/stats/<wall_id>', methods=['GET'])
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

# ─── Search API V2 (Phase 3 Migration) ────────────────────────────────────
from methods.search_api import search_v2_endpoint, search_analytics_endpoint
app.add_url_rule('/api/v2/search', view_func=search_v2_endpoint, methods=['GET'])
app.add_url_rule('/api/v2/search/analytics', view_func=search_analytics_endpoint, methods=['POST'])

@app.route('/api/admin/entity/add', methods=['POST'])
@auth_required
def api_add_entity():
    data = request.json
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
        
    from methods.supabase_helper import add_new_entity
    result = add_new_entity(entity_type, name, short_name, code, semester, parent_id)
    return jsonify(result), 200 if result.get('success') else 500

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    app.run(debug=debug_mode)
