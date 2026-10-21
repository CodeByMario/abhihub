import os
import re
import json
import logging
from flask import (
    Blueprint, request, session, redirect, url_for, render_template,
    abort, make_response, current_app, jsonify
)
from routes.auth import is_admin_user, auth_required, log_admin_action
from routes.seo import sitemap_page, slugify
from methods.supabase_helper import (
    init_supabase, get_all_colleges, get_all_branches, get_college_by_slug,
    get_colleges_by_brand, get_college_stats, get_waitlist_count,
    get_recent_college_files, get_department_by_slug, get_department_stats,
    get_recent_department_files, get_subjects_by_slug, get_subject_stats,
    get_recent_subject_files, get_document_by_id_rich, get_leaderboard_data,
    log_notification
)

library_bp = Blueprint('library', __name__)


def _get_user_standing(user_id, leaderboard_data):
    if not user_id:
        return None
    user_entry = None
    user_rank = None
    for entry in leaderboard_data:
        if entry.get('user_id') == user_id:
            user_entry = entry
            user_rank = entry.get('rank')
            break

    if not user_entry:
        try:
            from methods.supabase_helper import calculate_user_ranks
            all_ranks = calculate_user_ranks()
            for idx, r in enumerate(all_ranks):
                if r.get('uploader_id') == user_id:
                    user_rank = idx + 1
                    pts = r.get('points', 0)
                    user_entry = {
                        'rank': user_rank,
                        'user_id': user_id,
                        'name': r.get('author') or 'You',
                        'total_xp': int(pts) if isinstance(pts, (int, float)) else 0,
                        'upload_count': r.get('upload_count', 0),
                        'students_helped': r.get('students_helped', 0),
                    }
                    break
        except Exception:
            pass

    xp = float(user_entry.get('total_xp', 0)) if user_entry else 0.0
    uploads_count = user_entry.get('upload_count', 0) if user_entry else 0
    students_helped = user_entry.get('students_helped', 0) if user_entry else 0

    tiers = [
        {'title': 'Beginner', 'icon': '🌱', 'min': 0, 'next': 'Contributor', 'target': 50},
        {'title': 'Contributor', 'icon': '🥉', 'min': 50, 'next': 'Scholar', 'target': 250},
        {'title': 'Scholar', 'icon': '🥈', 'min': 250, 'next': 'Hero', 'target': 500},
        {'title': 'Hero', 'icon': '🥇', 'min': 500, 'next': 'Legend', 'target': 1000},
        {'title': 'Legend', 'icon': '👑', 'min': 1000, 'next': None, 'target': 1000}
    ]

    current_tier = tiers[0]
    for t in tiers:
        if xp >= t['min']:
            current_tier = t

    if current_tier['next']:
        next_target = current_tier['target']
        tier_span = next_target - current_tier['min']
        progress_pct = min(100, max(0, int(((xp - current_tier['min']) / tier_span) * 100))) if tier_span > 0 else 100
        xp_to_next = max(0, int(next_target - xp))
    else:
        progress_pct = 100
        xp_to_next = 0

    nudge = {}
    if user_rank and user_rank > 1:
        ahead_entry = next((item for item in leaderboard_data if item.get('rank') == user_rank - 1), None)
        if ahead_entry:
            diff = max(1, int(float(ahead_entry.get('total_xp', 0)) - xp + 1))
            notes_needed = max(1, (diff + 29) // 30)
            peer_name = ahead_entry.get('name', 'peer').split()[0]
            nudge = {
                'ahead_name': peer_name,
                'ahead_rank': user_rank - 1,
                'xp_gap': diff,
                'notes_needed': notes_needed,
                'message': f"You are only {diff} XP behind #{user_rank - 1} {peer_name}. Upload {notes_needed} note{'s' if notes_needed > 1 else ''} (+{notes_needed * 30} XP) to overtake them!"
            }
        else:
            notes_needed = max(1, (xp_to_next + 29) // 30) if xp_to_next else 1
            nudge = {
                'xp_gap': xp_to_next,
                'notes_needed': notes_needed,
                'message': f"Upload {notes_needed} note{'s' if notes_needed > 1 else ''} to unlock {current_tier['next']} badge!" if current_tier['next'] else "You hold the pinnacle rank!"
            }
    elif user_rank == 1:
        nudge = {
            'xp_gap': 0,
            'notes_needed': 0,
            'message': "👑 You are leading at #1! Keep sharing to secure your legendary spot."
        }
    else:
        nudge = {
            'xp_gap': 30,
            'notes_needed': 1,
            'message': "You are unranked. Upload 1 study note or PYQ to earn instant XP and claim your place on the leaderboard!"
        }

    return {
        'is_ranked': bool(user_rank),
        'rank': user_rank,
        'total_xp': int(xp) if xp.is_integer() else xp,
        'upload_count': uploads_count,
        'students_helped': students_helped,
        'tier_title': current_tier['title'],
        'tier_icon': current_tier['icon'],
        'next_tier': current_tier['next'],
        'next_tier_target': current_tier['target'],
        'xp_to_next_tier': xp_to_next,
        'progress_pct': progress_pct,
        'nudge': nudge
    }


@library_bp.route('/leaderboard', methods=['GET'])
def leaderboard():
    """Global Gamification Leaderboard — Apple UI/UX redesign with personal standing."""
    import app
    cache = app.cache

    college_id = request.args.get('college_id')
    cache_key = f"leaderboard:{college_id or 'all'}"

    def fetch_lb():
        result = get_leaderboard_data(college_id=college_id, limit=50)
        return result.get('data', []) if result.get('success') else []

    leaderboard_data = cache.get_cached(cache_key, level=cache.L2, ttl=cache.LONG, fetcher=fetch_lb)
    user_info = session.get('user')
    user_uid = (user_info.get('uid') or user_info.get('id')) if user_info else None
    user_standing = _get_user_standing(user_uid, leaderboard_data) if user_uid else None

    # Guarantee uid field exists for template checks
    if user_info and user_uid and 'uid' not in user_info:
        user_info['uid'] = user_uid

    response = make_response(render_template(
        'leaderboard.html',
        leaderboard=leaderboard_data,
        current_user=user_info,
        user_standing=user_standing
    ))
    if user_info:
        response.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
    else:
        cache.set_cache_headers(response, max_age=cache.LONG, stale_while_revalidate=True)
    return response


@library_bp.route('/pyq')
@sitemap_page(priority="0.95", changefreq="daily")
def pyq_landing():
    """SEO landing page targeting 'PYQ' and '[college] PYQ' searches"""
    colleges_res = get_all_colleges()
    colleges = colleges_res.get('data', [])
    try:
        client = init_supabase()
        if client:
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
    colleges.sort(key=lambda c: c.get('doc_count', 0), reverse=True)
    return render_template('pyq_landing.html', colleges=colleges)


@library_bp.route('/pyq_landing')
def pyq_landing_legacy_redirect():
    """301 permanent redirect from old /pyq_landing to /pyq."""
    return redirect(url_for('library.pyq_landing'), code=301)


@library_bp.route('/search')
def search_page():
    """Public search page. Accepts ?q=... to prefill + auto-run search on load."""
    q = request.args.get('q', '').strip()
    return render_template('site/search.html', initial_query=q)


@library_bp.route('/college/<college_slug>')
def college_landing(college_slug):
    """Dynamic SEO-optimized college landing page."""
    route_prefix = '/college'

    # 1. Check if slug matches a brand group
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

    # 2. Resolve as individual college slug
    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)

    college = college_res.get('data')
    college_id = college.get('id')

    # 3. If accessed via alias, 301-redirect
    canonical_slug = slugify(college.get('abbreviation') or college.get('name'))
    if college_slug != canonical_slug:
        return redirect(f"{route_prefix}/{canonical_slug}", code=301)

    # 4. Check doc count
    stats = get_college_stats(college_id).get('data', {})
    total_docs = stats.get('total_documents', 0)
    if total_docs < 1:
        waitlist_count = get_waitlist_count(college_id)
        return render_template('college_coming_soon.html',
                               college=college,
                               waitlist_count=waitlist_count,
                               noindex=True)

    recent_files = get_recent_college_files(college_id, limit=6).get('data', [])
    departments = get_all_branches().get('data', [])

    return render_template('college.html',
                           college=college,
                           stats=stats,
                           recent_files=recent_files,
                           departments=departments)


@library_bp.route('/pyq/<college_slug>')
def pyq_college_legacy_redirect(college_slug):
    """Permanent 301 redirect from legacy /pyq/<college_slug> to canonical /college/<college_slug>."""
    return redirect(url_for('library.college_landing', college_slug=college_slug), code=301)


@library_bp.route('/college/<college_slug>/files')
def college_files(college_slug):
    """College files listing with filters, search, and pagination."""
    client = init_supabase()
    if not client:
        abort(500, description='Database client unavailable')

    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)
    college = college_res.get('data')
    college_id = college.get('id')

    raw_type = request.args.get('type', '').strip().lower()
    doc_type_map = {
        'pyq': 'papers',
        'papers': 'papers',
        'paper': 'papers',
        'notes': 'notes',
        'practical': 'practical',
        'practicals': 'practical',
        'other': 'other',
    }
    doc_type = doc_type_map.get(raw_type, raw_type)
    department_slug = request.args.get('branch', '').strip().lower()
    search_query = request.args.get('search', '').strip()
    page = max(1, int(request.args.get('page', '1') or '1'))
    page_size = 16
    offset = (page - 1) * page_size

    dept_res = {'success': False, 'data': {}}
    if department_slug:
        dept_res = get_department_by_slug(department_slug)

    q = client.table('documents') \
        .select('*, subjects(name, subject_code), profiles!documents_uploader_id_fkey(full_name), colleges(name, abbreviation), departments(name, abbreviation)') \
        .eq('college_id', college_id) \
        .in_('status', ['approved', 'pending']) \
        .order('view_count', desc=True)

    if doc_type:
        q = q.eq('document_category', doc_type)
    if dept_res.get('success') and dept_res.get('data', {}).get('college_id') == college_id:
        q = q.eq('department_id', dept_res['data']['id'])
    if search_query:
        q = q.or_(f"title.ilike.%{search_query}%,description.ilike.%{search_query}%")

    try:
        count_resp = client.table('documents') \
            .select('id', count='exact') \
            .eq('college_id', college_id) \
            .in_('status', ['approved', 'pending'])
        if doc_type:
            count_resp = count_resp.eq('document_category', doc_type)
        if dept_res.get('success') and dept_res.get('data', {}).get('college_id') == college_id:
            count_resp = count_resp.eq('department_id', dept_res['data']['id'])
        total_count = count_resp.execute().count or 0

        items_resp = q.limit(page_size).offset(offset).execute()
        files = items_resp.data or []
    except Exception as e:
        logging.error(f"[college_files] query failed: {e}")
        files = []
        total_count = 0

    departments = get_all_branches().get('data', [])

    return render_template('college_files.html',
                           college=college,
                           files=files,
                           departments=departments,
                           filters={
                               'type': doc_type,
                               'branch': department_slug,
                               'search': search_query,
                               'page': page,
                               'page_size': page_size,
                               'total': total_count
                           })


