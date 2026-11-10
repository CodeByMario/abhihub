"""
Channel Service (Phase 1)
Handles creator channels: 1 channel per account, custom branding, vanity handles,
and document association without modifying existing document tables.
"""
import logging
import re
from datetime import datetime, timezone
from methods.supabase_helper import init_supabase, init_supabase_admin, SUPABASE_URL, SUPABASE_KEY, SUPABASE_AVAILABLE
from supabase import create_client, ClientOptions

logger = logging.getLogger(__name__)

def _get_client(schema="abhihub"):
    admin = init_supabase_admin()
    if admin:
        return admin
    client = init_supabase()
    if client:
        return client
    if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema=schema))
        except Exception as e:
            logger.error(f"[CHANNEL] Fallback client error: {e}")
    return None

def _execute_with_schema_fallback(query_fn):
    """Executes query with 'abhihub' schema first; if table missing, tries 'public' schema."""
    client = _get_client("abhihub")
    if client:
        try:
            return query_fn(client)
        except Exception as e:
            err_str = str(e).lower()
            if "relation" in err_str or "does not exist" in err_str or "pgrst" in err_str:
                logger.info("[CHANNEL] Retrying with public schema...")
                try:
                    pub_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public"))
                    return query_fn(pub_client)
                except Exception as pub_err:
                    logger.error(f"[CHANNEL] Public schema error: {pub_err}")
            raise e
    return None

def sanitize_handle(handle: str) -> str:
    """Validate and clean handle: 3-30 chars, alphanumeric + underscores."""
    if not handle:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9_]', '', handle.strip().lower())
    return clean[:30]

def get_channel_by_handle(handle: str):
    """Fetch channel by handle (case-insensitive)."""
    clean_handle = sanitize_handle(handle)
    if not clean_handle:
        return None

    def _query(client):
        res = client.table('channels').select('*').ilike('handle', clean_handle).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None

    try:
        return _execute_with_schema_fallback(_query)
    except Exception as e:
        logger.error(f"[CHANNEL] get_channel_by_handle error: {e}")
        return None

def get_channel_by_user_id(user_id: str):
    """Fetch single channel owned by a user (1 channel per account)."""
    if not user_id:
        return None

    def _query(client):
        res = client.table('channels').select('*').eq('user_id', str(user_id)).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None

    try:
        return _execute_with_schema_fallback(_query)
    except Exception as e:
        logger.error(f"[CHANNEL] get_channel_by_user_id error: {e}")
        return None

def auto_index_channel(handle: str):
    """
    Automatically triggers search engine discovery (Google sitemap ping + IndexNow push)
    for a new or updated creator channel in a background thread with zero latency impact.
    """
    import threading

    def _worker():
        try:
            import os, requests
            base_domain = os.getenv('BASE_DOMAIN', 'www.abhihub.edu.eu.org').strip().lower()
            clean_h = sanitize_handle(handle)
            if not clean_h:
                return

            channel_url = f"https://{base_domain}/c/{clean_h}"
            sitemap_url = f"https://{base_domain}/sitemap-channels.xml"

            # 1. Instant submission to IndexNow (Bing, Yandex, Seznam, Naver)
            try:
                from methods.seo_helper import submit_to_indexnow
                submit_to_indexnow([channel_url])
            except Exception as e_in:
                logger.debug(f"[CHANNEL INDEX] IndexNow submit failed: {e_in}")

            # 2. Ping Google and Bing with updated Channels Sitemap
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AbhiHub-Bot/1.0; +https://www.abhihub.edu.eu.org)"}
            for ping_url in [
                f"https://www.google.com/ping?sitemap={sitemap_url}",
                f"https://www.bing.com/ping?sitemap={sitemap_url}"
            ]:
                try:
                    requests.get(ping_url, headers=headers, timeout=5)
                except Exception:
                    pass

            logger.info(f"[CHANNEL INDEX] Automatic search index ping completed for @{clean_h}")
        except Exception as e:
            logger.warning(f"[CHANNEL INDEX] Auto-index worker error for @{handle}: {e}")

    threading.Thread(target=_worker, daemon=True).start()

