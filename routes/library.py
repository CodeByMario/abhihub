import os
import re
import json
import logging
import time
from urllib.parse import urlsplit
from flask import (
    Blueprint, request, session, redirect, url_for, render_template,
    abort, make_response, current_app, jsonify, has_request_context
)
from routes.auth import is_admin_user, auth_required, log_admin_action
from routes.seo import sitemap_page, slugify
from cache_manager import get_cache, TTL
from methods.supabase_helper import (
    init_supabase, init_supabase_admin, get_all_colleges, get_all_branches, get_college_by_slug,
    get_colleges_by_brand, get_college_stats, get_waitlist_count,
    get_recent_college_files, get_department_by_slug, get_department_stats,
    get_recent_department_files, get_subjects_by_slug, get_subject_stats,
    get_recent_subject_files, get_document_by_id_rich, get_leaderboard_data,
    get_departments_by_college,
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
    """Global Gamification Leaderboard with Apple HIG UI/UX, rate limiting, multi-level caching & pagination."""
    import app
    cache = app.cache

    # 1. Rate Limiting Protection (per user or per IP)
    user_info = session.get('user')
    user_uid = (user_info.get('uid') or user_info.get('id')) if isinstance(user_info, dict) else None
    principal = str(user_uid or (user_info.get('email') if isinstance(user_info, dict) else None) or request.remote_addr or 'anon').strip().lower()
    kind = 'user' if user_uid else 'ip'
    max_reqs = 120 if user_uid else 60

    try:
        from methods.api_rate_limiter import check_api_rate_limit
        allowed, retry_after = check_api_rate_limit(
            f"leaderboard_{kind}",
            principal,
            max_requests=max_reqs,
            window_seconds=60
        )
        if not allowed:
            if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
                return jsonify({
                    'success': False,
                    'message': 'Rate limit exceeded. Please wait a moment and try again.',
                    'retry_after': retry_after
                }), 429, {'Retry-After': str(retry_after)}
            resp = make_response(render_template(
                'p_error.html',
                error_message="Too Many Requests",
                error_description=f"Please wait {retry_after} seconds before refreshing the leaderboard."
            ))
            resp.status_code = 429
            resp.headers['Retry-After'] = str(retry_after)
            return resp
    except Exception:
        pass  # Fail open if rate limiter encounters transient error

    # 2. Multi-Level Caching (L1/L2)
    college_id = request.args.get('college_id')
    cache_key = f"leaderboard:v4:{college_id or 'all'}"

    def fetch_lb():
        result = get_leaderboard_data(college_id=college_id, limit=100)
        return result.get('data', []) if result.get('success') else []

    leaderboard_data = cache.get_cached(cache_key, level=cache.L2, ttl=cache.LONG, fetcher=fetch_lb) or []
    user_standing = _get_user_standing(user_uid, leaderboard_data) if user_uid else None

    # Guarantee uid field exists for template checks
    if user_info and user_uid and 'uid' not in user_info:
        user_info['uid'] = user_uid

    # 3. Server-side & Query-driven Pagination
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(50, max(5, int(request.args.get('per_page', 20))))
    except (ValueError, TypeError):
        per_page = 20

    total_items = len(leaderboard_data)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = min(page, total_pages)

    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_items)
    paged_items = leaderboard_data[start_idx:end_idx]

    # JSON response support for dynamic pagination or mobile clients
    if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
        return jsonify({
            'success': True,
            'page': page,
            'per_page': per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'data': paged_items
        }), 200

    response = make_response(render_template(
        'leaderboard.html',
        leaderboard=leaderboard_data,
        paged_leaderboard=paged_items,
        current_page=page,
        total_pages=total_pages,
        total_items=total_items,
        per_page=per_page,
        start_idx=start_idx + 1 if total_items > 0 else 0,
        end_idx=end_idx,
        college_id=college_id,
        current_user=user_info,
        user_standing=user_standing
    ))

    if user_info:
        response.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
    else:
        cache.set_cache_headers(response, max_age=cache.LONG, stale_while_revalidate=True)
    return response


