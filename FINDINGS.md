# Findings Register

Phase 0 discovery is complete. Phase 1 is underway. SEC-002 is fixed and verified; direct PII logging is partially remediated under PRIV-001.

## PRIV-003 — AI provider failures logged response and exception content

**Severity:** MEDIUM  
**Status:** Fixed and targeted verification passed  
**Location:** `methods/ai_provider.py`, `OpenRouterAdapter.complete` and Ollama request handling; `routes/ai.py`, AI request/error handlers; `routes/api.py`, `api_extract_upload_metadata` AI extraction error handling.  
**Problem:** Provider failure paths logged response bodies and raw exception text while processing user prompts and document content. The provider may echo request data or return sensitive diagnostic details.  
**Root cause:** Error logging treated provider response and exception strings as safe diagnostic material.  
**Impact:** Prompt/document content or provider details could be retained in application logs. No live leak was asserted; this is confirmed from source behavior.  
**Evidence:** Before the change, OpenRouter failure handling logged a response-body prefix and exception text, and related AI route handlers logged raw exceptions. A mocked HTTP failure test injects sentinel prompt/body/key values and asserts they do not appear in captured logs.  
**Recommended correction:** Log bounded metadata such as status, model, and exception class; keep user-facing provider errors generic.  
**Implementation:** Removed provider response text and raw exception values from the reviewed AI paths. Replaced provider error detail with a generic message and added a redaction regression test. No successful AI request behavior was intended to change.  
**Verification:** New mocked-provider redaction test passed (1 test); `tests/test_feature_ai.py` passed (3 tests); `py_compile` passed for touched modules. A combined AI/security test run was interrupted without a result and is inconclusive. `git diff --check` reports existing trailing whitespace in dirty templates, outside this finding.  
**Remaining risk:** Broader raw-exception inventory remains in progress under PRIV-002; full regression has not been run.

## API-002 — Beta origin is not consistently supported by API/file CORS

**Severity:** MEDIUM functional/configuration issue; CORS is not an authorization boundary
**Status:** Confirmed source-level behavior; exact user-facing impact depends on how beta calls APIs and serves documents
**Location:** `app.py`, `VALID_DOMAINS` around line 319, `enhance_resource_page_security` around lines 374–384, Socket.IO setup around lines 521–525, and `handle_canonical_and_subdomain_routing` around lines 463–485; `routes/api.py`, `_ALLOWED_CORS_ORIGINS` and `_get_safe_cors_origin` around lines 1884–1898.
**Problem:** `beta.abhihub.edu.eu.org` is accepted by host routing and avoids canonical redirect, but is absent from the file/API CORS origin set. File responses from beta requests can therefore return `Access-Control-Allow-Origin: https://www.abhihub.edu.eu.org`, which browsers reject for a beta page. Resource responses set only `https://{BASE_DOMAIN}` (default www). Socket.IO defaults to only www when `FLASK_ENV=production`; when the variable is unset or anything other than exact `production`, the code sets `cors_allowed_origins='*'`. The generic API origin checker logs unknown origins and allows the request; it does not enforce an origin policy.
**Root cause:** Host allowlisting, CORS, canonical redirect, and Socket.IO origin configuration use separate allowlists/defaults.
**Impact:** Browser requests from beta may fail to read proxied PDFs/files or resource responses. Conversely, wildcard Socket.IO origin behavior may permit cross-origin socket handshakes in configurations that are not exactly labeled production; authentication and event authorization still need separate assessment.
**Evidence:** `VALID_DOMAINS` contains beta; `_ALLOWED_CORS_ORIGINS` does not. `_get_safe_cors_origin` falls back to the www origin. Socket.IO uses a wildcard whenever `os.getenv('FLASK_ENV') != 'production'`. `validate_api_domain` explicitly logs but allows invalid API origins.
**Recommended correction:** Define one explicit allowlist of exact HTTPS origins (include beta if supported) and use it consistently for file/resource CORS and Socket.IO. Keep credentials behavior explicit; do not use a broad wildcard with cookies. Confirm whether beta uses same-origin API calls or needs cross-origin credentialed access before changing cookie domain or CORS credentials. Add host matrix tests. Treat CORS only as browser read policy; enforce user/document authorization server-side.
**Implementation:** Not implemented pending confirmation of intended beta and other subdomain behavior.
**Verification:** Static source inspection only; no browser/API host matrix run.
**Remaining risk:** User's “etc” does not define whether every subdomain is trusted. Runtime `BASE_DOMAIN`, `FLASK_ENV`, reverse-proxy routing, and session sharing behavior are unavailable. No `SESSION_COOKIE_DOMAIN` setting is present in the inspected app configuration, so sessions are host-only by default.

## API-003 — Rate limiting is incomplete and process-local

