# Changelog — AbhiHub

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Security
- **Purged student PII from git history.** `exports/*.csv` (campaign
  exports, send logs) contained real student names and institutional email
  addresses. The data was confined to unpushed commits and never reached
  the remote; the unpushed range was rewritten to remove it entirely.
- `exports/` and `*.csv` are now git-ignored so generated user data cannot
  be committed again.
- `SECURITY.md` — documented that the Supabase **anon** key in
  `static/supabase-config.js` is publishable by design and that **RLS is
  the real security boundary**, so a missing RLS policy is a security bug.
- Turnstile sitekey moved out of 4 templates into `TURNSTILE_SITEKEY`.
- `WTF_CSRF_TIME_LIMIT` set to 3600 (tokens previously never expired).
- `ADMIN_EMAILS` no longer falls back to a hardcoded address.
- `@auth_required` added to `/delete-account`; `/pdf-proxy/<name>` gained
  auth, a Referer check, and rate limiting.
- SocketIO CORS restricted to the app domain (was `*`).

### Added
- `docs/architecture/ARCHITECTURE.md` — layer map and per-file roles,
  including why a directory named `app/` must never exist at the repo root
  (it shadows `app.py` and silently 404s any route it lacks).
- `docs/README.md` — documentation index organised by purpose.
- `dev/route_parity.py` — snapshots and verifies all 150 URL rules via
  static AST parse, so a refactor cannot silently drop an endpoint.
- `dev/check_doc_links.py` — validates every relative markdown link.
- `dev/verify_bugs.py` — checks each `BUGS.md` item against the code.
- `tests/conftest.py` — puts the repo root on `sys.path` and supplies
  dummy env vars so tests run from any directory.
- `.python-version` (3.10), replacing deprecated `runtime.txt`.
- **Governance Engine** (`.ai/`) — Multi-agent governance system with Policy
  Engine, Change Ledger, Project State Manager, Agent Gateway, and
  Governance Engine. Supports AUDIT / MAINTAIN / GOVERN / EMERGENCY modes.
- **Agent manifests** — `coding-agent.yaml`, `research-agent.yaml`,
  `testing-agent.yaml`, `documentation-agent.yaml`, `cleanup-agent.yaml`
  with role-based permissions.
- **CLI** (`governo.py`) — 13 subcommands for audit, onboarding, mode
  switching, request approval, and change log inspection.
- **pytest** added to `requirements.txt` for test infrastructure.

### Changed
- **Documentation reorganised.** Root markdown reduced from 11 files to 4
  (`README`, `CONTRIBUTING`, `SECURITY`, `CHANGELOG`). Everything else
  moved into `docs/` by purpose: `architecture/`, `guides/`, `reference/`,
  `product/`, `history/` (history is snapshot-only and never edited).
- **`README.md` rewritten.** It previously contained a CSS-pipeline
  summary with copy-paste artifacts rather than a project introduction.
  The original content is preserved as
  `docs/architecture/CSS_PIPELINE.md`.
- **`bots/` → `dev/bots/`, `scripts/` → `dev/scripts/`.** Fixed `.env`
  resolution in `dev/bots/config.py` and `ROOT` in `run.py`, which the
  move would otherwise have silently broken.
- Root `.py` files reduced from 23 to 7: 12 one-off migration scripts
  removed, `generate_vapid.py` kept as tooling, 3 test files moved to
  `tests/`.
- `node_modules` untracked (3,141 files); reproducible from
  `package-lock.json`.
- `.gitignore` — added `node_modules/`, `exports/`, `*.csv`, `.wip/`.
- `requirements.txt` — added `pytest` and `pytest-timeout` as dev deps.
- `ROUTES.md` — added 27 previously undocumented routes; relabelled
  ROUTE-104…110 as `[REMOVED]`.
- `.documentation/5_apis.md` — expanded from 6 to 61 documented endpoints.

### Fixed
- **All 97 remaining `print()` calls** in `app.py`, `methods/` and `data/`
  converted to `logging` with inferred levels. Production code now has
  zero `print()`.
- `traceback.print_exc()` calls replaced with `logging.error(...,
  exc_info=True)` so stack traces go to the log rather than stderr.
- Removed every bare `except:` from production code.
- Deduplicated view logging: added `detect_file_type()` and
  `log_document_view()`, collapsing logic that was repeated across
  `/preview`, `/view_pdf` and `/resource/<slug>`.
- Leaderboard rank lookup is O(1) (was a linear scan per request).
- `/dashboard` categorises files in a single pass (was 4 comprehensions).
- Input length validation added to `/api/subjects`, `/api/colleges`,
  `/api/departments`.
- Hardcoded year fallback replaced with `datetime.now().year`.
- Removed orphaned `static/static/` (duplicate of `static/premium/images/`).
- `firebase-auth.json` was tracked in git — untracked via `git rm --cached`.
- Sensitive data files (`admin_users.json`, `push_subscriptions.json`,
  `suspects.json`) were tracked — untracked.
- Missing `.env.example` — created with all required environment variables.
- `agent_gateway.py` — critical-risk operations now require explicit
  approval in GOVERN mode (not auto-executed).
- `project_state.py` — test runner now uses `sys.executable` for proper
  venv python invocation.

---

## [0.8.2] — 2025-07-10

### Added
- MemoryWall / Know Me feature — public memory wall pages with word cloud,
  signature composite, and spam protection.
- File Access History tracking with `public.file_access_history` table.
- Promo / Notification System with in-app announcement cards.
- Referral system with unique referral codes.
- PWA support with service worker and offline fallback.

### Changed
- CSS pipeline consolidated into `static/css/pipeline/` with 11 modular files.
- Route documentation auto-generated via `route-dependency-agent`.

---

## [0.8.1] — 2025-06-26

### Added
- Search architecture with pre-built index and client-side web worker.
- Document ranking and leaderboard system.
- Paper quota system for free-tier users.

### Changed
- Firebase configuration modularized into `firebase_config.py`.

---

## [0.8.0] — 2025-05-06

### Added
- Initial AbhiHub platform with user authentication (Supabase Auth).
- Document upload with Cloudinary storage and AES encryption.
- Push notification system with VAPID keys.
- Admin dashboard with user management and document moderation.
- College/department onboarding system.
