"""
Interactive Guide Engine Service.
Handles eligibility evaluation, JSON registry loading, and user progress syncing with Supabase.
"""

import json
import logging
import os
from datetime import datetime, timezone
from methods.supabase_helper import init_supabase, init_supabase_admin

GUIDES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'guides.json')


def _get_table(client):
    """Retrieve guide_progress table handle, prioritizing abhihub schema."""
    try:
        return client.schema('abhihub').table('guide_progress')
    except Exception:
        return client.table('guide_progress')


def load_guides():
    """Load guide registry from data/guides.json."""
    if not os.path.exists(GUIDES_FILE):
        return []
    try:
        with open(GUIDES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[GUIDE] Failed loading guides: {e}")
        return []


def get_user_guide_progress(user_id):
    """Fetch all guide progress records for a user with session fallback."""
    from flask import session
    session_progress = session.get('guide_progress', {})

    client = init_supabase_admin() or init_supabase()
    if not client or not user_id:
        return session_progress
    try:
        tbl = _get_table(client)
        res = tbl.select('*').eq('user_id', str(user_id)).execute()
        if res.data:
            merged = dict(session_progress)
            merged.update({row['guide_id']: row for row in res.data})
            return merged
    except Exception as e:
        logging.warning(f"[GUIDE] Progress fetch error: {e}")
    return session_progress


def get_eligible_guides(user_id, screen=None):
    """Filter guides eligible for display to the user."""
    guides = load_guides()
    if not guides:
        return []

    progress_map = get_user_guide_progress(user_id) if user_id else {}
    eligible = []

    for guide in guides:
        g_id = guide.get('id')
        ver = guide.get('version', 1)
        progress = progress_map.get(g_id)

        # Skip if completed or dismissed on the current version
        if progress:
            if progress.get('status') in ('completed', 'dismissed') and progress.get('version', 1) >= ver:
                continue

        # Check screen trigger if specified
        trigger = guide.get('trigger', {})
        if screen and trigger.get('screen') and trigger.get('screen') != screen:
            continue

        guide_copy = dict(guide)
        guide_copy['current_step'] = progress.get('current_step', 0) if progress else 0
        guide_copy['status'] = progress.get('status', 'not_started') if progress else 'not_started'
        eligible.append(guide_copy)

    eligible.sort(key=lambda x: (-x.get('priority', 0), str(x.get('id', ''))))
    return eligible


def update_guide_progress(user_id, guide_id, status, current_step=0, version=1):
    """Upsert user progress for a given guide with session persistence."""
    from flask import session
    if 'guide_progress' not in session:
        session['guide_progress'] = {}
    session['guide_progress'][guide_id] = {
        'user_id': str(user_id or ''),
        'guide_id': str(guide_id),
        'version': version,
        'status': status,
        'current_step': current_step,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    session.modified = True

    client = init_supabase_admin() or init_supabase()
    if not client or not user_id or not guide_id:
        return True
    try:
        tbl = _get_table(client)
        payload = {
            'user_id': str(user_id),
            'guide_id': str(guide_id),
            'version': version,
            'status': status,
            'current_step': current_step,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        tbl.upsert(payload, on_conflict='user_id,guide_id').execute()
    except Exception as e:
        logging.warning(f"[GUIDE] Progress update DB notice (cached in session): {e}")
    return True

