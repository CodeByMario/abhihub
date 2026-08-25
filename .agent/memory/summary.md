# Summary — AbhiHub

## Project Structure (Layer Map)

### Web Layer (`app.py`)
- 155 `@app.route` registrations
- Global decorators: `auth_required`, `admin_required`
- Global middleware: `check_csrf`, `redirect_to_custom_domain`
- SocketIO event handlers (6 events)
- 2 error handlers (404, 500)
- 5254 total lines

### Service Layer (`methods/`)
- `supabase_helper.py` — Main data-access hub (2.3k lines)
- `cloudinary_upload.py` — Upload + compress to Cloudinary, canonical storage path
- `cloudinary_helper.py` — Cloudinary URL/transform helpers
- `storage.py`, `storage_providers.py` — Storage abstraction (Cloudinary / Firebase)
- `analytics_tracker.py` — GA4-style event capture; registers its own routes
- `search_api.py` — Search API v2 endpoints (`/api/v2/search`)
- `indexer.py` — Search index build
- `seo_helper.py` — Slug/canonical helpers
- `know_me.py`, `know_me_generator.py` — Memory Wall feature
- `upload_notifier.py` — Post-upload push notification job
- `get_user_uploaded_files.py` — Per-user upload listing

### Model Layer (`data/`)
- `db.py` — Supabase client singleton (schema `abhihub`)
- `documents.py` — `documents` table
- `profiles.py` — `profiles`, `user_sessions` tables
- `interactions.py` — `document_views`, likes, bookmarks, comments
- `colleges.py` — `colleges`, `departments`, `subjects` tables
- `notifications.py` — `notifications` table
- `analytics.py` — analytics tables
- `raw/` — Local JSON snapshots (gitignored, not source of truth)

### Templates (`templates/`)
- 58 Jinja2 templates (`p_*.html` = page, `_*.html` = partial)
- PDF viewer templates

### Static Assets (`static/`)
- CSS pipeline: 11 modular files in `static/css/pipeline/`
- Self-hosted PDF.js at `static/pdfjs-6.1.200-dist/`
- JS, images

### Developer Tooling (`dev/`)
- `dev/route_parity.py` — Snapshots/verifies all URL rules by static AST parse
- `dev/route_snapshot.json` — Baseline: 150 rules
- `dev/check_doc_links.py` — Validates every relative markdown link
- `dev/bots/` — Internal LLM "company" bots + their reports
- `dev/scripts/` — Ops scripts (campaign export/report, exam-pack drip)

### Documentation (`docs/`)
- `architecture/` — How it's built (ARCHITECTURE.md, CSS_PIPELINE.md)
- `guides/` — How to do X (USER_GUIDE.md, GA4_IMPLEMENTATION.md, etc.)
- `reference/` — Lookups (ROUTES.md, BUGS.md, etc.)
- `product/` — Vision and scope (IDEA.md)
- `history/` — Snapshot records (never edited)

### Configuration
- Environment variables via `.env` and `.env.example`
- Required: `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- Admins: `ADMIN_EMAILS` env var
- Cloudinary: `CLOUDINARY_*` env vars
- Turnstile: `TURNSTILE_SECRET` env var

## Key Routes (Approximate Bands in app.py)
- 500–999: Bootstrap, auth, quota, static
- 1000–1499: Taxonomy APIs (college/branch/subject)
- 1500–1999: Social + view logging
- 2000–2499: Upload & preview
- 2500–2999: Account, profile, SEO landings
- 3000–3499: Document delivery
- 3500–3999: Dashboard & PWA
- 4000–4499: Admin
- 4500–4999: Store Room (labelling queue)
- 5000–5499: Memory Wall
- 5500–5999: Peer chat (SocketIO)

## Recent Reorganization (2026-08)
- Root MD files reduced from 11 to 4 (`README`, `CONTRIBUTING`, `SECURITY`, `CHANGELOG`)
- Everything else moved into `docs/` by purpose
- `README.md` rewritten as project introduction
- `bots/` → `dev/bots/`, `scripts/` → `dev/scripts/`
- Root `.py` files reduced from 23 to 7

## Verification Before Deploy
```bash
python dev/route_parity.py verify    # no route lost
python3 -c "from app import app"     # imports without error
grep -rn "print(" app.py methods/ data/ --include="*.py"  # expect 0 (or test only)
```