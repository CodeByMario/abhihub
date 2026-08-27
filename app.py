# Gevent monkey patch must be executed at the very beginning
try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

from flask import Flask, redirect, render_template, request, make_response, session, abort, jsonify, url_for, send_file, send_from_directory, flash, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets
from functools import wraps
from push_api import init_push_api

import os
import io
import time
import hashlib
import hmac
import requests
import json
from datetime import timedelta, datetime
import logging
from dotenv import load_dotenv
from supabase import create_client, ClientOptions

# Load environment variables
load_dotenv()

# IndexNow must use one environment-managed key for both submission and ownership verification.
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'abhihub.edu.eu.org').strip().lower()
INDEXNOW_KEY = os.getenv('INDEX_NOW_BING_API_KEY', '').strip()
TURNSTILE_SITEKEY = os.getenv('TURNSTILE_SITEKEY', '')

# Initialize Supabase client for authentication
# DEFERRED: create_client crashes if SUPABASE_URL/KEY are None (causes H10 on Heroku startup).
# We use a lazy proxy so the client is only created when first accessed.
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_PUBLIC_API_KEY')

_supabase_client = None  # Lazily initialized

class _SupabaseProxy:
    """Defer client creation until first attribute access so missing env vars
    don't crash the app at import time (fixes Heroku H10 startup crash)."""
    def _ensure(self):
        global _supabase_client
        if _supabase_client is None:
            if not SUPABASE_URL or not SUPABASE_KEY:
                raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables are required")
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="abhihub"))
        return _supabase_client
    def __getattr__(self, name):
        return getattr(self._ensure(), name)

supabase = _SupabaseProxy()

# Initialize Firebase Admin SDK for storage only
import firebase_admin
from firebase_admin import credentials, storage

# Load Firebase service-account credentials:
#   1. FIREBASE_SERVICE_ACCOUNT_JSON env var (primary — works local + Heroku)
#   2. firebase-auth.json file (fallback, local dev) — git-ignored
cred = None
firebase_service_account = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
if firebase_service_account:
    try:
        cred_dict = json.loads(firebase_service_account)
        if 'private_key' not in cred_dict or cred_dict.get('type') != 'service_account':
            logging.warning(
                "Firebase: FIREBASE_SERVICE_ACCOUNT_JSON looks like the WEB CLIENT config "
                "(apiKey/authDomain/appId), not a service-account key. Firebase Storage signing "
                "will fail. Generate a service account key: Firebase Console -> Project Settings "
                "-> Service accounts -> Generate new private key."
            )
        else:
            cred = credentials.Certificate(cred_dict)
            logging.info("Firebase: credentials loaded from FIREBASE_SERVICE_ACCOUNT_JSON env var")
    except (json.JSONDecodeError, Exception) as e:
        logging.warning(f"Firebase: Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")

if cred is None:
    _firebase_key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firebase-auth.json')
    if os.path.exists(_firebase_key_path):
        try:
            cred = credentials.Certificate(_firebase_key_path)
            logging.info("Firebase: credentials loaded from firebase-auth.json")
        except Exception as e:
            logging.warning(f"Firebase: failed to load firebase-auth.json: {e}")
            cred = None

if cred is None:
    logging.warning(
        "Firebase: no credentials found (neither FIREBASE_SERVICE_ACCOUNT_JSON nor "
        "firebase-auth.json). Firebase storage unavailable — signed URL generation "
        "will fail for Firebase-hosted documents."
    )

if cred:
    firebase_admin.initialize_app(cred, {
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'abhi-hub.appspot.com')
    })
else:
    # Initialize with no cred — Firebase features will gracefully degrade
    firebase_admin.initialize_app(None)

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

# Initialize Flask app
app = Flask(__name__)
try:
    from flask_compress import Compress
    Compress(app)
except Exception:
    pass  # Compression is optional; skip gracefully if unavailable

# Initialize the Level-wise Cache Management System
from cache_manager import init_cache, get_cache
cache = init_cache(app)

socketio = SocketIO(app, cors_allowed_origins="https://app.abhihub.run.place", logger=False, engineio_logger=False)

import mimetypes
mimetypes.add_type('application/javascript', '.mjs')

# Free models on OpenRouter (prompt=0, completion=0) — verified 2026-08
# Kept small: fewer models = fewer dead-end retries, faster response.
# OpenRouter handles provider-level load balancing and fallback internally.
AI_MODELS = [
    "google/gemma-4-31b-it:free",       # vision + text, best free model
    "google/gemma-4-26b-a4b-it:free",   # vision + text, MoE variant
    "nvidia/nemotron-nano-12b-v2-vl:free", # vision
    "openai/gpt-oss-20b:free",           # text fallback
    "meta-llama/llama-3.1-8b-instruct:free", # reliable text fallback
]
# Vision-capable free models (support image_url in messages)
AI_VISION_MODELS = {
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
}

# Stateless helpers — no in-process cooldown (breaks under multi-worker gunicorn).
# OpenRouter's own provider routing handles rate limits and fallback.

def get_best_ai_model():
    """Return the primary text model; OpenRouter will fallback automatically."""
    return AI_MODELS[0]

def _resolve_model(selected_model):
    """Normalize model selection: 'auto' or unknown → primary model."""
    if not selected_model or selected_model == 'auto' or selected_model not in AI_MODELS:
        return get_best_ai_model()
    return selected_model

def _build_model_list(preferred, pool):
    """Return pool with preferred first."""
    ordered = [preferred] if preferred in pool else []
    ordered += [m for m in pool if m != preferred]
    return ordered

# Log API key presence at startup (no values, just presence)
logging.info(f"[AI] OPENROUTER_API_KEY present: {bool(os.getenv('OPENROUTER_API_KEY'))}")
logging.info(f"[AI] NVIDIA_API_KEY present: {bool(os.getenv('NVIDIA_API_KEY'))}")

# Global in-memory chat history for rate limiting (user_id -> list of float timestamps)
_chat_history = {}

def extract_pdf_info(pdf_bytes):
    """Extract text from PDF or convert page 1 / extract embedded image to bytes."""
    extracted_text = ""
    img_bytes, mime_type = None, None
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_text += t + "\n"
            if not img_bytes and hasattr(page, 'images'):
                try:
                    for img in page.images:
                        img_bytes = img.data
                        name = (getattr(img, 'name', '') or '').lower()
                        if name.endswith('.png'): mime_type = 'image/png'
                        elif name.endswith('.webp'): mime_type = 'image/webp'
                        else: mime_type = 'image/jpeg'
                        break
                except Exception:
                    pass
    except Exception as e:
        logging.warning(f"[extract_pdf_info] pypdf error: {e}")

    if not img_bytes:
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if not extracted_text:
                for page in doc:
                    extracted_text += page.get_text() + "\n"
            if len(doc) > 0:
                pix = doc[0].get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                mime_type = "image/png"
        except Exception as e:
            logging.warning(f"[extract_pdf_info] fitz error: {e}")

    return extracted_text.strip(), img_bytes, mime_type


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
def redirect_to_new_domain():
    old_domains = ["app.abhihub.run.place", "abhihub.herokuapp.com", "abhihub.run.place"]
    if any(d in request.host for d in old_domains):
        new_url = "https://www.abhihub.edu.eu.org" + request.full_path
        return redirect(new_url, code=301)

init_push_api(app)

# Initialize background scheduler for upload notifications
try:
    from scheduled_tasks import init_scheduler
    init_scheduler(app)
    logging.info("✅ Background task scheduler initialized")
except ImportError as e:
    logging.warning(f"⚠️ Background scheduler not available (missing dependency): {e}")
    logging.info("Upload notifications will not be sent automatically")
except Exception as e:
    logging.error(f"⚠️ Failed to initialize background scheduler: {e}")
    logging.error("Upload notifications will not be sent automatically")


# File Upload Security Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
# Match file input accept attr + JS type check: images + PDF only.
# PDFs and images are the canonical upload types for AbhiHub.
ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'
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


# Extension -> logical file-type used by file_records / document_views.
_FILE_TYPE_BY_EXT = {
    '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
    '.gif': 'image', '.webp': 'image', '.svg': 'image',
    '.pdf': 'pdf',
    '.doc': 'document', '.docx': 'document', '.txt': 'document',
    '.xls': 'spreadsheet', '.xlsx': 'spreadsheet',
    '.ppt': 'presentation', '.pptx': 'presentation',
}


def detect_file_type(filename: str) -> str:
    """Map a filename/URL to a logical file type ('pdf', 'image', ...).

    Single source of truth — previously this dict was inlined per route.
    """
    ext = os.path.splitext(os.path.basename(filename or '').split('?')[0])[1].lower()
    return _FILE_TYPE_BY_EXT.get(ext, 'file')


def log_document_view(file_name, file_url, record_id=None,
                      file_type=None, file_path=None, user_email=None):
    """Record that the current user viewed a document.

    Shared by /preview, /view_pdf and /resource/<slug> so the view-logging
    contract lives in exactly one place. Never raises: a logging failure
    must not break document delivery.
    """
    if user_email is None:
        user_email = session.get('user', {}).get('email', '')
    if not user_email:
        return False
    try:
        save_file_access(
            user_email=user_email,
            file_name=file_name,
            file_type=file_type or detect_file_type(file_name or file_url),
            file_path=file_path if file_path is not None else file_url,
            file_url=file_url,
            record_id=record_id,
        )
        return True
    except Exception as e:
        logging.warning(f"[VIEW-LOG] could not record view for {file_name}: {e}")
        return False


########################
#-------function-------#
from methods.storage import upload_file, list_files, download_file, delete_file
from methods.analytics_tracker import register_analytics_routes, get_full_profile_json
from methods.analytics_reporter_routes import register_reporter_routes

# Register analytics routes
register_analytics_routes(app)
register_reporter_routes(app)

# Make user profile data available to all templates
@app.context_processor
def inject_user_profile():
    """Inject user profile JSON into all templates for GA4 tracking."""
    return {
        'get_full_profile_json': get_full_profile_json
    }


@app.context_processor
def inject_ad_decision():
    """Inject dynamic ad decision (from access level) into all templates.

    Templates use: {% if ad_decision.show_ads %}{% include 'ads/banner.html' %}{% endif %}
    Density drives per-slot frequency: 'minimal'/'very_low' show ads rarely.
    """
    user_id = session.get('user', {}).get('uid')
    try:
        from methods.scoring_engine import get_ad_decision
        ad_decision = get_ad_decision(user_id)
    except Exception:
        ad_decision = {'show_ads': True, 'density': 'high', 'level': None}
    return {
        'ad_decision': ad_decision,
        'ad_density': ad_decision.get('density', 'high'),
        # Convenience flags for slot-level frequency gating
        'show_secondary_ads': ad_decision.get('density') in ('high', 'medium'),
    }


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

# Admin emails from environment variable (comma-separated, fall back to ADMIN_EMAIL)
ADMIN_EMAILS = [e.strip().lower() for e in (os.getenv('ADMIN_EMAILS') or os.getenv('ADMIN_EMAIL') or '').split(',') if e.strip()]

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

# ─── PDF Access Token Security (prevents download managers from catching raw URLs) ──

