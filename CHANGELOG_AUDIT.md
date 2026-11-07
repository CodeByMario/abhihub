# Audit Change Log

## 2026-11-06 — Phase 0 records initialized

- **Finding IDs:** DISC-001, DISC-002; initial leads JOB-001, JOB-002, PRIV-001, SEC-001, TIME-001 recorded.
- **Files changed:** `AUDIT_MASTER.md`, `TASK_TRACKER.md`, `FINDINGS.md`, `CHANGELOG_AUDIT.md`, `SESSION_HANDOFF.md`.
- **What changed:** Added persistent audit records based on repository discovery and source inspection.
- **Why:** Preserve scope, findings, evidence, unknowns, and next steps as requested.
- **Previous behavior:** No equivalent audit records found at repository root.
- **New behavior:** Audit status and evidence are captured; no application behavior changed.
- **Tests performed:** None. Static inspection only, as this is Phase 0 and application code was not edited.
- **Results:** Record creation completed. Worktree already had 35 changed/untracked paths before audit records; preserved.
- **Rollback:** Remove only the five newly created audit record files if this audit record set is intentionally discarded. No application rollback required.

## 2026-11-06 — SEC-002 signed URL log redaction

- **Finding ID:** SEC-002.
- **Files changed:** `routes/api.py`, `routes/webhooks.py`, `methods/supabase_helper.py`, `methods/cloudinary_upload.py`, `push_notifications.py`, `tests/test_sensitive_url_logging.py`.
- **What changed:** Replaced URL/raw-exception log interpolation with event, host, and exception-class context; added regression tests for failing proxy and post-upload requests.
- **Why:** Signed URLs can carry temporary access credentials; log retention turns those URLs into reusable access capabilities.
- **Previous behavior:** Several success/failure logs included full URLs or exceptions containing request URLs.
- **New behavior:** Audited paths omit URL query strings and raw URL-bearing exceptions from logs. Request, storage, and HTTP response behavior is unchanged.
- **Tests performed:** Focused suite of upload/storage/document-viewing/production-smoke tests plus new redaction tests; `py_compile`; `git diff --check`.
- **Test results:** 80 passed, 18 subtests passed in the initial focused run; subsequent notification/redaction runs passed 8 and 85 tests respectively (the 85-test run had 12 subtests). An initial run had one Windows temp-directory permission failure; rerun with temp variables directed into the writable project directory passed. 29,599 dependency deprecation warnings were emitted in the initial run.
- **Rollback:** Revert only this finding's log-message changes and remove `tests/test_sensitive_url_logging.py`; no schema or data rollback is needed.

## 2026-11-06 — PRIV-001 direct PII logging reduction

- **Finding ID:** PRIV-001.
- **Files changed:** `routes/app_pages.py`, `methods/upload_notifier.py`, `methods/get_user_uploaded_files.py`, `app.py`, `methods/channel_service.py`, `methods/supabase_helper.py`, `routes/payments.py`, `routes/webhooks.py`, `push_notifications.py`, `routes/ai.py`, `routes/admin.py`, `methods/know_me.py`, `methods/storage.py`, `routes/library.py`, `routes/api.py`, `tests/test_sensitive_url_logging.py`.
- **What changed:** Removed direct user IDs, emails, filenames, viewer names, user quota values, storage paths, push endpoint prefixes, provider error text, and raw tracebacks from reviewed log messages. Lookup error response text is now generic.
- **Why:** Operational logs should retain event and failure context without exposing personal or document metadata.
- **Previous behavior:** Reviewed log sites interpolated direct identity/content values or provider exception details.
- **New behavior:** Reviewed paths log event/status, safe counts, device/platform details, or exception type; action and data-flow behavior remains unchanged.
- **Tests performed:** Relevant upload, notification, payments, AI, document viewing, channels, account/profile, and redaction tests; `py_compile`; `git diff --check`.
- **Test results:** 85 passed, 12 subtests passed in the feature run; a subsequent redaction/notification run passed 8 tests. Existing dependency deprecation warnings were emitted.
- **Rollback:** Revert this entry's log-only changes and test additions. If reverting the lookup response change, restore its prior error response separately.

