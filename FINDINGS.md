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
