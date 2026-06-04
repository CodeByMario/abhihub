# AbhiHub Current Architecture Analysis
Generated: 2026-06-04

## 1. App Entry Point: app.py (2978 lines)

### Flask Setup
- `Flask(__name__)`, `Flask-Compress`, `Flask-WTF` (CSRF enabled globally via `WTF_CSRF_ENABLED`)
- `SECRET_KEY` from env, sessions are permanent (90 days), HTTPS-only cookies in prod
- Supabase client: `create_client(..., options=ClientOptions(schema="abhihub"))` → schema = `abhihub`
- Firebase Admin: Storage bucket `abhi-hub.appspot.com`

### Auth Pattern
- Session-based: `session['user'] = {uid, email, name, provider, user_metadata}`
- Decorator: `@auth_required` → checks `'user' in session`, redirects to `/login` or returns 401 for API routes
- Admin decorator: `@admin_required` → checks email against hardcoded list
- **No JWT in templates** — server-side session only

### Route Naming Convention
```python
@app.route('/route')
def route_name():
    return render_template('p_template.html', **context)
```
- Auth routes use `@auth_required`
- API routes prefix `/api/...` or `/api/feature/...`
- Public routes have no decorator

### Existing Route Patterns (relevant samples)
```
GET  /login             → render p_login.html
GET  /dashboard         → render p_index.html  (auth_required)
GET  /profile           → render p_profile.html (auth_required)
GET  /upload            → render p_upload.html  (auth_required)
GET  /ranking           → render p_ranking.html
POST /api/interactions/like    → auth_required JSON API
POST /api/interactions/bookmark → auth_required JSON API
POST /store-room/api/label     → auth_required JSON API
GET  /api/quota                → auth_required JSON API
```

## 2. Template System

### Base Template: `p_struct.html` (1391 lines)
This is the **master layout** for all authenticated pages. It includes:
- `<head>`: Fonts (Kanit via Google Fonts), CSS files
- `{% include 'google_tag.html' %}` — GA4 included globally here
- `{% include 'js/analytics-helper.js' %}` — deferred analytics script
- `window.__CURRENT_USER__` — exposes session user to JS
- PWA install popup, profile nudge overlay, promo card overlay — all inline here
- `{% include 'includes/promo_card.html' %}` inside body

### CSS Architecture
- `static/premium/css/style.css` — main app styles (v=2.0.1)
- `static/css/overlay-system.css` — overlay system
- `static/css/tailwind.min.css` — Tailwind utilities (present but minimal usage observed)
- `static/css/study-pass.css` — feature-specific CSS
- Pattern: **feature-specific CSS in `static/css/`**

### Nav: `templates/p_nav.html`
- Bottom mobile navbar with 5 items: Home, Ranking, Upload (FAB), Account, Store Room
- Admin item conditional on email
- `{% include 'p_nav.html' %}` inside p_struct.html body

### Footer: `templates/footer.html`
- Simple Bootstrap-style footer (bg-dark, container, rows)
- Used in public-facing pages (not in the auth app layout)

### Public Pages Nav: `templates/navbar_public.html`
- Separate navbar for unauthenticated pages

### Template inheritance: **NOT Jinja2 block inheritance**
- `p_struct.html` is a full standalone HTML file
- Pages are rendered as standalone templates, each including nav/footer manually
- Or p_struct.html IS the layout and it includes sections via `{% include %}`

## 3. Analytics: `google_tag.html`
GA4 ID: `G-EH5BGS9BEG`
- `window.AbhiHubTracking` object with methods: `trackFileView`, `trackShare`, `trackUpload`, etc.
- `window.safeGtag(cmd, name, params)` — deduplication wrapper
- `window.trackEvent(eventName, data)` — global shorthand
- Pattern for new events:
```js
window.AbhiHubTracking.trackMemorywallCreate = function(wallId) {
  safeGtag('event', 'memorywall_create', { wall_id: wallId, page_path: window.location.pathname });
};
```

## 4. Supabase: `methods/supabase_helper.py`
- Schema: `abhihub` (NOT public)
- Client singleton via `init_supabase()` → returns `_supabase_client`
- Pattern:
```python
def my_fn(param: str) -> Dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "No client"}
    try:
        res = client.table('table_name').select(...).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        return {"success": False, "message": str(e)}
```
- UUID validation via `validate_uuid(val)`
- All functions return `{"success": bool, ...}` dicts

## 5. Firebase Storage: `methods/storage.py`
- Firebase Admin SDK initialized in app.py
- Bucket: `abhi-hub.appspot.com`
- Functions: `upload_file`, `list_files`, `download_file`, `delete_file`

## 6. Methods Folder
```
methods/
  __init__.py
  supabase_helper.py   — 1195 lines, all DB ops
  storage.py           — Firebase Storage ops
  cloudinary_helper.py — Cloudinary ops
  cloudinary_upload.py — Upload handler
  encryption.py        — File encryption
  upload_notifier.py   — Push notification triggers
```

## 7. Security
- `Flask-WTF` installed and `WTF_CSRF_ENABLED = True` (CSRF protection active)
- File extension whitelist in `ALLOWED_EXTENSIONS`
- `sanitize_filename()` utility in app.py
- Security audit logs via `log_security_audit_event()` in supabase_helper.py
- `@auth_required` / `@admin_required` decorators

## 8. Rate Limiting
- **Flask-Limiter is NOT in requirements.txt** — must add `flask-limiter` if needed
- OR implement manual IP-based rate limiting with Redis/session

## 9. Dependencies (requirements.txt)
```
Flask==2.0.1, gunicorn, firebase-admin==5.2.0, werkzeug==2.0.3
Pillow>=10.0.0, flask-socketio, pywebpush, python-dotenv
supabase, cloudinary, PyJWT, Flask-WTF, python-multipart, Flask-Compress
```
- `wordcloud` NOT installed — must add
- `flask-limiter` NOT installed — must add

## 10. Migration Pattern (migrations/)
```sql
-- migrations/add_quota_fields.sql
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS paper_quota_remaining INTEGER DEFAULT 19,
ADD COLUMN IF NOT EXISTS last_quota_reset TEXT DEFAULT '2026-05';
```
Note: `public.` prefix used in migrations (the abhihub schema is accessed via ClientOptions in code, but SQL migrations use `public.`)

## Key Integration Points for MemoryWall

1. **Routes** → Add directly to `app.py` (same file, not append_routes.py which is a dev utility)
2. **DB helpers** → Add to `methods/supabase_helper.py` following existing pattern  
3. **Business logic** → New file `methods/know_me.py`
4. **Generator** → New file `methods/know_me_generator.py`
5. **Templates** → `templates/know_me/` subfolder, include `p_nav.html` manually
6. **CSS** → `static/css/know-me.css`
7. **JS** → `static/js/know-me.js`
8. **Analytics** → Extend `window.AbhiHubTracking` via page-level script (NOT modifying google_tag.html)
9. **Storage** → Generated assets in `static/know_me/generated/` + Firebase Storage
10. **Migration** → `migrations/know_me_tables.sql`