## 2026-11-07 — PRIV-003 AI provider log redaction

- **Finding ID:** PRIV-003.
- **Files changed:** `methods/ai_provider.py`, `routes/ai.py`, `routes/api.py`, `tests/test_sensitive_url_logging.py`.
- **What changed:** Removed provider response bodies and raw exception details from reviewed prompt/document processing logs; provider failure messages are generic. Added a mocked failure test checking that prompt, response body, and key sentinels are absent from logs.
- **Why:** Provider responses and exceptions may echo user prompts or document data.
- **Previous behavior:** Provider and AI route failures could write raw response or exception strings to logs.
- **New behavior:** These paths log bounded metadata or exception classes; successful AI flow behavior is unchanged by design.
- **Tests performed:** Targeted mocked-provider test (1 passed), `tests/test_feature_ai.py` (3 passed), and `py_compile` for touched modules. A broader combined run was interrupted and has no result. `git diff --check` reports trailing whitespace in pre-existing dirty templates, not these changes.
- **Test results:** Targeted checks passed; broader suite remains inconclusive.
- **Rollback:** Restore prior log statements and provider error detail behavior, and remove the added regression test. No schema/data rollback is needed.

## 2026-11-07 — API-002/API-003 hostname and rate-limit audit

- **Finding IDs:** API-002, API-003.
- **Files reviewed:** `app.py`, `routes/api.py`, `routes/ai.py`, `routes/auth.py`, `methods/ai_safety.py`, `methods/analytics_tracker.py`, `cache_manager.py`, `Procfile`, `gunicorn.conf.py`, `requirements.txt`, `requirements-min.txt`.
- **What changed:** Added findings and tracker items only; no application code changed. Recorded inconsistent beta CORS/Socket.IO origin handling and limitations in process-local API rate controls/client-IP derivation.
- **Why:** The requested hostnames and API abuse controls need to be assessed across browser origin policy, sessions, worker topology, and proxy trust.
- **Previous behavior:** Findings were not tracked explicitly.
- **New behavior:** Exact source evidence, uncertainty, and remediation dependencies are recorded under API-002/API-003.
- **Tests performed:** Static source/configuration review only; no endpoint/browser host matrix was run.
- **Test results:** Source findings confirmed. Deployment environment and proxy behavior remain unknown. Redis appears optional in `cache_manager.py`; neither requirements file declares a Redis package, so availability cannot be assumed.
- **Rollback:** Remove these audit-only entries from the five audit records. No application changes or runtime behavior changed.

## 2026-11-07 — API-004 global per-user request limiting

- **Finding ID:** API-004.
- **Files changed:** `app.py`, new `methods/api_rate_limiter.py`, new `tests/test_api_rate_limiter.py`, new `tests/test_api_rate_limit_middleware.py`, and audit records.
- **What changed:** Added a request hook for `/api/`, `/admin/api/`, and `/store-room/api/` with configurable 300/user/minute and 60/anonymous socket-peer/minute defaults. Authenticated users are keyed by session UID (email fallback); anonymous keys use `request.remote_addr`, never raw `X-Forwarded-For`. OPTIONS, health, and provider webhook requests are exempt. Rejections return JSON 429 and `Retry-After`. Store is thread-safe, sliding-window, bounded, process-local.
- **Why:** Add a common per-user guard before route/database work to limit request bursts across API groups.
- **Previous behavior:** No common API request cap; only selected AI and analytics functions had process-local limits.
- **New behavior:** Requests over the configurable window are rejected per principal within each app process.
- **Tests performed:** `python -m pytest -q tests/test_api_rate_limiter.py tests/test_api_rate_limit_middleware.py`.
- **Test results:** 6 passed in 16.86 seconds. Multi-instance shared enforcement and real proxy address normalization were not tested because deployment topology is unknown.
- **Rollback:** Remove the `enforce_api_rate_limit` hook and `methods/api_rate_limiter.py`, remove the two added tests, then revert API-004 audit entries. Existing feature-level limiters remain unchanged.