def _generate_pdf_token(doc_id, user_id=None, max_age=3600):
    """Generate a session-bound access token for PDF viewing.

    The token is an HMAC-SHA256 of (doc_id + user_id + expiry_timestamp)
    signed with the app secret key. Download managers cannot forge this
    because they don't have the user's session cookie.
    """
    expiry = int(time.time()) + max_age
    msg = f"{doc_id}:{user_id}:{expiry}".encode()
    sig = hmac.new(app.secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return f"{expiry}:{sig}"

def _verify_pdf_token(doc_id, token, max_age=3600):
    """Verify a session-bound PDF access token.

    Returns True if the token is valid and not expired.
    Requires an active user session (the token is bound to user_id).
    """
    if not token or ':' not in token:
        return False
    parts = token.split(':', 1)
    if len(parts) != 2:
        return False
    try:
        expiry = int(parts[0])
    except ValueError:
        return False
    provided_sig = parts[1]

    # Check expiry
    if time.time() > expiry:
        return False

    # Reconstruct the expected signature using the session user
    user = session.get('user', {})
    user_id = user.get('uid', '')
    msg = f"{doc_id}:{user_id}:{expiry}".encode()
    expected_sig = hmac.new(app.secret_key.encode(), msg, hashlib.sha256).hexdigest()

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided_sig, expected_sig)


# Each upload grants QUOTA_PER_UPLOAD paper opens.
# Admins and unauthenticated users are not affected (unauthenticated is blocked
# by @auth_required anyway).
QUOTA_PER_UPLOAD = 19

def _get_quota():
    """Return the current quota dict from session, synced with backend, processing monthly resets.
    Caches the Supabase response at L1 for 60s to reduce DB load."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return {'credits': 19, 'total_views': 0}

    # Check L1 cache for quota (short TTL since it changes on every paper open)
    cached_quota = cache.l1.get(f"user:quota:{user_id}")
    if cached_quota[0] is not None:
        return cached_quota[0]

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

    # Invalidate quota cache — it changed
    cache.l1.delete(f"user:quota:{user_id}")

    return True

@app.route('/api/quota', methods=['GET'])
@auth_required
def api_get_quota():
    """Return the current quota for the logged-in user — cached at L1 for 60s."""
    q = _get_quota()
    response = jsonify({
        'credits': q.get('credits', 0),
        'total_views': q.get('total_views', 0),
        'quota_per_upload': QUOTA_PER_UPLOAD
    }), 200
    cache.set_cache_headers(response[0], max_age=cache.SHORT, stale_while_revalidate=True)
    return response


@app.route('/api/cache-health', methods=['GET'])
def api_cache_health():
    """Cache system health check — returns stats for all cache layers."""
    return jsonify({
        'status': 'ok',
        'cache': cache.stats(),
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200
# ─────────────────────────────────────────────────────────────────────────────

from PIL import Image

# Configure logging
logging.basicConfig(level=logging.DEBUG)

import traceback


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


@app.route('/api/referral/register', methods=['POST'])
def api_referral_register():
    """Capture a referral code at signup and credit both sides.

    Body: {"code": "ABHI-XXXXXX"}
    The new user is taken from the active session (set by /auth).
    Safe to call repeatedly; the credit logic is idempotent per code.
    """
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        payload = request.get_json(silent=True) or {}
        code = (payload.get('code') or '').strip()
        if not code:
            return jsonify({'success': False, 'message': 'No referral code provided'}), 400
        new_user_id = session['user'].get('uid')
        # Make sure the new user has their own code too (idempotent)
        ensure_referral_code(new_user_id)
        result = register_referral(new_user_id, code)
        if result.get('success'):
            return jsonify({'success': True, 'credit_invitee': result.get('credit_invitee', 0)}), 200
        return jsonify({'success': False, 'message': result.get('message', 'Could not apply referral')}), 400
    except Exception as e:
        logging.error(f"[Referral] register endpoint failed: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500


@app.route('/api/referral/my-code', methods=['GET'])
@auth_required
def api_referral_my_code():
    """Return the logged-in user's shareable referral code + link + progress."""
    try:
        uid = session['user'].get('uid')
        code = ensure_referral_code(uid)
        base = os.getenv('BASE_DOMAIN', 'abhihub.edu.eu.org')
        # Pull progress stats (referral_count, referral_credits) for the dashboard
        referral_count = 0
        referral_credits = 0
        client = init_supabase()
        if client:
            try:
                pr = client.table('profiles').select('referral_count, referral_credits').eq('id', uid).limit(1).execute()
                if pr.data:
                    referral_count = pr.data[0].get('referral_count', 0) or 0
                    referral_credits = pr.data[0].get('referral_credits', 0) or 0
            except Exception:
                pass
        return jsonify({
            'success': True,
            'code': code,
            'share_url': f"https://{base}/signup?ref={code}",
            'referral_count': referral_count,
            'referral_credits': referral_credits,
        }), 200
    except Exception as e:
        logging.error(f"[Referral] my-code failed: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

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

@app.route('/robots.txt')
def robots_txt():
    """Expose the crawler directives at the host root."""
    response = make_response(send_from_directory(app.root_path, 'robots.txt'))
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response

@app.route('/<key>.txt')
def index_now_key(key):
    if INDEXNOW_KEY and key == INDEXNOW_KEY:
        return INDEXNOW_KEY, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    return abort(404)

@app.route('/sitemap.xml')
def sitemap():
    
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
    response = make_response(render_template('logout_clear.html'))
    response.set_cookie('session', '', expires=0)  # Clear the session cookie
    return response

@app.route('/api/profile-status')
@auth_required
def profile_status(user_data=None):
    """Lightweight endpoint for access-gates.js — returns profile completion state."""
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
    """Get all colleges for dropdown — cached at L1 for 1 hour (L3: browser/CDN 1hr)."""
    def fetch_all_colleges():
        result = get_all_colleges()
        if result.get('success'):
            return result.get('data', [])
        return []

    colleges = cache.get_cached('dropdowns:colleges', level=cache.L1, ttl=cache.LONG, fetcher=fetch_all_colleges)
    response = jsonify({
        'success': True,
        'colleges': colleges
    }), 200
    cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
    return response


@app.route('/api/branches', methods=['GET'])
def api_get_branches():
    """Get all branches for dropdown — cached at L1 for 1 hour (L3: browser/CDN 1hr)."""
    def fetch_all_branches():
        result = get_all_branches()
        if result.get('success'):
            return result.get('data', [])
        return []

    branches = cache.get_cached('dropdowns:branches', level=cache.L1, ttl=cache.LONG, fetcher=fetch_all_branches)
    response = jsonify({
        'success': True,
        'branches': branches
    }), 200
    cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
    return response


# T1 — Cascading dropdowns
@app.route('/api/departments', methods=['GET'])
def api_get_departments():
    """Return departments for a college (cascading dropdown, T1/T8)."""
    college_id = request.args.get('college_id', '').strip()
    if not college_id:
        return jsonify({'success': False, 'departments': [], 'message': 'college_id required'}), 400
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
    """Return subjects for a department, optionally filtered by semester — cached at L1 for 30min."""
    department_id = request.args.get('department_id', '').strip()
    semester = request.args.get('semester', type=int)  # optional
    if not department_id:
        return jsonify({'success': False, 'subjects': [], 'message': 'department_id required'}), 400

    cache_key = f"subjects:{department_id}:{semester or 0}"
    def fetch_subjects():
        result = get_subjects_by_department(department_id, semester=semester)
        return result.get('data', []) if result.get('success') else []

    subjects = cache.get_cached(cache_key, level=cache.L1, ttl=cache.LONG, fetcher=fetch_subjects)
    response = jsonify({
        'success': True,
        'subjects': subjects
    }), 200
    cache.set_cache_headers(response[0], max_age=cache.LONG, stale_while_revalidate=True, stale_if_error=86400)
    return response


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
        
        # Auto-generate and store acronym alias (e.g. Transform Numerical Method -> tnm)
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
                except Exception as e:
                    logging.info(f"Failed to save alias {acronym} for subject: {e}")
                    
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
    if len(name) > 200:
        return jsonify({'success': False, 'message': 'College name too long (max 200 chars)'}), 400
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
    
    client = init_supabase()
    
    words = re.split(r'[\W_]+', filename.split('.')[0])
    prediction = {'subject_id': None, 'type': None, 'unit': None,
                  'year': str(datetime.now().year)}
    
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
            logging.error(f"Prediction error: {e}")

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

    if not validate_uuid(college_id):
        return jsonify({'success': False, 'message': 'Invalid college'}), 400

    result = join_college_waitlist(college_id, email, name)
    return jsonify(result), 200


# T4 — Onboarding status
@app.route('/api/onboarding/status', methods=['GET'])
@auth_required
def api_onboarding_status():
    user_id = session.get('user', {}).get('uid')
    result = get_onboarding_status(user_id)
    return jsonify(result), 200 if result.get('success') else 500


@app.route('/api/onboarding/welcome-seen', methods=['POST'])
@auth_required
def api_onboarding_welcome_seen():
    user_id = session.get('user', {}).get('uid')
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
    track_user_event(user_id, event_type, data.get('metadata', {}))
    return jsonify({'success': True}), 200


@app.route('/store-room/api/label', methods=['POST'])
@auth_required
def label_store_room_paper():
    """
    Label a paper from store room and save to file_records table.
    Expects JSON with: filename, url, college_name, subject_name, branch, year, exam_type, etc.
    """
    global _unlabeled_cache
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
        program = data.get('program', 'b.tech') or 'b.tech'
        semester_raw = data.get('semester')
        semester = int(semester_raw) if semester_raw and str(semester_raw).isdigit() and 1 <= int(semester_raw) <= 8 else None

        missing_fields = []
        if not filename: missing_fields.append('filename')
        if not file_url: missing_fields.append('url')
        if not subject_name: missing_fields.append('subject_name')
        if not year: missing_fields.append('year')

        if missing_fields:
            logging.debug(f"[DEBUG] Missing required fields: {missing_fields}")
            return jsonify({'success': False, 'message': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        if not subject_id:
            return jsonify({'success': False, 'message': 'Subject selection is required'}), 400

        # Validate the academic hierarchy
        if not verify_hierarchy(college_id, branch_id, subject_id):
            return jsonify({'success': False, 'message': 'Invalid academic hierarchy (mismatched college/branch/subject)'}), 400

        allowed_categories = ['papers', 'notes', 'practical', 'syllabus', 'assisment', 'timetable']
        if document_category not in allowed_categories:
            document_category = 'papers'

            logging.info(f"[STORE_ROOM_LABEL] User: {user_email}, File: {filename}")
            logging.info(f"[STORE_ROOM_LABEL] College:{college_id} Branch:{branch_id} Subject:{subject_id} Sem:{semester}")

        # Use the storage index identifier when supplied by the Store Room.
        # Parsing a Cloudinary URL can include a version segment and leave the
        # asset status as PENDING even though its document was saved.
        storage_provider = (data.get('storage_provider') or '').strip().lower()
        cloudinary_public_id = (data.get('provider_public_id') or '').strip()
        if not cloudinary_public_id and 'cloudinary.com' in file_url:
            parts = file_url.split('/')
            if 'upload' in parts:
                idx = parts.index('upload')
                if idx + 1 < len(parts):
                    p_id_ext = '/'.join(parts[idx + 1:])
                    p_id_ext = re.sub(r'^v\d+/', '', p_id_ext)
                    cloudinary_public_id = p_id_ext.rsplit('.', 1)[0]
        if not cloudinary_public_id:
            cloudinary_public_id = filename

        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
        file_type = 'pdf' if file_ext == 'pdf' else 'image'


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
            exam_type=exam_type,
            program=program
        )
        
        if result.get('success'):
            logging.info(f"[STORE_ROOM_LABEL] SUCCESS: Saved to file_records")
            
            # 1. Update storage_assets status to LABELED
            storage_provider = storage_provider or ('cloudinary' if cloudinary_public_id else 'firebase')
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
            _unlabeled_cache['data'] = None
            
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data', {})
            }), 200
        else:
            logging.error(f"[STORE_ROOM_LABEL] ERROR: {result.get('message')}")
            # A pre-existing, fully labeled document can still have an old
            # PENDING storage row.  Clear that stale queue row so it is not
            # presented for labeling again.
            if result.get('conflict'):
                storage_provider = storage_provider or ('cloudinary' if cloudinary_public_id else 'firebase')
                if cloudinary_public_id:
                    mark_storage_asset_labeled(storage_provider, cloudinary_public_id)
                _unlabeled_cache['data'] = None
                return jsonify({
                    'success': True,
                    'message': 'File was already labeled and has been removed from the Store Room queue.',
                    'data': result.get('data', {})
                }), 200
            status_code = 409 if result.get('conflict') else 500
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save label')
            }), status_code
    
    except Exception as e:
        logging.error(f"[STORE_ROOM_LABEL] EXCEPTION: {e}")
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
        
    res = toggle_bookmark(user_email, doc_id)
    return jsonify(res), 200 if res.get('success') else 500

