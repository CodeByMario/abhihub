# Gevent monkey patch must be executed at the very beginning
try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

import sys
sys.modules.setdefault('app', sys.modules[__name__])

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
from datetime import timedelta, datetime, timezone
import logging
from dotenv import load_dotenv
from supabase import create_client, ClientOptions

# Load environment variables
load_dotenv()

# IndexNow must use one environment-managed key for both submission and ownership verification.
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'www.abhihub.edu.eu.org').strip().lower()
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

if not firebase_admin._apps:
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

from jinja2 import FileSystemLoader, TemplateNotFound

class _AliasedTemplateLoader(FileSystemLoader):
    _ALIASES = {
        'app/dashboard.html': 'p_index.html',
        'app/account.html': 'p_account.html',
        'app/file_receiver.html': 'p_file_receiver.html',
        'app/view.html': 'p_view.html',
        'app/share_receiver.html': 'p_share_receiver.html',
        'app/upload_gate.html': 'p_upload_gate.html',
        'app/local_preview.html': 'p_local_preview.html',
        'app/upload.html': 'p_upload.html',
        'app/pdf_reader.html': 'p_pdf_reader.html',
        'app/store_room.html': 'p_store_room.html',
        'app/search.html': 'p_search.html',
        'site/login.html': 'p_login.html',
        'site/signup.html': 'p_signup.html',
        'site/landing.html': 'p_landing.html',
        'site/error.html': 'p_error.html',
        'site/support.html': 'p_support.html',
    }

    def get_source(self, environment, template):
        try:
            return super().get_source(environment, template)
        except TemplateNotFound:
            pass

        if template in self._ALIASES:
            try:
                return super().get_source(environment, self._ALIASES[template])
            except TemplateNotFound:
                pass

        if template.startswith('app/'):
            base = template[4:]
            for candidate in (f'p_{base}', base):
                try:
                    return super().get_source(environment, candidate)
                except TemplateNotFound:
                    pass

        if template.startswith('site/'):
            base = template[5:]
            for candidate in (f'p_{base}', base):
                try:
                    return super().get_source(environment, candidate)
                except TemplateNotFound:
                    pass

        if template.startswith('admin/'):
            base = template[6:]
            for candidate in (f'admin_{base}', base):
                try:
                    return super().get_source(environment, candidate)
                except TemplateNotFound:
                    pass

        raise TemplateNotFound(template)

app.jinja_loader = _AliasedTemplateLoader(app.template_folder)

# App Shell configuration flags
app.config['APP_SHELL_ENABLED'] = os.environ.get('APP_SHELL_ENABLED', 'true').lower() in ('true', '1', 'yes')
app.config['SHELL_IN_MOBILE_BROWSER'] = os.environ.get('SHELL_IN_MOBILE_BROWSER', 'false').lower() in ('true', '1', 'yes')

# Response caching to improve server response time
from flask import make_response, request
# Response caching and security headers
from flask import make_response, request
import time

@app.after_request
def apply_security_and_cache_headers(response):
    """Add security and cache control headers to all responses."""
    # Global Security Headers
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    
    # Allow iframe embedding for /ai/embed across all AbhiHub subdomains
    if request.path.startswith('/ai/embed'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self' https:; "
            "frame-ancestors 'self' https://*.abhihub.edu.eu.org https://abhihub.edu.eu.org http://localhost:* http://127.0.0.1:*"
        )
        response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
        if 'X-Frame-Options' in response.headers:
            del response.headers['X-Frame-Options']
    else:
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; object-src 'none'; base-uri 'self'; form-action 'self' https:; frame-ancestors 'self'"
        )

    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()')
    
    # HSTS in production
    if os.getenv('FLASK_ENV', 'production').lower() != 'development':
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

    # Security & Search Engine directives: noindex on private / app / admin areas
    if request.path.startswith(('/admin', '/app', '/dashboard', '/settings', '/earnings', '/upload', '/store-room', '/chat')):
        response.headers.setdefault('X-Robots-Tag', 'noindex, nofollow')

    # Performance / Cache-Control
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, must-revalidate'
        if request.path.startswith('/static/js/ai/'):
            response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
    elif request.path.startswith('/api/'):
        if 'Cache-Control' not in response.headers:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    elif request.path.endswith('.html') and not request.path.startswith('/dashboard'):
        response.headers.setdefault('Cache-Control', 'public, max-age=60, must-revalidate')
    return response