**Severity:** MEDIUM
**Status:** Confirmed source-level reliability gap; abuse impact depends on deployment and endpoint workload
**Location:** `methods/ai_safety.py`, `check_rate_limit` around lines 138–152; `routes/ai.py`, AI key/assistant/tool routes around lines 256–282, 395–425, and 867–879; `methods/analytics_tracker.py`, analytics limiter around lines 110–135; IP derivation in `routes/ai.py` and multiple `routes/api.py` / `routes/auth.py` routes.
**Problem:** Feature-level AI and analytics protections use per-process in-memory dictionaries, so those limits do not coordinate across Gunicorn workers or instances and reset on restart. Several other existing endpoints derive the client address directly from `X-Forwarded-For`, which is client-spoofable unless the deployment proxy overwrites/normalizes it. The new API-004 common limiter uses `request.remote_addr` for anonymous requests and avoids trusting the raw forwarding header, but anonymous clients may share a proxy peer address.
**Root cause:** Existing feature limiters use local stores and the app has no configured trusted-proxy boundary or shared atomic limiter backend.
**Impact:** Existing feature-level limits can be bypassed by worker/instance spread or restarts; other route-specific IP controls may be spoofable. Common per-user limiting now applies within each process; anonymous requests behind a shared proxy may contend for one bucket.
**Evidence:** `check_rate_limit` stores timestamps in module-global `_RATE_LIMIT_STORE`; analytics creates a separate local dict. `Procfile` uses one Gunicorn worker, but deployment replica count is not known. No `ProxyFix`/trusted proxy setup was found. `cache_manager.py` optionally imports redis-py, while neither requirements file declares Redis; no runtime connection status was inspected.
**Recommended correction:** Use Redis or an equivalent atomic shared limiter for multi-instance deployments; configure trusted proxy hops at the WSGI boundary and derive client IP from normalized request data. Add tests for multi-instance semantics. Do not rate-limit webhooks or trusted internal traffic without provider-specific allowances.
**Implementation:** Partially addressed by API-004's common process-local API guard; distributed shared storage and proxy normalization remain unimplemented pending deployment evidence.
**Verification:** API-004 middleware/helper tests passed (6); static review confirms no distributed rate-limit backend is configured.
**Remaining risk:** Current deployment replica count, Redis availability, proxy header behavior, and endpoint traffic profile are unknown.

## API-004 — API requests lacked a common per-user request limit

**Severity:** MEDIUM
**Status:** Fixed and verified for one process
**Location:** `app.py`, `enforce_api_rate_limit` around lines 420–467; `methods/api_rate_limiter.py`; tests in `tests/test_api_rate_limiter.py` and `tests/test_api_rate_limit_middleware.py`.
**Problem:** Before this change, rate limits applied only to selected features and were not shared across API route groups.
**Root cause:** No common request hook applied a principal-level quota before route/database work.
**Impact:** An authenticated account could issue high-volume requests across separate API endpoints without a shared application-level cap.
**Evidence:** Added middleware tests demonstrate per-user isolation, 429 responses with `Retry-After`, anonymous IP fallback that ignores untrusted `X-Forwarded-For`, and webhook/preflight exemptions.
**Recommended correction:** Keep endpoint-specific tighter limits for expensive operations, tune the global quotas from production traffic, and use an atomic shared backend when deploying multiple app instances.
**Implementation:** Added configurable defaults of 300 requests per user per 60 seconds and 60 requests per socket peer for anonymous API traffic. The hook covers `/api/`, `/admin/api/`, `/store-room/api/`, unprefixed `/auth`, file utility routes, and `/pdf-proxy/`; skips OPTIONS, health checks, and provider webhooks; and returns JSON 429 with `Retry-After`. The limiter uses a bounded, locked process-local sliding-window store and hashes principal keys in memory.
**Verification:** Helper and middleware/error-redaction suites: 10 passed. Includes per-user isolation, `429`/`Retry-After`, anonymous forwarding-header resistance, exclusions, window expiry, and the unprefixed `/auth` route. `py_compile` passed.
**Remaining risk:** Limits are per process and reset on restart; multiple deployment instances do not share counters. Anonymous callers behind a proxy may share the proxy's socket-peer bucket until trusted proxy handling is configured. Per-user authenticated calls remain correctly separated across those IPs.

## PRIV-004 — Payment provider exception detail was returned to the caller

**Severity:** MEDIUM
**Status:** Fixed and verified
**Location:** `routes/payments.py`, `initiate_payment` order-creation exception handler around lines 268–272; regression test `tests/test_sensitive_error_logging.py`.
**Problem:** The Razorpay order-creation exception was logged verbatim and its string was embedded in the JSON error response.
**Root cause:** Provider exceptions were treated as safe client-facing diagnostic messages.
**Impact:** Provider response details or internal service information could be disclosed to an authenticated caller and retained in logs.
**Evidence:** The regression test injects a sentinel provider exception and asserts that it appears neither in the response nor captured logs.
**Recommended correction:** Return a generic service error and log only the exception class; correlate detailed diagnostics through a safe request ID if needed.
**Implementation:** The order endpoint now logs the exception type and returns a generic payment-provider-unavailable message, preserving HTTP 500 behavior. Reviewed payment/auth/wallet/webhook/Cloudinary exception log messages were also reduced to exception type (PRIV-002 remains open for other call sites).
**Verification:** `tests/test_sensitive_error_logging.py`: 1 passed.
**Remaining risk:** Raw exceptions returned by other API routes and Supabase helper results remain under review in PRIV-005.

## PRIV-005 — Wallet and data-access exceptions were returned in API error bodies

