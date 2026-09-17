# AbhiHub Production Deployment Runbook

## 1. Prerequisites & Access Checklist
- **Hosting Platform**: Heroku / Container Registry access with deployment permissions.
- **Database**: Supabase PostgreSQL administrative access for schema migrations.
- **Environment Secrets**: Verified configuration variables configured in platform environment manager (never committed to repository).
  - `SECRET_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - Storage & notification keys (Cloudinary, VAPID, Turnstile, email).

---

## 2. Pre-Deployment Verification

1. **Verify Clean Release Branch**:
   Ensure you are deploying from `release/production-deployment` (or a tagged release commit).
2. **Execute Database Migrations**:
   If there are pending SQL migrations in `migrations/`:
   - Open Supabase SQL Editor.
   - Run any unapplied migrations in ascending numeric sequence (e.g. `026_*.sql`, `027_*.sql`).
3. **Build & Verify Production Package**:
   ```bash
   python release/build-production-artifact.py
   ```
   Ensure output reports `Artifact successfully packaged and verified` with zero security leaks.

---

## 3. Deployment Steps

### Option A: Heroku Git Deployment
```bash
# Push release branch to Heroku remote
git push heroku release/production-deployment:main
```

### Option B: Docker Container Deployment
```bash
# Build production multi-stage image
docker build -t abhihub:latest .

# Run local sanity check
docker run --rm -p 5000:5000 \
  -e SECRET_KEY="test-secret" \
  -e SUPABASE_URL="https://example.supabase.co" \
  -e SUPABASE_KEY="test-key" \
  abhihub:latest

# Push to container registry & release
docker tag abhihub:latest registry.heroku.com/abhihub/web
docker push registry.heroku.com/abhihub/web
heroku container:release web -a abhihub
```

---

## 4. Post-Deployment Smoke Verification

1. **Liveness Check**:
   ```bash
   curl -i https://<your-production-domain>/health
   # Expected: HTTP/1.1 200 OK
   # Body: {"service":"abhihub","status":"healthy",...}
   ```
2. **PWA & Static Asset Check**:
   - `curl -i https://<your-production-domain>/static/sw.js` (Must return HTTP 200)
   - `curl -i https://<your-production-domain>/static/manifest.json` (Must return HTTP 200)
   - `curl -i https://<your-production-domain>/static/css/tailwind.min.css` (Must return HTTP 200)
3. **Core Journey Sanity**:
   - Navigate to `/` in a browser.
   - Verify landing page renders and notification bell initializes without console errors.
   - Test search query resolution.

---

## 5. Deployment Troubleshooting
- **H10 / Crash on Startup**: Verify `SUPABASE_URL` and `SUPABASE_KEY` config vars are non-empty.
- **WebSocket 502 Errors**: Ensure Gunicorn is using `geventwebsocket.gunicorn.workers.GeventWebSocketWorker` with single-process worker (`-w 1`).
- **Static Asset 404s**: Confirm `npm run build:css` was executed and `static/css/tailwind.min.css` is present.
