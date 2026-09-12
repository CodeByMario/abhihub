# AbhiHub Production Deployment Contract

## 1. Runtime & Environment Specification

| Parameter | Value / Requirement | Notes |
| :--- | :--- | :--- |
| **Runtime Language** | Python 3.12 (CPython) | Specified via `.python-version` |
| **Node Build Tooling** | Node.js 18+ / 20+ (Build-time only) | Required solely for compiling Tailwind CSS |
| **Package Manager** | `pip` (Python), `npm` (Node) | Lockfiles: `requirements.txt`, `package-lock.json` |
| **Host & Port** | `0.0.0.0:${PORT:-5000}` | Listens on dynamic `$PORT` provided by container / PaaS |
| **Worker Architecture** | Gunicorn with GeventWebSocket worker | `geventwebsocket.gunicorn.workers.GeventWebSocketWorker` (1 worker recommended for WebSocket state synchronization) |

---

## 2. Build & Start Commands

### Build Phase (CI/CD or Docker Builder Stage)
```bash
# 1. Compile Tailwind CSS (frontend minification)
npm ci --only=dev
npm run build:css

# 2. Install production Python packages
pip install --no-cache-dir -r requirements.txt
```

### Runtime Start Command (Production Execution)
```bash
# Executed via Procfile or Container CMD
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --bind 0.0.0.0:$PORT --config gunicorn.conf.py app:app
```

---

## 3. Health, Liveness & Readiness Checks

- **Liveness Path**: `GET /health`
- **Readiness Path**: `GET /api/health`
- **Expected Status Code**: `200 OK`
- **Expected Response Payload**:
  ```json
  {
    "service": "abhihub",
    "status": "healthy",
    "timestamp": "2026-09-11T09:30:00.000000+00:00",
    "version": "1.0.0"
  }
  ```
- **Security Constraint**: Health endpoints return zero internal configuration, database strings, or memory dumps.

---

## 4. Environment Variables Contract (Names Only)

> **CRITICAL**: Never embed secret values into code, manifests, Docker images, or version control. All values are injected via platform environment managers (e.g., Heroku Config Vars, Kubernetes Secrets, Cloud Run env).

### Mandatory Variables
| Variable Name | Description |
| :--- | :--- |
| `SECRET_KEY` | Cryptographic secret for Flask session signing and CSRF tokens. |
| `SUPABASE_URL` | Supabase project API gateway endpoint (`https://<project-id>.supabase.co`). |
| `SUPABASE_KEY` | Supabase service-role key for backend DB operations and auth validation. |

### Optional / Integration Variables (Gracefully degraded when unset)
| Variable Name | Description |
| :--- | :--- |
| `BASE_DOMAIN` | Canonical domain for absolute URLs, sitemaps, and email links (default: `www.abhihub.edu.eu.org`). |
| `CLOUDINARY_URL` / `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Primary cloud document and media storage backend. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Service account JSON string for legacy Firebase storage integration. |
| `FIREBASE_STORAGE_BUCKET` | Firebase storage bucket domain. |
| `VAPID_PUBLIC_KEY` | Public VAPID key for Web Push notification client subscription. |
| `VAPID_PRIVATE_KEY` | Private VAPID key for backend push notification signing. |
| `VAPID_CLAIMS_EMAIL` | Admin contact email associated with VAPID subject claim (`mailto:...`). |
| `OPENROUTER_API_KEY` | API token for AI study bot and chatbot features. |
| `NVIDIA_API_KEY` | Alternate LLM acceleration endpoint token. |
| `TURNSTILE_SITEKEY` / `TURNSTILE_SECRET` | Cloudflare Turnstile anti-bot verification keys for contact/upload forms. |
| `INDEX_NOW_BING_API_KEY` | IndexNow key for instant search engine URL indexing. |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | SMTP outbound credentials for referral / password reset transactional emails. |
| `BREVO_API_KEY` / `BREVO_SENDER` | Alternate Brevo transactional email credentials. |
| `RESEND_API_KEY` / `RESEND_SENDER` | Alternate Resend transactional email credentials. |
| `CAMPAIGN_FROM` / `CAMPAIGN_FROM_NAME` | Outbound email sender name and address. |

---

## 5. Storage & Persistence Requirements

1. **Stateless Container / App Layer**: The web application filesystem is strictly ephemeral. No uploaded student documents, chat attachments, or avatar files are stored on local disk.
2. **Document & Media Storage**: All files uploaded via `/upload` are streamed directly or synced to Cloudinary / Supabase Storage.
3. **Database**: PostgreSQL hosted via Supabase (`abhihub` schema).

---

## 6. Migration Protocol & Database Schema

- **Migration Tooling**: Raw SQL scripts stored in `migrations/`.
- **Execution Order**: Strictly numeric (008 → 009 → ... → 027).
- **Execution Protocol**: Run prior to web process rollout via Supabase SQL Editor or CI/CD database deploy pipeline.
- **Rollback Safety**: Migrations are additive (`ADD COLUMN IF NOT EXISTS`, idempotent indexes).

---

## 7. Service Worker & PWA Contract

- **Service Worker Location**: `/static/sw.js` (served with HTTP header `Service-Worker-Allowed: /` or route rule `/sw.js`).
- **Scope**: Entire application scope `/`.
- **Cache Strategy**: Stale-while-revalidate for static assets, network-first for HTML pages, offline fallback to `/templates/offline.html`.
- **Push Notification Listener**: Webpush events dispatched with payload `{ "title": "...", "body": "...", "url": "...", "icon": "..." }`.

---

## 8. Rollback & Shutdown Protocol

- **Graceful Shutdown**: Gunicorn traps `SIGTERM` / `SIGINT` and allows in-flight WebSocket connections and requests up to 30s to complete.
- **Rollback Method**: Instant release rollback on hosting platform (e.g., `heroku rollback` or container image tag revert).
- **Database Rollback Strategy**: Forward-compatible migrations ensure prior release functions without schema breakage.