**Severity:** MEDIUM
**Status:** Partially fixed; broader inventory remains in progress
**Location:** `methods/wallet_service.py`, exception returns in `credit_creator_for_purchase`, `get_creator_wallet`, `request_withdrawal`, `get_all_payout_requests`, `process_payout_request`, and `admin_adjust_creator_wallet`; `routes/payments.py`, document pricing/coupon handlers around lines 625–671; reviewed document/history/file-list/chat/upload/dashboard handlers in `routes/api.py`; additional direct exception responses remain in `routes/api.py`, `routes/admin.py`, and `methods/supabase_helper.py`.
**Problem:** Several data-layer exception strings were returned directly to API clients. Wallet methods exposed these values in their result dictionaries/tuples, which routes and the payment engine serialize or log. Document pricing and coupon endpoints returned raw database exceptions in JSON.
**Root cause:** Helper and route error contracts reused exception text as the user-facing message.
**Impact:** Callers could see database/provider details, schema names, query failures, or identifiers that should remain in server-side diagnostics.
**Evidence:** Before remediation, wallet functions returned `str(e)` and payment pricing/coupon handlers returned it in JSON. Tests inject private sentinel exception strings and assert they are absent from API results and logs. Static scan also found direct raw exception responses in other route/helper families.
**Recommended correction:** Preserve response shape and status codes while returning stable generic messages; log exception class and safe correlation context. Trace helper result propagation before changing each contract. Keep expected validation/duplicate outcomes as explicit typed business errors.
**Implementation:** Wallet exception return values now use generic messages; document pricing/coupon, file verification/signing/metadata, history/file-list, peer/chat, upload, dashboard, and reviewed admin handlers return stable generic responses and avoid raw exception logs. More API/Supabase helper return paths remain under review.
**Verification:** `tests/test_sensitive_error_logging.py` and `tests/test_api_rate_limit_middleware.py`: 10 passed combined. Sentinel tests verify provider, wallet, pricing, coupon, file-signing, and file-verification response/log redaction.
**Remaining risk:** Direct exception responses in other `routes/api.py` handlers and many `methods/supabase_helper.py` result objects remain. Some may contain expected validation details; each requires caller and response-contract review. Current error-redaction suite has two file-route tests whose setup is rejected by current 400/401 guards before reaching mocked provider errors.

## DOC-002 — Signed storage URL can be generated without document access validation

**Severity:** HIGH
**Status:** Fixed and verified at route level
**Location:** `routes/api.py`, `get_file_url` around lines 2751–2772.
**Problem:** Previously the endpoint required any authenticated session and signed a caller-supplied Firebase object path without mapping it to a document or checking entitlement.
**Root cause:** Authorization was based on authentication and path syntax rather than document access policy.
**Impact:** A logged-in user who knew or guessed another private object path could obtain a valid signed URL.
**Evidence:** The route now rejects requests without `doc_id` and delegates to `authorize_document_access`, which loads the authoritative document and applies `has_document_access`. `tests/test_legacy_document_access.py` confirms path-only input is rejected, denial status is propagated, and an allowed response returns the authorized URL.
**Recommended correction:** Keep document-ID based authorization through the shared viewer policy; validate the legacy caller if it is restored.
**Implementation:** `/get-file-url` no longer signs a caller-provided path. It requires a document ID, calls `authorize_document_access`, and returns its signed URL only on status 200.
**Verification:** `python -m pytest -q tests/test_legacy_document_access.py`: 3 passed, including both URL-route cases; `py_compile` passed for the route and test module.
**Remaining risk:** Live Firebase/Cloudinary signing, bucket visibility, and real cross-user entitlement behavior were not exercised. The legacy template posts `file_path`; no rendering route was found, so that caller would need updating if reactivated.

## DOC-003 — File verification can insert approved records without authentication

**Severity:** HIGH
**Status:** Fixed and verified at route level
**Location:** `routes/api.py`, `verify_file` around lines 2712–2751.
**Problem:** Previously the route had no authentication or admin decorator; it could register an existing storage path with `status='approved'`.
**Root cause:** The legacy verification operation did not establish caller identity or privilege.
**Impact:** An unauthenticated caller could create approved document records, with possible downstream publication consequences.
**Evidence:** `tests/test_legacy_document_access.py` confirms anonymous requests receive 401 and student requests receive 403 before storage access; an admin request reaches the operation successfully.
**Recommended correction:** Keep this legacy registration utility admin-only and preserve CSRF protection. Separately verify approved-row publication semantics and storage policy.
**Implementation:** Added `@auth_required` and `@admin_required` to `/verify-file`; failures now return a generic error while logging only the exception type.
**Verification:** `python -m pytest -q tests/test_legacy_document_access.py`: 3 passed, covering anonymous, non-admin, and admin behavior. `py_compile` passed for the route and test module.
**Remaining risk:** Tests mock Firebase and Supabase; they do not validate deployed RLS, real bucket policy, review workflow, or whether approved rows become publicly discoverable.

## DOC-004 — Legacy PDF proxy served arbitrary storage paths outside resource pages

**Severity:** HIGH
**Status:** Fixed and verified at route level
**Location:** `routes/api.py`, `pdf_proxy` around line 2654 and `proxy_file` around line 2038; callers in `static/premium/js/store_room.js` and `static/js/carousel-personalization.js`.
**Problem:** The routes accepted a supplied storage path or external URL and served/redirected it directly. The referrer check was not an authorization control. This bypassed document lookup and `/resources/<slug-or-id>` routing.
**Root cause:** A legacy compatibility proxy treated a supplied path/URL as the resource identity rather than requiring a registered document.
**Impact:** A user could retrieve a known private object path without the document-level ownership, purchase, or preview checks used by the resource viewer; allowed-host URLs could also be redirected outside the canonical route.
**Evidence:** The prior PDF handler called `storage.bucket().blob(pdf_name).download_as_bytes()` for arbitrary input and redirected allowed-host URLs; `/api/proxy-file` proxied a caller-provided allowed-host URL. Regression tests confirm an unregistered path returns 404, a registered exact `file_url` redirects to `/resources/<document-id>`, and the URL proxy now requires a document ID and redirects to the resource page.
**Recommended correction:** Keep this endpoint as a compatibility redirect only; resolve the exact stored document path, then send clients through the canonical resource route and its viewer authorization.
**Implementation:** Removed direct Firebase download, external URL redirect, and raw URL proxying. `/pdf-proxy` looks up an exact `documents.file_url` match; `/api/proxy-file` requires a valid document ID. Both redirect to `/resources/<id>`.
**Verification:** `tests/test_legacy_document_access.py`: 8 passed; focused `test_proxy_file_requires_document_id_instead_of_signed_url`: 1 passed. Python compilation and scoped `git diff --check` passed. Existing PDF-proxy callers remain supported when their URL exactly matches a document record.
**Remaining risk:** The lookup was mocked in tests; live Supabase query semantics and access policies on the resource page were not tested. Direct provider URLs already stored in public Cloudinary/Firebase configurations may remain usable outside AbhiHub if known; deployed provider ACLs were not inspected.