## 2026-11-07 — PRIV-002/PRIV-004 authentication and payment error redaction

- **Finding IDs:** PRIV-002, PRIV-004.
- **Files changed:** `routes/payments.py`, `routes/auth.py`, `routes/webhooks.py`, `methods/wallet_service.py`, `methods/cloudinary_upload.py`, new `tests/test_sensitive_error_logging.py`, and audit records.
- **What changed:** Replaced raw exception strings in reviewed authentication, payment, wallet, webhook, and Cloudinary logs with exception-type diagnostics. Razorpay order creation now returns a generic provider-unavailable message instead of `str(exception)` while retaining HTTP 500.
- **Why:** Exception messages may contain provider bodies, URLs, identifiers, or database details.
- **Previous behavior:** Selected exception strings were written to logs, and payment order errors were also sent to clients.
- **New behavior:** Reviewed paths omit exception text; the payment route preserves the status code and returns generic text.
- **Tests performed:** `python -m pytest -q tests/test_sensitive_error_logging.py`.
- **Test results:** 1 passed; simulated sentinel content was absent from response and logs. Broader exception inventory and regression suite remain pending.
- **Rollback:** Restore the prior log interpolations and payment response string, and remove the new regression test. No data/schema changes.

## 2026-11-07 — PRIV-005 wallet and payment data-error response redaction

- **Finding ID:** PRIV-005.
- **Files changed:** `methods/wallet_service.py`, `routes/payments.py`, `routes/api.py`, `tests/test_sensitive_error_logging.py`, and audit records.
- **What changed:** Wallet helper exception results now use generic messages; document pricing/coupon and selected document/history/file-list/chat/upload/dashboard failures log exception classes and return generic response text. Added sentinel tests for wallet/pricing/coupon/storage paths.
- **Why:** Helper error objects and endpoint JSON were forwarding raw database exceptions to clients.
- **Previous behavior:** Selected error results contained `str(exception)`.
- **New behavior:** Error response shape and status are preserved while raw exception strings are omitted.
- **Tests performed:** `python -m pytest -q tests/test_sensitive_error_logging.py tests/test_api_rate_limit_middleware.py`.
- **Test results:** 10 passed in 20.73 seconds. Sentinel content was absent from tested response bodies/logs; unprefixed `/auth` was throttled as configured.
- **Rollback:** Restore the prior exception-string values/responses and remove the added tests. No schema/data rollback is required.

## 2026-11-07 — API-004 legacy endpoint coverage and DOC-002/DOC-003 triage

- **Finding IDs:** API-004, DOC-002, DOC-003.
- **Files changed:** `app.py`, `routes/api.py`, `tests/test_api_rate_limit_middleware.py`, `tests/test_sensitive_error_logging.py`, and audit records.
- **What changed:** Added rate-limit coverage for unprefixed `/auth`, `/verify-file`, `/get-file-url`, `/update-file-metadata`, and `/pdf-proxy/` paths. Redacted exception details from reviewed auth, document history/file-list, signing/verification/metadata, peer/chat, upload, and dashboard error paths. Recorded two legacy storage authorization gaps; no access policy changed.
- **Why:** The original `/api/` path filter missed API functions registered at legacy URLs, and storage routes showed missing document-level authorization.
- **Previous behavior:** Legacy routes were not covered by the common API limiter; selected handlers exposed raw exception messages; signed URL/verification authorization had not been tracked.
- **New behavior:** The identified legacy APIs are throttled and selected error responses are generic. DOC-002/DOC-003 have precise findings for follow-up.
- **Tests performed:** `python -m py_compile routes/api.py app.py tests/test_sensitive_error_logging.py tests/test_api_rate_limit_middleware.py`; combined pytest run for the two test files.
- **Test results:** Compilation passed; 10 tests passed in 20.73 seconds. An initial test collection caught a syntax indentation error introduced in the auth error-log edit; it was corrected before the successful compile/test rerun.
- **Rollback:** Remove the added legacy path matches in `enforce_api_rate_limit`, restore prior error messages/logging only if intentionally reverting, and remove the added tests/audit entries. DOC-002/DOC-003 are audit records only.

