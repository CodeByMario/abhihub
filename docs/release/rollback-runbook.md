# AbhiHub Production Rollback Runbook

## 1. Rollback Triggers & Criteria
Trigger immediate rollback if:
- Health check `GET /health` fails (> 3 consecutive 5xx responses).
- Core user flows (login, document viewing, search) suffer widespread 500 errors.
- Critical regression in WebSocket connection stability or memory consumption.
- Critical security flaw discovered in newly deployed build.

---

## 2. Instant Application Rollback

### Option A: Heroku Instant Rollback
```bash
# View recent releases
heroku releases -a abhihub

# Roll back to previous known stable release (e.g., v142)
heroku rollback v142 -a abhihub
```

### Option B: Docker Container Tag Revert
```bash
# Re-tag and release previous stable image digest
docker tag registry.heroku.com/abhihub/web:<previous-stable-tag> registry.heroku.com/abhihub/web:latest
docker push registry.heroku.com/abhihub/web:latest
heroku container:release web -a abhihub
```

---

## 3. Database Schema Rollback Protocol

- **Additive Migration Safety**: All production migrations in `migrations/` are forward-compatible (new columns with default values, non-breaking indexes).
- **Rollback Safety**: Previous releases can safely operate with newer schema columns present.
- If a specific migration must be undone:
  1. Inspect the migration SQL file in `migrations/`.
  2. Write an explicit reverse SQL statement (e.g., `ALTER TABLE abhihub.notifications DROP COLUMN IF EXISTS ...;`).
  3. Execute in Supabase SQL Editor during maintenance window.

---

## 4. Post-Rollback Validation

1. **Verify Health Endpoint**:
   ```bash
   curl -i https://<your-production-domain>/health
   ```
2. **Inspect Server Logs**:
   ```bash
   heroku logs --tail -a abhihub
   ```
   Confirm zero unhandled tracebacks or crash loops.
3. **Notify Stakeholders**:
   Record incident details, rollback timestamp, and root cause in incident log.