# Subdomain router & Canonical Host 301 Redirection
@app.before_request
def handle_canonical_and_subdomain_routing():
    host = (request.host or '').lower().split(':')[0]
    
    # 1. AI Subdomain handling - redirect to main dashboard where Tarika is integrated
    if host.startswith('ai.'):
        return redirect(f"https://{BASE_DOMAIN}/dashboard", code=301)
        
    # 2. Skip redirect for local development & internal health checks
    if host in ('localhost', '127.0.0.1', '0.0.0.0') or host.startswith('192.168.') or host.startswith('10.'):
        return None
    if request.path in ('/health', '/api/health'):
        return None

    # 3. Protocol & Host Canonical Enforcement (301 Redirect)
    # Redirect non-www, Heroku, run.place, and http:// requests to canonical https://www.abhihub.edu.eu.org
    proto = request.headers.get('X-Forwarded-Proto', request.scheme or 'https').lower()
    needs_host_redirect = host in ('abhihub.edu.eu.org', 'abhi-hub-06bba7f4101d.herokuapp.com', 'app.abhihub.run.place') or (host != BASE_DOMAIN and not host.startswith('ai.'))
    needs_proto_redirect = proto == 'http'
    
    if needs_host_redirect or needs_proto_redirect:
        full_query = f"?{request.query_string.decode('utf-8')}" if request.query_string else ""
        target_url = f"https://{BASE_DOMAIN}{request.path}{full_query}"
        return redirect(target_url, code=301)

@app.context_processor
def inject_seo_globals():
    env_name = os.getenv('FLASK_ENV', os.getenv('APP_ENV', os.getenv('ENV', 'development'))).lower()
    is_prod = env_name in ('production', 'prod')
    return {
        'BASE_URL': f"https://{BASE_DOMAIN}",
        'BASE_DOMAIN': BASE_DOMAIN,
        'CANONICAL_DOMAIN': f"https://{BASE_DOMAIN}",
        'IS_PRODUCTION': is_prod,
        'APP_ENV': env_name,
        'GOOGLE_SITE_VERIFICATION': os.getenv('GOOGLE_SITE_VERIFICATION', ''),
        'BING_SITE_VERIFICATION': os.getenv('BING_SITE_VERIFICATION', '')
    }

# Add gzip compression for text responses
try:
    from flask_compress import Compress
    compress = Compress()
    compress.init_app(app)
except ImportError:
    pass


from routes.seo import sitemap_page, _SITEMAP_REGISTRY, slugify

# Initialize the Level-wise Cache Management System
from cache_manager import init_cache, get_cache
cache = init_cache(app)

_socket_cors_origins = os.getenv('SOCKETIO_CORS_ORIGINS', 'https://www.abhihub.edu.eu.org').split(',')
# Permit local/preview hosts during development; production remains allow-listed.
if os.getenv('FLASK_ENV') != 'production':
    _socket_cors_origins = '*'
socketio = SocketIO(app, cors_allowed_origins=_socket_cors_origins, logger=False, engineio_logger=False)

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

# Backward-compatibility re-exports for blueprints/legacy callers
from data.pricing import has_document_access, extract_document_pricing
from routes.store_room import get_cached_unlabeled_files

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