def save_user_channel(user_id: str, title: str, handle: str, bio: str = "",
                      avatar_url: str = "", banner_url: str = "", social_links: dict = None):
    """
    Creates or updates the user's single channel.
    Enforces 1 channel per account and unique handle.
    """
    clean_handle = sanitize_handle(handle)
    if not clean_handle or len(clean_handle) < 3:
        return False, "Handle must be at least 3 characters (letters, numbers, underscores)."

    title = (title or '').strip()[:100]
    if not title:
        return False, "Channel title is required."

    bio = (bio or '').strip()[:500]
    social_links = social_links or {}

    existing_channel = get_channel_by_user_id(user_id)

    # Check if handle is already taken by someone else
    handle_owner = get_channel_by_handle(clean_handle)
    if handle_owner and str(handle_owner.get('user_id')) != str(user_id):
        return False, f"Handle '@{clean_handle}' is already taken. Please choose another."

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        'title': title,
        'handle': clean_handle,
        'bio': bio,
        'avatar_url': avatar_url or '',
        'banner_url': banner_url or '',
        'social_links': social_links,
        'updated_at': now_iso
    }

    def _upsert(client):
        if existing_channel:
            res = client.table('channels').update(payload).eq('user_id', str(user_id)).execute()
        else:
            payload['user_id'] = str(user_id)
            payload['views_count'] = 0
            payload['created_at'] = now_iso
            res = client.table('channels').insert(payload).execute()
        return res.data

    try:
        _execute_with_schema_fallback(_upsert)
        auto_index_channel(clean_handle)
        return True, clean_handle
    except Exception as e:
        logger.error(f"[CHANNEL] save_user_channel error: {e}")
        return False, f"Failed to save channel: {str(e)}"

def increment_channel_views(channel_id: str, current_views: int = 0):
    """Increment view counter for a channel."""
    if not channel_id:
        return

    def _inc(client):
        client.table('channels').update({
            'views_count': (current_views or 0) + 1
        }).eq('id', channel_id).execute()

    try:
        _execute_with_schema_fallback(_inc)
    except Exception as e:
        logger.warning(f"[CHANNEL] increment_channel_views error: {e}")

def get_channel_notes(user_id: str):
    """
    Fetches all notes/documents published by this channel's owner.
    Reuses existing documents table with full Apple card metadata relations.
    """
    if not user_id:
        return []

    client = _get_client("abhihub")
    if not client:
        return []

    try:
        select_fields = (
            'id, title, document_category, file_type, file_url, status, view_count, is_paid, price, created_at, '
            'subjects(name, subject_code), colleges(name, abbreviation), departments(name, abbreviation), profiles:uploader_id(full_name)'
        )
        res = client.table('documents').select(
            select_fields
        ).eq('uploader_id', str(user_id)).order('created_at', desc=True).limit(100).execute()

        items = []
        for r in (res.data or []):
            subj = r.get('subjects') if isinstance(r.get('subjects'), dict) else {}
            col = r.get('colleges') if isinstance(r.get('colleges'), dict) else {}
            dept = r.get('departments') if isinstance(r.get('departments'), dict) else {}
            uploader = r.get('profiles') if isinstance(r.get('profiles'), dict) else {}

            subj_name = subj.get('name') or ''
            subj_code = subj.get('subject_code') or (dept.get('abbreviation') or 'ENG')
            college_abbr = col.get('abbreviation') or (col.get('name')[:6] if col.get('name') else 'GHRCE')
            uploader_name = uploader.get('full_name') or 'Creator'

            items.append({
                'id': r.get('id'),
                'title': r.get('title') or 'Untitled Document',
                'category': (r.get('document_category') or 'Notes').capitalize(),
                'document_category': r.get('document_category') or 'notes',
                'subject': subj_name or 'General',
                'subject_name': subj_name,
                'subject_code': subj_code,
                'college_abbr': college_abbr,
                'uploader_name': uploader_name,
                'file_type': (r.get('file_type') or 'PDF').upper(),
                'status': r.get('status') or 'approved',
                'views': r.get('view_count') or 0,
                'view_count': r.get('view_count') or 0,
                'is_paid': bool(r.get('is_paid')),
                'price': float(r.get('price') or 0),
                'price_inr': float(r.get('price') or 0),
                'file_url': r.get('file_url') or '',
                'created_at': r.get('created_at', '')
            })
        return items
    except Exception as e:
        logger.error(f"[CHANNEL] get_channel_notes error: {e}")
        return []

