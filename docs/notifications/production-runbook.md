# AbhiHub Notification Production Runbook

**Version:** 1.0.0  
**Target Environments:** Staging (`https://staging.abhihub.com`), Production (`https://abhihub.com`)  
**Channel Scope:** In-App Notifications (`abhihub.notifications`), Web Push (`abhihub.push_subscriptions`)  

---

## 1. Environment & Secrets Configuration

Ensure the following variables are configured in the production environment (e.g. Heroku Config Vars / Cloudflare / Server `.env`):

| Variable | Required | Description | Example / Format |
| :--- | :---: | :--- | :--- |
| `VAPID_PUBLIC_KEY` | **Yes** | Web Push public application server key (base64url) | `BNx...` |
| `VAPID_PRIVATE_KEY` | **Yes** | Web Push private server key (Never commit to git!) | `9F4...` |
| `VAPID_CLAIMS_EMAIL` | **Yes** | Contact email for Web Push provider identify (`mailto:`) | `mailto:admin@abhihub.com` |
| `ADMIN_EMAILS` | **Yes** | Comma-separated admin emails authorized to broadcast push | `admin@abhihub.com` |
| `SUPABASE_URL` | **Yes** | Supabase project URL | `https://xyz.supabase.co` |
| `SUPABASE_KEY` | **Yes** | Supabase service_role / anon key | `eyJhbG...` |

### Generating New VAPID Keys
To generate a new key pair if migrating or rotating:
```bash
python dev/scripts/generate_vapid.py
```
Copy `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` into production environment variables.

---

## 2. Database Migration Checklist

Run the following migrations in the Supabase SQL editor:
1. `migrations/026_add_missing_notification_types.sql`
2. `migrations/027_notification_reliability_enhancements.sql`

Verify tables:
```sql
-- Verify push_subscriptions columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'abhihub' AND table_name = 'push_subscriptions';

-- Verify profiles preference columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'abhihub' AND table_name = 'profiles' 
  AND column_name LIKE 'notif_%';
```

---

## 3. Service Worker Verification

The service worker is served at `/sw.js` with the following HTTP headers:
- `Content-Type: application/javascript`
- `Cache-Control: no-cache`
- `Service-Worker-Allowed: /`

Verify via curl:
```bash
curl -I https://abhihub.com/sw.js
```
Confirm response contains `HTTP/2 200` and `Service-Worker-Allowed: /`.

---

## 4. Troubleshooting & Operational Guide

### Issue A: Push Permission Denied by User
- **Symptom**: Bell indicator shows 🔕, push toggle disabled.
- **Cause**: User clicked "Block" on browser native permission dialog.
- **Resolution**: Prompt user to click the lock/tune icon in their browser address bar, reset Notification permissions to "Allow", and reload the page.

### Issue B: iOS Push Notifications Not Arriving
- **Symptom**: Push fails or is unsupported on iPhone/iPad.
- **Root Cause**: Apple Web Push requires the web app to be added to the Home Screen as an **Installed PWA** (iOS 16.4+). In-tab Safari does not support PushManager.
- **Resolution**: Guide iOS users to use Safari's "Share" -> "Add to Home Screen". Once opened from the home screen, Web Push permissions can be granted. In-app bell notifications work in all browsers.

### Issue C: High Stale Endpoint / Expired Token Rate (HTTP 410)
- **Symptom**: Increased `expired` count in push delivery logs.
- **Root Cause**: Users cleared browser storage, uninstalled browser, or OS revoked push token.
- **Behavior**: Automatic cleanup — `push_notifications.py` automatically detects HTTP 404/410 from Web Push endpoints and deletes the dead row from `abhihub.push_subscriptions`.

### Issue D: Database / Supabase Connectivity Disruption
- **Symptom**: API endpoints return 500 or degraded status.
- **Behavior**: In-app notifications gracefully degrade; push sending logs warning and does not crash upload, note view, or chat messaging pipelines.

---

## 5. Rollback Procedure

If issues occur with Web Push delivery in production:

### Soft Rollback (Disable Push Delivery):
Set `VAPID_PUBLIC_KEY=""` and `VAPID_PRIVATE_KEY=""` in production environment variables.
- All push send calls will gracefully log warnings without throwing exceptions.
- In-app notification bell continues working normally via `/api/my-notifications`.

### Full Git Rollback:
If code rollback is needed:
```bash
git checkout main
# or revert specific commit:
git revert <commit-hash>
```
Deploy the stable commit. Database schema additions in `027_notification_reliability_enhancements.sql` are backward-compatible and do not need to be rolled back.
