# AbhiHub Technical Audit Master Record

## Project overview

AbhiHub is a Flask application with HTML/CSS/JavaScript pages and PWA assets. Its source includes Supabase/PostgreSQL data access, Firebase and Cloudinary storage integrations, payments, push notifications, document viewing/upload, AI/search features, Socket.IO chat, an APScheduler background scheduler, and an application cache with optional Redis.

## Discovered architecture (Phase 0)

- **Startup / WSGI:** `app.py` constructs the Flask app and initializes security settings, push API integration, and a background scheduler at import time. `Procfile` runs `gunicorn` with `geventwebsocket`, one worker, and `app:app`. `gunicorn.conf.py` contains compatibility setup only.
- **Routing:** `routes/__init__.py` registers blueprints for site, auth, library, app pages, API, admin, webhooks, SEO, storage room, payments, AI, channels, and observability. `app.py` also retains legacy routes and Socket.IO handlers.
- **Database/auth:** Supabase client setup exists in both `app.py` (lazy proxy) and `data/db.py` / `methods/supabase_helper.py` (shared helper). The app uses Supabase auth and a custom session/auth layer. Schema is `abhihub` in client initialization.
- **Storage/documents:** Document routes/data helpers use Firebase and Cloudinary, with document code in `routes/api.py`, `routes/library.py`, `routes/app_pages.py`, `data/documents.py`, `methods/storage.py`, `methods/storage_providers.py`, and Cloudinary helpers.
- **Background jobs:** `scheduled_tasks.py` registers upload notifications, search indexing, analytics, score recalculation, wallet reconciliation, and model catalog sync. `methods/upload_notifier.py` performs a time-window query.
- **Cache/search:** `cache_manager.py` implements L1 and optional Redis L2. Search code spans `methods/search_api.py`, indexing methods, API routes, and `static/premium/js/search-worker.js`.
- **Frontend/PWA:** Templates live in `templates/`; browser code/styles in `static/`. Service-worker candidates include `static/sw.js` and `static/js/service-worker.js`.
- **Database change evidence:** `migrations/` and `scripts/` contain SQL changes and operational checks, including some RLS-related scripts. This checkout does not provide a single authoritative deployed schema/policy export.
- **Tests:** A substantial pytest suite exists in `tests/`, plus script-based checks in `scripts/`. Phase 0 did not run tests.

## Scope and operating rules

Proceed phase-by-phase using the user-provided 0–12 plan. Phase 0 is discovery only; no application code has been changed. Preserve existing worktree changes. Do not read, print, or commit secrets. No production data changes or destructive migrations without explicit approval. Do not report a check as passed unless it ran successfully.

## Phase plan

| Phase | Scope | Status |
|---|---|---|
| 0 | Project discovery and architecture mapping | [x] Discovery recorded; remaining source inventory to refine in later phases |
| 1 | Critical security and configuration | [~] |
| 2 | Authentication, authorization and Supabase RLS | [ ] |
| 3 | Database correctness and query optimization | [ ] |
| 4 | Document storage, uploads and access control | [ ] |
| 5 | Wallet, credits and quota integrity | [ ] |
| 6 | Scheduler and background-worker reliability | [ ] |
| 7 | Search, indexing and caching | [ ] |
| 8 | Flask backend functionality and API validation | [ ] |
| 9 | Frontend, JavaScript and PWA security | [ ] |
| 10 | Performance and scalability | [ ] |
| 11 | Integration and regression testing | [ ] |
| 12 | Final security review and deployment readiness | [ ] |

## Initial risk assessment