_seed_done = False

def ensure_seed_channels():
    """Generates channels for target accounts if not already present."""
    global _seed_done
    if _seed_done:
        return
    _seed_done = True

    targets = [
        {
            'emails': ['vaibhavi@abhihbu.com', 'vaibhavi@abhihub.com'],
            'handle': 'vaibhavi',
            'title': 'Vaibhavi Study Hub',
            'bio': 'Curated university notes, revision roadmaps, and high-yield exam material.'
        },
        {
            'emails': ['abhijeetshende4053@gmail.com'],
            'handle': 'abhijeet',
            'title': 'Abhijeet Shende',
            'bio': 'Engineering question papers, handwritten lecture notes, and topper resources.'
        },
        {
            'emails': ['codebymario@gmail.om', 'codebymario@gmail.com'],
            'handle': 'codebymario',
            'title': 'CodeByMario',
            'bio': 'Computer Science, coding notes, engineering formulas, and lab practicals.'
        }
    ]

    client = _get_client("abhihub")
    if not client:
        return

    for target in targets:
        user_id = None
        for em in target['emails']:
            try:
                p_res = client.table('profiles').select('id, full_name, email').ilike('email', em).limit(1).execute()
                if p_res.data and len(p_res.data) > 0:
                    user_id = p_res.data[0].get('id')
                    break
            except Exception as e:
                logger.debug(f"[CHANNEL SEED] Profile lookup error for {em}: {e}")

        if not user_id:
            continue

        existing = get_channel_by_user_id(user_id)
        if not existing:
            save_user_channel(
                user_id=user_id,
                title=target['title'],
                handle=target['handle'],
                bio=target['bio']
            )
            logger.info("[CHANNEL SEED] Created seeded creator channel")

def get_featured_channels(limit=10, user_college_id=None):
    """Fetches active creator channels, prioritizing user's college first then AbhiHub."""
    try:
        ensure_seed_channels()
    except Exception as e:
        logger.warning(f"[CHANNEL] ensure_seed_channels failed: {e}")

    def _query(client):
        res = client.table('channels').select('*').order('views_count', desc=True).limit(25).execute()
        return res.data or []

    channels = []
    try:
        raw_channels = _execute_with_schema_fallback(_query) or []
        user_ids = [ch['user_id'] for ch in raw_channels if ch.get('user_id')]
        prof_map = {}
        if user_ids:
            try:
                client = _get_client("abhihub")
                if client:
                    p_res = client.table('profiles').select('id, college_id, full_name, colleges(name, abbreviation)').in_('id', user_ids).execute()
                    for p in (p_res.data or []):
                        prof_map[p['id']] = p
            except Exception as e_p:
                logger.debug(f"[CHANNEL] Profile lookup for channels: {e_p}")

        campus_channels = []
        other_channels = []

        for ch in raw_channels:
            u_id = ch.get('user_id')
            prof = prof_map.get(u_id, {})
            col_info = prof.get('colleges') or {}
            ch_col_id = prof.get('college_id')
            col_name = col_info.get('name') or ''
            col_abbr = col_info.get('abbreviation') or ''

            ch['college_name'] = col_name
            ch['college_abbr'] = col_abbr
            ch['creator_name'] = prof.get('full_name') or ch.get('title')

            notes = get_channel_notes(u_id) if u_id else []
            ch['notes_count'] = len(notes)

            # Preference: creator from user's college first, then AbhiHub
            if user_college_id and ch_col_id and str(ch_col_id) == str(user_college_id):
                ch['is_campus_match'] = True
                ch['badge_label'] = f"Your Campus • {col_abbr}" if col_abbr else "Campus Creator"
                campus_channels.append(ch)
            else:
                ch['is_campus_match'] = False
                ch['badge_label'] = f"{col_abbr} • Creator" if col_abbr else "AbhiHub Creator"
                other_channels.append(ch)

        channels = (campus_channels + other_channels)[:limit]
    except Exception as e:
        logger.error(f"[CHANNEL] get_featured_channels error: {e}")

    return channels