@app.route('/api/interactions/comments/<doc_id>', methods=['GET', 'POST'])
def api_comments(doc_id):
    
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
        
        # Detect device type via shared helper
        device_type = get_device_type(user_agent)
        
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

            # Scoring engine: award contribution points for unique views only
            try:
                from methods.scoring_engine import process_event
                is_owner = False
                try:
                    _res = init_supabase().table('documents').select('uploader_id').eq('id', document_id).limit(1).execute()
                    if _res.data:
                        is_owner = (_res.data[0].get('uploader_id') == user_id)
                except Exception:
                    pass
                score_res = process_event(
                    user_id=user_id,
                    event_type='resource_viewed',
                    entity_id=document_id,
                    entity_type='document',
                    actor_is_owner=is_owner,
                    description='Viewed a resource',
                )
                if score_res.get('scored'):
                    logging.info(f"[SCORING] view scored for {user_id}: +{score_res.get('xp_gained')}")
            except Exception as e:
                logging.warning(f"[SCORING] view scoring skipped: {e}")

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
    res = mark_notifications_read(user_id)
    return jsonify(res), 200 if res.get('success') else 500


@app.route('/api/notifications/<notif_id>/read', methods=['POST'])
@auth_required
def api_mark_single_notification_read(notif_id):
    """Mark a single notification as read by its ID."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    try:
        client = None
        client = init_supabase()
        if not client or not validate_uuid(notif_id):
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        res = client.table('notifications') \
            .update({'is_read': True}) \
            .eq('id', notif_id) \
            .eq('user_id', user_id) \
            .eq('is_read', False) \
            .execute()
        if res.data:
            return jsonify({'success': True}), 200
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    except Exception as e:
        logging.error(f"[api_mark_single_notification_read] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/notifications')
@auth_required
def notifications_page():
    """Full notification center page with all notifications (paginated)."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return redirect(url_for('login'))
    limit = min(request.args.get('limit', 50, type=int), 100)
    offset = request.args.get('offset', 0, type=int)
    items = get_user_notifications(user_id, limit=limit, offset=offset)
    unread = sum(1 for n in items if not n.get('is_read'))
    has_more = len(items) == limit
    return render_template('notifications.html', notifications=items, unread=unread,
                           offset=offset, limit=limit, has_more=has_more)