@library_bp.route('/pyq/<college_slug>/files')
def pyq_college_files_legacy_redirect(college_slug):
    """Permanent 301 redirect from legacy /pyq/<college_slug>/files to canonical /college/<college_slug>/files."""
    return redirect(url_for('library.college_files', college_slug=college_slug, **request.args), code=301)


@library_bp.route('/college/<college_slug>/<department_slug>')
def department_landing(college_slug, department_slug):
    """Dynamic SEO-optimized department landing page"""
    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)
    college = college_res.get('data')
    college_id = college.get('id')

    dept_res = get_department_by_slug(department_slug)
    if not dept_res.get('success'):
        abort(404)
    department = dept_res.get('data')
    dept_id = department.get('id')

    stats = get_department_stats(college_id, dept_id).get('data', {})
    recent_files = get_recent_department_files(college_id, dept_id, limit=6).get('data', [])

    return render_template('department.html',
                           college=college,
                           department=department,
                           stats=stats,
                           recent_files=recent_files)


@library_bp.route('/pyq/<college_slug>/<department_slug>')
def pyq_department_legacy_redirect(college_slug, department_slug):
    """Permanent 301 redirect from legacy /pyq/<college_slug>/<department_slug> to canonical /college/<college_slug>/<department_slug>."""
    return redirect(url_for('library.department_landing', college_slug=college_slug, department_slug=department_slug), code=301)