get_home_creator_channels = get_featured_channels



def get_preview_notes(slug=None):
    """Fetches live real paid and free notes from AbhiHub with full homepage metadata."""
    if slug:
        channel = get_channel_by_handle(slug)
        if channel and channel.get('user_id'):
            notes = get_channel_notes(channel.get('user_id'))
            if notes:
                return notes

    client = _get_client("abhihub")
    if not client:
        return []

    try:
        select_fields = (
            'id, title, document_category, file_type, file_url, status, view_count, is_paid, price, created_at, '
            'subjects(name, subject_code), colleges(name, abbreviation), departments(name, abbreviation), profiles:uploader_id(full_name)'
        )
        paid_res = client.table('documents').select(select_fields).eq('is_paid', True).order('created_at', desc=True).limit(6).execute()
        free_res = client.table('documents').select(select_fields).eq('is_paid', False).order('created_at', desc=True).limit(6).execute()

        items = []
        for r in (paid_res.data or []) + (free_res.data or []):
            subj = r.get('subjects') if isinstance(r.get('subjects'), dict) else {}
            col = r.get('colleges') if isinstance(r.get('colleges'), dict) else {}
            dept = r.get('departments') if isinstance(r.get('departments'), dict) else {}
            prof = r.get('profiles') if isinstance(r.get('profiles'), dict) else {}

            subj_name = subj.get('name') if subj else None
            file_title = r.get('title') or 'Untitled Document'
            display_subject = subj_name if (subj_name and subj_name != 'General Engineering' and subj_name != 'General') else file_title
            subj_code = subj.get('subject_code') or dept.get('abbreviation') or 'ENG'
            uploader = prof.get('full_name') or 'Student Contributor'
            college_abbr = col.get('abbreviation') or 'GHRCE'

            items.append({
                'id': r.get('id'),
                'title': file_title,
                'display_subject': display_subject,
                'category': (r.get('document_category') or 'Notes').capitalize(),
                'subject': subj_name or 'General',
                'subject_code': subj_code,
                'college_abbr': college_abbr,
                'uploader_name': uploader,
                'file_type': (r.get('file_type') or 'PDF').upper(),
                'status': r.get('status') or 'approved',
                'views': r.get('view_count') or 0,
                'is_paid': bool(r.get('is_paid')),
                'price': float(r.get('price') or 0),
                'file_url': r.get('file_url') or ''
            })
        return items
    except Exception as e:
        logger.error(f"[CHANNEL] get_preview_notes error: {e}")
        return []


