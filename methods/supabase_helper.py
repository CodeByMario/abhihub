"""
Supabase Helper Module
Provides functions to interact with Supabase for storing labeled papers and documents.
"""

import os
import json
import logging
import traceback
import time
from datetime import datetime
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

log = logging.getLogger(__name__)

# Try to import supabase
try:
    from supabase import create_client, Client, ClientOptions
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None
    ClientOptions = None
    logging.warning("Warning: supabase-py not installed. Install with: pip install supabase")

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Public/anon key — accepts legacy name SUPABASE_KEY or new SUPABASE_PUBLIC_API_KEY
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLIC_API_KEY") or ""
# Service key for admin access (new-style name preferred)
SUPABASE_SECRET_API_KEY = os.getenv("SUPABASE_SECRET_API_KEY") or ""
# Admin/service credential — bypasses RLS for tables like user_crushes where
# anon access is denied. Accepts either:
#   - SUPABASE_JWT = the JWT *signing secret* (raw string) → we mint a
#     service_role token from it (Supabase legacy JWT secret auth), or
#   - SUPABASE_JWT / SUPABASE_SERVICE_ROLE = an eyJ... API key (used as-is).
# Falls back to SUPABASE_KEY if neither is set.
_RAW_ADMIN_SECRET = os.getenv("SUPABASE_JWT") or os.getenv("SUPABASE_SERVICE_ROLE") or ""

def _resolve_admin_key() -> str:
    """Return a valid Supabase API key for admin access."""
    # Preferred: real service_role / secret API key
    if SUPABASE_SECRET_API_KEY:
        return SUPABASE_SECRET_API_KEY
    if _RAW_ADMIN_SECRET.startswith("eyJ"):
        return _RAW_ADMIN_SECRET  # already a real API key (service_role)
    if _RAW_ADMIN_SECRET:
        # Raw signing secret — mint a service_role HS256 token.
        try:
            import jwt as pyjwt
            return pyjwt.encode(
                {"role": "service_role", "iss": "supabase", "iat": int(time.time()),
                 "exp": int(time.time()) + 10 * 365 * 24 * 3600},
                _RAW_ADMIN_SECRET,
                algorithm="HS256",
            )
        except Exception as e:
            logging.error(f"❌ Could not mint service_role token from secret: {e}")
    return SUPABASE_KEY or ""

_supabase_client = None
_supabase_admin_client = None

def init_supabase_admin():
    """Supabase client using the service/JWT key (bypasses RLS).

    Use ONLY for tables blocked by RLS for the anon key (e.g. user_crushes).
    """
    global _supabase_admin_client
    if not SUPABASE_AVAILABLE:
        logging.error("❌ init_supabase_admin: supabase-py not installed")
        return None
    admin_key = _resolve_admin_key()
    if not SUPABASE_URL or not admin_key:
        logging.error("❌ init_supabase_admin: SUPABASE_URL or admin key missing")
        return None
    if _supabase_admin_client is None:
        try:
            _supabase_admin_client = create_client(
                SUPABASE_URL,
                admin_key,
                options=ClientOptions(schema="abhihub")
            )
            logging.info("✅ Supabase admin client initialized")
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error initializing Supabase admin client: {e}")
            return None
    return _supabase_admin_client

def init_supabase():
    global _supabase_client
    if not SUPABASE_AVAILABLE:
        logging.error("❌ list_supabase: SUPABASE_AVAILABLE is False")
        return None
    if not SUPABASE_URL:
        logging.error("❌ list_supabase: SUPABASE_URL is empty")
        return None
    if not SUPABASE_KEY:
        logging.error("❌ list_supabase: SUPABASE_KEY is empty")
        return None
        
    if _supabase_client is None:
        try:
            _supabase_client = create_client(
                SUPABASE_URL, 
                SUPABASE_KEY,
                options=ClientOptions(schema="abhihub")
            )
            logging.info("Success: Supabase client initialized with abhihub schema")
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error initializing Supabase client: {e}")
            return None
    return _supabase_client

def format_file_size(bytes: int) -> str:
    if not bytes: return "0 B"
    units = ['B', 'KB', 'MB', 'GB']
    index = 0
    size = float(bytes)
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.1f} {units[index]}"

def validate_uuid(val):
    import uuid
    try:
        uuid.UUID(str(val))
        return True
    except Exception as e:
        log.debug(f"validate_uuid failed for {val!r}: {e}")
        return False

def get_all_colleges() -> Dict:
    cached = _cache_get('all_colleges')
    if cached is not None:
        return {"success": True, "data": cached}
    client = init_supabase()
    if not client: return {"success": False, "data": []}
    try:
        response = client.table("colleges").select("*").order("name").execute()
        for c in response.data:
            c['short_name'] = c.get('abbreviation')
        _cache_set('all_colleges', response.data)
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "data": []}