@library_bp.route('/subject/<subject_slug>')
def subject_landing(subject_slug):
    """Dynamic SEO-optimized subject landing page (aggregated across colleges)"""
    subject_res = get_subjects_by_slug(subject_slug)
    if not subject_res.get('success'):
        abort(404)

    subject_data = subject_res.get('data')
    subject_ids = subject_data.get('ids')
    subject_name = subject_data.get('name')

    stats = get_subject_stats(subject_ids).get('data', {})
    recent_files = get_recent_subject_files(subject_ids, limit=12).get('data', [])

    return render_template('subject.html',
                           subject_name=subject_name,
                           stats=stats,
                           recent_files=recent_files)


@library_bp.route('/resource/<path:slug>-view')
def resource_landing_redirect(slug):
    """Redirect resource slug with -view suffix to clean URL"""
    return redirect(url_for('library.resource_landing', slug=slug), code=301)


@library_bp.route('/resource/<path:slug>')
@library_bp.route('/resources/<path:slug>')
def resource_landing(slug):
    """Dynamic SEO-optimized resource landing page"""
    import app
    log_document_view = getattr(app, 'log_document_view', None)
    from data.pricing import has_document_access, extract_document_pricing
    from routes.ai import AI_MODELS, get_best_ai_model

    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    match = re.search(uuid_pattern, slug.lower())
    if not match:
        abort(404)

    doc_id = match.group(0)
    cache = getattr(app, 'cache', None)
    doc_res = None
    if cache:
        doc_res = cache.get_cached(f"doc_rich:{doc_id}", level=cache.L1, ttl=300)
    if not doc_res:
        doc_res = get_document_by_id_rich(doc_id)
        if doc_res.get('success') and cache:
            cache.set_cached(f"doc_rich:{doc_id}", doc_res, ttl=300)

    if not doc_res or not doc_res.get('success'):
        abort(404)

    document = dict(doc_res.get('data') or {})

    file_url = document.get('file_url', '')
    if file_url:
        ext = ''
        if document.get('file_type') == 'pdf':
            ext = '.pdf'
        elif '.' in file_url.split('/')[-1]:
            ext = '.' + file_url.split('/')[-1].split('.')[-1].split('?')[0]
        document['file_url'] = f'/api/view-doc/{doc_id}/file{ext}'

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

    if slug.lower() != canonical_slug:
        target_url = url_for('library.resource_landing', slug=canonical_slug)
        if request.query_string:
            target_url = f"{target_url}?{request.query_string.decode('utf-8')}"
        return redirect(target_url, code=301)

    document['is_liked'] = False
    document['is_bookmarked'] = False

    user_info = session.get('user', {})
    current_user_id = user_info.get('uid') or user_info.get('id')
    is_admin = is_admin_user(user_info)
    is_uploader = bool(current_user_id and str(document.get('uploader_id') or '') == str(current_user_id))
    can_manage = is_admin or is_uploader

    ai_chat_allowed = False
    if current_user_id:
        try:
            from methods.scoring_engine import get_feature_gate
            ai_chat_allowed = get_feature_gate(current_user_id).get('level') in ['contributor', 'power_contributor', 'community_leader']
        except Exception:
            ai_chat_allowed = False

    client = init_supabase()
    if current_user_id and client:
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

    viewers = []
    if can_manage and client:
        try:
            v_res = client.table('document_views').select(
                'id, user_id, accessed_at, device_type'
            ).eq('document_id', doc_id).order('accessed_at', desc=True).limit(50).execute()
            raw_views = v_res.data or []
            u_ids = list({v['user_id'] for v in raw_views if v.get('user_id')})
            profiles_map = {}
            if u_ids:
                try:
                    p_res = client.table('profiles').select('id, full_name, email, role, degree').in_('id', u_ids).execute()
                    if p_res.data:
                        profiles_map = {p['id']: p for p in p_res.data}
                except Exception as p_err:
                    logging.warning(f"Could not batch fetch profiles for viewers: {p_err}")

            for v in raw_views:
                uid = v.get('user_id')
                prof = profiles_map.get(uid) or {}
                name = prof.get('full_name') or (f"User ({uid[:8]}...)" if uid else "Anonymous Student")
                viewers.append({
                    'user_id': uid,
                    'name': name,
                    'email': (prof.get('email') or '—') if is_admin else None,
                    'role': prof.get('role', 'student'),
                    'device': v.get('device_type') or 'desktop',
                    'accessed_at': v.get('accessed_at')
                })
        except Exception as v_err:
            logging.warning(f"[resource_landing] Could not fetch viewers: {v_err}")

    log_document_view(
        file_name=title,
        file_url=document.get('file_url'),
        record_id=doc_id,
        file_type=document.get('file_type'),
    )

    suggested_docs = []
    store_room_docs = []
    subj_id = document.get('subject_id')
    sug_cache_key = f"sug_docs:{subj_id or 'none'}:{doc_id}"
    if cache:
        cached_sug = cache.get_cached(sug_cache_key, level=cache.L1, ttl=600)
        if cached_sug is not None:
            suggested_docs = cached_sug

    if not suggested_docs:
        try:
            if subj_id and client:
                sug_res = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').eq('subject_id', subj_id).neq('id', doc_id).limit(4).execute()
                suggested_docs = sug_res.data or []
            if cache and suggested_docs:
                cache.set_cached(sug_cache_key, suggested_docs, ttl=600)
        except Exception as e:
            logging.error(f"[Supabase] Error fetching suggestions: {e}")

    from methods.seo_helper import is_resource_indexable
    is_thin = not is_resource_indexable(document)
    render_noindex = is_thin

    is_prod = os.environ.get('FLASK_ENV') == 'production' or current_app.config.get('ENV') == 'production' or current_app.config.get('PRODUCTION', False)
    mock_study_kit = False if is_prod else bool(current_app.config.get('MOCK_STUDY_KIT', False) or os.environ.get('MOCK_STUDY_KIT') == '1')

    desc_raw = document.get('description') or ''
    pricing = extract_document_pricing(document)
    if isinstance(desc_raw, str) and desc_raw.strip().startswith('{'):
        try:
            document['display_description'] = json.loads(desc_raw.strip()).get('text_description', '')
        except Exception:
            document['display_description'] = desc_raw
    elif isinstance(desc_raw, dict):
        document['display_description'] = desc_raw.get('text_description', '')
    else:
        document['display_description'] = desc_raw

    has_access = has_document_access(current_user_id, doc_id, document)

    all_colleges = []
    all_branches = []
    if can_manage or is_admin:
        try:
            c_res = get_all_colleges()
            b_res = get_all_branches()
            all_colleges = c_res.get('data', []) if c_res.get('success') else []
            all_branches = b_res.get('data', []) if b_res.get('success') else []
        except Exception as err:
            logging.warning(f"Error fetching dropdown lists for resource manager: {err}")

    recorded_views = len(viewers) if viewers else 0
    view_earnings = round(recorded_views * 0.20, 2)

    return render_template(
        'resource.html',
        document=document,
        pricing=pricing,
        has_access=has_access,
        can_manage=can_manage,
        is_admin=is_admin,
        is_uploader=is_uploader,
        viewers=viewers,
        recorded_views=recorded_views,
        view_earnings=view_earnings,
        all_colleges=all_colleges,
        all_branches=all_branches,
        ai_models=AI_MODELS,
        best_model=get_best_ai_model(),
        suggested_docs=suggested_docs,
        store_room_docs=store_room_docs,
        ai_chat_allowed=ai_chat_allowed,
        noindex=render_noindex,
        mock_study_kit=mock_study_kit
    )