## 2026-11-07 — DOC-002/DOC-003 document route authorization fixes

- **Finding IDs:** DOC-002, DOC-003.
- **Files changed:** `routes/api.py`, new `tests/test_legacy_document_access.py`, and audit records.
- **What changed:** `/get-file-url` now requires `doc_id` and delegates URL generation/access checks to `authorize_document_access`. `/verify-file` now requires an authenticated admin before checking Firebase storage or inserting an approved document row. Both error paths return generic text and log only exception classes.
- **Why:** Authentication alone did not establish entitlement to a document, and the verification route previously allowed unauthenticated approved-row insertion.
- **Previous behavior:** A logged-in caller could request a signed URL for an arbitrary path; anonymous callers could invoke verification and potentially register an existing path as approved.
- **New behavior:** Signed URLs use the shared viewer authorization policy. Only administrators can run the legacy verification operation.
- **Tests performed:** `python -m pytest -q tests/test_legacy_document_access.py`; `python -m py_compile routes/api.py tests/test_legacy_document_access.py`.
- **Test results:** 3 passed; compilation passed. Firebase and Supabase were mocked, so live storage, RLS, and downstream approved-document publication were not tested.
- **Rollback:** Restore the previous `/get-file-url` path-signing handler and remove auth decorators from `/verify-file`; remove the focused test and corresponding audit updates. No schema or data changes were made.

## 2026-11-07 — DOC-004 route legacy PDF access through resource pages

- **Finding ID:** DOC-004.
- **Files changed:** `routes/api.py`, `tests/test_legacy_document_access.py`, `tests/test_sensitive_url_logging.py`, and audit records. Existing callers in `static/premium/js/store_room.js` and `static/js/carousel-personalization.js` were traced and remain compatible for registered paths.
- **What changed:** `/pdf-proxy/<path>` now looks up an exact `documents.file_url` and redirects to `/resources/<document-id>`. `/api/proxy-file` no longer accepts a raw URL; it requires a document ID and redirects to its resource page. Neither route serves or redirects directly to a file.
- **Why:** The user confirmed that document files should be accessed through canonical `/resources/<...>` pages, where document access policy is applied.
- **Previous behavior:** Any authenticated caller could request a known Firebase path directly; allowed external URLs could be redirected without document entitlement checks.
- **New behavior:** Only file paths registered to a document resolve; clients continue through the resource page/viewer.
- **Tests performed:** `python -m py_compile routes/api.py tests/test_legacy_document_access.py tests/test_sensitive_url_logging.py`; focused pytest runs for both files; scoped `git diff --check`.
- **Test results:** Seven document-route tests and the focused proxy-file test passed; compilation and diff check passed. The Supabase lookup was mocked.
- **Rollback:** Restore the previous direct download/redirect implementation and remove the two proxy regression tests and this audit entry. No schema/data changes were made.

## 2026-11-07 — DOC-005 keep paid previews on the restricted viewer route

- **Finding ID:** DOC-005.
- **Files changed:** `routes/api.py`, `tests/test_legacy_document_access.py`, and audit records.
- **What changed:** Authorization now returns only a local `/api/view-doc/<id>/file` URL for entitled content (`stream=1`) or the restricted preview URL (`preview=1`). Browser-facing direct signed URL generation and cache use were removed; viewer streaming keeps provider access server-side.
- **Why:** Direct provider URLs let browser clients bypass the viewer, including its page-one preview limit and repeated access checks.
- **Previous behavior:** Authorization returned direct signed provider URLs, including for previews, allowing full source retrieval outside the viewer's page limit.
- **New behavior:** File delivery stays behind the local viewer route, which rechecks access and restricts preview output.
- **Tests performed:** `python -m py_compile routes/api.py tests/test_legacy_document_access.py`; `python -m pytest -q tests/test_legacy_document_access.py`.
- **Test results:** Seven document-route tests passed, including assertions that neither ordinary nor preview authorization returns a provider URL.
- **Rollback:** Restore prior provider URL signing/cache behavior for authorization responses and remove the regression test/audit entry. No schema/data changes were made.

