# Important Notes — AbhiHub

## PDF Viewer Policy (Non-Negotiable)
- **PDF.js is the canonical viewer** — self-hosted at `static/pdfjs-6.1.200-dist/`
- **Never swap to Adobe Embed SDK as primary.** Adobe Embed SDK may exist only as fallback.
- In-page preview only — no download links, no `Content-Disposition: attachment`
- `/pdf-proxy/` and `/api/view-doc/` set `Content-Disposition: inline`, `X-Download-Options: noopen`, `no-store`, and Referer check

## Authentication Rules
- `@auth_required` — session must exist. API paths get 401 JSON; pages redirect to `/login`
- `@admin_required` — email must be in `ADMIN_EMAILS` (env var, default: empty list)
- **H4 Bug:** Hardcoded admin email fallback in `ADMIN_EMAILS` default at `app.py:420`
  - Old: `os.getenv('ADMIN_EMAILS', 'abhijeetshende4053@gmail.com, codebymario@gmail.com')`
  - Fix: Change default to empty list `os.getenv('ADMIN_EMAILS', '').split(',')`
  - Ensure Heroku env has `ADMIN_EMAILS` set

## Import Hygiene Issues (Pending Consolidation)
- **M3:** Inline `from methods.supabase_helper import X` inside 20+ route functions in `app.py`
  - Fix: Consolidate to single block at top of `app.py`
- **M4:** `init_supabase` imported 9× at module level in `app.py`
  - Fix: Keep one import at top, remove duplicates
- **M5:** `storage`, `Image`, `datetime` imported multiple times at module level
  - Fix: One import per symbol at top of each file
- **M9:** `traceback` imported inside functions in `methods/supabase_helper.py`
  - Fix: Move to top of file
- **M10:** `re` imported inside a function in `app.py:509`
  - Fix: Move to top of `app.py`

## Print() in Production (Phase 2 Target)
- **M6:** 87 `print()` calls across `app.py`, `methods/`, `data/`
  - Fix: Replace every `print()` with appropriate `logging.*` call
- **L8:** `print()` in `methods/supabase_helper.py:1786, 1788, 1789` (file access logging)
  - Fix: Replace with `logging.info()` calls

## CORS Configuration
- **H6:** `Access-Control-Allow-Origin: '*'` on proxy endpoints in `app.py:2188, 3220`
  - Fix: Replace with origin-aware logic mirroring Referer check
- **M15:** `SocketIO(app, cors_allowed_origins="*")` at `app.py:187`
  - Fix: Restrict to specific origin `https://app.abhihub.run.place`

## Quota / Credit System
- Each upload grants `QUOTA_PER_UPLOAD` (19) paper opens; monthly reset
- `_consume_credit()` gates every paper open. Admins bypass.
- `_check_and_log_view()` is the shared helper — use it, don't re-implement (M1 bug)
- **Open Question:** Full credit/earning system (upload → earn credits → view files) is a larger feature, not a bug fix

## Route Verification
- Run `python dev/route_parity.py verify` before every deploy that touched routing
- 148 REST routes + 6 Socket.IO events + 2 error handlers = 156 total registrations
- Routes ROUTE-104 through ROUTE-110 are [REMOVED] — tag or remove from ROUTES.md

## CORS vs flask-cors Conflict (Phase 2 Target)
- **M8:** Manual CORS setup alongside `flask-cors` in `cors.py`
  - Two CORS mechanisms running in parallel — may conflict or double-set headers
  - `flask-cors` library already installed — handles edge cases better
  - Audit `cors.py` against `flask-cors`; delete or consolidate

## Fuzzy Search Migration (Future Project)
- **M7:** Custom fuzzy search (~128 lines in `app.py:43-170`)
  - `rapidfuzz` already in `requirements.txt`
  - Custom implementation doesn't handle edge cases as well as library would
  - **Decision:** Leave as-is, add `# TODO: migrate to rapidfuzz/Supabase FTS` comment
  - Don't attempt migration as part of this cleanup