@library_bp.route('/pyq')
@library_bp.route('/college')
@sitemap_page(priority="0.95", changefreq="daily")
def pyq_landing():
    """SEO landing page targeting 'PYQ' and '[college] PYQ' searches with L1 cache and minimal field projection."""
    import app
    cache = getattr(app, 'cache', None)

    def fetch_colleges_summary():
        from methods.supabase_helper import get_colleges_with_document_counts
        res = get_colleges_with_document_counts()
        items = res.get('data', []) if res.get('success') else []
        clean = []
        for c in items:
            clean.append({
                'id': c.get('id'),
                'name': c.get('name'),
                'abbreviation': c.get('abbreviation') or '',
                'popular_name': c.get('popular_name') or '',
                'city': c.get('city') or '',
                'doc_count': c.get('doc_count', 0),
                'waitlist_count': c.get('waitlist_count', 0),
            })
        clean.sort(key=lambda x: (x.get('doc_count', 0), x.get('waitlist_count', 0)), reverse=True)
        return clean

    if cache:
        colleges = cache.get_cached('colleges:summary:v3', level=cache.L1, ttl=cache.LONG, fetcher=fetch_colleges_summary)
    else:
        colleges = fetch_colleges_summary()

    response = make_response(render_template('pyq_landing.html', colleges=colleges))
    if cache:
        cache.set_cache_headers(response, max_age=cache.LONG, stale_while_revalidate=True)
    return response


@library_bp.route('/pyq_landing')
def pyq_landing_legacy_redirect():
    """301 permanent redirect from old /pyq_landing to /pyq."""
    return redirect(url_for('library.pyq_landing'), code=301)


@library_bp.route('/search')
def search_page():
    """Search route removed; redirect to home where search panel opens."""
    q = request.args.get('q', '').strip()
    return redirect(url_for('app_pages.home', q=q) if q else url_for('app_pages.home'))


