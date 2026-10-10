import os
import re
from datetime import datetime
from functools import wraps
from flask import (
    Blueprint, current_app, request, make_response, render_template,
    send_from_directory, send_file, abort
)
from methods.supabase_helper import get_sitemap_urls
from methods.seo_helper import is_resource_indexable

seo_bp = Blueprint('seo', __name__)

BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'www.abhihub.edu.eu.org').strip().lower()
INDEXNOW_KEY = os.getenv('INDEX_NOW_BING_API_KEY', '').strip()

_SITEMAP_REGISTRY = {}


def sitemap_page(priority="0.80", changefreq="weekly"):
    """Mark a static Flask view as eligible for inclusion in the sitemap."""
    def decorator(view_func):
        _SITEMAP_REGISTRY[view_func.__name__] = {
            "priority": priority,
            "changefreq": changefreq,
        }

        @wraps(view_func)
        def wrapper(*args, **kwargs):
            return view_func(*args, **kwargs)
        return wrapper
    return decorator


def slugify(text):
    """Normalize names into canonical SEO slugs."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')


@seo_bp.route('/<key>.txt')
def indexnow_key_file(key):
    """Serve the IndexNow key verification file dynamically based on .env configuration."""
    if INDEXNOW_KEY and key == INDEXNOW_KEY:
        return INDEXNOW_KEY, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    abort(404)


@seo_bp.route('/ads.txt')
def ads_txt():
    return "google.com, pub-8274846157272362, DIRECT, f08c47fec0942fa0", 200, {'Content-Type': 'text/plain'}


@seo_bp.route('/robots.txt')
def robots_txt():
    """Expose crawler directives with a sitemap URL for the canonical host."""
    with open(os.path.join(current_app.root_path, 'robots.txt'), encoding='utf-8') as robots_file:
        robots_content = robots_file.read()
    robots_content = re.sub(
        r'^Sitemap:\s*.*$',
        f"Sitemap: https://{BASE_DOMAIN}/sitemap.xml",
        robots_content,
        flags=re.MULTILINE,
    )
    response = make_response(robots_content)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response


@seo_bp.route('/llms.txt')
def llms_txt():
    """GEO signal file for AI model crawlers (GPTBot, PerplexityBot, ClaudeBot, Gemini)."""
    return send_from_directory('static', 'llms.txt', mimetype='text/plain')


@seo_bp.route('/manifest.json')
def premium_manifest():
    return send_file('static/manifest.json', mimetype='application/manifest+json')


@seo_bp.route('/favicon.ico')
def favicon():
    return send_file('static/images/favicon.ico', mimetype='image/vnd.microsoft.icon')


@seo_bp.route('/sitemap.xml')
def sitemap():
    """Return Sitemap Index pointing to modular sub-sitemaps for search engines."""
    base_url = f"https://{BASE_DOMAIN}"
    now_iso = datetime.utcnow().strftime('%Y-%m-%d')
    sitemaps = [
        {'loc': f"{base_url}/sitemap-pages.xml", 'lastmod': now_iso},
        {'loc': f"{base_url}/sitemap-colleges.xml", 'lastmod': now_iso},
        {'loc': f"{base_url}/sitemap-documents.xml", 'lastmod': now_iso},
    ]
    response = make_response(render_template('sitemap_index.xml', sitemaps=sitemaps))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@seo_bp.route('/sitemap-pages.xml')
def sitemap_pages():
    """Sitemap module for core static public routes."""
    urls = []
    seen = set()
    base_url = f"https://{BASE_DOMAIN}"
    for rule in current_app.url_map.iter_rules():
        # Match endpoint either as bare name or prefixed by blueprint (e.g. 'site.about')
        ep_name = rule.endpoint.split('.')[-1]
        if ep_name not in _SITEMAP_REGISTRY and rule.endpoint not in _SITEMAP_REGISTRY:
            continue
        if 'GET' not in rule.methods or rule.arguments:
            continue
        loc = f"{base_url}{rule}"
        if loc not in seen:
            seen.add(loc)
            metadata = _SITEMAP_REGISTRY.get(ep_name) or _SITEMAP_REGISTRY.get(rule.endpoint)
            urls.append({'loc': loc, 'priority': metadata['priority'], 'changefreq': metadata['changefreq']})
    response = make_response(render_template('sitemap.xml', urls=urls))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@seo_bp.route('/sitemap-colleges.xml')
def sitemap_colleges():
    """Sitemap module for colleges, departments, and subjects."""
    urls = []
    seen = set()
    base_url = f"https://{BASE_DOMAIN}"

    def add_u(path, lastmod=None, priority="0.85", changefreq="weekly"):
        loc = f"{base_url}{path}"
        if loc not in seen:
            seen.add(loc)
            entry = {'loc': loc, 'priority': priority, 'changefreq': changefreq}
            if lastmod:
                entry['lastmod'] = str(lastmod)[:10]
            urls.append(entry)

    sitemap_res = get_sitemap_urls()
    data = sitemap_res.get('data', {}) if sitemap_res.get('success') else {}
    colleges = data.get('colleges', [])
    departments = data.get('departments', [])
    subjects = data.get('subjects', [])
    documents = data.get('documents', [])

    populated_college_ids = {doc.get('college_id') for doc in documents if doc.get('college_id')}
    populated_department_ids = {doc.get('department_id') for doc in documents if doc.get('department_id')}
    populated_subject_ids = {doc.get('subject_id') for doc in documents if doc.get('subject_id')}

    college_slugs = {}
    for c in colleges:
        if c.get('id') not in populated_college_ids:
            continue
        c_slug = slugify(c.get('abbreviation') or c.get('name'))
        if not c_slug:
            continue
        college_slugs[c.get('id')] = c_slug
        add_u(f"/college/{c_slug}", c.get('created_at'), "0.90", "weekly")

    for department in departments:
        if department.get('college_id') not in populated_college_ids:
            continue
        if department.get('id') not in populated_department_ids:
            continue
        c_slug = college_slugs.get(department.get('college_id'))
        d_slug = slugify(department.get('abbreviation') or department.get('name'))
        if c_slug and d_slug:
            add_u(f"/college/{c_slug}/{d_slug}", department.get('created_at'), "0.85", "weekly")

    seen_subjects = set()
    for s in subjects:
        if s.get('id') not in populated_subject_ids:
            continue
        s_slug = slugify(s.get('name'))
        if s_slug and s_slug not in seen_subjects:
            seen_subjects.add(s_slug)
            add_u(f"/subject/{s_slug}", s.get('created_at'), "0.90", "weekly")

    response = make_response(render_template('sitemap.xml', urls=urls))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@seo_bp.route('/sitemap-documents.xml')
def sitemap_documents():
    """Sitemap module for approved documents and PYQs."""
    urls = []
    seen = set()
    base_url = f"https://{BASE_DOMAIN}"

    sitemap_res = get_sitemap_urls()
    data = sitemap_res.get('data', {}) if sitemap_res.get('success') else {}
    documents = data.get('documents', [])
    for doc in documents:
        if not is_resource_indexable(doc):
            continue
        college_data = doc.get('college') or {}
        dept_data = doc.get('department') or {}
        subj_data = doc.get('subject') or {}

        c_slug = slugify(college_data.get('abbreviation') or college_data.get('name') or 'college')
        d_slug = slugify(dept_data.get('abbreviation') or dept_data.get('name') or 'dept')
        s_slug = slugify(subj_data.get('name') or 'subject')
        t_slug = slugify(doc.get('title') or 'file')

        canonical_slug = f"{c_slug}-{d_slug}-{s_slug}-{t_slug}-{doc.get('id')}"
        loc = f"{base_url}/resource/{canonical_slug}"
        if loc not in seen:
            seen.add(loc)
            entry = {'loc': loc, 'priority': "0.75", 'changefreq': "monthly"}
            lastmod = doc.get('updated_at') or doc.get('created_at')
            if lastmod:
                entry['lastmod'] = str(lastmod)[:10]
            urls.append(entry)

    response = make_response(render_template('sitemap.xml', urls=urls))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@seo_bp.route('/sitemap-audit')
def sitemap_audit():
    """List unclassified static GET routes while running in debug mode."""
    if not current_app.debug:
        abort(404)
    missing = []
    for rule in current_app.url_map.iter_rules():
        ep_name = rule.endpoint.split('.')[-1]
        if ep_name in _SITEMAP_REGISTRY or rule.endpoint in _SITEMAP_REGISTRY:
            continue
        if 'GET' not in rule.methods or rule.arguments or rule.endpoint == 'static':
            continue
        missing.append(str(rule))
    return {'unclassified_get_routes': sorted(missing)}


@seo_bp.route('/sw.js')
def service_worker_root():
    """Serve service worker from root with proper headers"""
    from flask import make_response, send_file
    response = make_response(send_file('static/sw.js', mimetype='application/javascript'))
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

