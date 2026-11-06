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