## 2026-11-07 — DOC-006 enforce publication status on direct resource routes

- **Finding ID:** DOC-006.
- **Files changed:** `routes/api.py`, `routes/library.py`, `tests/test_legacy_document_access.py`, and audit records.
- **What changed:** Added publication visibility checks to document authorization, file streaming, and resource landing routes. `approved` records remain public; other statuses require uploader or privileged staff identity.
- **Why:** Approved-only catalogs could be bypassed by requesting a known pending document ID directly.
- **Previous behavior:** Direct document lookup and free-document access did not enforce `status='approved'`.
- **New behavior:** Pending/unpublished record IDs return 404 to non-owners and non-staff users.
- **Tests performed:** `python -m py_compile routes/api.py routes/library.py tests/test_legacy_document_access.py`; `python -m pytest -q tests/test_legacy_document_access.py`.
- **Test results:** Seven passed; regression test verifies both authorization and file routes reject a pending record for an unrelated visitor.
- **Rollback:** Remove the visibility helper/checks and regression test. No schema/data changes were made.

## 2026-11-07 — Direct provider delivery and authenticated new uploads

- **Finding IDs:** DOC-005, DOC-007.
- **Files changed:** `routes/api.py`, `methods/cloudinary_upload.py`, `templates/resource.html`, `tests/test_legacy_document_access.py`, `tests/test_upload_images_pdf.py`, and audit records.
- **What changed:** Entitled full documents receive a 10-minute signed provider URL for PDF.js/image rendering, avoiding Flask transfer of the file bytes. Paid previews continue through the local viewer, which returns only page one. New Cloudinary uploads use authenticated delivery; the viewer's existing `download=false` mode hides PDF.js download/print controls, and purchase copy now describes online reading.
- **Why:** The user requested direct storage-provider delivery and view-focused UX.
- **Previous behavior:** All full files were streamed through Flask; new Cloudinary assets were explicitly public.
- **New behavior:** Authorized full file bytes flow from Firebase/Cloudinary/Supabase directly to the browser where provider signing is available. Cloudinary assets created by this code require authenticated delivery. Preview bytes still pass through the server to enforce the page limit.
- **Tests performed:** Python compilation; focused Firebase signing, preview confinement, and Cloudinary authenticated-upload tests.
- **Test results:** Three focused tests passed. Real provider CORS, access modes, and existing assets were not tested or changed.
- **Rollback:** Restore local viewer URLs for full documents and public Cloudinary upload parameters. No schema or remote asset changes were made.

## 2026-11-07 — Personalized site watermark, context menu, and profile log redaction

- **Finding IDs:** UI-001, PRIV-006, SEC-006.
- **Files changed:** `templates/p_struct.html`, `templates/admin_base.html`, `static/css/site-protection.css`, `static/js/site-protection.js`, `methods/supabase_helper.py`, and audit records.
- **What changed:** A repeated AbhiHub watermark with signed-in email and registration/student ID now appears only over resource PDF/image viewers. Right-click opens a personalized menu except on editable fields. Removed ineffective DevTools/extension/screenshot/print interception and extension-like DOM removal. Student profile fetch logs no longer contain the full profile object.
- **Why:** User requested site-wide attribution and personalized context menu; source review also confirmed direct PII in profile logs. Browser-side controls do not stop local capture or extension use.
- **Tests performed:** JS syntax check; Flask test-client `GET /login` returned HTTP 200 with both assets; scoped diff check; `tests/test_resource_v2.py`.
- **Test results:** Syntax/render/diff checks passed. Resource suite returned 7 failed, 1 passed because DOC-006 publication checks return 404 for its fixtures. Browser interaction was not automated.
- **Rollback:** Remove shared asset references and new static files. Restore the original profile logs only if the privacy exposure is explicitly accepted.