## DOC-005 — Document delivery must authorize before issuing provider URLs

**Severity:** HIGH
**Status:** Fixed and verified at route level
**Location:** `routes/api.py`, `authorize_document_access` around lines 2090–2218; reachable from `/api/documents/<doc_id>/authorize` and `/api/view-doc/<doc_id>/authorize`.
**Problem:** File authorization must happen before the browser receives a storage URL. A full signed URL cannot be issued to a paid preview because it permits retrieval of the full source instead of only the preview pages.
**Root cause:** Earlier versions either returned a full provider URL for previews or proxied all authorized file bytes through Flask.
**Impact:** Direct provider delivery for full authorized documents reduces app-server bandwidth, but a recipient can use a signed URL until expiry. Paid-preview users must not receive the full-file URL.
**Evidence:** The viewer route extracts only page one for unauthorized paid previews. Tests verify entitled Firebase files receive a short-lived provider URL while preview authorization stays on the local `preview=1` route.
**Recommended correction:** Return short-lived provider URLs only after visibility and entitlement checks. Keep paid previews on the restricted server viewer. Hide casual download/print controls while treating browser delivery as capturable.
**Implementation:** Authorized full documents now return 10-minute Firebase, Cloudinary, or Supabase URLs where signing is supported, so PDF.js or the image element fetches bytes directly from the provider. Paid previews still return `/api/view-doc/<id>/file?preview=1`. PDF.js download and print controls are hidden by the existing `download=false` guard. New Cloudinary uploads use authenticated delivery. Resource HTML and authorization API responses are no-store.
**Verification:** Three focused tests passed: direct Firebase URL issuance with 10-minute expiry, paid-preview confinement, and authenticated Cloudinary upload parameters. Python compilation passed.
**Remaining risk:** Signed URLs remain usable during their lifetime and users can save/capture bytes already delivered to their browser. Legacy Cloudinary objects remain public until migrated at the provider. Firebase bucket rules, legacy asset migration state, Supabase storage policies, and provider CORS for beta/other AbhiHub domains were unavailable. Unsupported or failed signing falls back to the server viewer.

## DOC-006 — Direct resource IDs bypassed publication status filters

**Severity:** HIGH
**Status:** Fixed and verified at route level
**Location:** `routes/library.py`, `resource_landing` around lines 463–510; `routes/api.py`, `authorize_document_access` and `view_doc` around lines 2068–2300.
**Problem:** Catalog/listing queries generally filter to `status='approved'`, but direct resource and viewer routes loaded documents by ID without checking publication status. For free documents, `has_document_access` permits access regardless of approval state, so a known pending document ID could bypass publication filters.
**Root cause:** Authorization and publication state were treated as separate concerns, but direct ID routes had no publication-state gate.
**Impact:** Pending or otherwise unpublished uploads could be viewed by users other than the uploader or staff if they learned the document ID.
**Evidence:** Source inspection found approved-only list/sitemap queries and unfiltered `get_document_by_id_rich` lookups in resource/view routes. A regression test confirms pending document IDs return 404 from both the authorization endpoint and file viewer for a non-owner, even when `has_document_access` is mocked true.
**Recommended correction:** Allow public access only to approved records; allow unpublished records only to their uploader and privileged staff. Apply the gate at the resource page and every direct file/authorization route.
**Implementation:** Added a shared route visibility check in `routes/api.py` for authorization and file streaming, and an equivalent gate in `routes/library.py` before rendering a resource page. Approved records remain public; non-approved records require uploader or `is_admin_user` status.
**Verification:** `tests/test_legacy_document_access.py`: 8 passed; `py_compile` passed for both route modules and test file.
**Remaining risk:** Tests use mocked document records and sessions. Deployed Supabase RLS and any alternate direct routes or public provider URLs are not covered. Privileged visibility includes moderator because the existing `is_admin_user` helper treats moderator as staff.

## DOC-007 — Cloudinary document uploads were explicitly public