def _canonical_college_redirect(college, requested_slug, suffix=''):
    canonical_slug = slugify(college.get('abbreviation') or college.get('name'))
    if requested_slug == canonical_slug:
        return None
    target = url_for('library.college_landing', college_slug=canonical_slug) + suffix
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8')}"
    return redirect(target, code=301)


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
    canonical_redirect = _canonical_college_redirect(college, college_slug)
    if canonical_redirect:
        return canonical_redirect

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
    departments = get_departments_by_college(college_id).get('data', [])

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
    client = init_supabase_admin() or init_supabase()
    if not client:
        abort(500, description='Database client unavailable')

    college_res = get_college_by_slug(college_slug)
    if not college_res.get('success'):
        abort(404)
    college = college_res.get('data')
    college_id = college.get('id')
    canonical_redirect = _canonical_college_redirect(college, college_slug, '/files')
    if canonical_redirect:
        return canonical_redirect

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
    search_query = re.sub(r'[^a-zA-Z0-9\s_-]', ' ', search_query)
    search_query = re.sub(r'\s+', ' ', search_query).strip()[:200]
    try:
        page = max(1, int(request.args.get('page', '1') or '1'))
    except (TypeError, ValueError):
        abort(400, description='page must be a positive integer')
    page_size = 16
    requested_page = page

    dept_res = {'success': False, 'data': {}}
    if department_slug:
        dept_res = get_department_by_slug(department_slug, college_id=college_id)

    q = client.table('documents') \
        .select('*, subjects(name, subject_code), profiles!documents_uploader_id_fkey(full_name), colleges(name, abbreviation), departments(name, abbreviation)') \
        .eq('college_id', college_id) \
        .eq('status', 'approved') \
        .order('view_count', desc=True)

    if doc_type:
        q = q.eq('document_category', doc_type)
    if dept_res.get('success') and dept_res.get('data', {}).get('college_id') == college_id:
        q = q.eq('department_id', dept_res['data']['id'])
    if search_query:
        search_terms = [
            f"title.ilike.%{search_query}%",
            f"description.ilike.%{search_query}%",
            f"search_text.ilike.%{search_query}%",
        ]
        # Subject names and codes live in the related subjects table. Resolve
        # their IDs first so they can participate in the same document OR.
        try:
            subject_matches = client.table('subjects') \
                .select('id') \
                .or_(f"name.ilike.%{search_query}%,subject_code.ilike.%{search_query}%") \
                .limit(100) \
                .execute().data or []
            subject_ids = [row.get('id') for row in subject_matches if row.get('id')]
            if subject_ids:
                search_terms.append(f"subject_id.in.({','.join(subject_ids)})")
        except Exception as search_err:
            logging.warning(f"[college_files] subject search lookup failed: {search_err}")
        q = q.or_(','.join(search_terms))

    # Level 1 cached department list (1 hr TTL)
    dept_cache_key = f"col_depts:{college_id}"
    departments = get_cache().get_cached(
        dept_cache_key,
        ttl=TTL.LONG,
        fetcher=lambda: get_departments_by_college(college_id).get('data', [])
    ) or []

    # Level 1 cached college files query (180s TTL)
    cache_key = f"col_files:{college_id}:{doc_type}:{department_slug}:{search_query}:{page}:{page_size}"

    def _fetch_college_files():
        count_resp = client.table('documents') \
            .select('id', count='exact') \
            .eq('college_id', college_id) \
            .eq('status', 'approved')
        if doc_type:
            count_resp = count_resp.eq('document_category', doc_type)
        if dept_res.get('success') and dept_res.get('data', {}).get('college_id') == college_id:
            count_resp = count_resp.eq('department_id', dept_res['data']['id'])
        if search_query:
            count_resp = count_resp.or_(','.join(search_terms))
        total_cnt = count_resp.execute().count or 0

        tot_pages = max(1, (total_cnt + page_size - 1) // page_size)
        cur_page = min(page, tot_pages)
        offset = (cur_page - 1) * page_size
        items = q.limit(page_size).offset(offset).execute().data or []
        return {'files': items, 'total_count': total_cnt, 'page': cur_page, 'total_pages': tot_pages}

    query_error = False
    try:
        cached_result = get_cache().get_cached(cache_key, ttl=180, fetcher=_fetch_college_files)
        files = cached_result.get('files', [])
        total_count = cached_result.get('total_count', 0)
        actual_page = cached_result.get('page', page)
        if actual_page != requested_page:
            corrected_args = request.args.to_dict(flat=True)
            corrected_args['page'] = actual_page
            return redirect(url_for('library.college_files', college_slug=college_slug, **corrected_args), code=302)
        page = actual_page
    except Exception as e:
        logging.error(f"[college_files] query failed: {e}")
        files = []
        total_count = 0
        query_error = True

    response = make_response(render_template('college_files.html',
                           college=college,
                           files=files,
                           departments=departments,
                           filters={
                               'type': doc_type,
                               'branch': department_slug,
                               'search': search_query,
                               'page': page,
                               'page_size': page_size,
                               'total': total_count,
                               'query_error': query_error
                           }))
    get_cache().set_cache_headers(response, max_age=180, stale_while_revalidate=True)
    return response


@library_bp.route('/pyq/<college_slug>/files')
def pyq_college_files_legacy_redirect(college_slug):
    """Permanent 301 redirect from legacy /pyq/<college_slug>/files to canonical /college/<college_slug>/files."""
    return redirect(url_for('library.college_files', college_slug=college_slug, **request.args), code=301)

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


@library_bp.route('/resources')
def resources_index_catalog():
    """Canonical /resources catalog index. Redirects to user's college files or general library."""
    profile = session.get('profile') or {}
    college_slug = profile.get('college_slug')
    if college_slug:
        return redirect(url_for('library.college_files', college_slug=college_slug))
    return redirect(url_for('library.pyq_landing'))


_reported_404_cache = {}


def report_resource_404(slug, doc_id=None, reason="404 Not Found"):
    """Log missing/deleted resource incidents to viewer_failure_reports for admin dashboard."""
    try:
        now = time.time()
        cache_key = str(slug or '').lower().strip()
        if cache_key in _reported_404_cache and (now - _reported_404_cache[cache_key]) < 300:
            return

        _reported_404_cache[cache_key] = now
        if len(_reported_404_cache) > 1000:
            expired = [k for k, v in _reported_404_cache.items() if now - v > 300]
            for k in expired:
                _reported_404_cache.pop(k, None)

        client = init_supabase_admin() or init_supabase()
        if not client:
            return

        user = session.get('user', {}) if has_request_context() else {}
        user_id = user.get('uid') or user.get('id')
        user_email = user.get('email')

        page_url = request.url if has_request_context() else f"/resources/{slug}"
        identifier = str(doc_id or slug or 'Unknown')

        report_data = {
            'doc_id': None,  # NULL prevents foreign key violation on non-existent documents
            'file_name': f"Missing Resource: {identifier[:80]}",
            'file_url': '',
            'file_type': 'resource',
            'issue_type': '404 Missing Resource',
            'error_msg': f"404 Resource Not Found ({reason}): {page_url}",
            'page_url': page_url,
            'reporter_email': user_email or 'system_404_monitor@abhihub.com',
            'reporter_id': user_id,
            'viewer_type': 'resource_landing',
            'status': 'open'
        }
        client.table('viewer_failure_reports').insert(report_data).execute()
        logging.info(f"[Resource 404] Logged missing resource {identifier} to viewer_failure_reports")
    except Exception as e:
        logging.warning(f"[Resource 404] Could not record missing resource report: {e}")


def render_resource_404(slug=None, doc_id=None, is_unapproved=False):
    """Render the redesigned 404 page specifically for study resources / files."""
    return render_template(
        'resource_not_found.html',
        slug=slug,
        doc_id=doc_id,
        is_unapproved=is_unapproved
    ), 404


@library_bp.route('/api/og/resource/<doc_id>.png')
@library_bp.route('/api/og/resource/<doc_id>')
def resource_og_image(doc_id):
    """Dynamic 1200x630 OG image generation for resources."""
    import app
    from methods.resource_og import generate_resource_og_image
    cache = getattr(app, 'cache', None)
    doc_res = None
    if cache and not current_app.config.get('TESTING'):
        doc_res = cache.get_cached(f"doc_rich:{doc_id}", level=cache.L1, ttl=300)
    if not doc_res:
        document_loader = getattr(app, 'get_document_by_id_rich', get_document_by_id_rich)
        doc_res = document_loader(doc_id)
        if doc_res and doc_res.get('success') and cache:
            cache.set_cached(f"doc_rich:{doc_id}", doc_res, ttl=300)

    doc = doc_res.get('data', {}) if doc_res and doc_res.get('success') else {}
    subj = doc.get('subject') or {}
    coll = doc.get('college') or {}
    up = doc.get('uploader') or {}

    img_data = {
        'id': doc_id,
        'title': doc.get('title') or 'Study Material',
        'subject': subj.get('name') if isinstance(subj, dict) else (doc.get('subject_name') or 'Engineering'),
        'author': up.get('full_name') if isinstance(up, dict) else (doc.get('uploader_name') or 'AbhiHub Member'),
        'semester': str(doc.get('semester') or doc.get('semester_code') or 'All Semesters'),
        'category': doc.get('document_category') or doc.get('file_type') or 'Notes',
        'college': coll.get('name') if isinstance(coll, dict) else (doc.get('college_name') or 'AbhiHub')
    }

    img_bytes = generate_resource_og_image(img_data)
    resp = make_response(img_bytes)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'public, max-age=86400, stale-while-revalidate=604800'
    return resp


@library_bp.route('/resource/<path:slug>')
@library_bp.route('/resources/<path:slug>')
def resource_landing(slug):
    """Dynamic SEO-optimized resource landing page"""
    import app
    log_document_view = getattr(app, 'log_document_view', None)
    from data.pricing import has_document_access, extract_document_pricing
    from routes.ai import AI_MODELS, get_best_ai_model

    clean_slug = re.sub(r'-view$', '', slug.lower().strip())
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    match = re.search(uuid_pattern, clean_slug)
    if not match:
        report_resource_404(slug, reason="Invalid resource format / UUID missing")
        return render_resource_404(slug=slug)

    doc_id = match.group(0)
    cache = getattr(app, 'cache', None)
    doc_res = None
    if cache and not current_app.config.get('TESTING'):
        doc_res = cache.get_cached(f"doc_rich:{doc_id}", level=cache.L1, ttl=300)
    if not doc_res:
        # Resolve through the application module so integrations and tests can
        # replace the document provider without patching this blueprint module.
        document_loader = getattr(app, 'get_document_by_id_rich', get_document_by_id_rich)
        doc_res = document_loader(doc_id)
        if doc_res.get('success') and cache:
            cache.set_cached(f"doc_rich:{doc_id}", doc_res, ttl=300)

    if not doc_res or not doc_res.get('success'):
        report_resource_404(slug, doc_id=doc_id, reason="Document ID not found in database")
        return render_resource_404(slug=slug, doc_id=doc_id)

    document = dict(doc_res.get('data') or {})
    if str(document.get('status') or '').strip().lower() != 'approved':
        viewer = session.get('user', {})
        viewer_id = viewer.get('uid') or viewer.get('id')
        is_owner = bool(viewer_id and str(viewer_id) == str(document.get('uploader_id') or ''))
        if not is_owner and not is_admin_user(viewer):
            report_resource_404(slug, doc_id=doc_id, reason="Unapproved document access attempt")
            return render_resource_404(slug=slug, doc_id=doc_id, is_unapproved=True)

    file_url = document.get('file_url', '')
    if file_url:
        document['raw_cloud_url'] = file_url
        clean_ext = os.path.splitext(urlsplit(str(file_url)).path)[1].lower()
        raw_type = str(document.get('file_type') or '').strip().lower()
        raw_mime = str(document.get('mime_type') or document.get('content_type') or '').strip().lower()
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.bmp'}
        image_types = {'image', 'jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'bmp'}
        image_mimes = {
            'image/jpeg', 'image/png', 'image/webp', 'image/gif',
            'image/avif', 'image/bmp',
        }
        if clean_ext in image_extensions:
            is_image = True
            is_pdf = False
        elif clean_ext == '.pdf':
            is_pdf = True
            is_image = False
        else:
            is_pdf = raw_type in {'pdf', 'application/pdf'} or raw_mime == 'application/pdf'
            is_image = (
                raw_type in image_types or
                raw_type in image_mimes or raw_mime in image_mimes or
                bool(document.get('is_image'))
            )
        if is_pdf:
            document['file_type'] = 'pdf'
            document['is_image'] = False
            document['viewer_type'] = 'pdf'
            clean_ext = '.pdf'
        elif is_image:
            document['file_type'] = 'image'
            document['is_image'] = True
            document['viewer_type'] = 'image'
        else:
            document['viewer_type'] = 'unsupported'
        document['file_url'] = f'/api/view-doc/{doc_id}/file{clean_ext}'

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

    client = init_supabase_admin() or init_supabase()
    if current_user_id and client:
        try:
            like_check = client.table('document_votes').select('document_id').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
            document['is_liked'] = bool(like_check.data)
        except Exception:
            pass
        try:
            bm_check = client.table('bookmarks').select('document_id').eq('document_id', doc_id).eq('user_id', current_user_id).execute()
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
            select_rich_fields = (
                'id, title, document_category, file_type, file_url, price, is_paid, view_count, '
                'subjects(name, subject_code), colleges(name, abbreviation), '
                'uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)'
            )
            if subj_id and client:
                sug_res = client.table('documents').select(select_rich_fields).eq('subject_id', subj_id).neq('id', doc_id).limit(4).execute()
                suggested_docs = sug_res.data or []

            # If fewer than 4 suggestions, complement with documents from the same college
            if len(suggested_docs) < 4 and client:
                col_id = document.get('college_id')
                q = client.table('documents').select(select_rich_fields).neq('id', doc_id)
                if col_id:
                    q = q.eq('college_id', col_id)
                fb_res = q.order('created_at', desc=True).limit(4 - len(suggested_docs)).execute()
                seen_s_ids = {d['id'] for d in suggested_docs}
                for fd in (fb_res.data or []):
                    if fd['id'] not in seen_s_ids:
                        suggested_docs.append(fd)
                        seen_s_ids.add(fd['id'])

            if cache and suggested_docs:
                cache.set_cached(sug_cache_key, suggested_docs, ttl=600)
        except Exception as e:
            logging.error(f"[Supabase] Error fetching suggestions: {e}")

    # Fetch recent files (user session recent trail + latest campus uploads)
    recent_files = []
    try:
        recent_view_ids = [str(i) for i in session.get('recent_views', []) if str(i) != str(doc_id)]
        if recent_view_ids and client:
            rv_res = client.table('documents').select(
                'id, title, document_category, file_type, file_url, price, is_paid, view_count, '
                'subjects(name, subject_code), colleges(name, abbreviation), '
                'uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)'
            ).in_('id', recent_view_ids[:4]).execute()
            recent_files = rv_res.data or []

        if len(recent_files) < 4 and client:
            rf_res = client.table('documents').select(
                'id, title, document_category, file_type, file_url, price, is_paid, view_count, '
                'subjects(name, subject_code), colleges(name, abbreviation), '
                'uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)'
            ).neq('id', doc_id).order('created_at', desc=True).limit(4 - len(recent_files)).execute()
            seen_r_ids = {d['id'] for d in recent_files}
            for rd in (rf_res.data or []):
                if rd['id'] not in seen_r_ids:
                    recent_files.append(rd)
                    seen_r_ids.add(rd['id'])
    except Exception as e_rf:
        logging.debug(f"[RESOURCE] Recent files fetch note: {e_rf}")

    # Track doc_id in session recent_views
    try:
        cur_views = session.get('recent_views', [])
        if doc_id in cur_views:
            cur_views.remove(doc_id)
        cur_views.insert(0, doc_id)
        session['recent_views'] = cur_views[:12]
    except Exception:
        pass

    from methods.seo_helper import is_resource_indexable
    is_thin = not is_resource_indexable(document)
    redesign_preview = request.args.get('redesign') == '1'
    render_noindex = is_thin or redesign_preview

    is_prod = os.environ.get('FLASK_ENV') == 'production' or current_app.config.get('ENV') == 'production' or current_app.config.get('PRODUCTION', False)
    mock_study_kit = False if is_prod else bool(current_app.config.get('MOCK_STUDY_KIT', False) or os.environ.get('MOCK_STUDY_KIT') == '1')

    desc_raw = document.get('description') or ''
    pricing = extract_document_pricing(document)
    custom_recommendations = {}
    if isinstance(desc_raw, str) and desc_raw.strip().startswith('{'):
        try:
            parsed_d = json.loads(desc_raw.strip())
            document['display_description'] = parsed_d.get('text_description', '')
            custom_recommendations = parsed_d.get('recommendations') or {}
        except Exception:
            document['display_description'] = desc_raw
    elif isinstance(desc_raw, dict):
        document['display_description'] = desc_raw.get('text_description', '')
        custom_recommendations = desc_raw.get('recommendations') or {}
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
    from methods.wallet_service import is_creator_verified
    is_uploader_verified = is_creator_verified(document.get('uploader_id'))
    view_earnings = round(recorded_views * 0.20, 2) if is_uploader_verified else 0.0

    direct_pdf_url = None
    if has_access and document.get('viewer_type') in {'pdf', 'image'}:
        try:
            from routes.api import authorize_document_access
            auth_payload, auth_status = authorize_document_access(doc_id)
            if auth_status == 200 and auth_payload and auth_payload.get('file_url'):
                direct_pdf_url = auth_payload.get('file_url')
        except Exception as auth_err:
            logging.warning(
                "[resource_landing] Could not pre-authorize direct PDF URL (error_type=%s)",
                type(auth_err).__name__,
            )

    # Format user-friendly display title: "<Subject Name>: <Category> (<Specifics>)"
    subject_display = ''
    if document.get('subject') and isinstance(document.get('subject'), dict):
        subject_display = document['subject'].get('name') or ''
    if not subject_display:
        subject_display = document.get('subject_name') or ''

    doc_raw_title = document.get('title') or ''
    clean_cat_part = ''
    cat_match = re.search(r'-\s*(Notes|PYQ|Paper|Papers|Practical|Syllabus|Assignment|Question Bank)\s*(?:\(([^)]+)\))?\s*-', doc_raw_title, re.IGNORECASE)
    if cat_match:
        c_name = cat_match.group(1).strip()
        c_detail = cat_match.group(2).strip() if cat_match.group(2) else ''
        if c_name.lower() in ('papers', 'pyq'):
            c_name = 'Paper'
        clean_cat_part = f"{c_name} ({c_detail})" if c_detail else c_name
    else:
        c_type = (document.get('document_category') or document.get('file_type') or 'Material').capitalize()
        c_detail = document.get('exam_type') or document.get('unit') or document.get('assignment_num') or ''
        clean_cat_part = f"{c_type} ({c_detail})" if c_detail else c_type

    if subject_display:
        display_title = f"{subject_display}: {clean_cat_part}"
    elif ':' in doc_raw_title:
        display_title = doc_raw_title
    else:
        display_title = f"{clean_cat_part} - {doc_raw_title}"

    return app.render_template(
        'resource.html',
        document=document,
        display_title=display_title,
        direct_pdf_url=direct_pdf_url,
        pricing=pricing,
        has_access=has_access,
        can_manage=can_manage,
        is_admin=is_admin,
        is_uploader=is_uploader,
        is_uploader_verified=is_uploader_verified,
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
        mock_study_kit=mock_study_kit,
        custom_recommendations=custom_recommendations,
        recent_files=recent_files,
        redesign_preview=redesign_preview
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
        if 'title' in doc_update_clean and len(str(doc_update_clean['title']).strip()) < 3:
            return jsonify({'success': False, 'message': 'Title must contain at least 3 characters'}), 400
        if 'document_category' in doc_update_clean:
            allowed_categories = {'papers', 'notes', 'practical', 'syllabus', 'question_bank', 'assignment', 'timetable', 'other'}
            category_value = str(doc_update_clean['document_category']).strip().lower()
            if category_value not in allowed_categories:
                return jsonify({'success': False, 'message': 'Invalid document category'}), 400
            doc_update_clean['document_category'] = category_value
        if 'price' in doc_update_clean:
            doc_update_clean['price'] = min(max(float(doc_update_clean['price']), 0.0), 5000.0)
            if doc_update_clean['price'] > 0:
                doc_update_clean['is_paid'] = True
        if doc_update_clean.get('is_paid') is False:
            doc_update_clean['price'] = 0.0
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
        try:
            from methods.search_api import invalidate_search_cache
            invalidate_search_cache()
        except Exception as cache_err:
            logging.warning(f"[api_edit_document] Search cache invalidation failed: {cache_err}")

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


@library_bp.route('/api/document/<doc_id>/recommendations', methods=['POST'])
@auth_required
def api_save_document_recommendations(doc_id):
    """
    Allow uploader / owner / admin to customize the Recommended For You section:
    - Videos: YouTube videos & playlists
    - Papers / Notes: AbhiHub direct links
    - Books: AbhiHub links OR verified bookstore affiliate links
    - Faculty / Peers: AbhiHub creator channels & peer links
    """
    client = init_supabase()
    if not client:
        return jsonify({'success': False, 'message': 'Database unavailable'}), 500

    doc_res = client.table('documents').select('id, uploader_id, description').eq('id', doc_id).limit(1).execute()
    if not doc_res.data:
        return jsonify({'success': False, 'message': 'Document not found'}), 404

    doc = doc_res.data[0]
    user_info = session.get('user', {})
    current_user_id = user_info.get('uid') or user_info.get('id')
    is_admin = is_admin_user(user_info)
    is_uploader = bool(current_user_id and str(doc.get('uploader_id') or '') == str(current_user_id))

    if not (is_admin or is_uploader):
        return jsonify({'success': False, 'message': 'Permission denied. Only uploader or admin can edit recommendations.'}), 403

    payload = request.get_json(silent=True) or {}
    recommendations = payload.get('recommendations') or {}

    clean_recs = {
        'videos': [],
        'papers': [],
        'notes': [],
        'books': [],
        'faculty': []
    }

    # 1. Videos (YouTube links & playlists)
    for v in recommendations.get('videos', []):
        t = str(v.get('title', '')).strip()[:100]
        u = str(v.get('url', '')).strip()
        if t and u and ('youtube.com' in u.lower() or 'youtu.be' in u.lower()):
            clean_recs['videos'].append({
                'title': t,
                'url': u,
                'type': 'playlist' if ('list=' in u.lower() or 'playlist' in u.lower()) else 'video'
            })

    # 2. Papers (AbhiHub direct links)
    for p in recommendations.get('papers', []):
        t = str(p.get('title', '')).strip()[:100]
        u = str(p.get('url', '')).strip()
        if t and u:
            clean_recs['papers'].append({
                'title': t,
                'url': u,
                'badge': str(p.get('badge') or 'PYQ')[:30]
            })

    # 3. Notes (AbhiHub direct links)
    for n in recommendations.get('notes', []):
        t = str(n.get('title', '')).strip()[:100]
        u = str(n.get('url', '')).strip()
        if t and u:
            clean_recs['notes'].append({
                'title': t,
                'url': u,
                'badge': str(n.get('badge') or 'Notes')[:30]
            })

    # 4. Books (AbhiHub direct links OR verified bookstore affiliate links)
    for b in recommendations.get('books', []):
        t = str(b.get('title', '')).strip()[:100]
        u = str(b.get('url', '')).strip()
        store = str(b.get('store', '')).strip()[:50]
        if t and u:
            is_affiliate = any(store_key in u.lower() for store_key in ['amazon', 'flipkart', 'amzn', 'fkrt', 'bookswagon', 'sapna'])
            clean_recs['books'].append({
                'title': t,
                'url': u,
                'store': store or ('Bookstore' if is_affiliate else 'AbhiHub'),
                'is_affiliate': is_affiliate
            })

    # 5. Faculty / Peers (AbhiHub peer/channel links)
    for f in recommendations.get('faculty', []):
        name = str(f.get('name', '')).strip()[:80]
        u = str(f.get('url', '')).strip()
        role = str(f.get('role', '')).strip()[:80]
        if name and u:
            clean_recs['faculty'].append({
                'name': name,
                'url': u,
                'role': role or 'Faculty / Peer Mentor'
            })

    desc_raw = doc.get('description') or ''
    desc_obj = {}
    if isinstance(desc_raw, str) and desc_raw.strip().startswith('{'):
        try:
            desc_obj = json.loads(desc_raw.strip())
        except Exception:
            desc_obj = {'text_description': desc_raw}
    elif isinstance(desc_raw, dict):
        desc_obj = dict(desc_raw)
    else:
        desc_obj = {'text_description': desc_raw}

    desc_obj['recommendations'] = clean_recs

    try:
        client.table('documents').update({
            'description': json.dumps(desc_obj)
        }).eq('id', doc_id).execute()
    except Exception as e:
        logging.error(f"[api_save_document_recommendations] DB Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

    try:
        import app
        c = getattr(app, 'cache', None)
        if c:
            c.invalidate(f"doc_rich:{doc_id}")
    except Exception:
        pass

    return jsonify({'success': True, 'recommendations': clean_recs})
