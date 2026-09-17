# Production Readiness Checklist: AbhiHub

## 1. Build and Code Quality
- [x] Production build succeeds from clean setup (`npm run build:css` and python imports).
- [x] No debug credentials, token dumps, or placeholder secrets exposed in logs.
- [x] Sensitive tokens (Bearer tokens, user emails) redacted from application logs.
- [x] Error responses do not leak tracebacks or raw database schemas (custom 404/500 handlers).
- [x] All Supabase database migrations reviewed and verified.
- [x] Zero PII transmitted in client/server analytics payloads.

## 2. Authentication and Authorization
- [x] Supabase Auth (Google OAuth and Email login) operational.
- [x] Session cookies use secure production defaults (`HttpOnly`, `SameSite=Lax`, `Secure` when HTTPS).
- [x] Logout invalidates sessions on server and expires cookie header.
- [x] Server-side `@auth_required` and `@admin_required` decorators enforced on API and UI routes.
- [x] Admin endpoints return 401/403 JSON payloads for API requests.

## 3. Upload and Content Safety
- [x] File upload size capped at 50MB (`MAX_CONTENT_LENGTH` and route-level validation).
- [x] Filenames sanitized to prevent path traversal attacks.
- [x] File header magic bytes verified for PDFs, PNGs, JPEGs, GIFs, and WEBP.
- [x] Unsanitized SVG file uploads restricted to prevent Stored XSS.
- [x] Cloud storage assets uploaded with image compression, grayscale auto-contrast, and metadata stripping.

## 4. API and Web Security
- [x] Global Security Headers configured via `@app.after_request`:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(self), microphone=(), geolocation=()`
  - `Strict-Transport-Security` enabled in production.
- [x] CSRF protection enabled on non-exempt mutating routes.
- [x] Rate limiter return status codes properly return HTTP 429.

## 5. Reliability and Operations
- [x] Dedicated `/health` and `/api/health` monitoring endpoints implemented.
- [x] In-memory caching and compression configured.
- [x] Deprecations cleaned up and UTC timestamps standardized.
- [x] Automated test suite covering health probes, security headers, auth gates, upload validation, and analytics privacy.