- **High (confirmed code-level concern):** Scheduler is started while importing the Flask app, creating one scheduler per process/instance. Current Procfile uses one Gunicorn worker, but multiple instances can still duplicate jobs; APScheduler jobs do not set explicit `max_instances`, `coalesce`, or `misfire_grace_time` here.
- **Medium (confirmed, partially remediated):** Upload, notification, profile, payment, document-view, and storage logs included user identifiers, emails, filenames, viewer names, or quota details. Direct values were removed from identified messages; broad raw-exception review remains pending.
- **Medium (confirmed conditional exposure):** Direct `python app.py` startup sets debug to true whenever `FLASK_ENV` is not exactly `production`, binds `0.0.0.0`, and uses `socketio.run`; this can expose the Werkzeug debugger if this development entry point is used in a reachable environment. Procfile itself uses Gunicorn and no debug option. Actual prior debugger exposure is not proven without the original logs/runtime config.
- **Low (confirmed technical debt):** `datetime.utcnow()` appears in multiple runtime modules and is naive; use timezone-aware UTC consistently when those code paths are reviewed.
- **Unresolved:** Supabase RLS/policy correctness, secret-key exposure in actual runtime environment, direct storage access controls, wallet transaction safety, Redis availability, notification durability, and real production server settings require deeper source review and/or deployment schema/runtime evidence.

## Critical findings

No critical finding confirmed in Phase 0. Findings and investigation leads are tracked in `FINDINGS.md`.

## Important architectural decisions

- Keep Phase 0 read-only with respect to application code.
- Root audit records are new because no equivalents were found at the workspace root.
- Use exact evidence and severity; runtime log observations remain leads until corroborated.
- Treat `dist/production-artifact/` as generated output unless source-of-truth review shows otherwise; avoid duplicated audit changes there.

## Current working phase

Phase 1 — Critical security and configuration. URL-bearing log messages were remediated and verified; debug startup approval and broader PII logging review remain pending.

## Remaining risks / missing evidence

- Original runtime logs were not present in the project inventory, so debugger/PIN exposure and exact PII in prior logs cannot be independently validated.
- No authoritative deployed PostgreSQL schema, grants, RLS policies, or Supabase RPC definitions were identified in this discovery pass.
- Deployment platform settings, environment values, replica count, and Redis configuration are not available from repository files alone.
- Existing worktree has 35 changed/untracked paths at discovery time; those changes predate this audit and must be preserved.

## Phase 1 update (2026-11-06 to 2026-11-07)

