# Security Policy

## Supported Versions

Only the latest version on the `main` branch is supported with security updates.

## Reporting a Vulnerability

If you discover a security issue in AbhiHub, please report it responsibly:

1. **Do not open a public issue** for security vulnerabilities.
2. Email the maintainer at **abhihub.02@gmail.com** with subject line
   `[SECURITY] <brief description>`.
3. Include:
   - A description of the vulnerability
   - Steps to reproduce (if possible)
   - The impact you expect
   - Your contact info for follow-up
4. You will receive an acknowledgment within 7 days. If you do not,
   follow up once.

We will work with you to understand the report, confirm the issue, and
coordinate a fix and disclosure timeline. We ask that you do not disclose
the issue publicly until we have had a reasonable chance to patch it.

## Scope

This policy covers the AbhiHub web application and its associated
configuration as found in this repository. Third-party services
(Supabase, Cloudinary, Firebase, Cloudflare, etc.) are out of scope for
this policy — report issues with those providers directly to them.

## What is NOT a vulnerability

- Missing features or usability concerns — open a normal issue.
- Issues that require credentials, internal network access, or physical
  access that an attacker would not reasonably have.
- Self-XSS or issues that require the victim to paste attacker-controlled
  content into their own browser console.
- Rate-limiting or denial-of-service concerns that are inherent to the
  hosting platform.

## Security-related configuration

Secrets (API keys, service-account JSON, passwords, tokens) must **never**
be committed to this repository. The `.env.example` file documents the
variables a deployment needs; live values belong in a deployment-local
`.env` that is git-ignored. If you believe a secret has been committed,
treat it as compromised: rotate it immediately and remove it from the
repository history.

## Hardening assumptions

- The application assumes HTTPS in production (Heroku provides this by
  default; custom domains should use a CDN/proxy that terminates TLS).
- CSRF protection is enabled globally; API endpoints under `/api/` are
  excluded from the CSRF check where appropriate.
- File upload is restricted to configured extensions and size limits; the
  anti-piracy policy forbids serving download links for document previews
  (preview only, in-page).