def extract_pdf_info(pdf_bytes, max_pages=3):
    """Extract text from PDF (pages 1 to 3) or convert page 1 / extract embedded image to bytes (Task 4.11)."""
    extracted_text = ""
    img_bytes, mime_type = None, None
    total_pages = 0
    pages_read = 0

    if not pdf_bytes or len(pdf_bytes) < 10:
        return "This PDF document is empty or corrupt.", None, None

    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            return "This PDF is password-protected and cannot be analyzed automatically.", None, None

        total_pages = len(reader.pages)
        pages_to_process = reader.pages[:max_pages]
        pages_read = len(pages_to_process)

        for page in pages_to_process:
            t = page.extract_text()
            if t:
                extracted_text += t + "\n"
            if not img_bytes and hasattr(page, 'images'):
                try:
                    for img in page.images:
                        if len(img.data) <= 2 * 1024 * 1024:  # Cap at 2MB per image
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
                total_pages = len(doc)
                pages_to_process = [doc[i] for i in range(min(len(doc), max_pages))]
                pages_read = len(pages_to_process)
                for page in pages_to_process:
                    extracted_text += page.get_text() + "\n"
            if len(doc) > 0:
                pix = doc[0].get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                mime_type = "image/png"
        except Exception as e:
            logging.warning(f"[extract_pdf_info] fitz error: {e}")

    if extracted_text and total_pages > 0:
        extracted_text = f"[Read pages 1 to {pages_read} of {total_pages}]\n" + extracted_text

    # Fallback: pure-python regex + zlib stream decompression for zero-dependency extraction
    if not extracted_text:
        try:
            import zlib
            text_chunks = []
            for match in re.finditer(rb'stream[\r\n]+([\s\S]*?)[\r\n]+endstream', pdf_bytes):
                raw_stream = match.group(1)
                try:
                    decomp = zlib.decompress(raw_stream)
                except Exception:
                    decomp = raw_stream
                for tj in re.finditer(rb'\((.*?)\)\s*Tj', decomp):
                    text_chunks.append(tj.group(1).decode('latin1', errors='ignore'))
                for tj_arr in re.finditer(rb'\[(.*?)\]\s*TJ', decomp):
                    for sub in re.finditer(rb'\((.*?)\)', tj_arr.group(1)):
                        text_chunks.append(sub.group(1).decode('latin1', errors='ignore'))
            extracted_text = re.sub(r'\s+', ' ', ' '.join(text_chunks)).strip()
        except Exception as e:
            logging.warning(f"[extract_pdf_info] raw stream extraction error: {e}")

    return extracted_text.strip(), img_bytes, mime_type


def _resolve_signed_url(file_url, log_tag="AI"):
    """Return an http(s) URL, signing a raw Firebase storage path if needed."""
    if not file_url or file_url.startswith('http'):
        return file_url
    bucket = storage.bucket()
    blob = bucket.blob(file_url)
    signed = blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
    return signed[0] if isinstance(signed, (list, tuple)) else signed


def _looks_like_pdf(content_type, file_url, content_bytes):
    """Identify PDFs from response metadata, URL, or file signature."""
    return (
        'pdf' in (content_type or '').lower()
        or str(file_url or '').lower().endswith('.pdf')
        or (content_bytes or b'').startswith(b'%PDF')
    )

def _load_contact_messages():
    """Load contact messages from JSON file, swallowing exceptions."""
    if not os.path.exists(CONTACT_FILE):
        return []
    try:
        with open(CONTACT_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


# Security Configuration - Load from environment variables
_configured_secret = os.getenv('SECRET_KEY')
if not _configured_secret:
    if os.getenv('FLASK_ENV', 'production').lower() != 'development':
        logging.critical("[SECURITY WARNING] SECRET_KEY environment variable is not set! Set SECRET_KEY in .env to prevent multi-worker session invalidation.")
    app.secret_key = secrets.token_hex(32)
else:
    app.secret_key = _configured_secret

# Configure session cookie settings
# SESSION_COOKIE_SECURE defaults to True for HTTPS, False for local development / localhost
_is_dev_env = (
    os.getenv('FLASK_ENV', '').lower() in ('development', 'testing')
    or os.getenv('BASE_DOMAIN', '').lower().startswith(('localhost', '127.0.0.1'))
    or os.getenv('SESSION_COOKIE_SECURE', '').lower() in ('false', '0', 'no')
)
app.config['SESSION_COOKIE_SECURE'] = not _is_dev_env
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB request limit to prevent DoS memory exhaustion

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
    'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif'
}