**Severity:** HIGH for paid or otherwise restricted documents
**Status:** Partially fixed for new uploads; legacy assets need provider-side migration
**Location:** `methods/cloudinary_upload.py`, `upload_file_to_cloudinary` around lines 235–270; delivery signing in `routes/api.py`, `_create_document_delivery_url`.
**Problem:** Upload options explicitly allowed anonymous delivery and set access mode to public. A direct Cloudinary URL could bypass AbhiHub account and purchase checks.
**Root cause:** Cloudinary was configured for public CDN delivery to support the previous proxy design.
**Impact:** Anyone who knows a legacy public asset URL can retrieve that file directly, regardless of AbhiHub authorization.
**Evidence:** Source configured `access_control` with `anonymous` and `access_mode='public'`. [Cloudinary documentation](https://cloudinary.com/documentation/control_access_to_media) states default `upload` delivery is publicly available; [the upload API reference](https://cloudinary.com/documentation/image_upload_api_reference) documents `authenticated` delivery for protected assets.
**Recommended correction:** Upload new documents as authenticated assets, issue short-lived signed URLs only after AbhiHub authorization, and migrate existing public assets through a reviewed provider-side operation.
**Implementation:** New Cloudinary uploads now use `type='authenticated'`; document authorization signs those URLs for 10 minutes. Deletion tries authenticated delivery type, then legacy public upload type. Existing Cloudinary objects were not modified.
**Verification:** Focused upload test confirms authenticated type and absence of anonymous/public parameters; no live Cloudinary account was accessed.
**Remaining risk:** Legacy public assets remain public until migrated. No provider inventory or access-control migration was run. Direct PDF.js delivery depends on provider CORS configuration, which was unavailable.

## JOB-001 — APScheduler starts inside web application import

**Severity:** HIGH  
**Status:** Confirmed code-level duplication risk; production impact depends on process/instance count  
**Location:** `app.py`, `init_scheduler(app)` around lines 739–749; `scheduled_tasks.py`, `init_scheduler` around lines 18–56  
**Problem:** The scheduler starts during app import. The module-global singleton only prevents duplicate initialization inside one Python process. Each Gunicorn worker or application instance has its own process and can start the same jobs. Current `Procfile` uses one worker but does not guarantee a single deployment instance.  
**Root cause:** Background job ownership is coupled to web-process startup; no distributed leader lock or separate worker process is shown.  
**Impact:** Duplicate notifications, repeated wallet actions, load amplification, and inconsistent job timing across instances.  
**Evidence:** `app.py` imports and invokes `init_scheduler` at module load; `scheduled_tasks.py` creates `BackgroundScheduler`; `Procfile` starts Gunicorn.  
**Recommended correction:** Move scheduled execution to a dedicated scheduler process or use distributed locking/coordination. Add explicit overlap, coalescing, and misfire policies and verify job idempotency before changing deployment behavior.  
**Implementation:** Not implemented; Phase 6.  
**Verification:** Static source inspection only.  
**Remaining risk:** Actual deployed replica count and duplicate execution logs are unknown.

## JOB-002 — Scheduler job execution policies are implicit

**Severity:** MEDIUM  
**Status:** Confirmed configuration gap  
**Location:** `scheduled_tasks.py`, `setup_jobs` around lines 59–169  
**Problem:** Jobs set stable IDs and `replace_existing`, but do not explicitly set `max_instances`, `coalesce`, or `misfire_grace_time`. No retry/persistent job-store policy is visible in this module.  
**Root cause:** APScheduler defaults are relied on without documenting whether they match each job's reliability requirements.  
**Impact:** Long-running job overlap is limited by defaults only within one scheduler; missed intervals and restart recovery may not match intended behavior. Distributed copies remain uncoordinated.  
**Evidence:** All `add_job` calls in `setup_jobs` omit these options.  
**Recommended correction:** Choose per-job execution semantics after inspecting idempotency and criticality; use a single scheduler owner and durable queue/watermark for critical work.  
**Implementation:** Not implemented; Phase 6.  
**Verification:** Static source inspection only.  
**Remaining risk:** APScheduler version/runtime settings and job duration data have not been measured.

## PRIV-001 — Logs contain user and upload metadata

**Severity:** MEDIUM  
**Status:** Representative examples confirmed; targeted direct PII log messages fixed; full logging scope pending  
**Location:** `routes/app_pages.py`, upload route around line 1052; `methods/upload_notifier.py`, notification helpers; `methods/get_user_uploaded_files.py`, lookup helper; and user/document event logs in `app.py`, `methods/supabase_helper.py`, `methods/storage.py`, `push_notifications.py`, `routes/ai.py`, `routes/admin.py`, `routes/library.py`, `routes/payments.py`, `routes/webhooks.py`, `methods/channel_service.py`, and `methods/know_me.py`  
**Problem:** Logging includes uploader user ID, college, branch, semester, subject, recipient email, and document filename.  
**Root cause:** Operational logs interpolate identity and content fields directly.  
**Impact:** Log readers and retained log archives can access personal or sensitive academic/upload metadata beyond what troubleshooting requires.  
**Evidence:** Before remediation, `routes/app_pages.py` logged uploader and academic fields; `methods/upload_notifier.py` logged recipient emails, filenames, document IDs, and raw provider errors; `methods/get_user_uploaded_files.py` logged the lookup email and traceback. A source scan also found direct identifiers in account, payment, document-view, and storage logs.  
**Recommended correction:** Replace direct identity/content with a non-reversible or suitably scoped correlation identifier; log event type, outcome, and counts. Audit all logging statements for credentials, tokens, signed URLs, headers, emails, phone numbers, and document content.  
**Implementation:** Replaced direct personal/content values with event/status-only messages or error classes in the locations listed above. The file-lookup failure response now returns a generic message instead of the raw exception. Notification delivery and data operations are unchanged.  
**Verification:** `tests/test_sensitive_url_logging.py` and relevant upload/account/profile/AI/payment/document/channel/notification suites passed: 85 tests and 12 subtests in one run; 8 tests in a subsequent notification/redaction run. `py_compile` and `git diff --check` passed. Existing Werkzeug/Supabase deprecation warnings remain.  
**Remaining risk:** Complete review of raw exception/provider error logs and log sink/retention remains pending.

## SEC-001 — Direct application startup enables debug outside exact production setting

**Severity:** HIGH if reachable outside local development; otherwise LOW operational risk  
**Status:** Confirmed conditional code path; prior runtime exposure unverified  
**Location:** `app.py`, `__main__` block around lines 2005–2008  
**Problem:** `debug_mode = os.getenv('FLASK_ENV') != 'production'` enables debug for an unset or differently cased environment value, then starts Socket.IO on `0.0.0.0`. The repository's Procfile uses Gunicorn, which does not invoke this block, but direct `python app.py` in a reachable environment would.  
**Root cause:** Debug is enabled by default unless one exact string is configured.  
**Impact:** If deployed through this path, interactive debugger/reloader behavior may expose sensitive internals and execute code under debugger conditions. The previous logs' debugger PIN claim cannot be validated from repository source alone.  
**Evidence:** `app.py:2005–2008`; `Procfile` uses Gunicorn. No explicit debug/reloader flags appear in `Procfile`.  
**Recommended correction:** In a later approved remediation, make debug opt-in only for explicit local development, force debug/reloader off outside that mode, and retain a production WSGI server. Inspect deployment command/config before changing startup.  
**Implementation:** Not implemented; Phase 1.  
**Verification:** Static source inspection only.  
**Remaining risk:** Actual runtime command and environment unavailable.

## TIME-001 — Naive `datetime.utcnow()` calls remain

**Severity:** LOW  
**Status:** Confirmed occurrences; behavioral impact requires call-site review  
**Location:** `app.py` (multiple call sites), `routes/app_pages.py`, `routes/api.py`, `routes/admin.py`, `routes/seo.py`  
**Problem:** Several modules call `datetime.utcnow()`, producing naive datetimes while other code (for example upload notifier) uses timezone-aware UTC.  
**Root cause:** Mixed timestamp conventions.  
**Impact:** Potential ambiguity in serialization and comparisons, especially around timezone boundaries; exact affected behavior remains to be established per call site.  
**Evidence:** `rg` found usages in `app.py`, `routes/app_pages.py`, `routes/api.py`, `routes/admin.py`, and `routes/seo.py`.  
**Recommended correction:** Normalize reviewed code paths to timezone-aware `datetime.now(timezone.utc)` and preserve expected database timestamp representation.  
**Implementation:** Not implemented; Phase 3 or targeted fixes.  
**Verification:** Static search only.  
**Remaining risk:** Full occurrence inventory and compatibility impact pending.

## Unverified investigation leads

- **Debugger/PIN in previous logs:** Source confirms a conditional debug path; logs and runtime config were not provided, so exposure is not independently confirmed.
- **Broader PII in logs:** Representative identity and upload metadata are confirmed, but no complete log corpus was available.
- **Notification timing/recovery:** `methods/upload_notifier.py` uses a 55–65 minute query window and filters `upload_notified IS NULL`; restart loss, repeated delivery, timezone correctness, marking order, and overlap require full function inspection and tests.
- **Supabase/RLS:** SQL scripts exist, including RLS-related changes, but deployed policies/grants/schema were not available. No secure-RLS conclusion is made.
- **Redis:** `cache_manager.py` supports optional Redis and falls back to L1. Runtime Redis availability and cache-key isolation are unverified.
- **Large/repeated database queries, HTTP 206, browser 404s, service-worker request frequency, and search completion:** No conclusions made in Phase 0; investigate relevant code and logs in later phases.

## SEC-002 — Credential-bearing file URLs were written to logs

**Severity:** HIGH when URLs carry signed access credentials; otherwise MEDIUM  
**Status:** Fixed and verified for the audited paths  
**Location:** `routes/api.py`, `proxy_file` around lines 2034–2056, `api_extract_upload_metadata` around lines 1470–1488, and `pdf_proxy` around lines 2680–2685; `methods/supabase_helper.py`, `save_file_record` around line 1067; `methods/cloudinary_upload.py`, `upload_file_to_cloudinary` around line 292; `routes/webhooks.py`, `_async_compress_and_update` around lines 44–86; and `push_notifications.py`, push delivery around lines 603–630.  
**Problem:** Failure or success messages included full source URLs or raw exception text that can contain the same URL. Signed storage URLs carry temporary access credentials in query parameters.  
**Root cause:** Logs interpolated untrusted URL inputs, URL-bearing provider results, or request exception messages directly.  
**Impact:** Anyone with access to retained application logs could reuse a still-valid signed URL to read a private object.  
**Evidence:** Previous code logged `file_url`, `pdf_name`, `secure_url`, or raw exception text in the affected paths. Regression tests inject a signed URL into a failing proxy request and a failing post-upload request and assert that its signature is absent from logs.  
**Recommended correction:** Log only non-secret context such as allowlisted host, error class, event, and counts. Never log a full signed URL or raw exception where it can repeat one.  
**Implementation:** Replaced the affected messages with host/error-type or event-only messages in `routes/api.py`, `routes/webhooks.py`, `methods/supabase_helper.py`, and `methods/cloudinary_upload.py`. Added `tests/test_sensitive_url_logging.py`. No response or storage behavior changed.  
**Verification:** 80 focused tests passed (storage upload, file upload, document viewing, production smoke, and two new log-redaction regression tests); 18 subtests passed. `py_compile` and `git diff --check` passed. One initial run failed because a test tried to change into a sandbox-protected Windows temp directory; rerunning with `TEMP`/`TMP` under the writable project directory passed. Existing suite emitted 29,599 dependency deprecation warnings.  
**Remaining risk:** The tests cover proxy/post-upload signed URL failures and upload-notification email/filename redaction. Other changed message sites were checked statically. Remaining raw exception logs are tracked in PRIV-002.

## SEC-003 — Production can explicitly disable the Secure session-cookie flag

**Severity:** MEDIUM, conditional on deployment configuration  
**Status:** Suspected configuration risk  
**Location:** `app.py`, session cookie configuration around lines 697–704.  
**Problem:** `SESSION_COOKIE_SECURE=false`, `0`, or `no` makes `_is_dev_env` true even when `FLASK_ENV` and `BASE_DOMAIN` identify production, which disables the Secure cookie attribute.  
**Root cause:** A generic environment override can turn off a production security control without an explicit development-only guard.  
**Impact:** If production serves any HTTP traffic, the browser may send the session cookie over that connection. Actual environment values and HTTPS edge behavior were not inspected.  
**Evidence:** Static branch inspection; `.env` and deployed environment values were not read.  
**Recommended correction:** Permit disabling Secure cookies only in explicit local development/testing; otherwise force Secure. Verify proxy/TLS deployment before changing.  
**Implementation:** Not implemented.  
**Verification:** Static inspection only.  
**Remaining risk:** Whether the override is set in the deployed environment is unknown.

## SEC-004 — Missing SECRET_KEY silently creates a per-process session key

**Severity:** MEDIUM reliability/configuration risk  
**Status:** Confirmed code behavior; deployment status unknown  
**Location:** `app.py`, secret-key configuration around lines 688–695.  
**Problem:** When `SECRET_KEY` is absent, the app logs a warning and generates a new random key at startup instead of refusing production startup.  
**Root cause:** Configuration fallback prioritizes import/startup availability over stable session signing.  
**Impact:** Restarts or multiple instances invalidate Flask sessions and session-bound PDF tokens. A strong random key still protects the running process; the demonstrated issue is instability, not weak entropy.  
**Evidence:** `app.secret_key = secrets.token_hex(32)` executes when no configured key exists.  
**Recommended correction:** Fail startup in production if `SECRET_KEY` is absent; retain a clearly local-only fallback for development/test.  
**Implementation:** Not implemented.  
**Verification:** Static inspection only; deployment configuration was not inspected.


## PRIV-002 — Remaining raw exception messages may contain sensitive request or database data

**Severity:** MEDIUM, suspected until call sites are reviewed  
**Status:** Needs investigation  
**Location:** Multiple `logging.*(..., e)` / interpolated exception sites across `app.py`, `routes/`, `methods/`, and `data/`. The audit scan identified many exception-bearing messages; each still requires call-site review to determine whether exception text can include emails, tokens, signed URLs, SQL, or request payloads.  
**Problem:** Raw exceptions from HTTP clients, storage providers, Supabase/PostgREST, and framework errors are often printed directly. Their contents vary by exception source, so not every occurrence is a confirmed leak.  
**Root cause:** Error diagnostics use exception text without a data-classification or redaction policy.  
**Impact:** Affected exceptions could disclose sensitive request values or provider response details to log readers. No additional concrete secret exposure was confirmed in this pass.  
**Evidence:** Static scan across runtime Python modules found numerous raw exception log statements; direct tests now cover representative signed-URL and notification cases.  
**Recommended correction:** Review each remaining call site; log exception class, stable provider error codes, and correlation IDs. Preserve stack traces only where they cannot include credentials or personal data.  
**Implementation:** Not implemented; investigation remains in progress.  
**Verification:** Static scan only; complete exception inventory not yet reviewed.  
**Remaining risk:** The exact number and sensitivity of remaining exception messages are not yet established.

## UI-001 — Personalized watermark and custom context menu are browser-side deterrents

**Severity:** LOW (requested UX and attribution control)
**Status:** Implemented; syntax and template rendering verified; browser interaction not automated
**Location:** `templates/p_struct.html` (shared public/account layout, identity setup around line 1530); `templates/admin_base.html` (admin layout, identity setup around line 698); `static/js/site-protection.js`; `static/css/site-protection.css`.
**Problem:** The shared layout suppressed right-click without a replacement and presented browser-side controls as protection against extension injection, downloads, screenshots, and DevTools. Such controls are bypassable and do not protect delivered content.
**Root cause:** Client-side event and DOM manipulation were treated as a security boundary.
**Impact:** Users lost native context-menu functions, including potentially useful browser actions, while having no real barrier to saving or copying delivered data.
**Evidence:** Shared template used a capture-phase `contextmenu` preventDefault handler and a MutationObserver that removed nodes based on extension-like attributes. PDF.js also receives content in the browser.
**Recommended correction:** Keep authorization and entitlement checks server-side. A custom context menu and visible per-user watermark may discourage casual redistribution but must not be treated as content protection.
**Implementation:** Added a shared right-click menu with the current account email and registration/student ID, excluding editable fields; moved the repeated `AbhiHub • email • student ID` overlay into only the PDF/image resource viewer containers; removed extension-node stripping and false DevTools/screenshot/print interception.
**Verification:** `node --check static/js/site-protection.js` succeeded. `/login` rendered with both shared assets (HTTP 200), and has no document watermark. Viewer/scope tests passed 4/4. Browser interaction was not automated.
**Remaining risk:** A user can disable JavaScript/CSS, use browser tools, capture screenshots, or save content already sent to their device. Public/legacy provider URLs remain governed by DOC-007 and provider configuration.

## PRIV-006 — Student profile details were written to application logs

**Severity:** MEDIUM
**Status:** Fixed; source inspection verified
**Location:** `methods/supabase_helper.py`, `get_student_profile`, around lines 1925 and 1956.
**Problem:** Both profile success paths interpolated the entire flattened profile object into logs, including email, phone, registration number, name, and college details.
**Root cause:** Debug logging serialized the database result for convenience.
**Impact:** Anyone with log access could see unnecessary student personal information.
**Evidence:** The logged `flat` mapping contains student name/email/mobile number, registration number, college and branch fields.
**Recommended correction:** Log only the event/outcome, never profile data.
**Implementation:** Replaced both full-object log messages with event-only messages.
**Verification:** Direct source inspection confirms the profile mapping is no longer passed to logging.
**Remaining risk:** Broader exception-log review PRIV-002 remains in progress.

## SEC-006 — Browser extensions and local capture cannot be disabled by a website

**Severity:** INFORMATIONAL
**Status:** Confirmed browser platform limitation; misleading interception removed from shared layouts
**Location:** `templates/p_struct.html`, `templates/admin_base.html`, and `static/js/site-protection.js`.
**Problem:** The prior page script attempted to block DevTools shortcuts and remove extension-like DOM nodes, implying that it disabled extensions or inspection. It cannot control browser extensions, screenshots, or files already delivered to the browser.
**Root cause:** Client-side controls were mistaken for enforceable browser policy.
**Impact:** False confidence and degraded usability; these handlers did not prevent access to content in the browser.
**Evidence:** Browser receives and renders page source and document bytes; page JavaScript cannot revoke that access.
**Recommended correction:** Enforce authorization before every server/provider delivery; use short-lived access URLs and watermarking only as deterrence.
**Implementation:** Removed shared-layout shortcut interception and extension DOM stripping; documented the watermark/menu as deterrents.
**Verification:** Login template and JS syntax check passed.
**Remaining risk:** Browser-side capture remains possible by design.

## DOC-008 — Resource viewer type selection and watermark scope

**Severity:** MEDIUM
**Status:** Fixed; focused route/template tests verified
**Location:** `routes/library.py`, `resource_landing`, around lines 505–521 and 674; `templates/resource.html`, viewer section around lines 355–450; `static/js/site-protection.js`.
**Problem:** The resource template selected PDF.js for any paid locked document and sent every remaining type through the image viewer. The prior user watermark was injected over every shared-layout page instead of only the document viewer.
**Root cause:** Viewer branches inferred format inconsistently in Jinja and treated a global site overlay as viewer attribution.
**Impact:** Paid images could show a broken PDF.js viewer, unsupported files could be sent as image URLs, and the personal watermark appeared on unrelated pages.
**Evidence:** `resource_landing` now classifies by storage path extension and normalized record type. The template uses explicit `viewer_type`: PDF to PDF.js, supported image to Viewer.js, and unsupported types to a non-download message. Viewer.js 1.15.2 is pinned and served from local static assets with its MIT license.
**Recommended correction:** Keep viewer selection server-normalized, preserve access control before delivery, and scope attribution overlays to the viewer container.
**Implementation:** Added explicit `viewer_type` routing; render paid locked images as an access message without requesting the file; gated provider URL generation to supported viewer types; replaced custom image zoom/pan behavior with Viewer.js and bundled its versioned CSS/JS locally; added its viewer-modal watermark; kept personalized watermark markup inside resource PDF/image viewers and removed global watermark rendering.
**Verification:** Focused resource tests passed 4/4 for type selection, Viewer.js image rendering/watermark, no watermark on shared pages, and legacy resource rendering. Latest targeted PDF/image/scope tests passed 3/3. Python compilation and `node --check` for both Viewer.js and site-protection JavaScript passed. Flask test client confirmed Viewer.js JS/CSS return HTTP 200. Full resource suite: 7 passed, 3 failed on existing Tarika/topic/YouTube assertions with external Supabase/catalog configuration unavailable; those failures are outside viewer selection.
**Remaining risk:** Only PDF and supported raster image formats are rendered. Other types show a safe fallback. Direct provider delivery remains subject to provider URL policy and the browser can save bytes it receives.

## DEP-001 — npm installation reported dependency advisories

**Severity:** HIGH pending package-level triage
**Status:** Suspected; needs investigation
**Location:** `package.json` and `package-lock.json`; dependency tree after adding Viewer.js 1.15.2.
**Problem:** The npm install summary reported six advisories (one moderate, five high), but did not include the affected package names or dependency paths in the captured output.
**Root cause:** Not yet established; the newly added Viewer.js package has no runtime dependencies, so the advisories may be in the pre-existing dependency tree.
**Impact:** A vulnerable production dependency could expose the application to a known issue; no exploitability is confirmed from the install summary alone.
**Evidence:** `npm install --save-exact viewerjs` completed and reported “6 vulnerabilities (1 moderate, 5 high)”. No full audit output was gathered.
**Recommended correction:** Inspect `npm audit` output, identify whether affected dependencies are production or development-only, then patch compatible dependencies in a separate scoped change.
**Implementation:** None; this issue was recorded for triage. No dependency updates beyond adding Viewer.js were applied.
**Verification:** Only the npm install audit summary was observed; exact package/version/advisory mapping remains unverified.
**Remaining risk:** Whether any advisory affects deployed production dependencies is unknown.

## DOC-009 — Paid image previews exposed the wrong preview behavior

**Severity:** MEDIUM
**Status:** Fixed; access and image transformation tests passed
**Location:** `routes/api.py`, `view_doc` and `_create_paid_image_preview`; `templates/resource.html`, paid image viewer branch.
**Problem:** Locked paid images previously showed a generic access notice rather than the requested limited image preview. A CSS-only blur would reveal the original image bytes to the browser.
**Root cause:** The document endpoint supported page-limited PDF previews but had no server-side image preview transform.
**Impact:** Users could not preview paid images as requested; a client-only blur would have allowed bypass by inspecting the delivered original.
**Evidence:** The new preview endpoint reads the provider image under the existing host allowlist, enforces byte/pixel limits, downsizes it, preserves the top 20%, Gaussian-blurs the remaining 80%, and encodes only the transformed JPEG for the browser.
**Recommended correction:** Deliver only a server-transformed preview to users without access; keep full-image delivery behind the existing entitlement check.
**Implementation:** Added a `preview=1` paid-image mode to `/api/view-doc/<id>/file`. Locked resource pages load that endpoint in Viewer.js, display a “Top 20% is clear” notice, and keep the personalized watermark over the preview. Paid image preview responses use a distinct ETag variant, private short-lived caching, no range support, and reject oversized or unsupported inputs. The preview query returns only the blurred preview even to entitled viewers; full delivery remains on the separate authorized resource path.
**Verification:** `tests/test_legacy_document_access.py` plus focused PDF/image/watermark tests passed 13 tests. This includes a test that unauthenticated full-image requests return 402, preview response is JPEG with the expected preview header, top pixels remain clear, and lower-region variance is reduced by blur. `python -m py_compile routes/api.py` passed.
**Remaining risk:** Server processing downloads the source image to transform it. Images over the configured byte/pixel limits receive no preview. Users can capture or save the transformed preview; the full image remains accessible to entitled users by design.
