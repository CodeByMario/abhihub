# Specification: AbhiHub Production Readiness Hardening

## Overview
Remediate all identified production risks across security, reliability, operations, file safety, and test automation for AbhiHub before deployment.

## Functional & Security Requirements
1. **Log Sanitization**: Redact sensitive data from logs (auth Bearer tokens in `/auth`, user emails, raw passwords, session cookies).
2. **Upload & Payload Protection**: Enforce `MAX_CONTENT_LENGTH = 50 * 1024 * 1024` on Flask application config; restrict/sanitize `.svg` uploads to avoid Stored XSS.
3. **Global Security Headers**: Add `@app.after_request` headers including `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy`.
4. **Health Check Endpoint**: Implement `/health` returning HTTP 200 with JSON status `{"status": "ok"}` without exposing internal secrets.
5. **Rate Limiter Bug Fix**: Fix return tuple in `api_ask_paper` to return HTTP 429 status code.
6. **Test Suite Modernization**: Fix test environment file encoding (`utf-8` in `test_referral_flow.py`) and ensure tests pass cleanly.

## Non-Functional Requirements
- Maintain backward compatibility with existing authentication and document storage APIs.
- Keep dependencies lean following Ponytail minimalist rules.
- Ensure all changes are isolated to the `chore/production-readiness` branch.