def allowed_file(filename):
    """Check if file extension is allowed"""
    if not filename or '.' not in filename:
        return False  # no extension — rejected
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def validate_file_content(file_obj, filename):
    """Validate both file extension and magic byte header signature."""
    if not allowed_file(filename):
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    try:
        header = file_obj.read(16)
        file_obj.seek(0)
    except Exception:
        return False

    if ext == 'pdf':
        return header.startswith(b'%PDF')
    elif ext in {'jpg', 'jpeg'}:
        return header.startswith(b'\xff\xd8\xff')
    elif ext == 'png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    elif ext == 'gif':
        return header.startswith(b'GIF87a') or header.startswith(b'GIF89a')
    elif ext == 'webp':
        return header.startswith(b'RIFF') and b'WEBP' in header[:16]
    return False

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
                      file_type=None, file_path=None, user_email=None,
                      uploader_id=None, uploader_email=None):
    """Record that the current user viewed a document.

    Shared by /preview, /view_pdf and /resource/<slug> so the view-logging
    contract lives in exactly one place. Deducts 1 view from paper quota
    only ONCE per day for non-uploaders (uploaders view for free).
    Never raises: a logging failure must not break document delivery.
    """
    if user_email is None:
        user_email = session.get('user', {}).get('email', '')
    user_id = session.get('user', {}).get('uid', '')
    if not user_email:
        return False
    try:
        # Check 1: Free view if user is the uploader
        is_owner = False
        if user_id and uploader_id and str(user_id) == str(uploader_id):
            is_owner = True
        elif user_email and uploader_email and user_email.lower() == str(uploader_email).lower():
            is_owner = True
        elif record_id and user_id:
            try:
                doc_chk = supabase.table('documents').select('uploader_id').eq('id', record_id).limit(1).execute()
                if doc_chk.data and str(doc_chk.data[0].get('uploader_id')) == str(user_id):
                    is_owner = True
            except Exception:
                pass

        # Check 2: Same-day deduplication (charge only once per day per file)
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        doc_key = str(record_id or file_name or file_url)
        cache_view_key = f"viewed:{user_id or user_email}:{doc_key}:{today_str}"

        already_viewed_today = False
        try:
            if cache.l1.get(cache_view_key)[0] is not None:
                already_viewed_today = True
        except Exception:
            pass

        if not already_viewed_today:
            viewed_dict = session.get('viewed_today', {})
            if viewed_dict.get(doc_key) == today_str:
                already_viewed_today = True

        # Deduct credit ONLY if user is not the uploader AND has not viewed it today
        if not is_owner and not already_viewed_today:
            allowed = _consume_credit()
            if allowed:
                try:
                    cache.l1.set(cache_view_key, True, ttl=86400)
                except Exception:
                    pass
                viewed_dict = session.get('viewed_today', {})
                viewed_dict[doc_key] = today_str
                session['viewed_today'] = viewed_dict
                session.modified = True

                # Send notification for credit deduction
                try:
                    doc_title = file_name or "document"
                    notif_title = "Resource unlocked! ⚡ Quick tip inside..."
                    notif_msg = f"You unlocked '{doc_title}'. Your academic streak is active—see the key formulas inside!"
                    action_url = f"/resource/{record_id}" if record_id else None

                    if user_id:
                        from data.notifications import Notification
                        res = Notification.create(user_id, "quota_deduction", notif_title, notif_msg, action_url)
                        # Fall back to 'marketing' if quota_deduction enum hasn't been migrated
                        if not res.get('success'):
                            Notification.create(user_id, "marketing", notif_title, notif_msg, action_url)
                        try:
                            from push_notifications import send_notification
                            send_notification(user_id, notif_title, notif_msg, action_url)
                        except Exception:
                            pass
                except Exception as ne:
                    logging.warning(f"[VIEW-LOG] Could not send deduction notification: {ne}")

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

from routes.auth import auth_required, admin_required, log_admin_action, ADMIN_EMAILS, is_safe_redirect_url

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