@app.route('/api/files/all', methods=['GET'])
def get_all_files():
    """
    API endpoint to get all files exclusively from the abhihub.documents table.
    Returns unified JSON array of all files.
    """
    try:
        logging.info("[API /api/files/all] Request received")
        
        
        # Check if user is logged in to return personalized interactions
        user_info = session.get('user', {})
        current_user_id = user_info.get('uid')
        
        result = get_all_files_merged(include_file_records=True, current_user_id=current_user_id)

        
        if result.get('success'):
            logging.info(f"[API /api/files/all] Returning {result.get('count', 0)} files")
            return jsonify({
                'success': True,
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 200
        else:
            logging.error(f"[API /api/files/all] ERROR: {result.get('message', 'Unknown error')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to load files'),
                'data': result.get('data', []),
                'count': result.get('count', 0)
            }), 500
    
    except Exception as e:
        logging.error(f"[API /api/files/all] EXCEPTION: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500




@app.route('/upload', methods=['GET', 'POST'])
@auth_required
def upload():
    if request.method == 'POST':
        # Access level: enforce daily upload quota (Phase 3 feature gating)
        try:
            from methods.scoring_engine import check_upload_quota
            quota = check_upload_quota(session.get('user', {}).get('uid'))
            if not quota.get('allowed'):
                return jsonify(success=False, message=(
                    f"Daily upload limit reached ({quota.get('limit')}/day for your level). "
                    "Contribute more to raise your access level!"
                )), 429
        except Exception as q_err:
            logging.warning(f"[GATING] upload quota check skipped: {q_err}")

        # Security: Check if file is present
        if 'upload_document' not in request.files:
            return jsonify(success=False, message="No file provided"), 400
        
        file = request.files['upload_document']
        
        # Security: Check if a file was selected
        if file.filename == '':
            return jsonify(success=False, message="No file selected"), 400
        
        # Security: Validate file extension
        if not allowed_file(file.filename):
            return jsonify(success=False, message="File type not allowed. Allowed types: PDF, PNG, JPG, JPEG, WEBP, GIF, SVG"), 400
        
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
            program = request.form.get('program', 'b.tech').strip() or 'b.tech'

            # Guard: reject uploads with no subject selected
            if not subject_id or subject_id == '__other__':
                logging.warning(f"[UPLOAD REJECTED] Reason:Missing subject_id Uploader:{user_id} File:{original_filename}")
                return jsonify(
                    success=False,
                    message="Subject selection is required. Please select a subject from the dropdown."
                ), 400


            logging.info(f"[UPLOAD] Uploader:{user_id} College:{college_id} Branch:{branch_id} Semester:{semester} Subject:{subject_name!r} SubjectID:{subject_id}")
            
            # Save to file_records table (Supabase abhihub.documents)
            from methods.cloudinary_upload import delete_file_from_cloudinary

            # Read optional fields the JS client sends
            file_hash = request.form.get('file_hash', '').strip() or None
            exam_type = request.form.get('exam_type', '').strip() or ''
            subject_code = request.form.get('subject_code', '').strip() or ''

            file_record_result = save_file_record(
                user_id=user_id,
                user_email=user_email,
                file_name=original_filename,
                file_url=upload_result['secure_url'],
                file_type=file_type_category,
                file_size=upload_result.get('bytes') or file_size,
                cloudinary_public_id=upload_result['public_id'],
                subject_name=subject_name,
                document_type=document_type.lower(),
                year=year,
                college_id=college_id if college_id else None,
                branch_id=branch_id if branch_id else None,
                title=subject_name if subject_name else original_filename,
                subject_id=subject_id if subject_id else None,
                semester=semester,
                program=program,
                exam_type=exam_type,
                subject_code=subject_code,
                file_hash=file_hash
            )
            
            if not file_record_result.get('success'):
                logging.error(f"[UPLOAD ERROR] Supabase record creation failed: {file_record_result.get('message')}")
                # Clean up the orphaned Cloudinary asset so we never leave
                # uploaded files stranded when the DB write fails.
                try:
                    _cleanup = delete_file_from_cloudinary(upload_result['public_id'], 'raw' if upload_result.get('resource_type') == 'raw' else 'image')
                    if not _cleanup.get('success'):
                        logging.warning(f"[UPLOAD] Cloudinary cleanup also failed for {upload_result['public_id']}: {_cleanup.get('error')}")
                except Exception as _cu_err:
                    logging.warning(f"[UPLOAD] Cloudinary cleanup exception: {_cu_err}")
                return jsonify(
                    success=False,
                    message=f"File uploaded to Cloudinary, but database record creation failed: {file_record_result.get('message')}"
                ), 500
            
            logging.info(f"[UPLOAD SUCCESS] Document ID: {file_record_result.get('data', {}).get('id')}")

            # ── Track UPLOAD event (non-blocking) ───────────────────────
            try:
                track_user_event(user_id, 'UPLOAD', {
                    'document_id': file_record_result.get('data', {}).get('id'),
                    'subject_id': subject_id or None,
                    'semester': semester,
                    'document_type': document_type.lower()
                })
            except Exception:
                pass

            # If this upload was in response to a material request, mark the request accepted
            try:
                material_request_id = request.form.get('material_request_id')
                if material_request_id:
                    client = init_supabase()
                    if client:
                        client.table('material_requests').update({
                            'status': 'accepted',
                            'responder_id': user_id,
                            'responder_email': user_email,
                            'response_message': f"Uploaded file {file_record_result.get('data', {}).get('id')}",
                            'response_document_id': file_record_result.get('data', {}).get('id'),
                            'responded_at': 'now()'
                        }).eq('id', material_request_id).execute()
            except Exception as _e:
                logging.warning(f"[UPLOAD] Warning: could not mark material_request accepted: {_e}")

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
                # XP for this specific upload (before persist)
                cat = document_type.lower()
                raw_pts = POINTS_MAP.get(cat, DEFAULT_POINTS)
                xp_gained = round(raw_pts * 0.5, 2)  # pending = half pts initially
                result_rank = recalculate_and_persist_user_rank(user_id)
                new_score = result_rank.get('score', 0.0)
            except Exception as rank_err:
                logging.warning(f"[UPLOAD] Rank recalc failed (non-critical): {rank_err}")

            # ── Invalidate cache layers on successful upload ────────
            # File list, search results, and dropdowns are now stale
            cache.invalidate_files()
            cache.invalidate_dropdowns()
            cache.bump_version()

            return jsonify(
                success=True,
                message="File uploaded and recorded successfully! 🎉",
                data={
                    'url': upload_result['secure_url'],
                    'record_id': file_record_result.get('data', {}).get('id'),
                    'public_id': upload_result['public_id'],
                    'file_size': upload_result['bytes'],
                    'file_type': file_type_category,
                    'compressed': upload_result.get('bytes', file_size) < file_size,
                    'credits_granted': QUOTA_PER_UPLOAD,
                    'credits_remaining': _get_quota().get('credits', 0),
                    'xp_gained': xp_gained,
                    'new_score': new_score
                }
            ), 200
            
        except Exception as e:
            logging.error(f"[UPLOAD EXCEPTION] Upload error: {e}")
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

@app.route('/local-viewer')
@auth_required
def local_viewer():
    """Standalone page: open a local image/PDF, preview it, then upload to Cloudinary."""
    return render_template('p_local_preview.html')


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
        resp.headers['Cache-Control'] = 'private, no-store, must-revalidate'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Disposition'] = 'inline'
        resp.headers['Access-Control-Allow-Origin'] = request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place'
        resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
        resp.headers['Referrer-Policy'] = 'no-referrer'
        resp.headers['X-Download-Options'] = 'noopen'
        resp.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
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
    """Clean proxy endpoint for viewing docs — no URL encoding needed in PDF.js file= param.
    
    Security: (1) Firebase signed URLs expire in 1 hour,
    (2) doc_id is a UUID (unguessable), (3) CORS headers restrict embedding.
    
    Supports Range headers for PDF.js partial content requests.
    """

    # Note: Removed Referer check — it blocks legitimate PDF.js iframe fetches.
    # Security relies on: (1) Firebase signed URLs expire in 1 hour,
    # (2) doc_id is a UUID (unguessable), (3) CORS headers restrict embedding.

    # Optional: token-based access for programmatic clients
    token = request.args.get('token', '')
    if token and not _verify_pdf_token(doc_id, token):
        abort(403, description="Invalid or expired access token")

    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        abort(404)
    document = doc_res.get('data', {})
    file_url = document.get('file_url', '')
    # Handle Supabase tuple response format: (value, error)
    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    if not file_url or not isinstance(file_url, str):
        abort(404)

    # Check for cached signed URL before generating a new one
    if not file_url.startswith('http'):
        cache_key = f"signed-url:{doc_id}"
        try:
            cached_url, _ = cache.l1.get(cache_key)  # Returns (data, ttl_left) tuple
            if cached_url is not None:
                file_url = cached_url
            else:
                raise ValueError("Cache miss")
        except Exception:
            try:
                bucket = storage.bucket()
                blob = bucket.blob(file_url)
                signed = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
                # Handle both string and tuple returns from generate_signed_url
                file_url = signed[0] if isinstance(signed, (list, tuple)) else signed
                try:
                    cache.l1.set(cache_key, file_url, ttl=300)  # 5 min TTL
                except Exception:
                    pass  # Non-fatal: cache storage can fail
            except Exception as e:
                cred_ok = bool(os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON'))
                if not cred_ok or 'default app' in str(e).lower() or 'credential' in str(e).lower():
                    logging.error(
                        f"[VIEW-DOC] Firebase credentials missing/invalid for {doc_id}: {e}. "
                        "Set FIREBASE_SERVICE_ACCOUNT_JSON to a SERVICE ACCOUNT key JSON "
                        "(Firebase Console -> Project Settings -> Service accounts -> Generate new private key), "
                        "NOT the web client config (apiKey/authDomain/appId)."
                    )
                else:
                    logging.error(f"[VIEW-DOC] Signed URL error for {doc_id}: {e}")
                abort(500)

    # Final safety: coerce to string
    if isinstance(file_url, (list, tuple)):
        file_url = file_url[0] if file_url else ''
    file_url = str(file_url)

    from urllib.parse import urlparse
    parsed = urlparse(file_url)
    if parsed.hostname not in _ALLOWED_PROXY_HOSTS:
        abort(403)

    # Support Range headers for PDF.js partial content requests
    upstream_headers = {'User-Agent': 'AbhiHub-Proxy/1.0'}
    if request.headers.get('Range'):
        upstream_headers['Range'] = request.headers['Range']

    def _fetch(url):
        return requests.get(url, stream=True, timeout=30, verify=True, headers=upstream_headers)

    upstream = _fetch(file_url)

    # Self-heal: a cached or stored Firebase URL can go stale (signed URLs expire
    # in 1h; token-less public URLs are rejected by storage rules). On 403/404,
    # invalidate the cache, re-sign from the raw storage path, and retry once.
    if upstream.status_code in (403, 404) and parsed.hostname in ('firebasestorage.googleapis.com', 'storage.googleapis.com'):
        try:
            cache.l1.delete(f"signed-url:{doc_id}")
        except Exception:
            pass
        raw_path = document.get('file_url', '')
        if isinstance(raw_path, (list, tuple)):
            raw_path = raw_path[0] if raw_path else ''
        raw_path = str(raw_path or '')
        # Accept both bare storage paths ("premium/docs/x.pdf") and full URLs
        # ("https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<path>%2Ffile.pdf?...")
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
                cred_ok = bool(os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON'))
                logging.error(
                    f"[VIEW-DOC] Re-sign failed for {doc_id}: {e}. "
                    + ("" if cred_ok else
                       "FIREBASE_SERVICE_ACCOUNT_JSON is missing or invalid — set it to a SERVICE ACCOUNT key JSON "
                       "(Firebase Console -> Project Settings -> Service accounts -> Generate new private key).")
                )

    try:
        if upstream.status_code == 204:
            # Firebase returned 204 No Content — document not found or access denied.
            # Don't silently return an empty 200 (breaks PDF.js "0 of 0 pages").
            # Return a proper 404 with a user-facing message.
            msg = json.dumps({"error": "Document not available", "detail": f"No content found for document {doc_id}"})
            return Response(msg, status=404, content_type='application/json', headers={
                'Cache-Control': 'private, no-store, must-revalidate',
                'Content-Disposition': 'inline',
                'Access-Control-Allow-Origin': request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place',
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'SAMEORIGIN',
                'Referrer-Policy': 'no-referrer',
                'X-Download-Options': 'noopen',
                'X-Permitted-Cross-Domain-Policies': 'none',
            })
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
                
        response_headers = {
            'Cache-Control': 'private, no-store, must-revalidate',
            'Content-Disposition': 'inline',
            'Access-Control-Allow-Origin': request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'Referrer-Policy': 'no-referrer',
            'X-Download-Options': 'noopen',
            'X-Permitted-Cross-Domain-Policies': 'none',
        }
        
        # Preserve Content-Length if available (for PDF.js)
        if 'Content-Length' in upstream.headers:
            response_headers['Content-Length'] = upstream.headers['Content-Length']
        
        # Support 206 Partial Content for Range requests
        if upstream.status_code == 206:
            response_headers['Content-Range'] = upstream.headers.get('Content-Range', '')
            response_headers['Accept-Ranges'] = 'bytes'
        
        return Response(generate(),
                        status=upstream.status_code,
                        content_type=content_type,
                        headers=response_headers)
    except Exception as e:
        logging.error(f"[VIEW-DOC] Exception streaming {doc_id}: {e}")
        abort(502)



def get_all_files_unified():
    """
    Get all active documents from Supabase `abhihub.documents`.
    """
    
    # Check if we have an active session to pass the user_id for like/bookmark status
    current_user_id = None
    if getattr(request, 'endpoint', None) and 'user' in session:
        current_user_id = session['user'].get('uid')
        
    result = get_all_files_merged(current_user_id=current_user_id)
    files = result.get('data', [])
    
    logging.info(f"Fetched {len(files)} files directly from Supabase documents.")
    
    return files


@app.route('/profile')
@auth_required
def profile():
    
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
    """Phase 19: Global Gamification Leaderboard — cached at L1 for 10min."""

    # Optional filter by college if requested
    college_id = request.args.get('college_id')

    cache_key = f"leaderboard:{college_id or 'all'}"
    def fetch_lb():
        result = get_leaderboard_data(college_id=college_id, limit=50)
        return result.get('data', []) if result.get('success') else []

    leaderboard_data = cache.get_cached(cache_key, level=cache.L2, ttl=cache.LONG, fetcher=fetch_lb)
    # Get current user for personalization in the template
    user_info = session.get('user')
    response = make_response(render_template('leaderboard.html',
                           leaderboard=leaderboard_data,
                           current_user=user_info))
    cache.set_cache_headers(response, max_age=cache.LONG, stale_while_revalidate=True)
    return response


@app.route('/account', methods=['GET'])
@auth_required
def account():
    """Display account management page"""
    
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
        'degree': request.form.get('degree'),
        'user_role': request.form.get('user_role'),
        'year_of_joining': request.form.get('year_of_joining'),
        'pursuing_year': request.form.get('pursuing_year') if request.form.get('pursuing_year') else None,
        'registration_number': request.form.get('registration_number')
    }
    
    # Fetch static form data ONCE (colleges/branches are now cached)
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
    """Display user settings page with account, notification, credit, and privacy controls."""
    user_data = session.get('user', {})
    return render_template('settings.html', user_data=user_data)


@app.route('/support')
@auth_required
def support():
    return render_template('p_support.html')

# Public pages
@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/open-source')
def open_source():
    """Open source page"""
    return render_template('open_source.html')

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


@app.route('/search')
def search_page():
    """Public search page (renders the orphaned p_search.html UI).
    Accepts ?q=... to prefill + auto-run the search on load."""
    q = request.args.get('q', '').strip()
    # Pass the query so the client can prefill + trigger SearchManager.
    return render_template('p_search.html', initial_query=q)

@app.route('/college/<college_slug>')
@app.route('/pyq/<college_slug>')
def college_landing(college_slug):
    """Dynamic SEO-optimized college landing page.
    Priority: brand group page > individual college page > 404
    """

    def slugify(text):
        return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')

    route_prefix = '/pyq' if request.path.startswith('/pyq') else '/college'

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
                return redirect(f"{route_prefix}/{canonical_slug}", code=301)
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
        return redirect(f"{route_prefix}/{canonical_slug}", code=301)

    # 4. Check doc count — show coming soon if empty
    COMING_SOON_THRESHOLD = 1  
    stats = get_college_stats(college_id).get('data', {})
    total_docs = stats.get('total_documents', 0)

    if total_docs < COMING_SOON_THRESHOLD:
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
@app.route('/pyq/<college_slug>/<department_slug>')
def department_landing(college_slug, department_slug):
    """Dynamic SEO-optimized department landing page"""
    
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
        client = init_supabase()
        if client:
            try:
                like_check = client.table('document_votes').select('id').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
                document['is_liked'] = bool(like_check.data)
            except Exception:
                pass
            try:
                bm_check = client.table('bookmarks').select('id').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
                document['is_bookmarked'] = bool(bm_check.data)
            except Exception:
                pass
            
    # Track view (shared helper — see log_document_view)
    log_document_view(
        file_name=title,
        file_url=document.get('file_url'),
        record_id=doc_id,
        file_type=document.get('file_type'),
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
        logging.error(f"[Supabase] Error fetching suggestions: {e}")

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

    # --- Turnstile siteverify ---
    turnstile_token = data.get('turnstile_token', '')
    turnstile_secret = os.environ.get('TURNSTILE_SECRET', '')
    if not turnstile_secret:
        logging.warning('[Turnstile] TURNSTILE_SECRET not set; rejecting contact submission')
        return jsonify({'success': False, 'error': 'Server misconfiguration'}), 500
    try:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
        ts_resp = requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data={
                'secret': turnstile_secret,
                'response': turnstile_token,
                'remoteip': client_ip,
            },
            timeout=5
        )
        ts_resp.raise_for_status()
        ts_result = ts_resp.json()
    except Exception as e:
        logging.warning(f'[Turnstile] siteverify error: {e}')
        return jsonify({'success': False, 'error': 'Security check failed'}), 403
    if not ts_result.get('success'):
        logging.warning(f'[Turnstile] verification failed: {ts_result.get("error-codes")}')
        return jsonify({'success': False, 'error': 'Security check failed'}), 403
    # --- end Turnstile ---

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
@auth_required
def delete_account():
    """Account deletion request page"""
    return render_template('delete_account.html')

@app.route('/register')
def register():
    """Register page (alias for signup)"""
    return redirect(url_for('signup'))

@app.route('/dashboard')
@auth_required
def dashboard():
    """Dashboard for authenticated users.

    This handler was previously named 'premium'. It is the sole
    registered handler for /dashboard, fixing a security issue where
    a duplicate unauthenticated dashboard() route shadowed this handler
    via Flask first-rule-wins routing.
    """
    # Use unified documents from database
    user_info = session.get('user', {})
    current_user_id = user_info.get('uid')
    files = get_all_file_records_formatted(current_user_id=current_user_id)
    
    # Extract SEO data
    all_subjects = list(set([f.get('subject', '') for f in files if f.get('subject', '').strip()]))
    top_subjects = sorted(all_subjects)[:8]
    paper_count = len([f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')])
    notes_count = len([f for f in files if f.get('type', '').lower() in ('notes', 'note', 'imp questions', 'imp_questions')])
    
    seo_keywords = "AbhiHub, GHRCE papers, engineering papers, " + ", ".join(top_subjects) + ", exam resources, study materials"
    
    # User-specific personalization data
    user_data = None
    if 'user' in session:
        user_info = session['user']
        user_name = user_info.get('name', '')
        user_email = user_info.get('email', '')
        user_id = user_info.get('uid', '')
        
        # Get user's uploaded files
        user_files = [f for f in files if f.get('author', '') == user_name or f.get('author_email', '') == user_email]
        user_uploads_count = len(user_files)

        # Single-pass categorization
        user_notes_count = 0
        user_papers_count = 0
        user_practicals_count = 0
        user_subjects = set()
        for f in user_files:
            ft = f.get('type', '').lower()
            if ft == 'notes':
                user_notes_count += 1
            elif ft in ('pyq', 'papers'):
                user_papers_count += 1
            elif ft == 'practical':
                user_practicals_count += 1
            subj = f.get('subject', '').strip()
            if subj:
                user_subjects.add(subj)
        
        # Get file access history of the user (recently viewed files)
        history_result = get_user_file_history(user_email, limit=10)
        file_history = []
        if history_result.get('success'):
            file_history = history_result.get('data', [])
        
        # Get college name from profile
        college_name = ''
        try:
            profile_res = get_student_profile(user_id)
            profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}
            college_name = profile_data.get('college_name') or ''

            # Enforce profile completion — redirect if college not set
            if not profile_data or not profile_data.get('college_id'):
                flash("Welcome to AbhiHub! Please complete your profile to access all personalized features.", "warning")
                return redirect(url_for('account'))

            # Calculate global rank
            rank_list = calculate_user_ranks()
            _rank_lookup = {e['uploader_id']: (str(i + 1), e.get('points', 0))
                            for i, e in enumerate(rank_list)}
            global_rank = _rank_lookup.get(user_id, ('-', 0))[0]
            computed_score = _rank_lookup.get(user_id, ('-', 0))[1]

            # Reputation stats
            rep_stats = get_reputation_stats(user_id)
            students_helped = rep_stats.get('students_helped', 0) if rep_stats.get('success') else 0
            badges = rep_stats.get('badges', []) if rep_stats.get('success') else []
        except Exception as e:
            logging.error(f"[Dashboard] Error fetching profile/rank data: {e}")
            profile_data = {}
            global_rank = '-'
            computed_score = 0
            students_helped = 0
            badges = []

        user_data = {
            'name': user_name,
            'email': user_info.get('email', ''),
            'uploads_count': user_uploads_count,
            'notes_count': user_notes_count,
            'papers_count': user_papers_count,
            'practicals_count': user_practicals_count,
            'subjects_contributed': len(user_subjects),
            'user_files': user_files[:10],  # Latest 10 user files for "Your Files" section
            'role': profile_data.get('role', 'student') if profile_data else 'student',
            'reputation_score': max(computed_score, profile_data.get('reputation_score', 0)) if profile_data else computed_score,
            'rank_title': profile_data.get('rank_title', 'Beginner') if profile_data else 'Beginner',
            'is_verified': profile_data.get('is_verified', False) if profile_data else False,
            'subscription_tier': profile_data.get('subscription_tier', 'free') if profile_data else 'free',
            'global_rank': global_rank,
            'students_helped': students_helped,
            'badges': badges,
            'college_name': college_name,
            # Reliable gate for peer suggestions — college_id comes straight from
            # profiles (always set when profile is complete), unlike the students-row
            # join that get_student_profile depends on.
            'college_id': profile_data.get('college_id') or ''
        }
    else:
        file_history = []
        
    if user_data is None:
        user_data = {}
        
    user_data.setdefault('paper_quota_remaining', _get_quota().get('credits', 19))
    user_data.setdefault('students_helped', 0)
    user_data.setdefault('reputation_score', 0)
    user_data.setdefault('badges', [])
    user_data.setdefault('global_rank', '-')
    user_data.setdefault('rank_title', 'Beginner')
    user_data.setdefault('is_verified', False)
    user_data.setdefault('college_name', '')
    user_data.setdefault('subscription_tier', 'free')
    
    promo_context = {
        'remaining_views': user_data.get('paper_quota_remaining', 19) if user_data else 19,
        'students_helped': user_data.get('students_helped', 0) if user_data else 0,
        'reputation_score': user_data.get('reputation_score', 0) if user_data else 0,
        'upload_goal_month': 'May'
    }

    # Personalized & trending papers
    all_papers = [f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')]
    all_papers_by_views = sorted(all_papers, key=lambda f: f.get('view_count', 0), reverse=True)

    # Personalized: same college, sorted by views
    user_college = user_data.get('college_name', '') if user_data else ''
    if user_college:
        college_papers = [f for f in all_papers_by_views if f.get('college', '') == user_college]
        relevant_papers = college_papers[:8]
        # Hero stats: show college-specific counts
        paper_count = len(college_papers)
    else:
        relevant_papers = all_papers_by_views[:8]

    # Trending: top viewed overall (may overlap with relevant but that's fine)
    trending_papers = all_papers_by_views[:8]

    # Recent papers: newest first
    recent_papers = sorted(all_papers, key=lambda f: f.get('date', ''), reverse=True)[:8]

    # ── Notes: personalized & trending & recent ──────────────────────────
    notes_type_values = ('notes', 'note', 'imp questions', 'imp_questions')
    all_notes = [f for f in files if f.get('type', '').lower() in notes_type_values]
    all_notes_by_views = sorted(all_notes, key=lambda f: f.get('view_count', 0), reverse=True)

    # Personalized notes: same college, sorted by views
    if user_college:
        college_notes = [f for f in all_notes_by_views if f.get('college', '') == user_college]
        relevant_notes = college_notes[:8]
        # Hero stats: show college-specific counts
        notes_count = len(college_notes)
    else:
        relevant_notes = all_notes_by_views[:8]

    # Trending notes: top viewed overall
    trending_notes = all_notes_by_views[:8]

    # Recent notes: newest first
    recent_notes = sorted(all_notes, key=lambda f: f.get('date', ''), reverse=True)[:8]

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
                         recent_papers=recent_papers,
                         relevant_notes=relevant_notes,
                         trending_notes=trending_notes,
                         recent_notes=recent_notes)


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


        # Log file access (shared helper — see log_document_view)
        log_document_view(
            file_name=os.path.basename(pdf_name),
            file_url=url_for('pdf_proxy', pdf_name=pdf_name, _external=True),
            record_id=record_id,
            file_type='pdf',
            file_path=pdf_name,
        )
        
        # Use proxy URL — security is handled by @auth_required + Referer check
        if pdf_name.startswith('http'):
            proxy_url = pdf_name
        else:
            proxy_url = url_for('pdf_proxy', pdf_name=pdf_name, _external=True)

        # Fetch document metadata for info panel
        file_meta = {}
        if record_id:
            try:
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
    # Security: Verify the request comes from an authenticated session
    # The @auth_required decorator already ensures a valid user session.
    # Additionally, check that the Referer matches our domain to prevent
    # hotlinking by download managers that strip session cookies.
    referer = request.headers.get('Referer', '')
    if referer:
        ref_host = referer.split('/')[2] if len(referer.split('/')) > 2 else ''
        allowed = (ref_host == BASE_DOMAIN or
                   ref_host.endswith('.' + BASE_DOMAIN) or
                   'localhost' in ref_host or
                   '127.0.0.1' in ref_host or
                   '0.0.0.0' in ref_host)
        if not allowed:
            logging.warning(f"[PDF-PROXY] Blocked cross-origin PDF access from {referer} for {pdf_name}")
            abort(403, description="Access denied")
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
        # PDF security: force inline display, prevent download managers, no caching
        response.headers['Access-Control-Allow-Origin'] = request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type, Content-Range'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'
        response.headers['Content-Disposition'] = f'inline; filename="{os.path.basename(pdf_name)}"'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Cache-Control'] = 'private, no-store, must-revalidate'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Download-Options'] = 'noopen'
        response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        
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

def _trigger_indexnow(urls: list):
    """Submit changed public URLs to IndexNow for faster discovery."""
    if not INDEXNOW_KEY:
        logging.error("IndexNow is not configured: INDEX_NOW_BING_API_KEY is missing.")
        return False
    try:
        import requests as _req
        payload = {
            "host": BASE_DOMAIN,
            "key": INDEXNOW_KEY,
            "keyLocation": f"https://{BASE_DOMAIN}/{INDEXNOW_KEY}.txt",
            "urlList": [u for u in urls if u.startswith('https://')]
        }
        if not payload["urlList"]:
            return False
        submission = _req.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        if submission.status_code in (200, 202):
            logging.info("IndexNow accepted %s URL(s).", len(payload["urlList"]))
            return True
        logging.warning(
            "IndexNow rejected submission (%s): %s",
            submission.status_code,
            submission.text[:500],
        )
    except requests.RequestException as exc:
        logging.warning("IndexNow submission request failed: %s", exc)
    return False

@app.route('/indexnow', methods=['POST'])
def indexnow():
    if not INDEXNOW_KEY:
        return jsonify({"message": "IndexNow is not configured"}), 503

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
    
    try:
        response = requests.post(
            indexnow_url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
    except requests.RequestException as exc:
        logging.warning("Manual IndexNow submission failed: %s", exc)
        return jsonify({"message": "IndexNow request could not be sent"}), 502
    
    if response.status_code in (200, 202):
        return jsonify({"message": "URLs submitted successfully"}), 200
    else:
        logging.warning("Manual IndexNow submission rejected (%s): %s", response.status_code, response.text[:500])
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
    cached at L2 for 5 minutes to reduce Supabase load.
    Invalidates automatically after uploads/deletes.
    """
    global data_cache

    # load once - now using unified file list with L2 cache
    if not data_cache:
        data_cache = cache.get_cached(
            "files:list:unified",
            level=cache.L2,
            ttl=cache.MEDIUM,
            fetcher=lambda: (lambda r: (logging.info(f"Loaded {len(r)} files from unified sources for search cache") or r))(get_all_files_unified())
        )
        if data_cache is None:
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
    # Redirect trailing-slash to canonical /dashboard which has full user_data
    return redirect(url_for('dashboard'), code=301)

@app.route('/dashboard/search', methods=['POST', 'GET'])
@auth_required
def search():
    search_query = request.form.get('search') or request.args.get('search', '')
    if not search_query:
        return redirect(url_for('dashboard'))
    # Redirect to dashboard with search_query so the main route renders with full user_data
    return redirect(url_for('dashboard', search_query=search_query))

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
        history = get_notification_history()
        return jsonify({'success': True, 'history': history})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def _getSuggestedPeers(client, uid):
    """Fetch up to 8 suggested peers from the same college as the user."""
    suggested = []
    try:
        my_prof = client.table('profiles') \
            .select('college_id') \
            .eq('id', uid).limit(1).execute()
        if not my_prof.data:
            return suggested
        my_college_id = my_prof.data[0].get('college_id')
        if my_college_id:
            sg = client.table('profiles') \
                .select('id, full_name, email, rank_title, reputation_score, is_verified, colleges(name)') \
                .eq('college_id', my_college_id) \
                .neq('id', uid) \
                .order('reputation_score', desc=True) \
                .limit(8).execute()
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


@app.route('/api/chat/search-peers', methods=['GET'])
@auth_required
def chat_search_peers():
    """Peer search for chat — available to all authenticated users.

    Returns: id, full_name, email, rank_title, reputation_score,
    college_name, is_verified, uploads_count, viewed_count
    """
    q = request.args.get('q', '').strip()
    uid = _get_uid()
    if len(q) < 2:
        return jsonify({'success': True, 'users': [], 'suggested': []})

    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'users': [], 'suggested': [], 'error': 'DB error'}), 500

        # Special internal flag: return only suggested peers (no text search)
        if q == '__suggested__':
            return jsonify({'success': True, 'users': [], 'suggested': _getSuggestedPeers(client, uid)})

        # Basic profile search — include college via join
        res = client.table('profiles') \
            .select('id, full_name, email, rank_title, reputation_score, is_verified, college_id, colleges(name)') \
            .or_(f'full_name.ilike.%{q}%,email.ilike.%{q}%') \
            .limit(10).execute()
        users = []
        for u in (res.data or []):
            col = u.get('colleges') or {}
            # Count uploads and viewed for each user
            upload_count = 0
            viewed_count = 0
            try:
                docs = client.table('documents').select('id', count='exact') \
                    .eq('uploader_id', u['id']).execute()
                upload_count = docs.count or 0
            except Exception:
                pass
            try:
                views = client.table('user_file_views').select('id', count='exact') \
                    .eq('user_id', u['id']).execute()
                viewed_count = views.count or 0
            except Exception:
                pass
            users.append({
                'id': u.get('id'),
                'full_name': u.get('full_name') or 'Student',
                'email': u.get('email', ''),
                'rank_title': u.get('rank_title', 'Student'),
                'reputation_score': u.get('reputation_score', 0),
                'college_name': col.get('name') or '',
                'is_verified': u.get('is_verified', False),
                'uploads_count': upload_count,
                'viewed_count': viewed_count
            })

        return jsonify({'success': True, 'users': users, 'suggested': _getSuggestedPeers(client, uid)})
    except Exception as e:
        return jsonify({'success': False, 'users': [], 'suggested': [], 'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@auth_required
@admin_required
def admin_get_users():
    """Get list of users for admin dashboard"""
    try:
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

@app.route('/api/admin/stats', methods=['GET'])
@auth_required
@admin_required
def get_admin_stats():
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
        
        users_res = client.table('profiles').select('id', count='exact').execute()
        total_users = users_res.count if hasattr(users_res, 'count') else len(users_res.data or [])
        
        approved_res = client.table('documents').select('id', count='exact').eq('status', 'approved').execute()
        approved_docs = approved_res.count if hasattr(approved_res, 'count') else len(approved_res.data or [])
        
        pending_res = client.table('documents').select('id', count='exact').eq('status', 'pending').execute()
        pending_docs = pending_res.count if hasattr(pending_res, 'count') else len(pending_res.data or [])
        
        from push_notifications import load_subscriptions
        try:
            subscriptions = load_subscriptions()
            total_subs = len(subscriptions)
        except Exception:
            total_subs = 0
            
        messages_count = 0
        if os.path.exists(CONTACT_FILE):
            try:
                with open(CONTACT_FILE, 'r') as f:
                    messages = json.load(f)
                    messages_count = len(messages)
            except Exception:
                pass
                
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'approved_documents': approved_docs,
                'pending_documents': pending_docs,
                'total_subscribers': total_subs,
                'total_messages': messages_count
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/pending-documents', methods=['GET'])
@auth_required
@admin_required
def get_pending_documents():
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
            
        res = client.table('documents')\
            .select('id, title, document_category, file_type, file_url, created_at, uploader_id, profiles(full_name, email)')\
            .eq('status', 'pending')\
            .order('created_at', desc=True)\
            .execute()
            
        return jsonify({'success': True, 'documents': res.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/analytics')
@auth_required
@admin_required
def admin_analytics_dashboard():
    """Admin analytics dashboard page."""
    return render_template('admin_analytics.html')


# ─── Admin Economy Dashboard (Dynamic Access & Contribution) ───

@app.route('/api/my-access', methods=['GET'])
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
        return jsonify({
            'success': True,
            'level': gate.get('level'),
            'limits': {k: v for k, v in gate.items() if k != 'level'},
            'uploads_today_remaining': quota.get('remaining'),
            'progress': progress,
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/economy')
@auth_required
@admin_required
def admin_economy_dashboard():
    """Admin economy dashboard: edit scoring config, view level distribution."""
    return render_template('admin_economy.html')


@app.route('/api/admin/economy/config', methods=['GET'])
@auth_required
@admin_required
def api_admin_economy_get_config():
    """Return all scoring_config entries."""
    try:
        res = init_supabase().table('scoring_config').select('*').order('key').execute()
        return jsonify({'success': True, 'config': res.data or []}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/economy/config', methods=['POST'])
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

        # Bust the in-process config cache so changes apply immediately
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


@app.route('/api/admin/economy/overview', methods=['GET'])
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


@app.route('/api/admin/economy/user/<user_id>', methods=['POST'])
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
        # Manual override marker via negative ccr sentinel is hacky; instead store on profile
        client.table('profiles').update({'access_level': level}).eq('id', user_id).execute()
        logging.info(f"[ECONOMY] admin set user {user_id} access_level={level}")
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/approve-document', methods=['POST'])
@auth_required
@admin_required
def approve_document():
    try:
        data = request.get_json()
        doc_id = data.get('document_id')
        if not doc_id:
            return jsonify({'success': False, 'error': 'Document ID is required'}), 400
            
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
            
        doc_res = client.table('documents').select('uploader_id').eq('id', doc_id).limit(1).execute()
        if not doc_res.data:
            return jsonify({'success': False, 'error': 'Document not found'}), 404
            
        uploader_id = doc_res.data[0].get('uploader_id')
        client.table('documents').update({'status': 'approved'}).eq('id', doc_id).execute()
        
        if uploader_id:
            recalculate_and_persist_user_rank(uploader_id)
            
        return jsonify({'success': True, 'message': 'Document approved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/reject-document', methods=['POST'])
@auth_required
@admin_required
def reject_document():
    try:
        data = request.get_json()
        doc_id = data.get('document_id')
        if not doc_id:
            return jsonify({'success': False, 'error': 'Document ID is required'}), 400
            
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'error': 'Database client not initialized'}), 500
            
        doc_res = client.table('documents').select('uploader_id').eq('id', doc_id).limit(1).execute()
        uploader_id = doc_res.data[0].get('uploader_id') if doc_res.data else None
        
        try:
            client.table('search_documents').delete().eq('file_id', doc_id).execute()
        except Exception:
            pass
            
        client.table('documents').delete().eq('id', doc_id).execute()

        if uploader_id:
            # Anti-abuse: penalize the uploader for removed/spam content
            try:
                from methods.scoring_engine import get_config
                pts = get_config('points') or {}
                penalty = float(pts.get('spam_penalty_min', -10))
                award_contribution_xp(
                    uploader_id, 'content_removed', doc_id, 'document',
                    'Document rejected/removed by moderation', base_xp=penalty
                )
            except Exception as pen_err:
                logging.warning(f"[SCORING] removal penalty skipped: {pen_err}")
            recalculate_and_persist_user_rank(uploader_id)

        return jsonify({'success': True, 'message': 'Document rejected and deleted successfully'})
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
    DEFAULT_POINTS,
    POINTS_MAP,
    _doc_to_json,
    add_comment,
    add_new_entity,
    add_paper_verification,
    award_contribution_xp,
    calculate_user_ranks,
    check_profile_completed,
    create_or_update_student_profile,
    create_subject_request,
    ensure_referral_code,
    get_all_branches,
    get_all_colleges,
    get_all_file_records_formatted,
    get_all_files_merged,
    get_college_by_slug,
    get_comments,
    get_contribution_timeline,
    get_department_by_slug,
    get_department_stats,
    get_departments_by_college,
    get_document_by_id_rich,
    get_leaderboard_data,
    get_notification_history,
    get_onboarding_status,
    get_papo_meter_data,
    get_pending_storage_assets,
    get_pending_verification_papers,
    get_recent_department_files,
    get_recent_subject_files,
    get_reputation_stats,
    get_sitemap_urls,
    get_student_profile,
    get_subject_stats,
    get_subjects_by_department,
    get_subjects_by_slug,
    get_user_file_history,
    get_user_notifications,
    get_user_peer_materials_db,
    get_user_uploaded_files,
    get_waitlist_count,
    init_supabase,
    init_supabase_admin,
    join_college_waitlist,
    log_label_audit,
    log_notification,
    log_security_audit_event,
    mark_notifications_read,
    mark_storage_asset_labeled,
    mark_welcome_seen,
    recalculate_and_persist_user_rank,
    register_referral,
    save_file_access,
    save_file_record,
    search_users_db,
    toggle_bookmark,
    toggle_like,
    track_user_event,
    update_document_metadata,
    validate_uuid,
    verify_hierarchy,
)

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
            'size': 'Unknown',
            'format': (f.get('mime') or 'unknown').split('/')[-1],
            'record_id': None,
            'verified': False,
            'verification_status': None,
            'like_count': 0,
            'bookmark_count': 0,
            'comment_count': 0,
            'view_count': 0
        })
        
    # Fetch labeled count (storage_assets with status 'LABELED')
    labeled_count = 0
    try:
        client = init_supabase()
        if client:
            res = client.table('storage_assets').select('id', count='exact').eq('status', 'LABELED').execute()
            labeled_count = res.count or 0
    except Exception as e:
        logging.warning(f"[STORE-ROOM] Error fetching labeled count: {e}")
        
    _unlabeled_cache['data'] = unlabeled_files
    _unlabeled_cache['labeled_count'] = labeled_count
    _unlabeled_cache['timestamp'] = now
    
    return unlabeled_files, labeled_count

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
    
    logging.info("=== Running upload notifications task ===")
    result = run_upload_notifications_task()
    logging.info(f"Complete: {result['sent']} sent, {result['failed']} failed, {result['total']} total")
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

# ─── AI Paper Q&A & Unlimited OCR ───────────────────────────────────────────
@app.route('/api/ask-paper', methods=['POST'])
@auth_required
def api_ask_paper():
    """Ask a question about a paper. Extracts text via pypdf/fitz or vision OCR first, then queries any LLM."""
    try:
        # --- Hour-based Rate Limiter (5 requests per hour) ---
        user = session.get('user', {})
        user_id = user.get('uid') or user.get('email')
        if user_id:
            import time
            now = time.time()
            one_hour_ago = now - 3600
            # Clean up old timestamps and retrieve current user history
            timestamps = [t for t in _chat_history.get(user_id, []) if t > one_hour_ago]
            _chat_history[user_id] = timestamps
            if len(timestamps) >= 5:
                return jsonify({
                    'success': False,
                    'message': 'You have reached the limit of 5 chats per hour. Please try again later.'
                }), 429
            # Record this chat request
            _chat_history[user_id].append(now)

        data = request.get_json(silent=True) or {}
        doc_id = (data.get('doc_id') or data.get('document_id') or '').strip()
        question = (data.get('question') or '').strip()
        selected_model = _resolve_model(data.get('model'))
        logging.info(f"[AI] ask-paper doc_id={doc_id!r} question_len={len(question)} model={selected_model} user_id={user_id}")

        if not doc_id or not question:
            logging.warning(f"[AI] ask-paper 400: doc_id={doc_id!r} question={question!r} raw_body={request.data[:200]}")
            return jsonify({'success': False, 'message': 'doc_id and question are required'}), 400

        # Always fetch raw file_url from DB
        client = init_supabase()
        raw = client.table('documents').select('file_url, title, document_category').eq('id', doc_id).single().execute()
        if not raw.data:
            return jsonify({'success': False, 'message': 'Document not found'}), 404

        file_url = raw.data.get('file_url', '')
        doc_title = raw.data.get('title', 'Unknown')
        doc_category = raw.data.get('document_category', '')

        # Resolve Firebase storage paths to real HTTP URLs
        if file_url and not file_url.startswith('http'):
            try:
                bucket = storage.bucket()
                blob = bucket.blob(file_url)
                file_url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
            except Exception as e:
                logging.warning(f"[AI] Firebase signed URL failed: {e}")
                return jsonify({'success': False, 'message': 'Could not resolve file URL'}), 400

        if not file_url:
            return jsonify({'success': False, 'message': 'File URL not available'}), 400

        # --- Step 1: Get document text (free, unlimited) ---
        import base64
        try:
            file_resp = requests.get(file_url, timeout=30, headers={'User-Agent': 'AbhiHub-AI/1.0'})
        except Exception as e:
            logging.warning(f"[AI] File fetch failed: {e}")
            return jsonify({'success': False, 'message': 'Could not fetch document file'}), 502
        if not file_resp.ok:
            logging.warning(f"[AI] File fetch HTTP {file_resp.status_code} for {file_url[:80]}")
            return jsonify({'success': False, 'message': f'Document fetch failed ({file_resp.status_code})'}), 502

        content_bytes = file_resp.content
        content_type = file_resp.headers.get('Content-Type', '').split(';')[0].lower()
        is_pdf = 'pdf' in content_type or file_url.lower().endswith('.pdf') or content_bytes.startswith(b'%PDF')

        doc_text = ''
        img_bytes = None
        img_mime = None

        if is_pdf:
            doc_text, img_bytes, img_mime = extract_pdf_info(content_bytes)
        
        # If no native text extracted, cannot proceed (OCR removed)
        if not doc_text or len(doc_text.strip()) < 10:
            return jsonify({'success': False, 'message': 'Could not extract text from this document.'}), 422

        # --- Step 2: Answer question using extracted text ---
        system_prompt = (
            f"You are a helpful AI study assistant for AbhiHub students.\n"
            f"CRITICAL RULE: Only answer questions directly related to AbhiHub, academic courses, or the provided document content.\n"
            f"If the question is unrelated to the document, say so and guide the user to search the website.\n\n"
            f"Document: {doc_title} ({doc_category})\n"
            f"--- DOCUMENT CONTENT ---\n{doc_text[:4000]}\n--- END ---\n\n"
            f"Give clear, accurate, well-formatted answers using Markdown."
        )

        openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip().strip("'\"")
        answer = None

        if openrouter_key:
            # Try each free text model in order — stop at first success
            for model_id in AI_MODELS:
                try:
                    resp = requests.post(
                        'https://openrouter.ai/api/v1/chat/completions',
                        headers={
                            'Authorization': f'Bearer {openrouter_key}',
                            'Content-Type': 'application/json',
                            'HTTP-Referer': 'https://abhihub.com',
                            'X-Title': 'AbhiHub'
                        },
                        json={
                            'model': model_id,
                            'messages': [
                                {'role': 'system', 'content': system_prompt},
                                {'role': 'user', 'content': question}
                            ],
                            'max_tokens': 600,
                            'temperature': 0.2,
                            'provider': {'allow_fallbacks': True, 'sort': 'throughput'}
                        },
                        timeout=30
                    )
                    if resp.ok:
                        choices = resp.json().get('choices', [])
                        if choices:
                            answer = choices[0]['message']['content']
                            logging.info(f"[AI] Q&A answered via {model_id}")
                            break
                    elif resp.status_code == 429:
                        logging.warning(f"[AI] {model_id} rate-limited, trying next")
                        continue
                    else:
                        logging.warning(f"[AI] {model_id} error {resp.status_code}: {resp.text[:100]}")
                        break
                except Exception as ex:
                    logging.warning(f"[AI] {model_id} failed: {ex}")
                    continue

        if answer:
            return jsonify({'success': True, 'answer': answer.strip()}), 200

        return jsonify({'success': False, 'message': 'All AI models are currently busy. Please try again in a moment.'}), 502

    except Exception as e:
        logging.error(f"[AI] ask-paper error: {e}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500


@app.route('/api/extract-ocr', methods=['POST'])
@auth_required
def api_extract_ocr():
    """Extract OCR text from paper image or PDF using free PyPDF/PyMuPDF or Vision models."""
    try:
        data = request.get_json(silent=True) or {}
        doc_id = (data.get('doc_id') or '').strip()
        selected_model = _resolve_model(data.get('model'))
        logging.info(f"[AI] extract-ocr using model: {selected_model}")
        if not doc_id:
            return jsonify({'success': False, 'message': 'doc_id required'}), 400

        client = init_supabase()
        raw = client.table('documents').select('file_url').eq('id', doc_id).single().execute()
        file_url = raw.data.get('file_url', '') if raw.data else ''

        # Resolve Firebase storage paths to real HTTP URLs
        if file_url and not file_url.startswith('http'):
            try:
                bucket = storage.bucket()
                blob = bucket.blob(file_url)
                file_url = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
            except Exception as e:
                logging.warning(f"[AI] OCR Firebase signed URL failed: {e}")
                return jsonify({'success': False, 'message': 'Could not resolve file URL'}), 400

        if not file_url:
            return jsonify({'success': False, 'message': 'File URL not available'}), 400

        import base64
        try:
            file_resp = requests.get(file_url, timeout=30, headers={'User-Agent': 'AbhiHub-AI/1.0'})
        except Exception as e:
            logging.warning(f"[AI] OCR file fetch failed: {e}")
            return jsonify({'success': False, 'message': 'Could not fetch file'}), 502
        if not file_resp.ok:
            return jsonify({'success': False, 'message': 'Could not fetch file'}), 502

        content_bytes = file_resp.content
        content_type = file_resp.headers.get('Content-Type', '').split(';')[0].lower()
        is_pdf = 'pdf' in content_type or file_url.lower().endswith('.pdf') or content_bytes.startswith(b'%PDF')

        # 1. Fast, Unlimited, 100% Free text extraction for PDFs
        if is_pdf:
            pdf_text, pdf_img_bytes, pdf_img_mime = extract_pdf_info(content_bytes)
            if pdf_text and len(pdf_text.strip()) > 50:
                # Cache native PDF text at L1 for 1hr — extraction is free, but saves repeated work
                cache.l1.set(f"ocr:pdf:{doc_id}", pdf_text.strip(), ttl=3600)
                return jsonify({'success': True, 'ocr_text': pdf_text.strip(), 'source': 'pdf_native'}), 200

            if pdf_img_bytes:
                content_bytes = pdf_img_bytes
                content_type = pdf_img_mime or 'image/png'

        # Check if we already have a cached vision OCR result
        cached_ocr = cache.l1.get(f"ocr:vision:{doc_id}")
        if cached_ocr[0] is not None:
            return jsonify({'success': True, 'ocr_text': cached_ocr[0], 'source': 'vision_ai_cached'}), 200

        return jsonify({'success': False, 'message': 'OCR feature is not available.'}), 501

    except Exception as e:
        logging.error(f"[AI] extract-ocr error: {e}")
        return jsonify({'success': False, 'message': f'OCR Error: {str(e)}'}), 500
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
        
    result = add_new_entity(entity_type, name, short_name, code, semester, parent_id)
    return jsonify(result), 200 if result.get('success') else 500

# ─── Peer User Search & Material Sharing APIs ──────────────────────────────
@app.route('/api/users/search', methods=['GET'])
@auth_required
def api_search_users():
    """Search student profiles by query string."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': True, 'users': []})
    users = search_users_db(q)
    return jsonify({'success': True, 'users': users})

@app.route('/api/user/<target_user_id>/materials', methods=['GET'])
@auth_required
def api_get_peer_materials(target_user_id):
    """Get target student's uploaded & referred study materials."""
    res = get_user_peer_materials_db(target_user_id)
    return jsonify(res)


@app.route('/api/chat/peer/<target_user_id>/materials-summary', methods=['GET'])
@auth_required
def api_chat_peer_materials_summary(target_user_id):
    """Quick material summary for chat — uploads count + recent 5 viewed files.

    Returns {success: true, user: {...}, uploads_count, recent_views: [...]}
    """
    res = get_user_peer_materials_db(target_user_id)
    if not res.get('success'):
        return jsonify({'success': False, 'message': 'User not found'}), 404
    return jsonify({
        'success': True,
        'user': res.get('user', {}),
        'uploads_count': len(res.get('uploads', [])),
        'recent_views': res.get('referred', [])[:5]
    })


@app.route('/api/request-material', methods=['POST'])
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
    sender_name = sender_user.get('name', 'A peer student')
    sender_email = sender_user.get('email', '')
    
    # Store or log request (simulated notification trigger)
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
        logging.error(f"[RequestMaterial] DB insert error (non-fatal): {e}")

    return jsonify({
        'success': True,
        'message': 'Request sent to the student'
    }), 200


@app.route('/api/material-requests', methods=['GET'])
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

        # Try to select requester profile inline; fallback to simple select if it fails
        try:
            res = client.table('material_requests')\
                .select('id, requester_id, target_user_id, subject, details, status, created_at, profiles!material_requests_requester_id_fkey(full_name,email)')\
                .eq('target_user_id', uid).order('created_at', desc=True).execute()
        except Exception:
            res = client.table('material_requests')\
                .select('id, requester_id, target_user_id, subject, details, status, created_at')\
                .eq('target_user_id', uid).order('created_at', desc=True).execute()

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
        logging.error(f"[MaterialRequests] Error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500


@app.route('/api/material-request/respond', methods=['POST'])
@auth_required
def api_respond_material_request():
    data = request.get_json() or {}
    req_id = data.get('id')
    action = data.get('action')  # 'accept' or 'reject'
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

        if action == 'accept':
            # Mark accepted; uploader should attach material_request_id when uploading file
            upd = {
                'status': 'accepted',
                'responder_id': uid,
                'responder_email': user_email,
                'response_message': message,
                'responded_at': 'now()'
            }
        else:
            upd = {
                'status': 'rejected',
                'responder_id': uid,
                'responder_email': user_email,
                'response_message': message,
                'responded_at': 'now()'
            }

        client.table('material_requests').update(upd).eq('id', req_id).execute()
        return jsonify({'success': True, 'message': f'Request {action}ed'}), 200
    except Exception as e:
        logging.error(f"[MaterialRequests] Respond error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

# ── Peer Chat SocketIO relay — strict 2-person rooms ─────────────────────────
# Server NEVER persists message content. Room IDs are deterministic pairs so
# only the two participants can ever be in the same room.

_chat_online = {}        # {user_id: {sid, name}}
_chat_online_http = {}   # {user_id: {time, name}}

def _pair_room(uid_a, uid_b):
    """Deterministic private room for exactly two users."""
    return 'cr_' + '_'.join(sorted([uid_a, uid_b]))

def _get_uid():
    user = session.get('user', {})
    return user.get('uid') or user.get('id') or user.get('user_id')

@socketio.on('connect')
def chat_connect():
    uid = _get_uid()
    if not uid:
        return
    user = session.get('user', {})
    name = user.get('name') or (user.get('user_metadata') or {}).get('full_name') or user.get('email', 'Student')
    _chat_online[uid] = {'sid': request.sid, 'name': name}
    join_room(uid)  # personal inbox room
    join_room('online-counter-room')  # for targeted online list broadcasts
    # Notify all connected clients of updated list
    socketio.emit('chat_online_update', {'online': _safe_online_list()})

@socketio.on('disconnect')
def chat_disconnect():
    uid = _get_uid()
    if uid and _chat_online.get(uid, {}).get('sid') == request.sid:
        del _chat_online[uid]
        socketio.emit('chat_online_update', {'online': _safe_online_list()})

def _get_merged_online_users():
    import time
    now_t = time.time()
    # Prune old HTTP users — users stay "online" for 1 hour after last activity
    ONLINE_WINDOW_S = 60 * 60
    to_delete = [k for k, v in _chat_online_http.items() if now_t - v['time'] > ONLINE_WINDOW_S]
    for k in to_delete:
        del _chat_online_http[k]
    # Merge socket & HTTP
    merged = {}
    for k, v in _chat_online.items():
        merged[k] = v['name']
    for k, v in _chat_online_http.items():
        merged[k] = v['name']
    return [{'id': k, 'name': name} for k, name in merged.items()]

def _safe_online_list():
    return _get_merged_online_users()

@socketio.on('chat_join')
def chat_join(data):
    """Client joins the private 2-person room for a specific conversation."""
    uid = _get_uid()
    peer_id = data.get('peer')
    if not uid or not peer_id or uid == peer_id:
        return
    room = _pair_room(uid, peer_id)
    join_room(room)
    emit('chat_joined', {'room': room})

@socketio.on('chat_send')
def chat_send(data):
    """Relay to the private pair room. Server NEVER stores the content."""
    uid = _get_uid()
    peer_id = data.get('to')
    if not uid or not peer_id or uid == peer_id:
        return
    room = _pair_room(uid, peer_id)
    payload = {
        'from': uid,
        'text': str(data.get('text', ''))[:2000],
        'ts': data.get('ts'),
        'sender_meta': data.get('sender_meta', {})
    }
    # Emit to the private room — only the two joined participants receive it
    emit('chat_receive', payload, to=room)

@socketio.on('chat_request_history')
def chat_request_history(data):
    uid = _get_uid()
    peer_id = data.get('to')
    if uid and peer_id:
        emit('chat_history_request', {'from': uid}, to=peer_id)

@socketio.on('chat_history_resend')
def chat_history_resend(data):
    uid = _get_uid()
    peer_id = data.get('to')
    if uid and peer_id:
        emit('chat_history_receive', {'messages': data.get('messages', []), 'from': uid}, to=peer_id)


@app.route('/api/chat/online')
@auth_required
def chat_online_users():
    """Returns currently online users for the dashboard widget, registering the caller's online heartbeat."""
    import time
    uid = _get_uid()
    if uid:
        user = session.get('user', {})
        name = user.get('name') or (user.get('user_metadata') or {}).get('full_name') or user.get('email', 'Student')
        _chat_online_http[uid] = {'time': time.time(), 'name': name}
        # Notify only clients in the 'online-counter' room (dashboard widgets only)
        # Avoids broadcasting to chat pages that don't need frequent updates
        socketio.emit('chat_online_update', {'online': _safe_online_list()}, to='online-counter-room')

    all_users = _get_merged_online_users()
    users = [u for u in all_users if u['id'] != uid]
    return jsonify({'success': True, 'online': users})


@app.route('/chat')
@auth_required
def chat_page():
    return render_template('chat.html')

@app.route('/chat/<peer_id>')
@auth_required
def chat_with_peer(peer_id):
    return render_template('chat.html', preload_peer=peer_id)


@app.route('/profile/<user_id>')
def peer_profile(user_id):
    """Legacy peer profile route — redirects to the new /u/<user_id> URL."""
    return redirect(url_for('instagram_profile', user_id=user_id))


# ─── Crush API ──────────────────────────────────────────────────────────────

@app.route('/api/crush/<target_id>', methods=['POST'])
@auth_required
def api_crush_toggle(target_id):
    """Toggle a crush on target_id. Max 2 crushes per calendar year."""
    me = session['user']['uid']
    if me == target_id:
        return jsonify({'success': False, 'message': 'Cannot crush yourself'}), 400
    year = datetime.utcnow().year
    try:
        if not validate_uuid(target_id):
            return jsonify({'success': False, 'message': 'Invalid user'}), 400
        client = init_supabase_admin()

        # Check if already crushed
        existing = client.table('user_crushes') \
            .select('id').eq('from_user', me).eq('to_user', target_id).eq('year', year).execute()
        if existing.data:
            # Un-crush
            client.table('user_crushes').delete() \
                .eq('from_user', me).eq('to_user', target_id).eq('year', year).execute()
            return jsonify({'success': True, 'action': 'removed', 'is_crush': False, 'is_match': False}), 200

        # Enforce 2-per-year limit
        count_res = client.table('user_crushes') \
            .select('id', count='exact').eq('from_user', me).eq('year', year).execute()
        if (count_res.count or 0) >= 2:
            return jsonify({'success': False, 'message': 'You can only mark 2 crushes per year'}), 429

        client.table('user_crushes').insert({'from_user': me, 'to_user': target_id, 'year': year}).execute()

        # Check mutual match
        mutual = client.table('user_crushes') \
            .select('id').eq('from_user', target_id).eq('to_user', me).eq('year', year).execute()
        is_match = bool(mutual.data)
        return jsonify({'success': True, 'action': 'added', 'is_crush': True, 'is_match': is_match}), 200
    except Exception as e:
        logging.error(f"[CRUSH] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/crush/status/<target_id>', methods=['GET'])
@auth_required
def api_crush_status(target_id):
    """Return crush/match state between current user and target."""
    me = session['user']['uid']
    year = datetime.utcnow().year
    try:
        if not validate_uuid(target_id):
            return jsonify({'success': False}), 400
        client = init_supabase_admin()
        i_crushed = bool(client.table('user_crushes').select('id')
            .eq('from_user', me).eq('to_user', target_id).eq('year', year).execute().data)
        they_crushed = bool(client.table('user_crushes').select('id')
            .eq('from_user', target_id).eq('to_user', me).eq('year', year).execute().data)
        crushes_used = (client.table('user_crushes').select('id', count='exact')
            .eq('from_user', me).eq('year', year).execute().count or 0)
        return jsonify({
            'success': True,
            'is_crush': i_crushed,
            'is_match': i_crushed and they_crushed,
            'crushes_used': crushes_used,
            'crushes_remaining': max(0, 2 - crushes_used)
        }), 200
    except Exception as e:
        return jsonify({'success': False}), 500

# ─────────────────────────────────────────────────────────────────────────────

@app.route('/u/<user_id>')
def instagram_profile(user_id):
    """Public, Instagram-friendly profile page with OG meta tags for sharing.

    URL: /u/<user_id>  — short, clean, perfect for Instagram bio links.
    No login required — anyone with the link can view the contributor's
    public profile and their shared materials.
    """
    if not validate_uuid(user_id):
        abort(404)
    client = init_supabase()
    if not client:
        abort(500)
    try:
        # pursuing_year / year_of_joining live in `students`, NOT profiles —
        # selecting them from profiles raises 42703 and 404s the whole page.
        pr = client.table('profiles') \
            .select('id, full_name, email, rank_title, reputation_score, is_verified, referral_code, college_id, department_id, colleges(name), departments(name, abbreviation)') \
            .eq('id', user_id).single().execute()
        if not pr.data:
            abort(404)
        p = pr.data
        # Optional academic details from the students row (may not exist)
        academic = {}
        try:
            st = client.table('students') \
                .select('pursuing_year, year_of_joining') \
                .eq('profile_id', user_id).limit(1).execute()
            if st.data:
                academic = st.data[0]
        except Exception as st_err:
            logging.info(f"[u/profile] students lookup unavailable for {user_id}: {st_err}")
        college_name = (p.get('colleges') or {}).get('name', '')
        dept = p.get('departments') or {}
        dept_name = dept.get('name') or dept.get('abbreviation') or ''
        peer = {
            'id': p.get('id'),
            'name': p.get('full_name') or 'Student',
            'email': p.get('email', ''),
            'rank_title': p.get('rank_title', 'Student'),
            'reputation_score': p.get('reputation_score', 0),
            'is_verified': p.get('is_verified', False),
            'referral_code': p.get('referral_code', ''),
            'college_name': college_name,
            'department_name': dept_name,
            'pursuing_year': academic.get('pursuing_year') or '',
            'year_of_joining': academic.get('year_of_joining') or '',
        }
    except Exception as e:
        logging.error(f"[u/profile] {e}")
        abort(404)

    # Uploads
    uploads = []
    try:
        docs = client.table('documents') \
            .select('id, title, document_category, view_count, subjects(name)') \
            .eq('uploader_id', user_id).eq('status', 'approved') \
            .order('created_at', desc=True).limit(12).execute()
        for d in (docs.data or []):
            uploads.append({
                'record_id': d.get('id'),
                'file-name': d.get('title') or 'Untitled',
                'type': d.get('document_category') or 'papers',
                'subject': (d.get('subjects') or {}).get('name', ''),
                'views': d.get('view_count', 0),
            })
    except Exception:
        pass

    # MemoryWall is public only while it is accepting responses.  Keep the
    # profile page useful even if the MemoryWall service is temporarily down.
    memory_wall = {'exists': False, 'is_open': False, 'url': '', 'response_count': 0}
    try:
        from methods.know_me import get_wall_by_user
        wall_result = get_wall_by_user(user_id)
        wall = wall_result.get('data') if wall_result.get('success') else None
        if wall:
            memory_wall = {
                'exists': True,
                'is_open': wall.get('status', 'open') != 'closed',
                'url': url_for('memorywall_public', slug=wall.get('slug')),
                'response_count': wall.get('response_count') or 0,
            }
    except Exception as e:
        logging.info(f"[u/profile] MemoryWall lookup unavailable: {e}")

    # Referred (recently viewed)
    referred = []
    try:
        views = client.table('document_views') \
            .select('document_id, documents(id, title, document_category, subjects(name))') \
            .eq('user_id', user_id).order('accessed_at', desc=True).limit(8).execute()
        seen = set()
        for v in (views.data or []):
            doc = v.get('documents') or {}
            did = doc.get('id')
            if did and did not in seen:
                seen.add(did)
                referred.append({
                    'record_id': did,
                    'file-name': doc.get('title') or 'Untitled',
                    'type': doc.get('document_category') or 'notes',
                    'subject': (doc.get('subjects') or {}).get('name', ''),
                })
    except Exception:
        pass

    # Crush state (only if viewer is logged in and not viewing own profile)
    crush_state = {'is_crush': False, 'is_match': False, 'crushes_remaining': 2, 'is_self': False}
    viewer_id = session.get('user', {}).get('uid')
    if viewer_id:
        if viewer_id == user_id:
            crush_state['is_self'] = True
        else:
            year = datetime.utcnow().year
            try:
                ac = init_supabase_admin() or client
                i_crushed = bool(ac.table('user_crushes').select('id')
                    .eq('from_user', viewer_id).eq('to_user', user_id).eq('year', year).execute().data)
                they_crushed = bool(ac.table('user_crushes').select('id')
                    .eq('from_user', user_id).eq('to_user', viewer_id).eq('year', year).execute().data)
                used = (ac.table('user_crushes').select('id', count='exact')
                    .eq('from_user', viewer_id).eq('year', year).execute().count or 0)
                crush_state = {
                    'is_crush': i_crushed,
                    'is_match': i_crushed and they_crushed,
                    'crushes_remaining': max(0, 2 - used),
                    'is_self': False,
                }
            except Exception:
                pass

    og_title = f"{peer['name']} on AbhiHub"
    og_description = f"{peer['name']} has shared {len(uploads)} study materials on AbhiHub."
    og_image = None

    return render_template('profile_instagram.html',
                           peer=peer,
                           uploads=uploads,
                           referred=referred,
                           memory_wall=memory_wall,
                           crush_state=crush_state,
                           og_title=og_title,
                           og_description=og_description,
                           og_image=og_image)


@app.route('/api/chat/user-info/<user_id>')
@auth_required
def chat_user_info(user_id):
    """Returns profile context shown in chat message badges."""
    try:
        prof = get_student_profile(user_id)
        # Check if we got a valid student name from the profile helper
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


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    socketio.run(app, debug=debug_mode)
