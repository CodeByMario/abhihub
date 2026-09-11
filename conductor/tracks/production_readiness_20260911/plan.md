# Implementation Plan: AbhiHub Production Readiness Hardening

## Phase 1: Critical Security & Privacy Redactions
- [x] Task: Remove token and email logging in `app.py` `/auth` route (SEC-01)
- [x] Task: Enforce `MAX_CONTENT_LENGTH` on `app.config` and validate upload mime/extensions (SEC-02)
- [x] Task: Harden session cookie defaults for production deployments (SEC-04)
- [x] Task: Phase 1 Verification & Redaction Check

## Phase 2: Reliability & Web Security Hardening
- [x] Task: Add global security headers in `@app.after_request` (SEC-03)
- [x] Task: Fix `api_ask_paper` rate limiter return status code to 429 (BUG-01)
- [x] Task: Implement lightweight `/health` and `/api/health` check endpoint (REL-01)
- [x] Task: Deduplicate `Compress(app)` initializations (PRF-01)
- [x] Task: Phase 2 Verification & Route Check

## Phase 3: Test Suite & Environment Verification
- [x] Task: Fix file encoding in `tests/test_referral_flow.py` (TST-01)
- [x] Task: Verify test execution with pytest
- [x] Task: Phase 3 Verification & Test Run

## Phase 4: Runbooks & Final Documentation
- [x] Task: Create `docs/production-readiness/checklist.md`
- [x] Task: Create `docs/production-readiness/deployment-runbook.md`
- [x] Task: Create `docs/production-readiness/final-report.md`
- [x] Task: Final Checkpoint & Stop before Git push/PR
