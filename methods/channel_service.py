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
    Reuses existing documents table with zero changes.
    """
    if not user_id:
        return []

    client = _get_client("abhihub")
    if not client:
        return []

    try:
        res = client.table('documents').select(
            'id, title, document_category, file_type, file_url, status, view_count, is_paid, price, created_at, subjects(name)'
        ).eq('uploader_id', str(user_id)).order('created_at', desc=True).limit(100).execute()

        items = []
        for r in (res.data or []):
            subj = (r.get('subjects') or {}).get('name') if isinstance(r.get('subjects'), dict) else ''
            items.append({
                'id': r.get('id'),
                'title': r.get('title') or 'Untitled Notes',
                'category': (r.get('document_category') or 'Notes').capitalize(),
                'subject': subj or 'General',
                'file_type': (r.get('file_type') or 'PDF').upper(),
                'status': r.get('status') or 'approved',
                'views': r.get('view_count') or 0,
                'is_paid': bool(r.get('is_paid')),
                'price': float(r.get('price') or 0),
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
            logger.info(f"[CHANNEL SEED] Created channel @{target['handle']} for {user_id}")

def get_featured_channels(limit=10):
    """Fetches list of active creator channels with note counts for dashboard moving cards."""
    try:
        ensure_seed_channels()
    except Exception as e:
        logger.warning(f"[CHANNEL] ensure_seed_channels failed: {e}")

    def _query(client):
        res = client.table('channels').select('*').order('views_count', desc=True).limit(limit).execute()
        return res.data or []

    channels = []
    try:
        raw_channels = _execute_with_schema_fallback(_query) or []
        for ch in raw_channels:
            u_id = ch.get('user_id')
            notes = get_channel_notes(u_id) if u_id else []
            ch['notes_count'] = len(notes)
            channels.append(ch)
    except Exception as e:
        logger.error(f"[CHANNEL] get_featured_channels error: {e}")

    return channels