PROSPECT_LEADS = {
    'cs_engineering_gyan': {
        'handle': 'cs_engineering_gyan',
        'title': 'CS Engineering Gyan',
        'bio': 'Computer Science Engineering lectures, DSA notes, Operating Systems, DBMS & GATE preparation material.',
        'avatar': 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@csegyan', 'telegram': 'https://t.me/csegyan'},
        'views': 45200,
        'rating': 4.9
    },
    'ak_engineering': {
        'handle': 'ak_engineering',
        'title': 'AK Engineering Academy',
        'bio': 'Civil & Mechanical Engineering standard university notes, SOM, TOM, Fluid Mechanics & solved question banks.',
        'avatar': 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@akengineering', 'telegram': 'https://t.me/akengineering'},
        'views': 38900,
        'rating': 4.8
    },
    'poriyaan_in': {
        'handle': 'poriyaan_in',
        'title': 'Poriyaan.in',
        'bio': 'Anna University & Tamil Nadu engineering semester notes, previous year question papers & lab manuals.',
        'avatar': 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@poriyaan', 'telegram': 'https://t.me/poriyaan'},
        'views': 52100,
        'rating': 4.9
    },
    'online_engineering': {
        'handle': 'online_engineering',
        'title': 'Online Engineering',
        'bio': 'Comprehensive Civil Engineering courses, ESE & GATE notes, Environmental & Structural Engineering formula sheets.',
        'avatar': 'https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@onlineengineering', 'telegram': 'https://t.me/onlineengineering'},
        'views': 64300,
        'rating': 5.0
    },
    'one_night_engineer': {
        'handle': 'one_night_engineer',
        'title': 'One Night Engineer',
        'bio': 'Exam-night savior summary sheets, passing cheat-sheets, high-weightage topics & solved KTUs/VTU/SPPU papers.',
        'avatar': 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@onenightengineer', 'telegram': 'https://t.me/onenightengineer'},
        'views': 89700,
        'rating': 4.9
    },
    'sandeep_jyani': {
        'handle': 'sandeep_jyani',
        'title': 'Sandeep Jyani Civil',
        'bio': 'All India SSC JE, State AE/JE, RRB JE Civil Engineering lecture notes, handbooks, and quick revision charts.',
        'avatar': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@sandeepjyanicivil', 'telegram': 'https://t.me/sandeepjyani'},
        'views': 112000,
        'rating': 5.0
    },
    'study_with_wasu': {
        'handle': 'study_with_wasu',
        'title': 'Study With Wasudha',
        'bio': 'Electronics & Communication, Digital Signal Processing, Embedded Systems & GHRCE university notes.',
        'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80',
        'banner': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200&auto=format&fit=crop&q=80',
        'socials': {'youtube': 'https://youtube.com/@studywithwasu', 'telegram': 'https://t.me/studywithwasu'},
        'views': 28400,
        'rating': 4.9
    }
}
ALL_LEADS = PROSPECT_LEADS


def get_all_channel_handles():
    """Returns unique handles and metadata for all channels (Supabase + Prospect leads) for Google sitemap indexing."""
    handles_map = {}

    # 1. Include prospect / seed leads
    for h, lead in ALL_LEADS.items():
        clean_h = sanitize_handle(h)
        if clean_h:
            handles_map[clean_h] = {
                'handle': clean_h,
                'updated_at': None
            }

    # 2. Include database channels
    def _query(client):
        return client.table('channels').select('handle, updated_at, created_at').execute().data or []

    try:
        db_channels = _execute_with_schema_fallback(_query) or []
        for ch in db_channels:
            h = sanitize_handle(ch.get('handle', ''))
            if h:
                handles_map[h] = {
                    'handle': h,
                    'updated_at': ch.get('updated_at') or ch.get('created_at')
                }
    except Exception as e:
        logger.warning(f"[CHANNEL] get_all_channel_handles db error: {e}")

    return list(handles_map.values())


def fetch_youtube_branding(channel_url_or_handle: str) -> dict:
    """
    Extracts channel title, avatar, and banner directly from a YouTube public link or handle
    using zero-cost HTML scraping (no Google API key required).
    """
    import requests, re, json

    raw = (channel_url_or_handle or "").strip()
    if not raw:
        return {"success": False, "error": "Empty channel link provided"}

    # Normalize target URL
    if not raw.startswith("http"):
        handle_clean = raw if raw.startswith("@") else f"@{raw}"
        target_url = f"https://www.youtube.com/{handle_clean}"
    else:
        target_url = raw

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(target_url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return {"success": False, "error": f"YouTube returned HTTP {resp.status_code}"}

        html = resp.text

        # 1. Avatar (og:image)
        avatar_url = None
        m_og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if not m_og_img:
            m_og_img = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html, re.I)
        if m_og_img:
            avatar_url = m_og_img.group(1)
            # Request higher resolution avatar
            avatar_url = re.sub(r'=s\d+-c-k-c0x[0-9a-f]+-no-rj', '=s800-c-k-c0x00ffffff-no-rj', avatar_url)

        # 2. Title & Description
        title = None
        m_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if m_title:
            title = m_title.group(1).replace("&amp;", "&")

        description = None
        m_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if m_desc:
            description = m_desc.group(1).replace("&amp;", "&")

        # 3. Channel Banner
        banner_url = None
        banner_matches = re.findall(r'https://yt3\.googleusercontent\.com/[a-zA-Z0-9_\-]+=w\d+-fcrop64=[a-zA-Z0-9_\-]+', html)
        if banner_matches:
            banner_url = re.sub(r'=w\d+-', '=w1280-', banner_matches[-1])

        if not banner_url:
            m_data = re.search(r'var ytInitialData\s*=\s*({.+?});</script>', html)
            if m_data:
                try:
                    data = json.loads(m_data.group(1))
                    header = data.get("header", {})
                    c_header = header.get("c4TabbedHeaderRenderer", {}) or header.get("pageHeaderRenderer", {})
                    banner = c_header.get("banner", {}) or c_header.get("content", {}).get("pageHeaderViewModel", {}).get("banner", {})
                    sources = banner.get("imageBannerViewModel", {}).get("image", {}).get("sources", []) or banner.get("thumbnails", [])
                    if sources:
                        banner_url = sources[-1].get("url")
                except Exception:
                    pass

        return {
            "success": True,
            "title": title,
            "description": description,
            "avatar_url": avatar_url,
            "banner_url": banner_url
        }
    except Exception as e:
        logger.error(f"[YOUTUBE SCRAPE] Error extracting branding: {e}")
        return {"success": False, "error": str(e)}