## 2026-11-07 — Route PDFs and images to dedicated viewers; scope watermark to reader

- **Finding ID:** DOC-008 (also updates UI-001).
- **Files changed:** `routes/library.py`, `templates/resource.html`, `static/js/site-protection.js`, `static/css/site-protection.css`, `static/css/pages/p_resource.css`, `tests/test_resource_v2.py`, and audit records.
- **What changed:** Resource routes now normalize a `viewer_type`. PDFs are rendered through PDF.js; supported raster images use the existing zoomable image viewer; unsupported types show a safe fallback. Paid locked images no longer attempt PDF.js or request protected image bytes. The personalized overlay now appears only within resource PDF/image viewer containers. Shared pages retain the custom context menu but show no watermark.
- **Why:** The prior global overlay appeared on all pages and paid image documents fell into the PDF.js branch; unsupported records fell through to the image viewer.
- **Tests performed:** `python -m py_compile routes/library.py`; `node --check static/js/site-protection.js`; focused resource tests; full `tests/test_resource_v2.py`.
- **Test results:** Focused selection/scope tests passed 4/4. Full resource suite: 7 passed, 3 failed on existing Tarika/topic/YouTube assertions when Supabase/catalog external configuration was unavailable.
- **Rollback:** Restore previous `resource_landing` classification/template conditions and re-enable global watermark insertion. No schema or production data changes.
- **Follow-up:** Adopted Viewer.js 1.15.2 for the resource image modal, pinned via `package.json`/`package-lock.json`, copied its minified runtime and CSS plus MIT license to local static vendor assets, and replaced custom zoom/pan listeners with Viewer.js controls. PDF.js remains dedicated to PDFs.
- **Follow-up verification:** PDF.js and Viewer.js selection/scope tests passed; local Viewer.js files returned 200; Python and JavaScript syntax checks passed.

## 2026-11-07 — Server-side partial preview for locked paid images

- **Finding ID:** DOC-009.
- **Files changed:** `routes/api.py`, `templates/resource.html`, `static/css/pages/p_resource.css`, `tests/test_legacy_document_access.py`, `tests/test_resource_v2.py`, and audit records.
- **What changed:** Locked paid images load a Viewer.js preview endpoint that sends a downscaled JPEG with the top 20% clear and the remaining 80% blurred. The page shows the preview inside the existing image viewer with the personalized watermark. Requests without `preview=1` still receive 402 for a user without access.
- **Why:** User requested a partial preview for paid images. The transform runs server-side so the unblurred full image is not delivered to an unentitled browser.
- **Tests performed:** Python compilation and focused document access/resource viewer tests.
- **Test results:** 13 focused tests passed; includes access denial and pixel-level blur checks.
- **Rollback:** Remove the image preview transformation path and restore the locked-image placeholder. No schema or production data changes.


## 2026-11-07 — Sanitize admin exception responses

- **Finding ID:** PRIV-005.
- **Files changed:** `routes/admin.py`, `tests/test_sensitive_error_logging.py`, and audit records.
- **What changed:** Admin API error bodies and health-check error descriptions no longer include raw caught exception text. Reviewed exception logs use fixed safe messages.
- **Why:** Database/provider exceptions can contain query details, identifiers, URLs, or other internal values even on admin routes.
- **Tests performed:** `python -m py_compile routes/admin.py`; `python -m pytest -q tests/test_sensitive_error_logging.py`; `git diff --check`.
- **Test results:** Compilation and diff check passed. New admin exception sentinel test passed; suite result was 5 passed and 2 failed because two existing file-route tests receive current authorization rejections (400/401) before reaching their mocked storage exception.
- **Rollback:** Restore prior exception interpolation in `routes/admin.py`. No schema or production data changes.