## Hardcoded Date Fallbacks (Phase 2 Target)
- **M11:** Hardcoded date strings as fallback (e.g. `'2026-05'`)
  - When code falls back to hardcoded date, it becomes stale the moment current month changes
  - Fix: Replace with `datetime.now().strftime('%Y-%m')`
  - Example: `default_month = datetime.now().strftime('%Y-%m')`

## Input Length Validation (Phase 2 Target)
- **M12:** No input length validation on `/api/subjects`, `/api/colleges`, `/api/departments`
  - Malicious client can send 10MB string as name
  - Fix: Add length guard at top of each route (max 200 characters)

## Rank Lookup Optimization (Phase 2 Target)
- **M13:** Linear O(N) search for user's rank in leaderboard at `app.py:1930`
  - Code loops through entire rank list per request — O(N) per request
  - Fix: Convert rank list to dict keyed by user ID for O(1) lookup

## Dashboard File Categorization (Phase 2 Target)
- **M14:** 4 separate list comprehensions over `files` in `/dashboard` at `app.py:1880`
  - Iterates over entire files list 4 times (once per content type)
  - Fix: Single-pass categorization building notes, papers, others lists once

## SocketIO Security (Phase 2 Target)
- **M15:** `SocketIO(app, cors_allowed_origins="*")` — WebSocket open to all origins
  - Any website can open WebSocket connection to AbhiHub Socket.IO server
  - Fix: Replace `"*"` with specific origin `https://app.abhihub.run.place`

## Dead Code Cleanup (Phase 3 Target)
- **L1:** ~180KB dead code files cluttering repo
  - Files: `old_store_room.js` (136KB), migration scripts, test stubs
  - Fix: Move to `/trash` directory first, then delete after verification

## Turnstile Sitekey (Phase 3 Target)
- **L4:** Cloudflare Turnstile sitekey hardcoded in `contact.html:206`, `forgot_password.html:165`
  - Fix: Move to single template include or config variable `TURNSTILE_SITEKEY` from env var

## CSS Documentation Location (Phase 3 Target)
- **L7:** CSS conflict resolution doc in `templates/_CSS_CONFLICTS_RESOLVED.md`
  - Templates folder semantically wrong for docs
  - Fix: Move to `docs/CSS_CONFLICTS_RESOLVED.md` or merge into `docs/ARCHITECTURE.md`

## Supabase Anon Key Documentation (Phase 3 Target)
- **L2:** Supabase anonymous key in `static/supabase-config.js:8`
  - Key is publishable by design (client-side Supabase usage with RLS)
  - Document in `SECURITY.md` that anon key is intentionally public but scoped by RLS

## Test File Hardcoded Secret (Phase 3 Target)
- **L3:** `test_dashboard_auth.py:64, 109` has hardcoded Flask secret key
  - Fix: Replace with `os.getenv('FLASK_SECRET_KEY', 'test-secret')` with comment "Test only"

## Redundant `|tojson|safe` (Phase 3 Target)
- **L6:** `|tojson|safe` in `p_store_room.html:82`, `_card_file.html:8`
  - `|tojson` already produces safe output; `|safe` is redundant
  - Fix: Remove `|safe` from both chains, keep only `|tojson`

## Inline Helper Imports (Phase 2 Target — M3)
- `app.py` imports from `methods.supabase_helper` inside ~91 route bodies
  - Rather than once at the top
  - **Decision:** Leave as-is for now (stylistic, not load-bearing)
  - Revisit only if `app.py` is split into blueprints

## CSS Pipeline Standardization
- Central CSS pipeline under `static/css/pipeline/`
- Entry points: `pipeline.css`, `pipeline-master.css`
- Modules: variables, reset, base, components, layout, utilities, pages, responsive, animations, app-shell, navbar, notification-bell, feature-tour, profile-nudge, promo, pwa-install
- Feature bundles: `upload-page.css`, `dashboard-home.css`, `support-page.css`
- Goal: extract inline `<style>` blocks and repeated `style=""` attributes into reusable classes

## M3 Deferred Decision (Investigated and Dismissed)
- Lazy imports in route functions are not load-bearing; they are stylistic
- Hoisting 59 distinct symbols into one module-level import touches nearly every route
- For zero functional gain and real regression risk — leave as-is
- Tracked, not ignored; revisit only if splitting into blueprints