@library_bp.route('/api/documents/<doc_id>/edit', methods=['POST'])
@auth_required
def api_edit_document(doc_id):
    """Edit document details (title, description, price, promo code) for uploader or admin."""
    try:
        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database client unavailable'}), 500

        doc_res = client.table('documents').select('*').eq('id', doc_id).limit(1).execute()
        if not doc_res.data:
            return jsonify({'success': False, 'message': 'Document not found'}), 404

        doc = doc_res.data[0]
        user_info = session.get('user', {})
        uid = user_info.get('uid') or user_info.get('id')
        is_admin = is_admin_user(user_info)
        is_uploader = bool(uid and str(doc.get('uploader_id') or '') == str(uid))

        if not (is_admin or is_uploader):
            return jsonify({'success': False, 'message': 'Unauthorized to modify this resource'}), 403

        data = request.get_json(silent=True) or {}
        admin_action = str(data.get('admin_action') or '').strip().lower()
        reason_preset = str(data.get('reason_preset') or '').strip()
        custom_note = str(data.get('custom_note') or '').strip()
        notify_owner = bool(data.get('notify_owner', True))
        status_action = str(data.get('status') or '').strip().lower()

        # Handle Admin Delete (Complete vs Partial)
        if is_admin and admin_action == 'delete':
            delete_mode = str(data.get('delete_mode') or 'complete').strip().lower()
            old_title = doc.get('title') or 'Document'
            file_url = doc.get('file_url') or ''
            provider_public_id = doc.get('provider_public_id')
            storage_provider = doc.get('storage_provider')

            # Complete Delete: purge physical asset from Cloud Storage
            if delete_mode == 'complete':
                # 1. Cloudinary
                cld_id = provider_public_id
                if not cld_id and 'cloudinary.com' in file_url:
                    m = re.search(r'/(?:image|raw|video)/upload/(?:v\d+/)?([^?#]+)', file_url)
                    if m:
                        cld_id = m.group(1)
                if cld_id or storage_provider == 'cloudinary' or 'cloudinary.com' in file_url:
                    try:
                        from methods.cloudinary_upload import delete_file_from_cloudinary
                        if cld_id:
                            res_raw = delete_file_from_cloudinary(cld_id, resource_type='raw')
                            if not res_raw.get('success'):
                                delete_file_from_cloudinary(cld_id, resource_type='image')
                    except Exception as cld_err:
                        logging.warning(f"[api_edit_document] Cloudinary deletion error: {cld_err}")

                # 2. Supabase Storage
                try:
                    if 'supabase.co/storage/v1/object/public/' in file_url:
                        path_part = file_url.split('/storage/v1/object/public/')[-1]
                        bucket = path_part.split('/')[0]
                        file_key = '/'.join(path_part.split('/')[1:])
                        client.storage.from_(bucket).remove([file_key])
                    if cld_id:
                        for ext in ['', '.pdf', '.txt', '.bin', '.jpg', '.png']:
                            try:
                                client.storage.from_('public').remove([f"cloudinary_fallback/{cld_id}{ext}"])
                            except Exception:
                                pass
                except Exception as sb_err:
                    logging.debug(f"[api_edit_document] Supabase storage removal note: {sb_err}")

                # 3. Firebase Storage
                if 'firebasestorage.googleapis.com' in file_url or storage_provider == 'firebase':
                    try:
                        from methods.storage import delete_file
                        blob_name = provider_public_id
                        if not blob_name and '/o/' in file_url:
                            import urllib.parse
                            blob_name = urllib.parse.unquote(file_url.split('/o/')[1].split('?')[0])
                        if blob_name:
                            delete_file(blob_name)
                    except Exception as fb_err:
                        logging.warning(f"[api_edit_document] Firebase storage deletion error: {fb_err}")

            # Database Records Clean-up (for both Complete and Partial delete)
            for tbl, col in [
                ('search_documents', 'file_id'),
                ('document_views', 'document_id'),
                ('document_likes', 'document_id'),
                ('document_bookmarks', 'document_id'),
                ('document_votes', 'document_id'),
                ('document_ratings', 'document_id'),
            ]:
                try:
                    client.table(tbl).delete().eq(col, doc_id).execute()
                except Exception:
                    pass

            try:
                client.table('material_requests').update({'response_document_id': None}).eq('response_document_id', doc_id).execute()
            except Exception:
                pass

            try:
                client.table('viewer_failure_reports').delete().eq('doc_id', doc_id).execute()
            except Exception:
                pass

            client.table('documents').delete().eq('id', doc_id).execute()

            try:
                import app
                c = getattr(app, 'cache', None)
                if c: c.invalidate(f"doc_rich:{doc_id}")
            except Exception: pass

            if notify_owner and doc.get('uploader_id'):
                try:
                    mode_label = "permanently purged (cloud storage + database)" if delete_mode == 'complete' else "unregistered from catalog (database only, cloud file retained)"
                    notif_body = f"Your uploaded file '{old_title}' was {mode_label} by an administrator."
                    if reason_preset:
                        notif_body += f"\nReason: {reason_preset}"
                    if custom_note:
                        notif_body += f"\nDetails: {custom_note}"
                    log_notification(doc.get('uploader_id'), 'document_deleted', f"File Removed: {old_title[:30]}", notif_body)
                except Exception as ne:
                    logging.warning(f"Failed to notify owner of delete: {ne}")

            log_admin_action('delete_document', target=doc_id, details={'title': old_title, 'mode': delete_mode, 'reason': reason_preset, 'note': custom_note})
            return jsonify({
                'success': True,
                'deleted': True,
                'mode': delete_mode,
                'redirect': '/dashboard',
                'message': f"Document {delete_mode} delete completed successfully."
            }), 200

        DOC_VALID_COLUMNS = {
            'title', 'description', 'college_id', 'department_id', 'subject_id',
            'document_category', 'exam_type', 'program', 'topics_covered',
            'difficulty_level', 'uploader_note', 'image_alt', 'is_paid',
            'price', 'coupon_code', 'coupon_discount', 'status'
        }
        valid_doc_cols = set(doc.keys()).intersection(DOC_VALID_COLUMNS)

        # Build updates mapping
        update_payload = {}
        updates_dict = {}

        if 'metadata_updates' in data and isinstance(data['metadata_updates'], dict):
            updates_dict = data['metadata_updates']
        elif 'field' in data:
            updates_dict = {data['field']: data.get('value')}

        target_subject_id = updates_dict.get('subject_id') or doc.get('subject_id')
        target_college_id = updates_dict.get('college_id') or doc.get('college_id')
        target_dept_id = updates_dict.get('department_id') or updates_dict.get('branch_id') or doc.get('department_id')

        # Process all identifying and hidden metadata fields
        for fld, val in updates_dict.items():
            fld_lower = fld.strip().lower()

            if fld_lower == 'title':
                update_payload['title'] = str(val or '').strip() or doc.get('title')
            elif fld_lower in ['document_category', 'category']:
                update_payload['document_category'] = str(val or '').strip()
            elif fld_lower == 'status' and is_admin:
                val_status = str(val or '').strip().lower()
                if val_status in ['approved', 'hidden', 'pending']:
                    update_payload['status'] = val_status
            elif fld_lower == 'price':
                try:
                    update_payload['price'] = max(0.0, float(val or 0))
                except (ValueError, TypeError):
                    update_payload['price'] = 0.0
            elif fld_lower == 'is_paid':
                update_payload['is_paid'] = bool(val)
            elif fld_lower == 'coupon_code':
                update_payload['coupon_code'] = str(val or '').strip().upper() or None
            elif fld_lower == 'coupon_discount':
                try:
                    update_payload['coupon_discount'] = max(0, min(100, int(val or 0)))
                except (ValueError, TypeError):
                    update_payload['coupon_discount'] = 0
            elif fld_lower == 'topics_covered' and is_admin:
                if isinstance(val, str):
                    t_list = [t.strip() for t in val.split(',') if t.strip()]
                    update_payload['topics_covered'] = t_list if t_list else None
                elif isinstance(val, list):
                    update_payload['topics_covered'] = [str(t).strip() for t in val if str(t).strip()] if val else None
                else:
                    update_payload['topics_covered'] = None
            elif fld_lower in ['exam_type', 'program', 'difficulty_level'] and is_admin:
                update_payload[fld_lower] = str(val or '').strip() or None
            elif fld_lower == 'semester' and is_admin:
                try:
                    s_int = int(val or 1)
                    if target_subject_id:
                        try: client.table('subjects').update({'semester': s_int}).eq('id', target_subject_id).execute()
                        except Exception as se: logging.warning(f"Error updating subjects.semester: {se}")
                except Exception: pass
            elif fld_lower == 'college_id' and is_admin:
                c_id_val = str(val or '').strip() or None
                update_payload['college_id'] = c_id_val
                target_college_id = c_id_val
            elif fld_lower in ['department_id', 'branch_id'] and is_admin:
                d_id_val = str(val or '').strip() or None
                update_payload['department_id'] = d_id_val
                target_dept_id = d_id_val
            elif fld_lower == 'subject_id' and is_admin:
                s_id_val = str(val or '').strip() or None
                update_payload['subject_id'] = s_id_val
                target_subject_id = s_id_val
            elif fld_lower == 'subject_code' and is_admin:
                s_code = str(val or '').strip().upper()
                if target_subject_id:
                    try: client.table('subjects').update({'subject_code': s_code}).eq('id', target_subject_id).execute()
                    except Exception as sce: logging.warning(f"Error updating subjects.subject_code: {sce}")
            elif fld_lower in ['subject_name', 'subject'] and is_admin:
                s_name = str(val or '').strip()
                if target_subject_id:
                    try: client.table('subjects').update({'name': s_name}).eq('id', target_subject_id).execute()
                    except Exception as sne: logging.warning(f"Error updating subjects.name: {sne}")
            elif fld_lower in ['college_name', 'college'] and is_admin:
                c_name = str(val or '').strip()
                if target_college_id:
                    try: client.table('colleges').update({'name': c_name}).eq('id', target_college_id).execute()
                    except Exception: pass
            elif fld_lower == 'college_abbr' and is_admin:
                c_abbr = str(val or '').strip().upper()
                if target_college_id:
                    try: client.table('colleges').update({'abbreviation': c_abbr}).eq('id', target_college_id).execute()
                    except Exception: pass
            elif fld_lower in ['department_name', 'department', 'branch'] and is_admin:
                d_name = str(val or '').strip()
                if target_dept_id:
                    try: client.table('departments').update({'name': d_name}).eq('id', target_dept_id).execute()
                    except Exception: pass
            elif fld_lower == 'department_abbr' and is_admin:
                d_abbr = str(val or '').strip().upper()
                if target_dept_id:
                    try: client.table('departments').update({'abbreviation': d_abbr}).eq('id', target_dept_id).execute()
                    except Exception: pass
            elif fld_lower == 'description':
                desc_raw = doc.get('description') or ''
                desc_obj = {}
                if isinstance(desc_raw, str) and desc_raw.strip().startswith('{'):
                    try: desc_obj = json.loads(desc_raw.strip())
                    except Exception: desc_obj = {}
                elif isinstance(desc_raw, dict):
                    desc_obj = dict(desc_raw)
                desc_obj['text_description'] = str(val or '').strip()
                update_payload['description'] = json.dumps(desc_obj)

        # Fallback if full form legacy submitted
        if not update_payload and not updates_dict:
            new_title = (data.get('title') or '').strip()
            new_text_desc = (data.get('description') or '').strip()
            is_paid = bool(data.get('is_paid', False))

            try:
                price = max(0.0, float(data.get('price', 0) or 0))
            except (ValueError, TypeError):
                price = 0.0

            coupon_code = str(data.get('coupon_code') or '').strip().upper() or None
            try:
                coupon_discount = max(0, min(100, int(data.get('coupon_discount', 0) or 0)))
            except (ValueError, TypeError):
                coupon_discount = 0

            desc_raw = doc.get('description') or ''
            desc_obj = {}
            if isinstance(desc_raw, str) and desc_raw.strip().startswith('{'):
                try: desc_obj = json.loads(desc_raw.strip())
                except Exception: desc_obj = {}
            elif isinstance(desc_raw, dict):
                desc_obj = dict(desc_raw)

            desc_obj['text_description'] = new_text_desc
            desc_obj['pricing'] = {
                'is_paid': is_paid,
                'price': price if is_paid else 0.0,
                'coupon_code': coupon_code if is_paid else '',
                'coupon_discount': coupon_discount if is_paid else 0,
                'seller_id': doc.get('uploader_id')
            }

            update_payload = {
                'title': new_title or doc.get('title'),
                'description': json.dumps(desc_obj),
                'is_paid': is_paid,
                'price': price if is_paid else 0.0,
                'coupon_code': coupon_code if is_paid else None,
                'coupon_discount': coupon_discount if is_paid else 0
            }
            if is_admin and status_action in ['approved', 'hidden', 'pending']:
                update_payload['status'] = status_action

        # Apply updates to documents table (filtering only columns that exist in documents)
        doc_update_clean = {k: v for k, v in update_payload.items() if k in valid_doc_cols}
        if doc_update_clean:
            try:
                client.table('documents').update(doc_update_clean).eq('id', doc_id).execute()
            except Exception as upd_err:
                logging.error(f"[api_edit_document] Table update error: {upd_err}")
                return jsonify({'success': False, 'message': f'Database update failed: {str(upd_err)}'}), 500

        # Invalidate Cache immediately
        try:
            import app
            c = getattr(app, 'cache', None)
            if c:
                c.invalidate(f"doc_rich:{doc_id}")
        except Exception as ce:
            logging.warning(f"Cache invalidate error: {ce}")

        # Notify owner if edited by admin
        if is_admin and notify_owner and doc.get('uploader_id'):
            try:
                note_preset = reason_preset or 'Name error fix'
                fld_keys = list(updates_dict.keys())
                field_label = (', '.join(fld_keys) if fld_keys else 'metadata details').replace('_', ' ')
                notif_msg = f"An administrator updated your file '{update_payload.get('title') or doc.get('title')}' in real-time."
                notif_msg += f"\nFields Changed: {field_label}"
                notif_msg += f"\nReason: {note_preset}"
                if custom_note:
                    notif_msg += f"\nDetails: {custom_note}"

                log_notification(
                    doc.get('uploader_id'),
                    'document_admin_edit',
                    f"Admin Edit: {(update_payload.get('title') or doc.get('title') or 'Document')[:30]}",
                    notif_msg,
                    url=f"/resource/{doc_id}"
                )
            except Exception as ne:
                logging.warning(f"Failed to notify owner of edit: {ne}")

        if is_admin:
            log_admin_action('edit_document', target=doc_id, details={'payload': update_payload, 'updates': updates_dict, 'reason': reason_preset, 'note': custom_note})

        return jsonify({
            'success': True,
            'message': 'Resource and metadata updated successfully in real time!',
            'data': update_payload
        }), 200

    except Exception as e:
        logging.error(f"[api_edit_document] {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@library_bp.route('/prepare/<subject>')
def exam_prep(subject="HE"):
    with open('static/premium/data.json', 'r') as f:
        data = json.load(f)
    prepair = [item for item in data if item.get('subject', '').lower().startswith(subject.lower())]
    return render_template('exam_page.html', data=prepair)


@library_bp.route('/uhv')
def uhv_notes():
    return render_template('video_page.html')


@library_bp.route('/rank')
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


@library_bp.route('/show_rank')
def show_rank():
    """Legacy route: redirect to new leaderboard"""
    return redirect(url_for('library.leaderboard'))

