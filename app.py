from flask import Flask, redirect, render_template, request, make_response, session, abort, jsonify, url_for, send_file
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
    import json
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
from difflib import SequenceMatcher

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
    """Fuzzy similarity (0..1) using stdlib difflib."""
    return SequenceMatcher(None, a, b).ratio()

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
    from datetime import datetime
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
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit on CSRF tokens

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
    'pdf', 'doc', 'docx', 'txt', 'ppt', 'pptx', 'xls', 'xlsx',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
    'zip', 'rar', '7z'
}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal and other attacks"""
    # Remove path components
    filename = os.path.basename(filename)
    # Remove any potentially dangerous characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename

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

# Admin email from environment variable
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'abhijeetshende4053@gmail.com')

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
        if user_email not in ['abhijeetshende4053@gmail.com', 'codebymario@gmail.com']:
            abort(403)  # Forbidden
            
        return f(*args, **kwargs)
    return decorated_function

# ─── Paper Access Quota ──────────────────────────────────────────────────────
# Each upload grants QUOTA_PER_UPLOAD paper opens.
# Admins and unauthenticated users are not affected (unauthenticated is blocked
# by @auth_required anyway).
QUOTA_PER_UPLOAD = 3

def _get_quota():
    """Return the current quota dict from session, creating it if absent."""
    if 'paper_quota' not in session:
        session['paper_quota'] = {'credits': 0, 'total_views': 0}
    return session['paper_quota']

def _grant_upload_credits():
    """Award QUOTA_PER_UPLOAD credits to the user after a successful upload."""
    q = _get_quota()
    q['credits'] = q.get('credits', 0) + QUOTA_PER_UPLOAD
    session['paper_quota'] = q
    session.modified = True
    logging.info(f"[QUOTA] Granted {QUOTA_PER_UPLOAD} credits → total credits: {q['credits']}")

def _consume_credit():
    """
    Deduct 1 credit for a paper open.
    Returns True if the open is allowed, False if quota is exhausted.
    Admins always pass.
    """
    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    # Admins bypass the gate
    if user_email in ['abhijeetshende4053@gmail.com', 'codebymario@gmail.com']:
        return True
    q = _get_quota()
    if q.get('credits', 0) <= 0:
        return False
    q['credits'] -= 1
    q['total_views'] = q.get('total_views', 0) + 1
    session['paper_quota'] = q
    session.modified = True
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

import logging
from PIL import Image
import json
import jwt

# Configure logging
logging.basicConfig(level=logging.DEBUG)



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
        device_type = 'desktop'
        userAgentLower = user_agent.lower()
        if 'mobile' in userAgentLower or 'android' in userAgentLower or 'iphone' in userAgentLower:
            device_type = 'mobile'
        elif 'tablet' in userAgentLower or 'ipad' in userAgentLower:
            device_type = 'tablet'
            
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

@app.route('/sitemap.xml')
def sitemap():
    return render_template('sitemap.xml')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

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

@app.route('/api/profile', methods=['GET'])
@auth_required
def get_profile():
    """Get current user profile"""
    try:
        user_info = session.get('user', {})
        return jsonify({
            'success': True,
            'user': {
                'uid': user_info.get('uid'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'name': user_info.get('name'),
                'provider': user_info.get('provider'),
                'user_metadata': user_info.get('user_metadata', {})
            }
        }), 200
    except Exception as e:
        logging.error(f"Error getting profile: {e}")
        return jsonify({'success': False, 'message': 'Failed to get profile'}), 500

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
        
        # Extract required fields
        filename = data.get('filename', '')
        file_url = data.get('url', '')
        college_name = data.get('college_name', '')
        subject_name = data.get('subject_name', '')
        subject_code = data.get('subject_code', '')
        branch_name = data.get('branch', '')
        year = str(data.get('year', ''))
        
        # New redesign fields
        custom_title = data.get('title', '')
        document_category = data.get('document_category', 'papers')
        custom_description = data.get('description', '')
        
        exam_type = data.get('exam_type', 'PYQ')  # Default to PYQ
        semesters = data.get('semesters', [])
        
        # Validate required fields
        if not all([filename, file_url, college_name, subject_name, branch_name, year]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Validate document category
        allowed_categories = ['papers', 'notes', 'practical', 'syllabus', 'assisment', 'timetable']
        if document_category not in allowed_categories:
            document_category = 'papers' # Fallback
            
        print(f"[STORE_ROOM_LABEL] User: {user_email}, File: {filename}")
        print(f"[STORE_ROOM_LABEL] Category: {document_category}, Title: {custom_title or filename}")
        
        # Look up college_id and branch_id
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        college_id = None
        branch_id = None
        
        if client:
            try:
                college_res = client.table('colleges').select('id').ilike('name', college_name).limit(1).execute()
                if college_res.data: college_id = college_res.data[0]['id']
            except: pass
            
            try:
                branch_res = client.table('departments').select('id').ilike('name', branch_name).limit(1).execute()
                if branch_res.data: branch_id = branch_res.data[0]['id']
            except: pass
        
        # Extract cloudinary_public_id from URL
        cloudinary_public_id = filename
        if 'cloudinary.com' in file_url:
            parts = file_url.split('/')
            if 'upload' in parts:
                idx = parts.index('upload')
                if idx + 1 < len(parts):
                    p_id_ext = '/'.join(parts[idx + 1:])
                    cloudinary_public_id = p_id_ext.rsplit('.', 1)[0]
        
        # Determine file type
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
        file_type = 'pdf' if file_ext == 'pdf' else 'image'
        
        # Save to file_records table
        from methods.supabase_helper import save_file_record
        
        # Merge custom description with metadata JSON if desired, OR just pass custom
        # Here we'll merge custom notes if provided
        final_description = custom_description if custom_description else ''
        
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
            subject_code=subject_code,
            semesters=semesters,
            title=custom_title,
            description=final_description
        )
        
        if result.get('success'):
            print(f"[STORE_ROOM_LABEL] SUCCESS: Saved to file_records")
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data', {})
            }), 200
        else:
            print(f"[STORE_ROOM_LABEL] ERROR: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save label')
            }), 500
    
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
            # The form might send 'type' or 'document_type'
            document_type = request.form.get('document_type') or request.form.get('type') or 'Other'
            subject_name = subject.strip()
            
            # Additional metadata for description
            unit = request.form.get('unit', '')
            practical_num = request.form.get('practical', '')
            practical_type = request.form.get('practical-type', '')
            
            print(f"[UPLOAD] Processing upload for User: {user_email}")
            print(f"[UPLOAD] Metadata - College: {college_id}, Branch: {branch_id}, Type: {document_type}, Subject: {subject_name}")
            
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
                title=subject_name if subject_name else original_filename
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

            # ── Grant paper-access credits for this upload ──────────────
            _grant_upload_credits()

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
    
    local_path = os.path.join('data', file_url)
    if not os.path.exists(local_path):
        bucket = storage.bucket()
        blob = bucket.blob(file_url)
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
    paper_count = len([f for f in files if f.get('type', '').lower() == 'pyq'])
    notes_count = len([f for f in files if f.get('type', '').lower() == 'notes'])
    
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
            
        # Get user profile basics from about_supabase schema
        from methods.supabase_helper import get_user_profile, calculate_user_ranks
        profile_res = get_user_profile(user_id)
        profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}
        
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
            'global_rank': global_rank
        }
    
    return render_template('p_index.html', 
                         data=files,
                         seo_keywords=seo_keywords,
                         top_subjects=top_subjects,
                         paper_count=paper_count,
                         notes_count=notes_count,
                         user_data=user_data,
                         file_history=file_history,
                         now=datetime.now())


@app.route('/profile')
@auth_required
def profile():
    from methods.supabase_helper import get_student_profile, get_user_uploaded_files, get_papo_meter_data
    
    user_info = session['user']
    user_id = user_info.get('uid')
    user_email = user_info.get('email', '')
    
    # Get all files for the "Shared" sections
    files = get_all_files_unified()
    
    # Get student profile info
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    
    # Get user's specifically uploaded files
    uploaded_files_result = get_user_uploaded_files(user_email, limit=50)
    uploaded_files = uploaded_files_result.get('data', []) if uploaded_files_result.get('success') else []
    
    # Map uploaded files to our unified format if necessary (though get_user_uploaded_files should return raw docs)
    # Actually, p_profile.html expects the unified format for the file cards
    from methods.supabase_helper import _doc_to_json
    formatted_uploads = [_doc_to_json(f, user_id) for f in uploaded_files]
    
    # Get Papo Meter data
    papo_meter = get_papo_meter_data(user_id)
    
    return render_template('p_profile.html', data={
        'user': user_info, 
        'data': files, 
        'uploaded_files': formatted_uploads,
        'profile': profile,
        'papo_meter': papo_meter
    })

@app.route('/premium/profile')
@auth_required
def p_profile_redirect():
    """Unify profile routes by redirecting to the main profile page"""
    return redirect(url_for('profile'))


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
    
    # Save profile
    result = create_or_update_student_profile(user_id, profile_data)
    
    if result.get('success'):
        # Redirect back to account page with success message
        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
        
        profile_result = get_student_profile(user_id)
        profile = profile_result.get('data') if profile_result.get('success') else None
        
        colleges_result = get_all_colleges()
        branches_result = get_all_branches()
        
        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
        branches = branches_result.get('data', []) if branches_result.get('success') else []
        
        return render_template('p_account.html', 
                             user=user_info, 
                             profile=profile,
                             colleges=colleges,
                             branches=branches,
                             message=result.get('message'),
                             message_type='success')
    else:
        # Show error message
        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
        
        profile_result = get_student_profile(user_id)
        profile = profile_result.get('data') if profile_result.get('success') else None
        
        colleges_result = get_all_colleges()
        branches_result = get_all_branches()
        
        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
        branches = branches_result.get('data', []) if branches_result.get('success') else []
        
        return render_template('p_account.html', 
                             user=user_info, 
                             profile=profile,
                             colleges=colleges,
                             branches=branches,
                             message=result.get('message', 'Failed to update profile'),
                             message_type='error')


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

@app.route('/team')
def team():
    """Team page"""
    return render_template('team.html')

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

@app.route('/register')
def register():
    """Register page (alias for signup)"""
    return redirect(url_for('signup'))

# Premium features
@app.route('/premium')
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
            'user_files': user_files[:10],  # Latest 10 user files for "Your Files" section
        }
    
    return render_template('p_index.html', 
                         data=files,
                         seo_keywords=seo_keywords,
                         top_subjects=top_subjects,
                         paper_count=paper_count,
                         notes_count=notes_count,
                         user_data=user_data,
                         now=datetime.now())

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
        # Log file access
        if 'user' in session:
            user_email = session['user'].get('email', '')
            file_basename = os.path.basename(pdf_name)
            record_id = request.args.get('record_id')
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
        
        # Pass the proxy URL to the PDF viewer template
        return render_template('p_pdf_reader.html', pdf_name=pdf_name, pdf_url=proxy_url)
    
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

@app.route('/indexnow', methods=['POST'])
def indexnow():
    urls = [
        "https://abhi-hub-06bba7f4101d.herokuapp.com/",
        "https://abhi-hub-06bba7f4101d.herokuapp.com/dashboard",
        # Add more URLs as needed
    ]
    
    indexnow_url = "https://api.indexnow.org/indexnow"
    
    payload = {
        "host": "abhi-hub-06bba7f4101d.herokuapp.com",
        "key": '358beb4ba88947458503f632b81ca8cf',
        "keyLocation": f"https://abhi-hub-06bba7f4101d.herokuapp.com/358beb4ba88947458503f632b81ca8cf.txt",
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

@app.route('/premium/suggest')
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

@app.route('/premium/')
@auth_required
def index():
    search_query = request.args.get('search_query')
    data = load_data(search_query)
    
    # Calculate counts for template
    paper_count = sum(1 for item in data if item.get('type') == 'Papers')
    notes_count = sum(1 for item in data if item.get('type') == 'Notes')
    
    return render_template('p_index.html', data=data, paper_count=paper_count, notes_count=notes_count)

@app.route('/premium/search', methods=['POST', 'GET'])
@auth_required
def search():
    search_query = request.form.get('search')
    if not search_query:
        return "Search query is missing", 400
    data = load_data(search_query)
    
    # Calculate counts for template
    paper_count = sum(1 for item in data if item.get('type') == 'Papers')
    notes_count = sum(1 for item in data if item.get('type') == 'Notes')
    
    return render_template('p_index.html', data=data, paper_count=paper_count, notes_count=notes_count)

@app.route('/premium/view', methods=['POST', 'GET'])
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

@app.route('/premium/share-receiver', methods=['POST', 'GET'])
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

@app.route('/premium/about')
@auth_required
def premium_about():
    return render_template('p_about.html')

@app.route('/premium/profile/old')
@auth_required
def p_profile_deprecated():
    return redirect(url_for('profile'))
@app.route('/premium/setting')
def p_setting():
    return render_template('settings.html')


@app.route('/premium/static/search.json')
@auth_required
def search_in():
    search_file = os.path.join(app.root_path, 'premium/static/search.json')
    try:
        with open(search_file, 'r') as f:
            searches = json.load(f)
        return jsonify(searches), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

@app.route('/premium/save_search', methods=['POST'])
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
    try:
        from methods.supabase_helper import calculate_user_ranks
        rank_list = calculate_user_ranks()
    except Exception as e:
        rank_list = []
        
    current_user_id = session.get('user', {}).get('uid') if 'user' in session else None
    return render_template('p_ranking.html', rank=rank_list, current_user_id=current_user_id)

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
def update_file_metadata():
    """
    Update file metadata in Supabase
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