_OG_CACHE = {}

def generate_channel_og_image(channel: dict) -> bytes:
    """
    Generates a 1200x630 pixel high-resolution OpenGraph preview image for social sharing
    (WhatsApp, Twitter, LinkedIn, Telegram, Discord, Google) with official AbhiHub branding.
    Includes in-memory caching to eliminate redundant render overhead.
    """
    handle = channel.get('handle') or 'creator'
    cache_key = f"{handle}_{channel.get('title', '')}_{channel.get('avatar_url', '')}"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    try:
        from PIL import Image, ImageDraw, ImageFont
        import os, io, requests

        w, h = 1200, 630
        img = Image.new('RGB', (w, h), color='#080c14')
        draw = ImageDraw.Draw(img)

        # Subtle ambient background glows
        for r in range(280, 0, -15):
            alpha = int(12 * (1 - r / 280))
            draw.ellipse([w - 200 - r, -100 - r, w - 200 + r, -100 + r], fill=(99, 102, 241, alpha))

        for r in range(240, 0, -15):
            alpha = int(10 * (1 - r / 240))
            draw.ellipse([-80 - r, h - 80 - r, -80 + r, h - 80 + r], fill=(6, 182, 212, alpha))

        # Card container & inner canvas
        draw.rounded_rectangle([28, 28, w - 28, h - 28], radius=24, outline='#1e293b', width=2)
        draw.rounded_rectangle([30, 30, w - 30, h - 30], radius=22, fill='#0d1322')

        # Font resolution
        font_bold = "C:\\Windows\\Fonts\\segoeuib.ttf" if os.path.exists("C:\\Windows\\Fonts\\segoeuib.ttf") else "C:\\Windows\\Fonts\\arialbd.ttf"
        font_reg = "C:\\Windows\\Fonts\\segoeui.ttf" if os.path.exists("C:\\Windows\\Fonts\\segoeui.ttf") else "C:\\Windows\\Fonts\\arial.ttf"

        f_brand = ImageFont.truetype(font_bold, 28) if os.path.exists(font_bold) else ImageFont.load_default()
        f_badge = ImageFont.truetype(font_bold, 15) if os.path.exists(font_bold) else ImageFont.load_default()
        f_title = ImageFont.truetype(font_bold, 44) if os.path.exists(font_bold) else ImageFont.load_default()
        f_handle = ImageFont.truetype(font_bold, 24) if os.path.exists(font_bold) else ImageFont.load_default()
        f_bio = ImageFont.truetype(font_reg, 22) if os.path.exists(font_reg) else ImageFont.load_default()
        f_pill = ImageFont.truetype(font_bold, 16) if os.path.exists(font_bold) else ImageFont.load_default()
        f_foot = ImageFont.truetype(font_reg, 16) if os.path.exists(font_reg) else ImageFont.load_default()
        f_foot_bold = ImageFont.truetype(font_bold, 18) if os.path.exists(font_bold) else ImageFont.load_default()

        # Top Header Branding
        draw.text((70, 68), "AbhiHub", fill='#38bdf8', font=f_brand)
        draw.text((188, 73), "CREATOR NETWORK", fill='#818cf8', font=f_badge)

        # Verified Partner Badge
        badge_text = "VERIFIED CAMPUS PARTNER"
        draw.rounded_rectangle([w - 320, 65, w - 70, 102], radius=18, fill='#064e3b', outline='#10b981', width=1)
        draw.text((w - 295, 74), badge_text, fill='#34d399', font=f_badge)

        draw.line([70, 126, w - 70, 126], fill='#1e293b', width=1)

        # Channel Avatar
        avatar_size = 140
        av_x, av_y = 70, 165
        avatar_drawn = False
        av_url = channel.get('avatar_url') or channel.get('avatar')
        if av_url and av_url.startswith('http'):
            try:
                r = requests.get(av_url, timeout=3)
                if r.status_code == 200:
                    raw_av = Image.open(io.BytesIO(r.content)).convert('RGBA')
                    raw_av = raw_av.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    mask = Image.new('L', (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                    draw.ellipse([av_x - 4, av_y - 4, av_x + avatar_size + 4, av_y + avatar_size + 4], fill='#4f46e5')
                    img.paste(raw_av, (av_x, av_y), mask)
                    avatar_drawn = True
            except Exception:
                pass

        if not avatar_drawn:
            draw.ellipse([av_x, av_y, av_x + avatar_size, av_y + avatar_size], fill='#312e81', outline='#6366f1', width=3)
            initial = (channel.get('title') or channel.get('handle') or 'A')[0].upper()
            f_init = ImageFont.truetype(font_bold, 72) if os.path.exists(font_bold) else ImageFont.load_default()
            draw.text((av_x + 48, av_y + 24), initial, fill='#ffffff', font=f_init)

        # Channel Meta Info
        text_x = av_x + avatar_size + 36
        title = (channel.get('title') or 'Creator Channel')[:38]
        draw.text((text_x, 168), title, fill='#ffffff', font=f_title)
        draw.text((text_x, 230), f"@{handle}", fill='#818cf8', font=f_handle)

        bio = (channel.get('bio') or 'Curated university lecture notes, exam roadmaps, and verified study resources.')[:120]
        draw.text((text_x, 275), bio, fill='#94a3b8', font=f_bio)

        # Feature Pills
        pills = [
            ("Verified University Notes", "#38bdf8", "#082f49"),
            ("Solved PYQs & Papers", "#a855f7", "#3b0764"),
            ("Free Student Access", "#10b981", "#022c22")
        ]
        px = text_x
        py = 350
        for ptext, pcolor, pbg in pills:
            pw = len(ptext) * 10 + 26
            draw.rounded_rectangle([px, py, px + pw, py + 38], radius=19, fill=pbg, outline=pcolor, width=1)
            draw.text((px + 13, py + 8), ptext, fill=pcolor, font=f_pill)
            px += pw + 14

        draw.line([70, 480, w - 70, 480], fill='#1e293b', width=1)

        # Footer Platform Branding
        draw.text((70, 515), "AbhiHub", fill='#ffffff', font=f_foot_bold)
        draw.text((156, 517), "— World's #1 PYQ & Notes Platform • Made in India", fill='#64748b', font=f_foot)
        draw.text((70, 545), "Join thousands of campus creators & students studying smarter.", fill='#475569', font=f_foot)

        # URL Capsule
        url_text = f"www.abhihub.edu.eu.org/c/{handle}"
        url_box_w = len(url_text) * 11 + 36
        bx1 = w - 70 - url_box_w
        draw.rounded_rectangle([bx1, 510, w - 70, 560], radius=16, fill='#1e293b', outline='#3b82f6', width=1)
        draw.text((bx1 + 18, 523), url_text, fill='#60a5fa', font=f_foot_bold)

        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        img_bytes = buf.getvalue()

        # Cache result (keep up to 100 images)
        if len(_OG_CACHE) > 100:
            _OG_CACHE.clear()
        _OG_CACHE[cache_key] = img_bytes
        return img_bytes
    except Exception as e:
        logger.error(f"[CHANNEL OG] Error generating image: {e}")
        # Return simple 1x1 fallback PNG on failure
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