def get_college_by_slug(slug: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table("colleges").select("*").execute()
        import re
        def _slug(text):
            return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
        
        for c in response.data:
            # Match abbreviation slug (canonical)
            abbr = (c.get('abbreviation') or '').lower()
            if abbr and abbr == slug:
                return {"success": True, "data": c}
            # Match full name slug
            name_slug = _slug(c.get('name') or '')
            if name_slug == slug:
                return {"success": True, "data": c}
            # Match popular_name (e.g. "raisoni" for GHRCE)
            popular = (c.get('popular_name') or '')
            if popular and _slug(popular) == slug:
                return {"success": True, "data": c}
            # Match aliases array (e.g. ["raisoni", "gh raisoni"])
            for alias in (c.get('aliases') or []):
                if alias and _slug(alias) == slug:
                    return {"success": True, "data": c}
        return {"success": False, "message": "College not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_colleges_by_brand(brand_slug: str) -> Dict:
    """Return all colleges that share the same popular_name (brand group).
    E.g. brand_slug='raisoni' → [GHRCEN, GHRCEM, GHRCEMNG, ...]
    """
    client = init_supabase()
    if not client: return {"success": False, "data": []}
    try:
        import re
        def _slug(text):
            return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
        
        response = client.table("colleges").select("*").execute()
        matches = []
        brand_display = None
        for c in response.data:
            popular = (c.get('popular_name') or '')
            if popular and _slug(popular) == brand_slug:
                matches.append(c)
                if not brand_display:
                    brand_display = popular
            else:
                # Also check aliases
                for alias in (c.get('aliases') or []):
                    if alias and _slug(alias) == brand_slug:
                        matches.append(c)
                        break
        
        if not matches:
            return {"success": False, "message": "Brand not found"}
        return {"success": True, "data": matches, "brand_name": brand_display or brand_slug.capitalize()}
    except Exception as e:
        return {"success": False, "data": [], "message": str(e)}

def get_waitlist_count(college_id: str) -> int:
    """Return how many students have joined the waitlist for a college."""
    client = init_supabase()
    if not client: return 0
    try:
        res = client.table('college_waitlist').select('id', count='exact').eq('college_id', college_id).execute()
        return res.count or 0
    except Exception as e:
        log.warning(f"get_waitlist_count failed for college_id={college_id!r}: {e}")
        return 0

def join_college_waitlist(college_id: str, email: str, name: str = '') -> Dict:
    """Add a student to the college waitlist. Returns count after insert."""
    client = init_supabase()
    if not client: return {'success': False, 'message': 'Service unavailable'}
    try:
        client.table('college_waitlist').insert({
            'college_id': college_id,
            'email': email.lower().strip(),
            'name': name.strip() or None
        }).execute()
        count = get_waitlist_count(college_id)
        return {'success': True, 'count': count}
    except Exception as e:
        if 'unique' in str(e).lower() or '23505' in str(e):
            count = get_waitlist_count(college_id)
            return {'success': True, 'already_joined': True, 'count': count}
        return {'success': False, 'message': str(e)}

def get_college_stats(college_id: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        doc_resp = client.table('documents').select('id', count='exact').eq('college_id', college_id).execute()
        total_docs = doc_resp.count or 0
        
        total_subs = 0
        try:
            # Subjects are linked to departments, not colleges directly.
            # To get an exact count we'd need to join or fetch departments first.
            # For now, we fetch departments and then sum their subjects.
            depts_resp = client.table('college_departments').select('department_id').eq('college_id', college_id).execute()
            dept_ids = [d['department_id'] for d in (depts_resp.data or [])]
            if dept_ids:
                sub_resp = client.table('subjects').select('id', count='exact').in_('department_id', dept_ids).execute()
                total_subs = sub_resp.count or 0
        except Exception as e:
            log.debug(f"join_college_waitlist: failed to count subjects for dept_ids={dept_ids!r}: {e}")
            pass

        return {
            "success": True, 
            "data": {
                "total_documents": total_docs,
                "total_subjects": total_subs
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_recent_college_files(college_id: str, limit: int = 5) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table('documents')\
            .select('*, subject:subjects(name), uploader:profiles!documents_uploader_id_fkey(full_name)')\
            .eq('college_id', college_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_department_by_slug(slug: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table("departments").select("*").execute()
        import re
        for c in response.data:
            abbr = (c.get('abbreviation') or '').lower()
            if abbr and abbr == slug:
                return {"success": True, "data": c}
            name_slug = re.sub(r'[^a-z0-9]+', '-', (c.get('name') or '').lower()).strip('-')
            if name_slug == slug:
                return {"success": True, "data": c}
        return {"success": False, "message": "Department not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_department_stats(college_id: str, dept_id: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        doc_resp = client.table('documents').select('id', count='exact').eq('college_id', college_id).eq('department_id', dept_id).execute()
        sub_resp = client.table('subjects').select('id', count='exact').eq('department_id', dept_id).execute()
        total_docs = doc_resp.count or 0
        total_subs = sub_resp.count or 0
        target = total_subs * 5
        completion = 0
        if target > 0:
            completion = min(100, int((total_docs / target) * 100))
            
        return {
            "success": True, 
            "data": {
                "total_documents": total_docs,
                "total_subjects": total_subs,
                "archive_completion": completion
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_recent_department_files(college_id: str, dept_id: str, limit: int = 6) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table('documents')\
            .select('*, subject:subjects(name), uploader:profiles!documents_uploader_id_fkey(full_name)')\
            .eq('college_id', college_id)\
            .eq('department_id', dept_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_subjects_by_slug(slug: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table("subjects").select("*").execute()
        import re
        matching_ids = []
        canonical_name = None
        for s in response.data:
            name_slug = re.sub(r'[^a-z0-9]+', '-', (s.get('name') or '').lower()).strip('-')
            if name_slug == slug:
                matching_ids.append(s.get('id'))
                if not canonical_name:
                    canonical_name = s.get('name')
        if not matching_ids:
            return {"success": False, "message": "Subject not found"}
        return {"success": True, "data": {"ids": matching_ids, "name": canonical_name}}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_subject_stats(subject_ids: list) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        # Aggregating across multiple IDs using 'in'
        doc_resp = client.table('documents').select('id', count='exact').in_('subject_id', subject_ids).execute()
        return {
            "success": True, 
            "data": {
                "total_documents": doc_resp.count or 0
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_recent_subject_files(subject_ids: list, limit: int = 10) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table('documents')\
            .select('*, college:colleges(name, abbreviation), uploader:profiles!documents_uploader_id_fkey(full_name)')\
            .in_('subject_id', subject_ids)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_document_by_id_rich(doc_id: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        response = client.table('documents')\
            .select('*, college:colleges(name, abbreviation), department:departments(name, abbreviation), subject:subjects(name), uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)')\
            .eq('id', doc_id)\
            .single()\
            .execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_sitemap_urls() -> Dict:
    """Fetches lightweight data across the entire database to generate SEO slugs for the XML sitemap."""
    client = init_supabase()
    if not client: return {"success": False}
    try:
        # 1. Colleges
        colleges = client.table('colleges').select('name, abbreviation, popular_name, created_at').execute().data
        
        # 2. Departments
        # Since department pages are nested under colleges in the UI, we just need unique departments 
        # (Though technically a department page route requires both. Let's just fetch all colleges and departments)
        depts = client.table('departments').select('name, abbreviation, created_at').execute().data
        
        # 3. Subjects
        subjects = client.table('subjects').select('name, created_at').execute().data
        
        # 4. Resources
        # We need the relations to generate the canonical slug
        docs = client.table('documents')\
            .select('id, title, updated_at, created_at, college:colleges(name, abbreviation), department:departments(name, abbreviation), subject:subjects(name)')\
            .in_('status', ['approved', 'pending'])\
            .execute().data
            
        return {
            "success": True, 
            "data": {
                "colleges": colleges,
                "departments": depts,
                "subjects": subjects,
                "documents": docs
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_all_branches() -> Dict:
    cached = _cache_get('all_branches')
    if cached is not None:
        return {"success": True, "data": cached}
    client = init_supabase()
    if not client: return {"success": False, "data": []}
    try:
        response = client.table("departments").select("*").order("name").execute()
        for b in response.data:
            b['short_name'] = b.get('abbreviation')
            b['branch_id'] = b.get('id')
            b['branch_name'] = b.get('name')
        _cache_set('all_branches', response.data)
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "data": []}


# ── T8: In-memory cache (colleges / departments / subjects) ──────────────────
import time as _time
_cache: Dict[str, Any] = {}
_CACHE_TTL = 300  # 5 minutes

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and (_time.time() - entry['ts']) < _CACHE_TTL:
        return entry['val']
    return None

def _cache_set(key: str, val):
    _cache[key] = {'val': val, 'ts': _time.time()}


def get_departments_by_college(college_id: str) -> Dict:
    """Return departments mapped to a college via college_departments table."""
    cache_key = f"depts:{college_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return {"success": True, "data": cached}

    client = init_supabase()
    if not client: return {"success": False, "data": []}
    try:
        res = client.table("college_departments") \
            .select("department_id, departments(id, name, abbreviation)") \
            .eq("college_id", college_id) \
            .execute()
        data = []
        for row in (res.data or []):
            dept = row.get("departments") or {}
            if dept:
                data.append({
                    "id": dept.get("id"),
                    "name": dept.get("name"),
                    "abbreviation": dept.get("abbreviation"),
                })
        _cache_set(cache_key, data)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "data": [], "message": str(e)}


def get_subjects_by_department(department_id: str, semester: int = None) -> Dict:
    """Return subjects for a department. Optionally filter by semester."""
    cache_key = f"subjs:{department_id}:{semester}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return {"success": True, "data": cached}

    client = init_supabase()
    if not client: return {"success": False, "data": []}
    try:
        q = client.table("subjects") \
            .select("id, name, subject_code, semester") \
            .eq("department_id", department_id)
        if semester:
            # Include exact semester match AND subjects with NULL semester (spans all semesters)
            res = q.or_(f"semester.eq.{semester},semester.is.null").order("name").execute()
        else:
            res = q.order("name").execute()
        data = res.data or []
        _cache_set(cache_key, data)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "data": [], "message": str(e)}


def create_subject_request(user_id: str, college_id: str, department_id: str,
                           subject_name: str, subject_code: str = '',
                           semester: int = None) -> Dict:
    """Insert a pending_subject_requests row. Duplicate protection via DB index."""
    client = init_supabase()
    if not client: return {"success": False, "message": "No client"}
    try:
        res = client.table("pending_subject_requests").insert({
            "user_id": user_id,
            "college_id": college_id or None,
            "department_id": department_id or None,
            "subject_name": subject_name,
            "subject_code": subject_code or None,
            "semester": semester or None,
            "status": "pending"
        }).execute()
        if res.data:
            return {"success": True, "data": res.data[0]}
        return {"success": False, "message": "Insert returned no data"}
    except Exception as e:
        # Unique constraint violation = duplicate pending request
        if 'unique' in str(e).lower() or '23505' in str(e):
            return {"success": False, "message": "A pending request for this subject already exists", "duplicate": True}
        return {"success": False, "message": str(e)}


def get_onboarding_status(user_id: str) -> Dict:
    """Read welcome_seen from profiles table (lightweight, no extra table)."""
    client = init_supabase()
    if not client: return {"success": False, "data": None}
    try:
        res = client.table("profiles").select("welcome_seen, last_donation_popup_at").eq("id", user_id).execute()
        if res.data:
            return {"success": True, "data": res.data[0]}
        return {"success": True, "data": {"welcome_seen": False}}
    except Exception as e:
        return {"success": False, "data": None, "message": str(e)}


def mark_welcome_seen(user_id: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False}
    try:
        client.table("profiles").update({"welcome_seen": True}).eq("id", user_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


def track_user_event(user_id: str, event_type: str, metadata: dict = None) -> None:
    """Fire-and-forget. Only tracks UPLOAD, DOWNLOAD, SUBJECT_REQUEST."""
    _ALLOWED = {'UPLOAD', 'DOWNLOAD', 'SUBJECT_REQUEST'}
    if event_type not in _ALLOWED:
        return  # silently ignore non-tracked types
    try:
        client = init_supabase()
        if not client: return
        client.table("user_events").insert({
            "user_id": user_id or None,
            "event_type": event_type,
            "metadata": metadata or {}
        }).execute()
    except Exception as e:
        log.debug(f"track_user_event: non-blocking insert failed: {e}")
        pass  # Non-blocking; never raise

def save_file_record(
    user_id: str, user_email: str, file_name: str, file_url: str,
    file_type: str, file_size: int, cloudinary_public_id: str,
    subject_name: str, document_type: str, year: str = '',
    college_id=None, branch_id=None, subject_code: str = '',
    semesters: list = None, title: str = '', description: str = '',
    subject_id: str = None, semester: int = None, exam_type: str = '', file_hash: str = None, program: str = 'b.tech'
) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        c_id = college_id if validate_uuid(college_id) else None
        d_id = branch_id if validate_uuid(branch_id) else None
        u_id = user_id if validate_uuid(user_id) else None

        # If u_id is not a valid UUID, try to look it up using user_email
        if not u_id and user_email:
            p_res = client.table('profiles').select('id').eq('email', user_email).execute()
            if p_res.data:
                u_id = p_res.data[0]['id']
                logging.info(f"[Supabase] Resolved uploader_id from email: {u_id}")
        
        # Ensure that if we have a u_id, the profile exists safely
        if u_id:
            p_check = client.table('profiles').select('id').eq('id', u_id).execute()
            if not p_check.data:
                logging.info(f"[Supabase] Profile for {u_id} not found, creating base profile.")
                try:
                    # Provide default full_name if user_email is available, else generic name
                    name_part = user_email.split('@')[0] if user_email else 'Unknown User'
                    email_part = user_email if user_email else 'unknown@example.com'
                    client.table('profiles').insert({
                        'id': u_id,
                        'email': email_part,
                        'full_name': name_part,
                        'role': 'student'
                    }).execute()
                    logging.info(f"[Supabase] Base profile created successfully.")
                except Exception as p_err:
                    logging.error(f"[Supabase] Failed to create base profile: {p_err}")

        # Resolve subject_id — prefer direct UUID from cascade dropdown
        sub_id = subject_id if validate_uuid(subject_id) else None

        # Fallback: fuzzy lookup by code or name (legacy / per-image modal path)
        if not sub_id and subject_code:
            sub_res = client.table("subjects").select("id").eq("subject_code", subject_code).limit(1).execute()
            if sub_res.data: sub_id = sub_res.data[0]['id']

        if not sub_id and subject_name:
            sub_res = client.table("subjects").select("id").ilike("name", f"%{subject_name}%").limit(1).execute()
            if sub_res.data: sub_id = sub_res.data[0]['id']

        # Construct description if not provided
        if not description:
            desc_data = {
                "subject": subject_name,
                "year": year,
                "subject_code": subject_code,
                "semesters": semesters or [],
                "semester": semester  # new: integer semester from cascade
            }
            description = json.dumps(desc_data)
        
        storage_provider = 'cloudinary' if cloudinary_public_id else 'firebase'

        data = {
            'uploader_id': u_id,
            'college_id': c_id,
            'department_id': d_id,
            'subject_id': sub_id,
            'title': title or file_name,
            'document_category': document_type or 'notes',
            'description': description,
            'file_url': file_url,
            'storage_provider': storage_provider,
            'provider_public_id': cloudinary_public_id,
            'file_type': file_type,
            'file_size_bytes': file_size,
            'status': 'pending',  # All new uploads start as pending
            'exam_type': exam_type or None,
            'file_hash': file_hash,
            'program': program
        }

        # A legacy/bulk upload can already have a document row for this URL
        # without the academic metadata.  Complete that row instead of trying
        # to insert a duplicate URL.  A complete row is already in the
        # verification/published workflow and must not be relabeled.
        existing_by_url = client.table('documents') \
            .select('id, college_id, department_id, subject_id, title, document_category') \
            .eq('file_url', file_url) \
            .limit(1) \
            .execute()
        if existing_by_url.data:
            existing = existing_by_url.data[0]
            is_labeled = all(existing.get(field) for field in (
                'college_id', 'department_id', 'subject_id', 'title', 'document_category'
            ))
            if is_labeled:
                logging.info(f"[Supabase] Duplicate registration prevented for URL: {file_url}")
                return {
                    'success': False,
                    'message': 'File is already labeled and registered in the system.',
                    'conflict': True,
                    'data': existing
                }

            update_res = client.table('documents').update(data).eq('id', existing['id']).execute()
            if update_res.data:
                logging.info(f"[Supabase] Completed metadata for existing document: {existing['id']}")
                return {'success': True, 'message': 'Existing file metadata updated', 'data': update_res.data[0]}
            return {'success': False, 'message': 'Failed to update existing file record'}
        # Duplicate protection for the same physical provider asset, even if
        # its URL changed after a Cloudinary transformation or delivery update.
        if cloudinary_public_id:
            dup_check = client.table('documents').select('id').eq('storage_provider', storage_provider).eq('provider_public_id', cloudinary_public_id).execute()
            if dup_check.data:
                logging.info(f"[Supabase] Duplicate registration prevented for {storage_provider} ID: {cloudinary_public_id}")
                return {'success': False, 'message': 'File is already labeled and registered in the system.', 'conflict': True, 'data': dup_check.data[0]}
        
        logging.info(f"[Supabase] Inserting document: {data.get('title')}")
        res = client.table('documents').insert(data).execute()
        
        if res.data:
            doc_id = res.data[0].get('id')
            logging.info(f"[Supabase] Successfully saved document record: {doc_id}")
            
            # --- Push to new Background Search Queue (Phase 2 Migration) ---
            try:
                client.table('search_documents').insert({
                    'file_id': doc_id,
                    'source': 'uploads',
                    'subject_id': sub_id,
                    'college_id': c_id,
                    'department_id': d_id,
                    'semester': semester,
                    'normalized_title': _normalize(title or file_name) if '_normalize' in globals() else (title or file_name).lower(),
                    'status': 'pending'
                }).execute()
                logging.info(f"[Supabase] Queued {doc_id} for background search indexing.")
            except Exception as search_q_err:
                logging.error(f"[Supabase] Warning: Could not queue for indexing: {search_q_err}")
            # -------------------------------------------------------------
            
            # Phase 15: Gamification / Dopamine Loop
            xp_data = {}
            if u_id:
                # Anti-abuse: duplicate uploads (same file_hash already published
                # by anyone) earn no publish points.
                is_duplicate = False
                if file_hash:
                    try:
                        dup_res = client.table('documents').select('id').eq('file_hash', file_hash).limit(2).execute()
                        # More than one row means: this new doc + an earlier identical one
                        is_duplicate = len(dup_res.data or []) > 1
                        if is_duplicate:
                            logging.info(f"[SCORING] duplicate upload detected (hash={file_hash[:12]}…), publish XP withheld for {u_id}")
                    except Exception as dup_err:
                        logging.warning(f"[SCORING] duplicate check failed (awarding XP): {dup_err}")

                desc = f"Uploaded {document_type} for {subject_name or 'subject'}"
                if is_duplicate:
                    xp_result = {'success': True, 'scored': False, 'reason': 'duplicate upload'}
                else:
                    xp_result = award_contribution_xp(u_id, 'upload_document', doc_id, 'document', desc, base_xp=25)
                if xp_result.get('success') and xp_result.get('xp_gained') is not None:
                    xp_data = {
                        'xp_gained': xp_result['xp_gained'],
                        'new_score': xp_result['new_score'],
                        'new_rank': xp_result['new_rank']
                    }
            
            res_data = res.data[0]
            res_data.update(xp_data)
            
            return {'success': True, 'message': 'Saved successfully', 'data': res_data}
        
        logging.error(f"[Supabase] Failed to save document record. Response empty.")
        return {'success': False, 'message': 'Failed to save record to database'}
        
    except Exception as e:
        traceback.print_exc()
        logging.error(f"[Supabase] Error saving file record: {e}")
        return {'success': False, 'message': str(e)}

def verify_hierarchy(college_id: str, branch_id: str, subject_id: str) -> bool:
    """Verifies that the provided academic hierarchy is valid."""
    client = init_supabase()
    if not client: return False
    try:
        # 1. Verify subject belongs to department (branch)
        if subject_id and branch_id:
            sub_res = client.table('subjects').select('id, department_id').eq('id', subject_id).execute()
            if not sub_res.data or str(sub_res.data[0].get('department_id')) != str(branch_id):
                return False
                
        # 2. Verify department belongs to college
        if branch_id and college_id:
            cd_res = client.table('college_departments').select('*').eq('college_id', college_id).eq('department_id', branch_id).execute()
            if not cd_res.data:
                return False

        return True
    except Exception as e:
        logging.error(f"[Supabase] Error in verify_hierarchy: {e}")
        return False

def get_registered_storage_ids() -> set:
    """Returns a set of strings in format 'storage_provider_id' for all registered files."""
    client = init_supabase()
    if not client: return set()
    try:
        res = client.table('documents').select('storage_provider, provider_public_id').execute()
        registered = set()
        for doc in res.data:
            prov = doc.get('storage_provider')
            sid = doc.get('provider_public_id')
            if prov and sid:
                registered.add(f"{prov}_{sid}")
        return registered
    except Exception as e:
        logging.error(f"[Supabase] Error getting registered storage ids: {e}")
        return set()

def get_pending_storage_assets() -> list:
    """Fetch files that still need labeling from the storage index."""
    client = init_supabase()
    if not client: return []
    try:
        res = client.table('storage_assets').select('*').eq('status', 'PENDING').execute()
        return res.data or []
    except Exception as e:
        logging.error(f"[Supabase] Error fetching pending assets: {e}")
        return []

def mark_storage_asset_labeled(provider: str, provider_public_id: str) -> bool:
    """Mark an asset as LABELED in the storage_assets table."""
    client = init_supabase()
    if not client: return False
    try:
        client.table('storage_assets').update({'status': 'LABELED'}).eq('provider', provider).eq('provider_public_id', provider_public_id).execute()
        return True
    except Exception as e:
        logging.error(f"[Supabase] Error updating asset status: {e}")
        return False

def log_label_audit(user_id: str, document_id: str, action: str, details: dict) -> bool:
    """Log an audit entry for labeling actions."""
    client = init_supabase()
    if not client: return False
    try:
        client.table('label_audit_logs').insert({
            'user_id': user_id,
            'document_id': document_id,
            'action': action,
            'details': json.dumps(details)
        }).execute()
        return True
    except Exception as e:
        logging.error(f"[Supabase] Error logging audit: {e}")
        return False

def _doc_to_json(doc: dict, current_user_id: str = None) -> dict:
    title = doc.get('title', 'Untitled')
    url = doc.get('file_url', '')
    doc_type = str(doc.get('document_category', 'Other')).capitalize()
    
    prof = doc.get('profiles') or doc.get('profiles!documents_uploader_id_fkey') or {}
    author = prof.get('full_name') or (prof.get('email') and prof.get('email').split('@')[0]) or 'Unknown'
    author_email = prof.get('email') or ''
    
    subj_data = doc.get('subjects') or doc.get('subjects!documents_subject_id_fkey') or {}
    subject = subj_data.get('name') or 'General'
    subject_code = subj_data.get('subject_code') or ''
    
    coll_data = doc.get('colleges') or doc.get('colleges!documents_college_id_fkey') or {}
    college_name = coll_data.get('name') or coll_data.get('abbreviation') or ''
    
    year = ''
    
    desc_str = doc.get('description') or '{}'
    try:
        if desc_str.startswith('{'):
            desc = json.loads(desc_str)
            if not subj_data: subject = desc.get('subject', subject)
            year = desc.get('year', '')
        else:
            if 'Year:' in desc_str:
                year = desc_str.split('Year:')[1].split('|')[0].strip()
    except Exception as e:
        log.debug(f'_doc_to_json: failed to parse description: {e}')

    file_path = url if url else f"Documents/{author}/{doc_type}/{year}/{subject}/{title}"
    
    # Check interaction status if current_user_id is provided
    is_liked = False
    is_bookmarked = False
    if current_user_id:
        if isinstance(doc.get('document_votes'), list):
            is_liked = any(str(v.get('user_id')) == str(current_user_id) for v in doc['document_votes'])
        if isinstance(doc.get('bookmarks'), list):
            is_bookmarked = any(str(b.get('user_id')) == str(current_user_id) for b in doc['bookmarks'])
    
    return {
        'file-name': title,
        'file-type': doc.get('file_type', 'pdf'),
        'file-path': file_path,
        'url': url,
        'type': doc_type,
        'subject': subject,
        'subject_code': subject_code,
        'year': str(year),
        'author': author,
        'author_email': author_email,
        'date': doc.get('created_at', '')[:10] if doc.get('created_at') else '',
        'size': format_file_size(doc.get('file_size_bytes') or 0),
        'cloudinary_id': doc.get('provider_public_id', ''),
        'source': doc.get('storage_provider', 'unknown'),
        'verified': doc.get('status') == 'approved',
        'record_id': doc.get('id', ''),
        'view_count': doc.get('view_count', 0),
        'like_count': doc.get('like_count', 0),
        'comment_count': len(doc.get('document_comments') or []) if 'document_comments' in doc else doc.get('comment_count', 0),
        'bookmark_count': doc.get('bookmark_count', 0),
        'is_liked': is_liked,
        'is_bookmarked': is_bookmarked,
        'college': college_name or 'Other'
    }

def get_all_files_merged(include_file_records=True, current_user_id=None) -> Dict:
    # Cache key: anon gets shared cache; authed users get personal cache (for like/bookmark state)
    _FILES_CACHE_TTL = 120  # 2 minutes
    cache_key = f'all_files:{current_user_id or "anon"}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return {'success': True, 'data': cached, 'count': len(cached)}
    client = init_supabase()
    if not client: return {'success': False, 'data': [], 'count': 0}
    try:
        res = client.table('documents') \
            .select('*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name, subject_code), colleges(name, abbreviation), document_votes(user_id), bookmarks(user_id), document_comments(id)') \
            .in_('status', ['approved', 'pending']) \
            .order('created_at', desc=True) \
            .execute()
        files = [_doc_to_json(d, current_user_id) for d in res.data] if res.data else []
        _cache[cache_key] = {'val': files, 'ts': _time.time() - (_CACHE_TTL - _FILES_CACHE_TTL)}
        return {'success': True, 'data': files, 'count': len(files)}
    except Exception as e:
        return {'success': False, 'data': [], 'count': 0, 'message': str(e)}

def get_all_file_records_formatted(current_user_id=None) -> List[Dict]:
    return get_all_files_merged(current_user_id=current_user_id).get('data', [])

def invalidate_files_cache():
    """Call after any document insert/update to clear the files cache."""
    keys_to_del = [k for k in _cache if k.startswith('all_files:')]
    for k in keys_to_del:
        del _cache[k]
    log.debug(f'Invalidated {len(keys_to_del)} file cache entries')

def get_related_documents(college_id: str = None, subject_id: str = None,
                           exclude_id: str = None, limit: int = 6) -> List[Dict]:
    """Fetch only related documents — avoids loading all 1000+ docs for sidebar."""
    client = init_supabase()
    if not client: return []
    try:
        q = client.table('documents') \
            .select('id, title, document_category, file_type, college_id, subject_id, created_at, view_count, provider_public_id, file_url, storage_provider') \
            .in_('status', ['approved', 'pending']) \
            .order('view_count', desc=True) \
            .limit(limit + 1)  # fetch one extra to exclude current doc
        if college_id and validate_uuid(college_id):
            q = q.eq('college_id', college_id)
        elif subject_id and validate_uuid(subject_id):
            q = q.eq('subject_id', subject_id)
        res = q.execute()
        docs = res.data or []
        # Exclude the current document
        if exclude_id:
            docs = [d for d in docs if d.get('id') != exclude_id]
        return docs[:limit]
    except Exception as e:
        log.error(f'get_related_documents error: {e}')
        return []

def search_file_records(search_query='', document_type=None, college_id=None, branch_id=None, year=None, program=None, limit=50) -> List[Dict]:
    client = init_supabase()
    if not client: return []
    try:
        q = client.table('documents').select('*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name)')
        if document_type: q = q.eq('document_category', document_type)
        if college_id and validate_uuid(college_id): q = q.eq('college_id', college_id)
        if branch_id and validate_uuid(branch_id): q = q.eq('department_id', branch_id)
        if program: q = q.eq('program', program)
        if search_query:
            q = q.or_(f"title.ilike.%{search_query}%,description.ilike.%{search_query}%")
        res = q.order('created_at', desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        log.error(f'search_file_records error: {e}')
        return []

def get_user_uploaded_files(user_email: str, limit: int = 20) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'data': []}
    try:
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': True, 'data': []}
        u_id = p_res.data[0]['id']
        
        res = client.table('documents') \
            .select('*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name)') \
            .eq('uploader_id', u_id) \
            .order('created_at', desc=True) \
            .limit(limit).execute()
        
        return {'success': True, 'data': res.data, 'count': len(res.data) if res.data else 0}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}

def delete_file_record(record_id: str, user_email: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False}
    try:
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        u_id = p_res.data[0]['id']
        
        res = client.table('documents').delete().eq('id', record_id).eq('uploader_id', u_id).execute()
        return {'success': True} if res.data else {'success': False}
    except Exception as e:
        log.error(f'delete_file_record error: {e}')
        return {'success': False}

def _get_document_uploader(document_id: str):
    """Uploader's profile id for a document, or None on failure."""
    try:
        res = init_supabase().table('documents').select('uploader_id').eq('id', document_id).limit(1).execute()
        return res.data[0].get('uploader_id') if res.data else None
    except Exception:
        return None


def toggle_like(user_email: str, document_id: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        u_id = p_res.data[0]['id']
        
        # Check if already voted
        vote_res = client.table('document_votes').select('*').eq('document_id', document_id).eq('user_id', u_id).execute()
        if vote_res.data:
            # Unlike
            client.table('document_votes').delete().eq('document_id', document_id).eq('user_id', u_id).execute()
            # Decrement document count (could be done via trigger, doing manually if no trigger available)
            doc_res = client.table('documents').select('like_count').eq('id', document_id).execute()
            count = max(0, (doc_res.data[0]['like_count'] or 0) - 1)
            client.table('documents').update({'like_count': count}).eq('id', document_id).execute()
            return {'success': True, 'is_liked': False, 'like_count': count}
        else:
            # Like
            client.table('document_votes').insert({'document_id': document_id, 'user_id': u_id, 'vote': 'like'}).execute()
            doc_res = client.table('documents').select('like_count').eq('id', document_id).execute()
            count = (doc_res.data[0]['like_count'] or 0) + 1
            client.table('documents').update({'like_count': count}).eq('id', document_id).execute()
            # Scoring: reward receiving a like (skip self-likes)
            try:
                from methods.scoring_engine import process_event
                uploader = _get_document_uploader(document_id)
                process_event(user_id=uploader, event_type='resource_liked', entity_id=document_id,
                              entity_type='document', actor_is_owner=(uploader == u_id),
                              description='Received a like')
            except Exception as e:
                logging.warning(f"[SCORING] like scoring skipped: {e}")
            return {'success': True, 'is_liked': True, 'like_count': count}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def toggle_bookmark(user_email: str, document_id: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        u_id = p_res.data[0]['id']
        
        check_res = client.table('bookmarks').select('*').eq('document_id', document_id).eq('user_id', u_id).execute()
        if check_res.data:
            # Remove bookmark
            client.table('bookmarks').delete().eq('document_id', document_id).eq('user_id', u_id).execute()
            # Update Document Counter
            doc_res = client.table('documents').select('bookmark_count').eq('id', document_id).execute()
            count = max(0, (doc_res.data[0]['bookmark_count'] or 0) - 1)
            client.table('documents').update({'bookmark_count': count}).eq('id', document_id).execute()
            return {'success': True, 'is_bookmarked': False, 'bookmark_count': count}
        else:
            # Add bookmark
            client.table('bookmarks').insert({'document_id': document_id, 'user_id': u_id}).execute()
            doc_res = client.table('documents').select('bookmark_count').eq('id', document_id).execute()
            count = (doc_res.data[0]['bookmark_count'] or 0) + 1
            client.table('documents').update({'bookmark_count': count}).eq('id', document_id).execute()
            # Scoring: reward receiving a bookmark (skip self-bookmarks)
            try:
                from methods.scoring_engine import process_event
                uploader = _get_document_uploader(document_id)
                process_event(user_id=uploader, event_type='resource_bookmarked', entity_id=document_id,
                              entity_type='document', actor_is_owner=(uploader == u_id),
                              description='Received a bookmark')
            except Exception as e:
                logging.warning(f"[SCORING] bookmark scoring skipped: {e}")
            return {'success': True, 'is_bookmarked': True, 'bookmark_count': count}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def add_comment(user_email: str, document_id: str, content: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        p_res = client.table('profiles').select('id, full_name, role').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        u_id = p_res.data[0]['id']
        
        res = client.table('document_comments').insert({
            'document_id': document_id,
            'user_id': u_id,
            'content': content
        }).execute()

        if res.data:
            # Scoring: reward the uploader receiving a comment (skip self-comments)
            try:
                from methods.scoring_engine import process_event
                uploader = _get_document_uploader(document_id)
                if uploader:
                    process_event(user_id=uploader, event_type='comment_created', entity_id=document_id,
                                  entity_type='document', actor_is_owner=(uploader == u_id),
                                  description='Received a comment')
            except Exception as e:
                logging.warning(f"[SCORING] comment scoring skipped: {e}")
            return {
                'success': True, 
                'comment': {
                    'id': res.data[0]['id'],
                    'content': res.data[0]['content'],
                    'created_at': res.data[0]['created_at'],
                    'user_id': u_id,
                    'profiles': {
                        'full_name': p_res.data[0]['full_name'],
                        'role': p_res.data[0]['role']
                    }
                }
            }
        return {'success': False, 'message': 'Failed'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_comments(document_id: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'data': []}
    try:
        res = client.table('document_comments') \
            .select('id, content, created_at, user_id, profiles(full_name, role)') \
            .eq('document_id', document_id) \
            .eq('is_deleted', False) \
            .order('created_at', desc=False) \
            .execute()
        return {'success': True, 'data': res.data if res.data else []}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}

def get_student_profile(user_id: str) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'data': None}
    try:
        # colleges and departments are FKs on profiles, NOT students
        # must be nested: profiles(*, colleges(*), departments(*))
        res = client.table('students') \
            .select('*, profiles(*, colleges(*), departments(*))') \
            .eq('profile_id', user_id) \
            .execute()

        if res.data:
            row     = res.data[0]
            prof    = row.get('profiles') or {}
            college = prof.get('colleges') or {}
            dept    = prof.get('departments') or {}
            flat = {
                'student_id':            row.get('profile_id'),
                'registration_number':   row.get('registration_number'),
                'pursuing_year':         row.get('pursuing_year'),
                'year_of_joining':       row.get('year_of_joining'),
                'degree':                row.get('degree') or prof.get('degree', ''),
                'profile_completed':     row.get('profile_completed', False),
                'student_name':          prof.get('full_name', ''),
                'student_email':         prof.get('email', ''),
                'student_moblie_number': prof.get('phone_number', ''),
                'user_role':             prof.get('role', 'student'),
                'college_id':            prof.get('college_id'),
                'branch_id':             prof.get('department_id'),
                'college_name':          college.get('name', ''),
                'branch_name':           dept.get('name', ''),
            }
            logging.info(f"[Profile] student row found -> {flat}")
            return {'success': True, 'data': flat}

        # Fallback: teacher role or no students row yet — read from profiles directly
        prof_res = client.table('profiles') \
            .select('*, colleges(*), departments(*)') \
            .eq('id', user_id) \
            .execute()

        if prof_res.data:
            prof    = prof_res.data[0]
            college = prof.get('colleges') or {}
            dept    = prof.get('departments') or {}
            flat = {
                'student_id':            user_id,
                'registration_number':   None,
                'pursuing_year':         None,
                'year_of_joining':       None,
                'degree':                prof.get('degree', ''),
                'profile_completed':     False,
                'student_name':          prof.get('full_name', ''),
                'student_email':         prof.get('email', ''),
                'student_moblie_number': prof.get('phone_number', ''),
                'user_role':             prof.get('role', 'student'),
                'college_id':            prof.get('college_id'),
                'branch_id':             prof.get('department_id'),
                'college_name':          college.get('name', ''),
                'branch_name':           dept.get('name', ''),
            }
            logging.warning(f"[Profile] profiles fallback -> {flat}")
            return {'success': True, 'data': flat}

        return {'success': True, 'data': None, 'message': 'Not found'}
    except Exception as e:
        logging.error(f"[supabase_helper] operation failed: {e}", exc_info=True)
        return {'success': False, 'data': None, 'message': str(e)}

def get_user_profile(user_id: str) -> Dict:
    """Fetch base profile data from the profiles table."""
    client = init_supabase()
    if not client: return {'success': False, 'data': None}
    try:
        res = client.table('profiles').select('*').eq('id', user_id).execute()
        if res.data: return {'success': True, 'data': res.data[0]}
        return {'success': False, 'data': None, 'message': 'Not found'}
    except Exception as e:
        return {'success': False, 'data': None, 'message': str(e)}

def create_or_update_student_profile(user_id: str, profile_data: dict) -> Dict:
    client = init_supabase()
    if not client:
        return {'success': False, 'message': 'Supabase client unavailable'}
    try:
        b_id   = profile_data.get('branch_id')
        c_id   = profile_data.get('college_id')
        role   = profile_data.get('user_role', 'student')
        degree = profile_data.get('degree')

        # Validate UUIDs – both college and branch are UUID FKs in abhihub schema
        valid_college_id    = c_id if validate_uuid(c_id) else None
        valid_department_id = b_id if validate_uuid(b_id) else None

        # Safely cast numeric fields
        def _int(val):
            try: return int(val) if val not in (None, '') else None
            except (ValueError, TypeError): return None

        logging.info(f"[Profile] Upserting profile for user_id={user_id}, role={role}, college={valid_college_id}, dept={valid_department_id}")

        prof_payload = {
            'id':            user_id,
            'role':          role,
            'email':         profile_data.get('student_email'),
            'full_name':     profile_data.get('student_name'),
            'college_id':    valid_college_id,
            'department_id': valid_department_id,
            'phone_number':  str(profile_data.get('student_moblie_number', '') or ''),
        }
        if degree:
            prof_payload['degree'] = degree

        try:
            profile_res = client.table('profiles').upsert(prof_payload).execute()
        except Exception:
            if 'degree' in prof_payload:
                prof_payload.pop('degree')
                profile_res = client.table('profiles').upsert(prof_payload).execute()

        if role == 'student':
            stud_payload = {
                'profile_id':          user_id,
                'registration_number': profile_data.get('registration_number') or None,
                'pursuing_year':       _int(profile_data.get('pursuing_year')),
                'year_of_joining':     _int(profile_data.get('year_of_joining')),
                'profile_completed':   True
            }
            if degree:
                stud_payload['degree'] = degree
            try:
                student_res = client.table('students').upsert(stud_payload).execute()
            except Exception:
                if 'degree' in stud_payload:
                    stud_payload.pop('degree')
                    student_res = client.table('students').upsert(stud_payload).execute()
            logging.info(f"[Profile] students upsert result: {student_res.data}")
        elif role == 'teacher':
            teacher_res = client.table('teachers').upsert({
                'profile_id':        user_id,
                'profile_completed': True
            }).execute()
            logging.info(f"[Profile] teachers upsert result: {teacher_res.data}")

        return {'success': True, 'message': 'Profile updated successfully'}

    except Exception as e:
        logging.error(f"[Profile ERROR] create_or_update_student_profile failed: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}

def check_profile_completed(user_id: str) -> bool:
    client = init_supabase()
    if not client: return False
    try:
        res = client.table('students').select('profile_completed').eq('profile_id', user_id).execute()
        if res.data: return res.data[0].get('profile_completed', False)
        return False
    except Exception as e:
        log.error(f'check_profile_completed error: {e}')
        return False
        
def get_all_file_records(limit=100, offset=0):
    client = init_supabase()
    try:
        res = client.table('documents').select('*', count='exact').range(offset, offset + limit - 1).execute()
        return {'success': True, 'data': res.data, 'total': getattr(res, 'count', 0), 'limit': limit, 'offset': offset}
    except Exception as e:
        return {'success': False, 'data': [], 'total': 0, 'message': str(e)}

def get_user_file_records(user_email: str, limit: int = 50) -> List[Dict]:
    res = get_user_uploaded_files(user_email, limit)
    return res.get('data', [])

# --- Analytics & Security Helpers ---

def log_security_audit_event(user_email: str, event_type: str, ip_address: str, user_agent: str, metadata: dict = None) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        user_id = None
        if user_email and user_email != 'unknown':
            p_res = client.table('profiles').select('id').eq('email', user_email).execute()
            if p_res.data:
                user_id = p_res.data[0]['id']
        
        client.table('security_audit_logs').insert({
            'user_id': user_id,
            'event': event_type,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'metadata': metadata or {}
        }).execute()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def save_push_subscription(user_email: str, endpoint: str, p256dh: str, auth: str, device_type: str = None) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        user_id = p_res.data[0]['id']
        
        client.table('push_subscriptions').upsert({
            'user_id': user_id,
            'endpoint': endpoint,
            'p256dh': p256dh,
            'auth': auth,
            'device_type': device_type
        }, on_conflict='endpoint').execute()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_all_push_subscriptions() -> Dict:
    client = init_supabase()
    if not client: return {}
    try:
        res = client.table('push_subscriptions').select('*, profiles(email)').execute()
        subs = {}
        for row in res.data:
            user_id = row['user_id']
            subs[user_id] = {
                'subscription': {
                    'endpoint': row['endpoint'],
                    'keys': {
                        'p256dh': row['p256dh'],
                        'auth': row['auth']
                    }
                },
                'email': row.get('profiles', {}).get('email', ''),
                'created_at': row.get('created_at'),
                'device_type': row.get('device_type')
            }
        return subs
    except Exception as e:
        logging.error(f"Error fetching subscriptions: {e}")
        return {}

def remove_push_subscription_by_endpoint(endpoint: str) -> bool:
    client = init_supabase()
    if not client: return False
    try:
        client.table('push_subscriptions').delete().eq('endpoint', endpoint).execute()
        return True
    except Exception as e:
        logging.error(f"Error removing subscription: {e}")
        return False

def log_notification(user_email: str, notification_type: str, title: str, message: str, url: str = None) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        if user_email == 'all':
            # Note: logging a system notification to a specific dummy table or leaving user_id null
            # The schema states user_id is NOT NULL, so logging an 'all' broadcast must be done differently.
            # We'll skip inserting into notifications table for 'all' broadcasts for now, 
            # or we could iterate users, which is heavy.
            return {'success': True, 'message': 'Broadcast not logged per-user'}
            
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data: return {'success': False, 'message': 'User not found'}
        user_id = p_res.data[0]['id']
        
        client.table('notifications').insert({
            'user_id': user_id,
            'type': notification_type,
            'title': title,
            'message': message,
            'action_url': url
        }).execute()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_notification_history(limit: int = 10) -> List[Dict]:
    client = init_supabase()
    if not client: return []
    try:
        res = client.table('notifications').select('*').order('created_at', desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        logging.error(f"Error fetching notifications: {e}")
        return []

# ── Points awarded per document category ───────────────────────────────────
POINTS_MAP = {
    'notes':          3,
    'imp questions':  3,
    'imp_questions':  3,
    'papers':         1,
    'paper':          1,
    'pyq':            1,
    'practical':      0.5,
    'syllabus':       0.5,
    'assisment':      0.5,
    'timetable':      0.5,
}
DEFAULT_POINTS = 0.5
# ────────────────────────────────────────────────────────────────────────────

def _doc_points(doc_category: str) -> float:
    """Return points for a given document_category string."""
    return POINTS_MAP.get((doc_category or '').lower(), DEFAULT_POINTS)


def calculate_user_ranks() -> List[Dict]:
    """
    Calculate the leaderboard by summing points per uploader across ALL
    their documents (both 'approved' and 'pending'), so new uploaders
    appear in the list immediately after their first upload.

    Returns a sorted list of dicts:
        [
          {
            'uploader_id': '<uuid>',
            'author':      '<full_name>',
            'points':      <float>,
            'upload_count': <int>
          },
          ...
        ]
    """
    client = init_supabase()
    if not client:
        return []
    try:
        # Include BOTH approved and pending so new uploaders are visible
        res = (
            client.table('documents')
            .select(
                'uploader_id, document_category, status, '
                'profiles!documents_uploader_id_fkey(full_name)'
            )
            .in_('status', ['approved', 'pending'])
            .execute()
        )

        # Key by uploader_id (UUID) — avoids name-collision bugs
        data_map: Dict[str, Dict] = {}  # uploader_id -> {author, points, upload_count}

        for doc in (res.data or []):
            uid = doc.get('uploader_id')
            if not uid:
                continue

            prof = doc.get('profiles')
            author_name = (
                prof.get('full_name', 'Unknown')
                if isinstance(prof, dict)
                else 'Unknown'
            )

            if uid not in data_map:
                data_map[uid] = {
                    'uploader_id':  uid,
                    'author':       author_name,
                    'points':       0.0,
                    'upload_count': 0,
                }

            # Always prefer a real name over 'Unknown'
            if author_name != 'Unknown':
                data_map[uid]['author'] = author_name

            cat = (doc.get('document_category') or '').lower()
            pts = _doc_points(cat)

            # Pending documents award half points until approved
            if doc.get('status') == 'pending':
                pts *= 0.5

            data_map[uid]['points']       += pts
            data_map[uid]['upload_count'] += 1

        rank_list = list(data_map.values())
        rank_list.sort(key=lambda x: x['points'], reverse=True)
        return rank_list

    except Exception as e:
        logging.error(f"[Ranking] Error calculating ranks: {e}")
        return []


def recalculate_and_persist_user_rank(user_id: str) -> Dict:
    """
    Recalculate the reputation score for a single user and write it
    back to abhihub.profiles.reputation_score.

    Call this after every successful upload so the DB stays in sync.
    """
    client = init_supabase()
    if not client:
        return {'success': False, 'message': 'No client'}
    try:
        res = (
            client.table('documents')
            .select('document_category, status')
            .eq('uploader_id', user_id)
            .in_('status', ['approved', 'pending'])
            .execute()
        )

        total_points = 0.0
        for doc in (res.data or []):
            cat = (doc.get('document_category') or '').lower()
            pts = _doc_points(cat)
            if doc.get('status') == 'pending':
                pts *= 0.5
            total_points += pts

        from decimal import Decimal, ROUND_HALF_UP
        precise = Decimal(str(total_points)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # profiles.reputation_score is INTEGER in DB — store rounded int
        # Run: ALTER COLUMN reputation_score TYPE numeric(10,2) to unlock decimals
        score_int = int(precise.to_integral_value(rounding=ROUND_HALF_UP))
        score = float(precise)  # returned in API response for XP display

        client.table('profiles').update(
            {'reputation_score': score_int}
        ).eq('id', user_id).execute()

        logging.info(f"[Ranking] Persisted reputation_score={score} for user {user_id}")
        return {'success': True, 'score': score}

    except Exception as e:
        logging.error(f"[Ranking] Error persisting rank for {user_id}: {e}")
        return {'success': False, 'message': str(e)}

def get_reputation_stats(user_id: str) -> Dict:
    """
    Dynamically calculate the 'students helped' metric and badges based on the user's approved documents.
    """
    client = init_supabase()
    if not client:
        return {'success': False, 'message': 'No client'}
    try:
        res = (
            client.table('documents')
            .select('status, view_count')
            .eq('uploader_id', user_id)
            .in_('status', ['approved', 'pending'])
            .execute()
        )
        
        approved_count = 0
        total_views = 0
        
        for doc in (res.data or []):
            if doc.get('status') == 'approved':
                approved_count += 1
            total_views += doc.get('view_count') or 0
            
        badges = []
        if approved_count >= 1:
            badges.append("Junior Helper")
        if approved_count >= 5:
            badges.append("Community Contributor")
        if total_views >= 500:
            badges.append("Senior Lifesaver")
            
        return {
            'success': True,
            'approved_uploads': approved_count,
            'students_helped': total_views,
            'badges': badges
        }
    except Exception as e:
        logging.error(f"[Ranking] Error calculating reputation stats for {user_id}: {e}")
        return {'success': False, 'message': str(e)}

def get_contribution_timeline(user_id: str) -> Dict:
    """Fetch user's contribution logs ordered by latest first."""
    client = init_supabase()
    if not client or not user_id: return {'success': False, 'timeline': []}
    try:
        res = client.table('contribution_logs').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(20).execute()
        return {'success': True, 'timeline': res.data or []}
    except Exception as e:
        logging.error(f"Error fetching timeline: {e}")
        return {'success': False, 'timeline': []}

def get_leaderboard_data(college_id: str = None, limit: int = 50) -> Dict:
    """Fetch leaderboard data. Tries leaderboard_view first, falls back to calculate_user_ranks()."""
    client = init_supabase()
    if not client: return {'success': False, 'data': []}

    def _build_from_view():
        query = client.table('leaderboard_view').select('*').gt('total_xp', 0)
        if college_id:
            query = query.eq('college_id', college_id)
        res = query.order('total_xp', desc=True).limit(limit).execute()
        leaderboard = []
        for i, row in enumerate(res.data or []):
            badges = []
            if row.get('total_xp') >= 1000: badges.append('Champion')
            elif row.get('total_xp') >= 500: badges.append('Hero')
            elif row.get('total_xp') >= 100: badges.append('Contributor')
            leaderboard.append({
                'rank': i + 1,
                'user_id': row.get('user_id'),
                'name': row.get('full_name') or 'Anonymous Student',
                'email': row.get('email', ''),
                'total_xp': row.get('total_xp', 0),
                'students_helped': row.get('students_helped', 0),
                'badges': badges
            })
        return leaderboard

    def _build_from_ranks():
        """Fallback: build leaderboard from calculate_user_ranks() + reputation stats."""
        ranks = calculate_user_ranks()
        leaderboard = []
        for i, r in enumerate(ranks[:limit]):
            uid = r.get('uploader_id')
            pts = r.get('points', 0)
            # Convert fractional points to XP (multiply by 10 for display)
            xp = int(pts * 10)
            badges = []
            if xp >= 1000: badges.append('Champion')
            elif xp >= 500: badges.append('Hero')
            elif xp >= 100: badges.append('Contributor')
            elif xp >= 10: badges.append('Starter')
            leaderboard.append({
                'rank': i + 1,
                'user_id': uid,
                'name': r.get('author') or 'Anonymous Student',
                'email': '',
                'total_xp': xp,
                'students_helped': r.get('upload_count', 0),
                'badges': badges
            })
        return leaderboard

    # Try the view first; fall back to direct calculation on any error
    try:
        result = _build_from_view()
        if result:
            return {'success': True, 'data': result}
    except Exception as e:
        logging.error(f"[Leaderboard] View query failed ({e}), falling back to calculate_user_ranks()")

    try:
        result = _build_from_ranks()
        return {'success': True, 'data': result}
    except Exception as e2:
        logging.error(f"[Leaderboard] Fallback also failed: {e2}")
        return {'success': False, 'data': []}

def update_document_metadata(file_path: str, update_data: dict) -> Dict:
    client = init_supabase()
    if not client: return {'success': False, 'message': 'No client'}
    try:
        # Match using file_url ilike mapping
        res = client.table('documents').select('id, description').ilike('file_url', f'%{file_path}%').limit(1).execute()
        if not res.data:
            return {'success': False, 'message': 'File not found'}
            
        doc_id = res.data[0]['id']
        current_desc_str = res.data[0].get('description') or '{}'
        try:
            desc = json.loads(current_desc_str)
        except Exception as e:
            log.debug(f'update_file_record: invalid JSON in description: {e}')
            desc = {}
            
        updates = {}
        if 'file-name' in update_data: updates['title'] = update_data['file-name']
        if 'file-type' in update_data: updates['file_type'] = update_data['file-type']
        if 'type' in update_data: updates['document_category'] = update_data['type']
        
        # update description JSON payload for subject and year
        if 'subject' in update_data: desc['subject'] = update_data['subject']
        if 'year' in update_data: desc['year'] = update_data['year']
        if 'exam' in update_data: desc['exam'] = update_data['exam']
        
        updates['description'] = json.dumps(desc)
        
        client.table('documents').update(updates).eq('id', doc_id).execute()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

# Dummy definitions for unused but imported
def get_all_uploaded_files(*a, **kw): return []
def save_uploaded_file_record(*a, **kw): pass
def validate_mobile_number(*a): return True
def validate_year_of_joining(*a): return True


def _notify_uploader_of_view(doc_id: str, viewer_id: str, viewer_email: str):
    """
    Notify the uploader when someone views their file.
    Throttled: skips if a 'file_view' notification was already sent for
    this uploader within the last 10 minutes (prevents spam).
    Runs in a daemon thread — non-blocking.
    """
    try:
        client = init_supabase()
        if not client:
            return

        # Fetch uploader_id, doc title, uploader profile name
        doc_res = client.table('documents') \
            .select('uploader_id, title, profiles!documents_uploader_id_fkey(full_name)') \
            .eq('id', doc_id).limit(1).execute()
        if not doc_res.data:
            return

        row = doc_res.data[0]
        uploader_id = row.get('uploader_id')
        doc_title = (row.get('title') or 'your file')[:50]

        # Skip self-view
        if not uploader_id or uploader_id == viewer_id:
            return

        # Throttle: if uploader already got a file_view notification in last 10 min, skip
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        recent = client.table('notifications') \
            .select('id') \
            .eq('user_id', uploader_id) \
            .eq('type', 'file_view') \
            .gte('created_at', cutoff) \
            .limit(1).execute()
        if recent.data:
            return  # Throttled

        # Resolve viewer display name from profile
        viewer_name = 'Someone'
        try:
            vr = client.table('profiles').select('full_name').eq('id', viewer_id).limit(1).execute()
            if vr.data:
                viewer_name = vr.data[0].get('full_name') or viewer_email.split('@')[0]
        except Exception as e:
            log.debug(f"save_file_record: profile lookup failed for viewer_id={viewer_id!r}: {e}")
            viewer_name = viewer_email.split('@')[0] if viewer_email else 'Someone'

        client.table('notifications').insert({
            'user_id': uploader_id,
            'type': 'file_view',
            'title': '\U0001f441\ufe0f Your file was viewed!',
            'message': f'{viewer_name} just viewed \u201c{doc_title}\u201d',
            'action_url': None,
            'is_read': False
        }).execute()
        logging.info(f'[NOTIFY] Sent file_view notification to uploader {uploader_id[:8]} from {viewer_name}')

    except Exception as e:
        logging.error(f'[NOTIFY] Non-critical notify error: {e}')


def get_user_notifications(user_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
    """Fetch paginated notifications for a user, newest first."""
    client = init_supabase()
    if not client:
        return []
    try:
        res = client.table('notifications') \
            .select('id, type, title, message, action_url, is_read, created_at') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        return res.data if res.data else []
    except Exception as e:
        logging.error(f'[NOTIFY] get_user_notifications error: {e}')
        return []


def mark_notifications_read(user_id: str) -> Dict:
    """Mark all unread notifications as read for a user."""
    client = init_supabase()
    if not client:
        return {'success': False}
    try:
        client.table('notifications') \
            .update({'is_read': True}) \
            .eq('user_id', user_id) \
            .eq('is_read', False) \
            .execute()
        return {'success': True}
    except Exception as e:
        logging.error(f'[NOTIFY] mark_notifications_read error: {e}')
        return {'success': False, 'message': str(e)}
def save_file_access(user_email: str, file_name: str, file_type: str = 'pdf', file_path: str = '', file_url: str = '', record_id: str = None) -> Dict:
    """
    Log a file access event and increment the view count for the document.
    Uses document_views table for tracking.
    """
    client = init_supabase()
    if not client: 
        return {'success': False, 'message': 'No Supabase client'}
    
    try:
        # 1. Resolve document_id from record_id or file metadata
        doc_id = record_id if record_id and validate_uuid(record_id) else None
        
        if not doc_id and file_url:
            res = client.table('documents').select('id').ilike('file_url', f'%{file_url}%').limit(1).execute()
            if res.data: 
                doc_id = res.data[0]['id']
        
        if not doc_id and file_path:
            res = client.table('documents').select('id').ilike('file_url', f'%{file_path}%').limit(1).execute()
            if res.data: 
                doc_id = res.data[0]['id']

        if not doc_id and file_name:
            res = client.table('documents').select('id').ilike('title', f'%{file_name}%').limit(1).execute()
            if res.data: 
                doc_id = res.data[0]['id']

        # 2. Get user_id from email
        user_id = None
        if user_email and user_email != 'unknown':
            profile_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if profile_res.data:
                user_id = profile_res.data[0]['id']

        # 3. Increment view_count in documents table
        if doc_id:
            try:
                doc_res = client.table('documents').select('view_count').eq('id', doc_id).execute()
                if doc_res.data:
                    current_views = doc_res.data[0].get('view_count') or 0
                    client.table('documents').update({'view_count': current_views + 1}).eq('id', doc_id).execute()
            except Exception as view_err:
                logging.error(f"Warning: Could not increment view count: {view_err}")

            # Fire-and-forget: notify uploader (non-blocking)
            import threading
            threading.Thread(
                target=_notify_uploader_of_view,
                args=(doc_id, user_id, user_email),
                daemon=True
            ).start()

        # 4. Log in document_views table
        if doc_id and user_id:
            try:
                from data.interactions import DocumentView
                result = DocumentView.log_view(
                    user_id=user_id,
                    document_id=doc_id,
                    ip_address='',
                    device_type=''
                )
                if result.get('success'):
                    logging.info(f"[FILE_ACCESS] Logged view for {user_email}: {file_name} (doc={doc_id[:8]})")
                else:
                    logging.warning(f"[FILE_ACCESS] Failed to log view: {result.get('message')}")
            except Exception as dv_err:
                logging.warning(f"Warning: Could not log to document_views: {dv_err}")
        else:
            logging.debug(f"[FILE_ACCESS] Skipped logging - doc_id={doc_id}, user_id={user_id}, file={file_name}")

        return {'success': True}
        
    except Exception as e:
        logging.error(f"Error in save_file_access: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}

def get_user_file_history(user_email: str, limit: int = 10) -> Dict:
    """
    Get file access history for a user using document_views table.
    """
    client = init_supabase()
    if not client: 
        return {'success': False, 'data': []}
    
    try:
        # Get user profile to find user_id
        profile_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
        if not profile_res.data:
            return {'success': False, 'data': [], 'message': 'User not found'}
        
        user_id = profile_res.data[0]['id']
        
        # Query document_views with document details
        res = client.table('document_views') \
            .select('id, document_id, accessed_at, documents(id, title, file_url, file_type, document_category)') \
            .eq('user_id', user_id) \
            .order('accessed_at', desc=True) \
            .limit(limit) \
            .execute()
        
        if res.data:
            # Transform to expected format, dedup by document_id
            history = []
            seen = set()
            for view in res.data:
                doc = view.get('documents')
                if doc and doc['id'] not in seen:
                    seen.add(doc['id'])
                    history.append({
                        'file_name': doc.get('title', 'Unknown'),
                        'file_type': doc.get('file_type', 'pdf'),
                        'file_url': doc.get('file_url', ''),
                        'accessed_at': view.get('accessed_at', ''),
                        'document_id': doc['id'],
                        'document_category': doc.get('document_category', ''),
                    })
            return {'success': True, 'data': history}
        
        return {'success': True, 'data': []}
            
    except Exception as e:
        logging.error(f"Error in get_user_file_history: {e}", exc_info=True)
        return {'success': False, 'data': [], 'message': str(e)}

def get_papo_meter_data(user_id: str) -> Dict:
    """
    Get Papo Meter data for a user.
    - pap_count: unique documents the user has accessed/viewed
    - punya_count: total views on all documents uploaded by the user
    """
    client = init_supabase()
    if not client:
        return {'pap_count': 0, 'punya_count': 0}
    
    pap_count = 0
    punya_count = 0
    
    try:
        # Pap: count distinct documents accessed by user
        views_res = client.table('document_views') \
            .select('document_id') \
            .eq('user_id', user_id) \
            .execute()
        if views_res.data:
            unique_docs = set(v['document_id'] for v in views_res.data)
            pap_count = len(unique_docs)
    except Exception as e:
        logging.error(f"[PapoMeter] Error getting pap count: {e}")
    
    try:
        # Punya: sum view_count of all documents uploaded by user
        docs_res = client.table('documents') \
            .select('view_count') \
            .eq('uploader_id', user_id) \
            .execute()
        if docs_res.data:
            punya_count = sum((d.get('view_count') or 0) for d in docs_res.data)
    except Exception as e:
        logging.error(f"[PapoMeter] Error getting punya count: {e}")
    
    return {'pap_count': pap_count, 'punya_count': punya_count}

def award_contribution_xp(user_id: str, action_type: str, entity_id: str = None, entity_type: str = 'document', description: str = '', base_xp=None) -> Dict:
    client = init_supabase()
    if not client or not user_id: return {'success': False}
    try:
        # Resolve points from scoring_config (admin-editable) unless caller pinned one
        if base_xp is None:
            try:
                from methods.scoring_engine import get_points
                pts = get_points()
                base_xp = float(pts.get(action_type, 0) or 0)
            except Exception:
                base_xp = 0.0
        if not base_xp or base_xp <= 0:
            return {'success': True, 'scored': False, 'reason': 'zero/unknown point value'}
        # 1. Log the contribution
        client.table('contribution_logs').insert({
            'user_id': user_id, 'action_type': action_type, 'entity_id': entity_id,
            'entity_type': entity_type, 'xp_awarded': base_xp, 'description': description
        }).execute()
        
        # 2. Update the profile XP
        p_res = client.table('profiles').select('reputation_score').eq('id', user_id).execute()
        if p_res.data:
            current_xp = p_res.data[0].get('reputation_score') or 0
            new_xp = current_xp + base_xp
            
            # Simple rank calculation based on new_xp
            rank = "Beginner"
            if new_xp >= 50: rank = "First Contribution"
            if new_xp >= 200: rank = "Contributor"
            if new_xp >= 500: rank = "Scholar"
            if new_xp >= 1000: rank = "Note Master"
            if new_xp >= 2500: rank = "Campus Legend"
            
            client.table('profiles').update({
                'reputation_score': new_xp,
                'rank_title': rank
            }).eq('id', user_id).execute()
            
            # 3. Badge Logic (Phase 15/17)
            if rank != "Beginner":
                try:
                    client.table('user_achievements').insert({
                        'user_id': user_id, 'badge_name': rank, 'badge_icon': '🏆'
                    }).execute()
                except Exception as e:
                    log.debug(f"add_xp_and_rank: badge insert failed (unique constraint?): {e}")
                    pass  # unique constraint handles duplicates
                    
            return {'success': True, 'xp_gained': base_xp, 'new_score': new_xp, 'new_rank': rank}
    except Exception as e:
        logging.error(f"Error awarding XP: {e}")
    return {'success': False}

def check_if_labeled(filename: str) -> bool:
    client = init_supabase()
    if not client: return False
    try:
        res = client.table('documents').select('id').eq('title', filename).limit(1).execute()
        return len(res.data) > 0
    except Exception as e:
        log.error(f'check_if_labeled error: {e}')
        return False
def save_labeled_paper(*a): return {'success': True}
def get_labeled_papers():
    client = init_supabase()
    if not client: return {'success': False, 'data': []}
    try:
        res = client.table('documents').select('*').execute()
        return {'success': True, 'data': res.data}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}
def add_paper_verification(*a): return {'success': True}
def get_pending_verification_papers(*a): return {'success': True, 'data': []}
def create_labeled_papers_table(*a): return True

def add_new_entity(entity_type: str, name: str, short_name: str = '', code: str = '', semester: int = None, parent_id: str = None) -> Dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "Database not initialized"}
    
    if parent_id == '0':
        parent_id = None
        
    try:
        if entity_type == 'college':
            res = client.table('colleges').insert({
                'name': name,
                'abbreviation': short_name,
                'popular_name': name
            }).execute()
            # Clear any specific caches if you have them, else just return
            return {"success": True, "id": res.data[0]['id'], "name": name}
            
        elif entity_type == 'department' or entity_type == 'branch':
            existing = client.table('departments').select('id, name').ilike('name', name).execute()
            if existing.data:
                dept_id = existing.data[0]['id']
            else:
                res = client.table('departments').insert({
                    'name': name,
                    'abbreviation': short_name
                }).execute()
                dept_id = res.data[0]['id']
                
            if parent_id:
                try:
                    client.table('college_departments').insert({
                        'college_id': parent_id,
                        'department_id': dept_id
                    }).execute()
                except Exception:
                    pass
            
            _cache_set(f"depts:{parent_id}", None)
            return {"success": True, "id": dept_id, "name": name}
            
        elif entity_type == 'subject':
            if not parent_id:
                return {"success": False, "message": "Department ID is required to add a subject"}
            res = client.table('subjects').insert({
                'name': name,
                'subject_code': code,
                'semester': semester if semester else None,
                'department_id': parent_id
            }).execute()
            
            _cache_set(f"subjs:{parent_id}:{semester}", None)
            _cache_set(f"subjs:{parent_id}:None", None)
            return {"success": True, "id": res.data[0]['id'], "name": name}
            
        else:
            return {"success": False, "message": "Unknown entity type"}
    except Exception as e:
        logging.error(f"[supabase_helper] operation failed: {e}", exc_info=True)
        return {"success": False, "message": str(e)}

def search_users_db(query_str: str, limit: int = 20) -> list:
    """Search student profiles by full_name, email, or document author names."""
    client = init_supabase()
    if not client: return []
    try:
        q = query_str.strip().lower()
        if not q: return []
        
        users_map = {}

        # 1. Search profiles table
        try:
            res = client.table('profiles').select('id, full_name, email, reputation_score, rank_title, is_verified, college_id, colleges(name)').or_(f"full_name.ilike.%{q}%,email.ilike.%{q}%").limit(limit).execute()
            for u in (res.data or []):
                uid = u.get('id')
                col = u.get('colleges') or {}
                name_str = u.get('full_name') or 'Student'
                users_map[uid] = {
                    'id': uid,
                    'name': name_str,
                    'email': u.get('email', ''),
                    'reputation_score': u.get('reputation_score', 0),
                    'rank_title': u.get('rank_title', 'Student'),
                    'is_verified': u.get('is_verified', False),
                    'college_name': col.get('name') or '',
                    'uploads_count': 0
                }
        except Exception as e1:
            logging.warning(f"[SearchUsersDB] Profiles query warning: {e1}")

        # 2. Search calculate_user_ranks() for document contributors
        try:
            ranks = calculate_user_ranks()
            for r in ranks:
                author_name = r.get('author') or ''
                uid = r.get('uploader_id')
                if q in author_name.lower() or (uid and uid in users_map):
                    if uid and uid in users_map:
                        users_map[uid]['uploads_count'] = r.get('upload_count', users_map[uid]['uploads_count'])
                        if r.get('points', 0) > 0:
                            users_map[uid]['reputation_score'] = int(r.get('points', 0) * 10)
                    elif uid:
                        users_map[uid] = {
                            'id': uid,
                            'name': author_name or 'Student',
                            'email': '',
                            'reputation_score': int(r.get('points', 0) * 10),
                            'rank_title': 'Contributor',
                            'is_verified': False,
                            'college_name': '',
                            'uploads_count': r.get('upload_count', 0)
                        }
        except Exception as e2:
            logging.warning(f"[SearchUsersDB] Ranks fallback warning: {e2}")

        result = list(users_map.values())[:limit]
        return result
    except Exception as e:
        logging.error(f"[SearchUsersDB] Error: {e}")
        return []

def get_user_peer_materials_db(target_user_id: str) -> dict:
    """Fetch user's uploaded materials and referred materials."""
    client = init_supabase()
    if not client: return {'success': False, 'uploads': [], 'referred': []}
    try:
        # 1. Fetch user's profile info
        prof_res = client.table('profiles').select('id, full_name, email, reputation_score, rank_title, referral_code, colleges(name)').eq('id', target_user_id).limit(1).execute()
        prof = (prof_res.data or [{}])[0]
        col = prof.get('colleges') or {}

        # 2. Fetch user's uploaded documents
        docs_res = client.table('documents').select('id, title, file_url, document_category, file_type, view_count, created_at, subjects(name)').eq('uploader_id', target_user_id).order('created_at', desc=True).limit(20).execute()
        uploads = []
        for d in (docs_res.data or []):
            subj = d.get('subjects') or {}
            uploads.append({
                'record_id': d.get('id'),
                'file-name': d.get('title'),
                'file-path': d.get('file_url'),
                'type': d.get('document_category') or 'Papers',
                'subject': subj.get('name', 'General'),
                'views': d.get('view_count', 0),
                'date': str(d.get('created_at', ''))[:10]
            })

        # 3. Fetch user's referred materials (recently accessed file history)
        referred = []
        try:
            history_res = client.table('user_file_views')\
                .select('file_id, created_at, documents(id, title, file_url, document_category, subjects(name))')\
                .eq('user_id', target_user_id).order('created_at', desc=True).limit(15).execute()
            seen_ids = set()
            for h in (history_res.data or []):
                doc = h.get('documents') or {}
                doc_id = doc.get('id')
                if not doc_id or doc_id in seen_ids: continue
                seen_ids.add(doc_id)
                subj = doc.get('subjects') or {}
                referred.append({
                    'record_id': doc_id,
                    'file-name': doc.get('title'),
                    'file-path': doc.get('file_url'),
                    'type': doc.get('document_category') or 'Notes',
                    'subject': subj.get('name', 'General')
                })
        except Exception as e:
            # Table may not exist in some deployments; log and continue with empty referred list
            logging.warning(f"[PeerMaterialsDB] History query skipped: {e}")

        return {
            'success': True,
            'user': {
                'id': prof.get('id'),
                'name': prof.get('full_name') or 'Student',
                'college_name': col.get('name') or '',
                'reputation_score': prof.get('reputation_score', 0),
                'rank_title': prof.get('rank_title', 'Student'),
                'referral_code': prof.get('referral_code') or ''
            },
            'uploads': uploads,
            'referred': referred
        }
    except Exception as e:
        logging.error(f"[PeerMaterialsDB] Error: {e}")
        return {'success': False, 'uploads': [], 'referred': []}


# ────────────────────────────────────────────────────────────────────────────
# Referral / Invite system (growth loop)
# ────────────────────────────────────────────────────────────────────────────

def generate_referral_code(user_id: str) -> str:
    """Deterministic, brandable referral code from the user's uuid.

    Format: ABHI-XXXXXX (first 6 hex chars of the uuid, uppercased).
    Falls back to a random suffix if it collides (extremely unlikely).
    """
    import uuid as _uuid
    import random as _random
    base = ('ABHI-' + str(user_id).replace('-', '')[:6].upper())
    # Guarantee uniqueness against the table.
    client = init_supabase()
    if not client:
        return base
    candidate = base
    for _ in range(5):
        res = client.table('profiles').select('id').eq('referral_code', candidate).execute()
        if not (res.data or []):
            return candidate
        candidate = base + _random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    # Last resort: fully random
    return 'ABHI-' + _uuid.uuid4().hex[:6].upper()


def ensure_referral_code(user_id: str) -> str:
    """Return the user's existing referral code, creating one if missing."""
    client = init_supabase()
    if not client:
        return ''
    try:
        res = client.table('profiles').select('referral_code').eq('id', user_id).limit(1).execute()
        if res.data and res.data[0].get('referral_code'):
            return res.data[0]['referral_code']
        code = generate_referral_code(user_id)
        client.table('profiles').update({'referral_code': code}).eq('id', user_id).execute()
        return code
    except Exception as e:
        logging.error(f"[Referral] ensure_referral_code failed: {e}")
        return ''


def resolve_referrer_by_code(code: str) -> str | None:
    """Map a referral code to a referrer profile id, or None."""
    if not code:
        return None
    client = init_supabase()
    if not client:
        return None
    try:
        res = client.table('profiles').select('id').eq('referral_code', str(code).strip().upper()).limit(1).execute()
        if res.data:
            return res.data[0].get('id')
    except Exception as e:
        logging.error(f"[Referral] resolve_referrer_by_code failed: {e}")
    return None


def register_referral(new_user_id: str, code: str, credit_inviter: int = 50, credit_invitee: int = 25) -> dict:
    """Credit both sides when a new user signs up via a referral code.

    - Sets referred_by on the new user (idempotent: only if not already set).
    - Awards referral_credits to both the inviter and the invitee.
    - Increments the inviter's referral_count.
    Idempotent: safe to call more than once for the same (user, code) pair.
    """
    client = init_supabase()
    if not client:
        return {'success': False, 'message': 'Supabase unavailable'}
    try:
        referrer_id = resolve_referrer_by_code(code)
        if not referrer_id or referrer_id == new_user_id:
            return {'success': False, 'message': 'No valid referrer for code'}

        # Guard: don't overwrite an already-credited referral (idempotency).
        # If already referred by the SAME code owner, treat as a safe repeat (no re-credit).
        cur = client.table('profiles').select('referred_by').eq('id', new_user_id).limit(1).execute()
        existing = (cur.data or [{}])[0].get('referred_by')
        if existing == referrer_id:
            return {'success': True, 'referrer_id': referrer_id,
                    'credit_inviter': 0, 'credit_invitee': 0, 'note': 'already referred'}
        if existing and existing != referrer_id:
            return {'success': False, 'message': 'User already referred by another code'}

        # Set referred_by on new user (idempotent no-op if already equal)
        client.table('profiles').update({'referred_by': referrer_id}).eq('id', new_user_id).execute()

        # Credit the invitee (read current, add, write)
        inv_data = client.table('profiles').select('referral_credits').eq('id', new_user_id).limit(1).execute()
        cur_credits = (inv_data.data or [{}])[0].get('referral_credits', 0) or 0
        client.table('profiles').update({'referral_credits': cur_credits + credit_invitee}).eq('id', new_user_id).execute()

        # Credit the inviter + bump count
        ref_data = client.table('profiles').select('referral_credits, referral_count').eq('id', referrer_id).limit(1).execute()
        rd = (ref_data.data or [{}])[0]
        client.table('profiles').update({
            'referral_credits': (rd.get('referral_credits', 0) or 0) + credit_inviter,
            'referral_count': (rd.get('referral_count', 0) or 0) + 1,
        }).eq('id', referrer_id).execute()

        return {'success': True, 'referrer_id': referrer_id,
                'credit_inviter': credit_inviter, 'credit_invitee': credit_invitee}
    except Exception as e:
        msg = str(e)
        # Distinguish a missing-column schema gap from other failures
        if 'referral_credits' in msg or 'referral_count' in msg or '42703' in msg:
            return {'success': False,
                    'message': 'Referral credit columns missing — apply migrations/016_referral_credit_columns.sql'}
        logging.error(f"[Referral] register_referral failed: {e}")
        return {'success': False, 'message': msg}