- Confirmed direct startup in `app.py` enables debug unless `FLASK_ENV` is exactly `production`; `Procfile` instead uses Gunicorn. A safe-default patch is proposed but awaits approval because it changes direct-startup behavior.
- Confirmed several logs included full file URLs or raw exceptions that can repeat signed URLs. Removed those values and verified with regression tests.
- Confirmed representative logs include email addresses, user IDs, document titles, and academic/upload fields. Broader redaction remains in progress.
- Confirmed production configuration can set `SESSION_COOKIE_SECURE=false` and missing `SECRET_KEY` falls back to a random per-process key. Runtime configuration is unknown.
- Focused test subset: 80 passed, 18 subtests passed; full regression remains pending. Existing dependency deprecation warnings remain.
- Additional direct PII log messages across account, payment, document access, and push workflows were changed to event/status-only diagnostics. Targeted scan now leaves only academic taxonomy IDs in a hierarchy-mismatch message; raw exception logs remain under review.
- AI provider response bodies and raw exception strings were also identified in prompt/document processing paths and removed from logs. Provider failures now log bounded status/model/error-type context. A dedicated mocked-provider test and the AI feature tests passed; a broader combined AI/security suite was interrupted and is inconclusive.
- Final `git diff --check` still reports pre-existing trailing whitespace in `templates/p_upload.html` and `templates/resource.html`; these unrelated dirty template changes were not modified. Python compilation passed for the touched AI modules and redaction tests.
- The requested hostname/API check confirmed mismatched CORS configuration: beta is a valid host but not a file CORS origin; Socket.IO is wildcard-enabled whenever `FLASK_ENV` is not exactly `production`; the API origin middleware logs unknown origins but allows them. Rate controls are feature-specific, per-process memory counters; several use raw `X-Forwarded-For`, with proxy normalization not found in source. These are tracked as API-002/API-003 pending deployment and supported-host decisions.
- Added API-004: a common Flask request hook now caps authenticated API calls at 300/user/60 seconds and anonymous calls at 60/socket-peer/60 seconds, with environment overrides, 429/Retry-After, bounded in-process state, and exclusions for OPTIONS, health, and provider webhooks. Six targeted tests passed. This is a single-process guard; shared atomic storage remains needed for multi-instance enforcement.
- Continued PRIV-002 through authentication, payment, wallet, webhook, and Cloudinary error paths. Raw exception details were removed from reviewed logs; the Razorpay order error response is now generic. The sentinel regression test passed. This narrows but does not complete the broad exception inventory.
- Added PRIV-005 after tracing wallet helper returns into route responses. Wallet and document pricing/coupon error responses now use generic messages. The wider API/admin/Supabase helper exception-return inventory remains open.
- Expanded the common limiter to include unprefixed auth/file utility/PDF proxy endpoints. The combined error-redaction and middleware suite passed 10 tests. DOC-002 and DOC-003 were then fixed: signed URL generation now uses the document viewer access policy, and file verification requires admin authentication. Three focused route tests passed; deployed storage/RLS and downstream publication behavior remain unverified.
- The old `abhijeetupdate.html` template still posts a path to `/get-file-url`, but no rendering route was found and `/abhijeetupdate` redirects to `/admin`. If the template is restored, its request must be migrated to `doc_id`.
- User clarified that document files must route through `/resources/<...>`. Added DOC-004: legacy PDF and generic file proxies now redirect to resource pages; raw storage paths and URLs are not served. Existing frontend callers were traced.
- Continued the document flow trace and found DOC-005: full authorized documents now receive short-lived provider URLs for direct PDF.js/image loading; paid previews stay on the page-one viewer. New Cloudinary uploads are authenticated assets. Three focused delivery/upload tests passed; legacy Cloudinary assets remain public until provider migration.
- Found DOC-006: direct resource and viewer routes fetched by document ID without enforcing publication status, even though public catalogs filter to approved. These routes now return 404 for unpublished documents unless the caller is the uploader or privileged staff. Eight focused document-route tests pass; deployed RLS remains unverified.
- User clarified full-file delivery should go directly from storage to PDF.js. Entitled full documents now receive 10-minute provider URLs; paid previews remain server-side and page-one limited. New Cloudinary uploads are authenticated rather than public. Three focused tests passed. Existing Cloudinary assets are still public until a provider-side migration; provider CORS and Firebase rules are unknown.
- UI-001/SEC-006: the custom context menu is shared across public/account and admin layouts; the personalized watermark is confined to resource PDF/image viewers. Misleading extension/DevTools/screenshot interception was removed. These are deterrents only; server-side authorization remains required. PRIV-006 removes full student profile values from logs.
- DOC-008: resource documents now receive explicit PDF/image/unsupported classifications. PDF.js handles PDFs, the existing image viewer handles supported raster formats, locked paid images do not request the file, unsupported formats show a safe fallback, and the personalized watermark is confined to viewer containers. Focused viewer tests passed 4/4; full resource suite is 7 passed/3 failed on external catalog-dependent assertions.
- DOC-008 follow-up: supported images now use locally bundled Viewer.js 1.15.2 for modal zoom/move/fullscreen; PDF.js remains the PDF viewer. Viewer controls and the user-specific watermark were checked with focused tests.
- DOC-009: locked paid images now receive a server-transformed low-resolution preview; the top 20% stays clear and the lower 80% is blurred before bytes reach the browser. Full image requests remain entitlement-gated. Thirteen focused access/viewer tests passed.

- PRIV-005 follow-up: removed raw exception bodies and exception text from reviewed admin APIs and health responses. New sentinel test confirms the admin payment-transactions endpoint does not leak database/provider exception text. Remaining API and Supabase helper paths are still under review.
