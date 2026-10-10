import os
import re
import json
import logging
from flask import (
    Blueprint, request, session, redirect, url_for, render_template,
    abort, make_response, current_app
)
from routes.seo import sitemap_page, slugify
from methods.supabase_helper import (
    init_supabase, get_all_colleges, get_all_branches, get_college_by_slug,
    get_colleges_by_brand, get_college_stats, get_waitlist_count,
    get_recent_college_files, get_department_by_slug, get_department_stats,
    get_recent_department_files, get_subjects_by_slug, get_subject_stats,
    get_recent_subject_files, get_document_by_id_rich, get_leaderboard_data
)

library_bp = Blueprint('library', __name__)


@library_bp.route('/leaderboard', methods=['GET'])
def leaderboard():
    """Global Gamification Leaderboard — cached at L1 for 10min."""
    import app
    cache = app.cache

    college_id = request.args.get('college_id')
    cache_key = f"leaderboard:{college_id or 'all'}"

    def fetch_lb():
        result = get_leaderboard_data(college_id=college_id, limit=50)
        return result.get('data', []) if result.get('success') else []

    leaderboard_data = cache.get_cached(cache_key, level=cache.L2, ttl=cache.LONG, fetcher=fetch_lb)
    user_info = session.get('user')
    response = make_response(render_template(
        'leaderboard.html',
        leaderboard=leaderboard_data,
        current_user=user_info
    ))
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
    doc_res = get_document_by_id_rich(doc_id)
    if not doc_res.get('success'):
        abort(404)

    document = doc_res.get('data')

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

    current_user_id = session.get('user', {}).get('uid')
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

    log_document_view(
        file_name=title,
        file_url=document.get('file_url'),
        record_id=doc_id,
        file_type=document.get('file_type'),
    )

    suggested_docs = []
    store_room_docs = []
    try:
        subj_id = document.get('subject_id')
        subj_name = document.get('subject', {}).get('name', '') if document.get('subject') else ''

        if subj_id:
            sug_res = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').eq('subject_id', subj_id).neq('id', doc_id).limit(4).execute()
            suggested_docs = sug_res.data or []

        similar_subj_ids = []
        if len(suggested_docs) < 4 and subj_name:
            name_res = client.table('subjects').select('id').ilike('name', subj_name.strip()).execute()
            similar_subj_ids = [s['id'] for s in name_res.data if s['id'] != subj_id] if name_res.data else []
            if similar_subj_ids:
                sug_res2 = client.table('documents').select('id, title, file_type, view_count, uploader:profiles!documents_uploader_id_fkey(full_name, is_verified)').in_('subject_id', similar_subj_ids).neq('id', doc_id).limit(4 - len(suggested_docs)).execute()
                if sug_res2.data:
                    suggested_docs.extend(sug_res2.data)

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
            keywords = [w for w in title.split() if len(w) > 3]
            if keywords:
                or_cond = ",".join([f"filename.ilike.*{kw}*" for kw in keywords[:2]])
                sr_res = client.table('storage_assets').select('id, provider_public_id, filename').eq('status', 'PENDING').or_(or_cond).limit(4).execute()
                store_room_docs = sr_res.data or []
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

    return render_template(
        'resource.html',
        document=document,
        pricing=pricing,
        has_access=has_access,
        ai_models=AI_MODELS,
        best_model=get_best_ai_model(),
        suggested_docs=suggested_docs,
        store_room_docs=store_room_docs,
        ai_chat_allowed=ai_chat_allowed,
        noindex=render_noindex,
        mock_study_kit=mock_study_kit
    )


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