@app.route('/store-room')
@auth_required
def store_room():
    """
    Store Room page - displays unsorted papers from Cloudinary
    Only loads initial batch for performance
    """
    try:
        # Fetch all files from Cloudinary to get counts and metadata
        all_files = fetch_all_files(resource_type="image")
        
        # Get labeled papers count from Supabase
        labeled_result = get_labeled_papers()
        labeled_count = len(labeled_result.get('data', [])) if labeled_result.get('success') else 0
        
        # Calculate statistics
        total_papers = len(all_files)
        sorted_papers = labeled_count
        remaining_papers = total_papers - sorted_papers
        
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


@app.route('/store-room/api/files', methods=['GET'])
@auth_required
def store_room_api_files():
    """
    API endpoint for fetching files with filters
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
        
        # Fetch all files
        all_files = fetch_all_files(resource_type="image")
        
        # Apply search
        if search_query:
            all_files = search_files(all_files, search_query)
        
        # Apply filters
        if format_filter or folder_filter:
            all_files = filter_files(all_files, format_filter, folder_filter)
        
        # Apply sorting
        all_files = sort_files(all_files, sort_by, order)
        
        # Get labeled papers and cross-reference
        labeled_result = get_labeled_papers()
        labeled_papers = labeled_result.get('data', []) if labeled_result.get('success') else []
        
        # Create lookup map for quick access (using provider_public_id)
        labeled_map = {p.get('provider_public_id'): p for p in labeled_papers if p.get('provider_public_id')}
        
        # Mark each file with its status and engagement data
        for f in all_files:
            doc = labeled_map.get(f.get('public_id'))
            if doc:
                f['record_id'] = doc.get('id')
                f['verified'] = (doc.get('status') == 'approved')
                f['verification_status'] = doc.get('status')
                # Include engagement stats
                f['like_count'] = doc.get('like_count', 0)
                f['bookmark_count'] = doc.get('bookmark_count', 0)
                f['comment_count'] = doc.get('comment_count', 0)
                f['view_count'] = doc.get('view_count', 0)
                # Check if liked/bookmarked (placeholders for now, or fetch from DB if needed)
                f['is_liked'] = False 
                f['is_bookmarked'] = False
            else:
                f['record_id'] = None
                f['verified'] = False
                f['verification_status'] = None
                f['like_count'] = 0
                f['bookmark_count'] = 0
                f['comment_count'] = 0
                f['view_count'] = 0
        
        # Calculate statistics
        total_papers = len(all_files)
        sorted_papers = len([f for f in all_files if f.get('record_id')])
        remaining_papers = total_papers - sorted_papers
        
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


@app.route('/store-room/api/label', methods=['POST'])
@auth_required
def store_room_api_label():
    """
    API endpoint for saving labeled papers to Supabase
    """
    try:
        # Get form data
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['filename', 'url', 'college_name', 'subject_name', 'exam_name', 
                          'exam_type', 'year', 'branch', 'semesters']
        
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400
        
        # Get user email from session
        user_email = session.get('user', {}).get('email', '')
        
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User email not found in session'
            }), 401
        
        # Add user email to data
        data['user_email'] = user_email
        
        # Save to Supabase
        result = save_labeled_paper(data)
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data')
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save labeled paper')
            }), 500
    
    except Exception as e:
        logging.error(f"Error saving labeled paper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/store-room/api/check-labeled', methods=['POST'])
@auth_required
def store_room_api_check_labeled():
    """
    API endpoint to check if a file has been labeled
    """
    try:
        data = request.get_json()
        filename = data.get('filename', '')
        
        if not filename:
            return jsonify({'success': False, 'message': 'Filename required'}), 400
        
        is_labeled = check_if_labeled(filename)
        
        return jsonify({
            'success': True,
            'is_labeled': is_labeled
        })
    
    except Exception as e:
        logging.error(f"Error checking labeled status: {e}")
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

if __name__ == '__main__':
    app.run(debug=True)