def log_credit_transaction(user_id, amount, tx_type, reason):
    """Record credit earning or spending transaction for ledger tracking."""
    if not user_id:
        return
    try:
        data = {
            'user_id': user_id,
            'amount': amount,
            'type': tx_type,  # 'earn' or 'spend'
            'reason': reason,
            'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        # Session storage for fast UI response
        history = session.get('credit_history', [])
        if not isinstance(history, list):
            history = []
        history.insert(0, data)
        session['credit_history'] = history[:100]
        session.modified = True

        # Database storage
        try:
            supabase.table('credit_transactions').insert(data).execute()
        except Exception:
            pass
    except Exception as e:
        logging.warning(f"[CREDIT-LOG] Could not log credit tx: {e}")

def _grant_upload_credits():
    """Award +3 paper quota views and +1 reputation score to the user after a successful upload."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return
    
    # Fetch current quota and rep
    res = supabase.table('profiles').select('paper_quota_remaining, reputation_score').eq('id', user_id).execute()
    if res.data:
        curr_quota = res.data[0].get('paper_quota_remaining')
        if curr_quota is None:
            curr_quota = 19
        curr_rep = res.data[0].get('reputation_score') or 0
        new_quota = curr_quota + 3
        
        supabase.table('profiles').update({
            'paper_quota_remaining': new_quota,
            'reputation_score': curr_rep + 1
        }).eq('id', user_id).execute()

        # Update session quota
        q = session.get('paper_quota', {})
        if isinstance(q, dict):
            q['credits'] = new_quota
            session['paper_quota'] = q
            session.modified = True

        cache.l1.delete(f"user:quota:{user_id}")
        log_credit_transaction(user_id, 3, 'earn', "Document upload reward (+3 views)")
        logging.info(f"[REWARD] Granted +3 views (quota={new_quota}) and +1 rep to {user.get('email')}")

def _consume_credit(doc_name="Document"):
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
        log_credit_transaction(user_id, -1, 'spend', f"Viewed: {doc_name}")

    # Invalidate quota cache — it changed
    cache.l1.delete(f"user:quota:{user_id}")

    return True




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


import json
import os
CONTACT_FILE = os.path.join('data', 'contact_messages.json')

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
    get_college_stats,
    get_colleges_by_brand,
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
    get_recent_college_files,
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
    return render_template('site/error.html', error="Page Not Found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('site/error.html', error="Internal Server Error"), 500






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

_chat_online = {}        # {user_id: {sid, name}}
_chat_online_http = {}   # {user_id: {time, name}}

CHAT_SECRET = os.getenv('CHAT_SECRET')

def _chat_secret():
    if not CHAT_SECRET:
        return None
    try:
        import base64
        b = base64.urlsafe_b64encode(CHAT_SECRET.encode('utf-8')[:32])
        return b.decode('utf-8')
    except Exception:
        return None

def _enc(text: str):
    secret = _chat_secret()
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(secret.encode('utf-8')).encrypt(text.encode('utf-8')).decode('utf-8')
    except Exception:
        return None

def _dec(token: str):
    secret = _chat_secret()
    if not secret or not token:
        return token
    try:
        from cryptography.fernet import Fernet
        return Fernet(secret.encode('utf-8')).decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception:
        return token

def _persist_chat_message(uid_a, uid_b, payload):
    """Persist chat message — Supabase (encrypted) with in-memory cache fallback."""
    from methods.encrypted_chat import save_message_supabase

    # Try Supabase persistence first (encrypted at rest)
    plaintext = payload.get('text', '')
    peer_pubkey = None

    # Try to get sender's public key for E2E encryption
    try:
        from methods.encrypted_chat import get_user_keys
        keys = get_user_keys(uid_a)
        peer_pubkey = keys.get('public_key')
    except Exception:
        pass

    saved = save_message_supabase(uid_a, uid_b, plaintext, sender_public_key=peer_pubkey)
    if saved:
        # Update payload with the server-assigned message ID
        payload['msg_id'] = saved.get('id', '')

    # Also keep in in-memory cache for real-time delivery
    try:
        key = 'chat_messages:' + '_'.join(sorted([uid_a, uid_b]))
        data = cache.l1.get(key)
        history = data[0] if data and data[0] else []
        if not isinstance(history, list):
            history = []
        item = {
            'cipher': _enc(payload.get('text', '')) or payload.get('text', ''),
            'from': payload.get('from'),
            'to': payload.get('to'),
            'ts': payload.get('ts'),
            'sender_meta': payload.get('sender_meta', {}),
            'status': 'sent',
            'msg_id': saved.get('id') if saved else '',
            'msg_type': payload.get('msg_type', 'text'),
            'file_req': payload.get('file_req'),
            'file_attachment': payload.get('file_attachment')
        }
        history.append(item)
        max_age = 3 * 24 * 60 * 60  # 3 days ephemeral retention
        cache.l1.set(key, history, ttl=max_age)
    except Exception:
        pass

def _get_chat_history(uid_a, uid_b):
    """Load chat history (strictly within last 3 days) — Supabase (encrypted) with in-memory fallback."""
    from methods.encrypted_chat import load_conversation_supabase
    from datetime import datetime, timedelta

    cutoff_iso = (datetime.utcnow() - timedelta(days=3)).isoformat()

    try:
        my_keys = {}
        try:
            from methods.encrypted_chat import get_user_keys
            my_keys = get_user_keys(uid_a)
        except Exception:
            pass
        my_privkey = my_keys.get('private_key')

        messages = load_conversation_supabase(
            uid_a, uid_b,
            my_privkey=my_privkey,
            peer_pubkey=my_keys.get('public_key')
        )
        if messages:
            return [m for m in messages if not m.get('ts') or m.get('ts') >= cutoff_iso]
    except Exception:
        pass

    # Fallback: in-memory cache
    try:
        key = 'chat_messages:' + '_'.join(sorted([uid_a, uid_b]))
        data = cache.l1.get(key)
        raw = data[0] if data and data[0] and isinstance(data[0], list) else []
        out = []
        for m in raw:
            m_ts = m.get('ts') or ''
            if m_ts and m_ts < cutoff_iso:
                continue
            out.append({
                'text': _dec(m.get('text') or m.get('cipher') or ''),
                'from': m.get('from'),
                'to': m.get('to'),
                'ts': m.get('ts'),
                'sender_meta': m.get('sender_meta', {}),
                'status': m.get('status', 'sent'),
                'msg_type': m.get('msg_type', 'text'),
                'file_req': m.get('file_req'),
                'file_attachment': m.get('file_attachment')
            })
        return out
    except Exception:
        return []

def _expire_chat_history(uid_a, uid_b):
    try:
        key = 'chat_messages:' + '_'.join(sorted([uid_a, uid_b]))
        cache.l1.delete(key)
    except Exception:
        pass


@socketio.on('chat_delivered')
def chat_delivered(data):
    uid = _get_uid()
    peer_id = data.get('to')
    msg_ts = data.get('ts')
    msg_id = data.get('msg_id', '')
    if not uid or not peer_id or not msg_ts:
        return
    room = _pair_room(uid, peer_id)
    emit('chat_received', {'from': uid, 'to': peer_id, 'ts': msg_ts, 'status': 'delivered'}, to=room)
    # Update Supabase
    if msg_id:
        try:
            from methods.encrypted_chat import mark_message_delivered
            mark_message_delivered(msg_id, uid)
        except Exception:
            pass

@socketio.on('chat_read')
def chat_read(data):
    uid = _get_uid()
    peer_id = data.get('to')
    msg_ts = data.get('ts')
    msg_id = data.get('msg_id', '')
    if not uid or not peer_id or not msg_ts:
        return
    room = _pair_room(uid, peer_id)
    emit('chat_read_receipt', {'from': uid, 'to': peer_id, 'ts': msg_ts, 'status': 'read'}, to=room)
    # Update Supabase
    if msg_id:
        try:
            from methods.encrypted_chat import mark_message_read
            mark_message_read(msg_id, uid)
        except Exception:
            pass

@socketio.on('connect')
def chat_connect():
    uid = _get_uid()
    if not uid:
        return
    user = session.get('user', {})
    name = user.get('name') or (user.get('user_metadata') or {}).get('full_name') or user.get('email', 'Student')
    _chat_online[uid] = {'sid': request.sid, 'name': name}
    join_room(uid)
    join_room('online-counter-room')
    socketio.emit('chat_online_update', {'online': _safe_online_list()})

@socketio.on('disconnect')
def chat_disconnect():
    uid = _get_uid()
    if uid and _chat_online.get(uid, {}).get('sid') == request.sid:
        del _chat_online[uid]
        socketio.emit('chat_online_update', {'online': _safe_online_list()})

@socketio.on('reconnect')
def chat_reconnect():
    chat_connect()

# ── Admin real-time updates ──────────────────────────────────────────────────
# Admin dashboard subscribes to 'admin-room' for live KPI / activity updates.

@socketio.on('join_admin_room')
def join_admin_room(data):
    """Admin joins the admin-room namespace to receive real-time updates."""
    socketio.join_room('admin-room')
    # Send immediate snapshot
    try:
        stats = get_admin_broadcast_delivery_stats(limit=20)
        health = get_system_health().get_json()
        socketio.emit('admin_snapshot', {
            'broadcast_stats': stats.get_json() if hasattr(stats, 'get_json') else stats,
            'system_health': health.get_json() if hasattr(health, 'get_json') else health,
            'ts': datetime.utcnow().isoformat() + 'Z'
        }, room='admin-room')
    except Exception as e:
        logging.error(f"[admin] snapshot error: {e}")


def _emit_admin_activity_event(event_type, **kwargs):
    """Push a real-time activity event to the admin dashboard."""
    try:
        payload = {'event': event_type, 'ts': datetime.utcnow().isoformat() + 'Z'}
        payload.update(kwargs)
        socketio.emit('admin_activity', payload, room='admin-room')
    except Exception as e:
        logging.debug(f"[admin] emit_activity failed: {e}")


def _notify_admin_of_chat_activity(sender_id, peer_id, msg_ts):
    """Lightweight notification to admin dashboard about chat activity."""
    try:
        client = init_supabase()
        if not client:
            return
        sender_name = 'A student'
        try:
            r = client.table('profiles').select('full_name').eq('id', sender_id).limit(1).execute()
            if r.data:
                sender_name = r.data[0].get('full_name', 'A student') or 'A student'
        except Exception:
            pass
        _emit_admin_activity_event('chat_message', {
            'sender_id': sender_id,
            'sender_name': sender_name,
            'peer_id': peer_id,
            'ts': msg_ts,
            'msg_id': 'ch_' + str(abs(hash(msg_ts + sender_id)))[-8:]
        })
    except Exception:
        pass


@socketio.on('heartbeat')
def chat_heartbeat(data):
    uid = _get_uid()
    if not uid:
        return
    user = session.get('user', {})
    name = user.get('name') or (user.get('user_metadata') or {}).get('full_name') or user.get('email', 'Student')
    _chat_online[uid] = {'sid': request.sid, 'name': name}

def _get_merged_online_users():
    import time
    now_t = time.time()
    ONLINE_WINDOW_S = 60 * 60
    to_delete = [k for k, v in _chat_online_http.items() if now_t - v['time'] > ONLINE_WINDOW_S]
    for k in to_delete:
        del _chat_online_http[k]
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
    uid = _get_uid()
    peer_id = data.get('peer')
    if not uid or not peer_id or uid == peer_id:
        return
    room = _pair_room(uid, peer_id)
    join_room(room)
    join_room(uid)
    emit('chat_joined', {'room': room})


def _relay_chat_message(uid, data):
    """Validate, persist, deliver, and alert for one chat message."""
    peer_id = (data or {}).get('to')
    text = str((data or {}).get('text', '')).strip()[:4000]
    if not uid or not peer_id or uid == peer_id or not text or not validate_uuid(peer_id):
        return None
    payload = {
        'from': uid,
        'to': peer_id,
        'text': text,
        'ts': (data or {}).get('ts') or datetime.utcnow().isoformat() + 'Z',
        'msg_id': (data or {}).get('msg_id') or '',
        'msg_type': (data or {}).get('msg_type') or 'text',
        'file_req': (data or {}).get('file_req') or None,
        'file_attachment': (data or {}).get('file_attachment') or None,
        'sender_meta': (data or {}).get('sender_meta') or {}
    }
    _persist_chat_message(uid, peer_id, payload)
    # Broadcast to recipient's personal room
    socketio.emit('chat_receive', payload, to=peer_id)
    # ACK back to sender that message was saved and queued for delivery
    sender_sid = _chat_online.get(uid, {}).get('sid')
    if sender_sid and sender_sid != peer_id:
        socketio.emit('chat_message_ack', {
            'msg_id': payload.get('msg_id', ''),
            'ts': payload.get('ts', ''),
            'error': None
        }, to=sender_sid)
    else:
        # Sender not connected via WebSocket - send ACK via HTTP fallback
        try:
            import requests as _req
            headers = {'Content-Type': 'application/json'}
            _req.post(f'http://127.0.0.1:{os.getenv("PORT", "5000")}/api/chat/messages', json={
                'to': uid, 'text': 'ACK: message delivered', 'ts': payload.get('ts', '')
            }, timeout=2, headers=headers)
        except Exception:
            pass
    # Notify admin dashboard of chat activity (privacy-safe, no message content)
    _notify_admin_of_chat_activity(uid, peer_id, payload.get('ts', ''))
    _create_chat_notification(uid, peer_id, payload)
    return payload


@socketio.on('chat_send')
def chat_send(data):
    _relay_chat_message(_get_uid(), data)


@socketio.on('chat_typing')
def chat_typing(data):
    uid = _get_uid()
    peer_id = (data or {}).get('to')
    is_typing = bool((data or {}).get('is_typing', True))
    if not uid or not peer_id or uid == peer_id:
        return
    socketio.emit('chat_peer_typing', {'from': uid, 'is_typing': is_typing}, to=peer_id)


@socketio.on('chat_react')
def chat_react(data):
    uid = _get_uid()
    peer_id = (data or {}).get('to')
    if not uid or not peer_id or uid == peer_id:
        return
    payload = {'from': uid, 'msg_id': (data or {}).get('msg_id'), 'ts': (data or {}).get('ts'), 'emoji': (data or {}).get('emoji')}
    socketio.emit('chat_peer_react', payload, to=peer_id)


@socketio.on('chat_file_fulfilled')
def chat_file_fulfilled(data):
    uid = _get_uid()
    peer_id = (data or {}).get('to')
    if not uid or not peer_id or uid == peer_id:
        return
    payload = {
        'from': uid,
        'msg_id': (data or {}).get('msg_id'),
        'ts': (data or {}).get('ts'),
        'file_url': (data or {}).get('file_url'),
        'file_name': (data or {}).get('file_name'),
        'file_size': (data or {}).get('file_size'),
        'doc_id': (data or {}).get('doc_id'),
        'resource_url': (data or {}).get('resource_url')
    }
    socketio.emit('chat_peer_file_fulfilled', payload, to=peer_id)


@socketio.on('chat_file_status')
def chat_file_status(data):
    uid = _get_uid()
    peer_id = (data or {}).get('to')
    if not uid or not peer_id:
        return
    payload = {
        'from': uid,
        'msg_id': (data or {}).get('msg_id'),
        'ts': (data or {}).get('ts'),
        'status': (data or {}).get('status', 'rejected'),
        'reason': (data or {}).get('reason', '')
    }
    socketio.emit('chat_peer_file_status', payload, to=peer_id)




def _create_chat_notification(sender_id, recipient_id, payload):
    """Store a chat alert and fan it out to subscribed devices."""
    try:
        sender = (payload.get('sender_meta') or {}).get('name') or 'A student'
        preview = str(payload.get('text') or '').strip().replace('\n', ' ')[:140]
        title = f"New message from {sender}"
        action_url = url_for('app_pages.chat_with_peer', peer_id=sender_id)
        from data.notifications import Notification
        res = Notification.create(recipient_id, 'chat_message', title, preview or 'Sent you a message', action_url)
        # Fall back to 'marketing' if chat_message enum hasn't been migrated yet
        if not res.get('success'):
            Notification.create(recipient_id, 'marketing', title, preview or 'Sent you a message', action_url)
        from push_notifications import send_notification
        send_notification(recipient_id, title, preview or 'Sent you a message', action_url, tag=f'chat-{sender_id}')
    except Exception as exc:
        logging.info(f"[chat] notification unavailable: {exc}")

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


# ─── Modular Route Blueprints (Phase 5 Routing Overhaul) ─────────────────────
try:
    from routes import register_blueprints
    register_blueprints(app)

    def _resolve_bare_endpoint_fallback(error, endpoint, values):
        if '.' not in endpoint:
            for ep in app.view_functions:
                if ep.endswith(f".{endpoint}"):
                    return url_for(ep, **values)
        return None
    app.url_build_error_handlers.append(_resolve_bare_endpoint_fallback)
except Exception as e:
    logging.warning(f"Failed to register modular blueprints: {e}")

# ─── Centralized 301 Redirects Table (Phase 2 Routing Overhaul) ───────────────
try:
    from routes.redirects import register_redirect_handlers
    register_redirect_handlers(app)
except Exception as e:
    logging.warning(f"Failed to register centralized redirect handlers: {e}")



if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)



