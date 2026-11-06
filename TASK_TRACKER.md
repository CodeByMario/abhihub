# Audit Task Tracker

Statuses: [ ] NOT STARTED · [~] IN PROGRESS · [x] COMPLETED · [!] BLOCKED · [?] NEEDS INVESTIGATION · [-] NOT APPLICABLE

| ID | Phase | Task | Severity | Status | Files | Verification |
|---|---:|---|---|---|---|---|
| DISC-001 | 0 | Inventory repository architecture, entry point, routes, integrations, tests, deployment files, and existing audit records | INFORMATIONAL | [x] | `app.py`, `routes/`, `data/`, `methods/`, `jobs/`, `migrations/`, `tests/`, `Procfile`, `requirements.txt` | Static source inventory completed |
| DISC-002 | 0 | Compare prior runtime-log leads with repository evidence and record unknowns | HIGH | [x] | `app.py`, `scheduled_tasks.py`, `methods/upload_notifier.py`, `routes/app_pages.py`, deployment files | Source evidence recorded; original logs/runtime config unavailable |
| SEC-001 | 1 | Gate development debugger and reloader behind explicit local development settings | HIGH | [~] | `app.py`, `Procfile`, `gunicorn.conf.py` | Conditional debug path confirmed; proposed fix awaiting approval; production runtime not inspected |
| SEC-002 | 1 | Remove signed or credential-bearing URLs from application logs | HIGH | [x] | `routes/api.py`, `routes/webhooks.py`, `methods/supabase_helper.py`, `methods/cloudinary_upload.py`, `push_notifications.py`, `tests/test_sensitive_url_logging.py` | URL and identity redaction tests passed; feature and notification suites passed; py_compile and diff check passed |
| SEC-003 | 1 | Verify secure-cookie setting cannot be disabled in production by environment override | MEDIUM | [?] | `app.py`, deployment environment | Source permits explicit insecure override; runtime environment unavailable |
| SEC-004 | 1 | Validate production SECRET_KEY is required and stable across restarts/instances | MEDIUM | [?] | `app.py`, deployment configuration | Source generates an ephemeral key when missing; deployed configuration unavailable |
| PRIV-001 | 1 | Remove direct PII/content from operational log messages | MEDIUM | [~] | `app.py`, `routes/`, `methods/`, `push_notifications.py` | Targeted log redaction and tests passed; broader exception review tracked in PRIV-002 |
| PRIV-002 | 1 | Review remaining raw exception and provider error logs for PII, signed URLs, and request data | MEDIUM | [~] | `app.py`, `routes/`, `methods/`, `data/`, `observability/` | Direct identity scan leaves only taxonomy IDs; all raw exception logs not yet reviewed |
| PRIV-003 | 1 | Remove provider response bodies and raw AI exception details from prompt/document processing logs | MEDIUM | [x] | `methods/ai_provider.py`, `routes/ai.py`, `routes/api.py`, `tests/test_sensitive_url_logging.py` | Mocked provider-body redaction test and AI feature tests passed; Python compilation passed |
| JOB-001 | 6 | Remove per-web-process scheduler ownership or establish single-owner coordination | HIGH | [?] | `app.py`, `scheduled_tasks.py`, `Procfile` | Import-time scheduling and multi-instance duplication risk confirmed by source; runtime duplication untested |
| JOB-002 | 6 | Review scheduler overlap, misfire, retries, durable recovery, and job idempotency | HIGH | [?] | `scheduled_tasks.py`, job method modules | Missing explicit APScheduler execution policies confirmed; job semantics pending |
| DB-001 | 2 | Inspect deployed Supabase RLS, grants, views, functions, and schema identity mapping | HIGH | [?] | `migrations/`, `scripts/`, `data/db.py`, `methods/supabase_helper.py` | No authoritative deployed policy/schema export available |
| DB-002 | 3 | Review query projection, pagination, repeated access, and index needs | HIGH | [?] | `data/`, `methods/`, `routes/`, `migrations/` | Not started |
| DOC-001 | 4 | Trace upload validation, storage visibility, signed URL lifetime, and document authorization | HIGH | [?] | `routes/api.py`, `routes/library.py`, `routes/app_pages.py`, `methods/storage*`, `methods/cloudinary*` | Not started |
| WAL-001 | 5 | Audit atomic credit and wallet operations for races, replay, and idempotency | HIGH | [?] | `methods/wallet_service.py`, `routes/payments.py`, `routes/webhooks.py`, migrations | Not started |
| JOB-003 | 6 | Validate upload notification time-window, watermark, restart, and duplicate behavior | MEDIUM | [?] | `methods/upload_notifier.py`, `scheduled_tasks.py` | Static inspection pending; durable watermark not established in Phase 0 |
| SRCH-001 | 7 | Trace search authorization, index queue completion/retry, and cache isolation | HIGH | [?] | `methods/search_api.py`, indexer modules, `cache_manager.py`, `routes/api.py` | Not started |
| API-001 | 8 | Review API input validation, auth decorators, CSRF exemptions, and error handling | HIGH | [?] | `routes/`, `app.py` | Not started |
| PWA-001 | 9 | Review service-worker cache contents, logout invalidation, CSP, and DOM sinks | HIGH | [?] | `static/sw.js`, `static/js/service-worker.js`, `static/`, `templates/` | Not started |
| PERF-001 | 10 | Profile and review scaling/query/cache behavior with bounded, representative workloads | MEDIUM | [?] | `cache_manager.py`, `data/`, `methods/`, `routes/` | Not started |
| REG-001 | 11 | Run relevant tests and regression suite after confirmed fixes | HIGH | [ ] | `tests/`, changed files | Phase 1 targeted subset run; full regression pending |
| FINAL-001 | 12 | Complete final security review and deployment readiness report | HIGH | [ ] | All audited modules | Not started |

