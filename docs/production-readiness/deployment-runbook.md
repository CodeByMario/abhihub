# Deployment Runbook: AbhiHub

## 1. Pre-Deployment Verification
1. **Environment Variables**: Ensure all required environment variables are set in the hosting provider dashboard (Heroku config vars / server env). Never commit `.env`.
   - Required: `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` / `SUPABASE_SECRET_API_KEY`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
   - Set `FLASK_ENV=production`.
2. **Build Assets**:
   ```bash
   npm run build:css
   ```
3. **Run Automated Test Suite**:
   ```bash
   pytest tests/test_production_readiness.py
   ```

## 2. Database Migrations Order
If deploying schema updates, apply migration SQL files in numerical order via Supabase SQL Editor:
- Ensure all RLS policies from `migrations/021_enable_rls_all.sql` are active.

## 3. Deployment Procedure (Heroku)
1. Confirm branch is `chore/production-readiness` or merged to `master`/`main`.
2. Push to target remote:
   ```bash
   git push heroku chore/production-readiness:main
   ```
3. Scale web dyno:
   ```bash
   heroku ps:scale web=1
   ```

## 4. Post-Deployment Smoke Tests
1. **Health Probe**:
   ```bash
   curl -I https://www.abhihub.edu.eu.org/health
   # Expected: HTTP 200 OK with X-Content-Type-Options: nosniff
   ```
2. **Authentication Flow**: Verify Google OAuth and Email login.
3. **Document Viewing**: Verify PDF and question paper viewers load correctly.
4. **Analytics**: Verify GA4 debug view reflects page views without PII.

## 5. Rollback Procedure
If any critical failure occurs post-deployment:
1. Revert to previous release on Heroku:
   ```bash
   heroku releases:rollback
   ```
2. Alternatively, deploy previous commit:
   ```bash
   git push heroku <previous_commit_sha>:main --force
   ```
3. Verify `/health` endpoint after rollback.
