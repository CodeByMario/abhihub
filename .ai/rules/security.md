# Security Rules

**Status:** Effective Immediately
**Source:** .ai/rules/security.md

---

## Core Security Rules

1. **NEVER hardcode credentials.** All secrets must come from environment
   variables (`.env`) or a secrets manager.
   Forbidden patterns: `password = "..."`, `api_key = "..."`,
   `SECRET_KEY = "..."` (literal strings in source).

2. **NEVER commit credential files.**
   Forbidden files: `.env`, `serviceAccountKey.json`, `firebase-auth.json`,
   `*.pem`, `*.key`, `*.p12`.

3. **Always use parameterized queries.** Never build SQL strings with
   f-strings or concatenation. Use Supabase client methods.

4. **Validate all user input.** Every route handler must validate input
   through Flask-WTF forms or explicit validation. CSRF protection is
   mandatory.

5. **Enforce access control.** Use `@auth_required` on all private routes.
   Use `@admin_required` on admin routes. Check ownership for
   per-resource operations.

6. **Encrypt sensitive files.** Uploaded documents must be encrypted
   before storage (see `methods/encryption.py`).

7. **Rate limit.** Apply rate limiting to auth endpoints and API endpoints.

8. **Log security events.** Record auth attempts, failed access,
   and admin actions.

9. **No direct SQL in routes.** All database operations must go through
   the Supabase client or methods/ utility modules.

10. **Keep dependencies updated.** Monitor for security advisories.
    Use `pip-audit` or equivalent.

## CSRF Protection

- All POST/PUT/DELETE forms must include CSRF tokens.
- `config_csrf.py` defines the CSRF configuration.
- `inject_csrf.py` injects CSRF tokens into templates.
- Verify CSRF on every state-changing request.

## File Upload Security

- Validate file types (only PDF, images allowed).
- Validate file size (max 50MB).
- Encrypt before storage.
- Store on Cloudinary with signed URLs.
- Never serve uploads directly from the web server.
