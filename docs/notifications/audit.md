# AbhiHub Notification Reliability Audit

**Date:** 2026-09-11  
**Auditor:** Notification Reliability Agent  
**Branch:** `fix/notifications-cross-device`  
**Status:** Audit Completed — Awaiting User Approval  

---

## 1. Executive Summary

An end-to-end audit of the notification subsystem in AbhiHub was conducted across backend services, database models, frontend scripts, service workers, and scheduled tasks. 

AbhiHub uses a hybrid notification architecture:
1. **In-App Notifications**: Backed by the PostgreSQL `notifications` table via Supabase, polled by the frontend (`/api/my-notifications`, `notification-bell.js`).
2. **Web Push Notifications**: Backed by standard Web Push (`pywebpush`) with VAPID authentication, storing subscription endpoints in `push_subscriptions` table.

Multiple severe reliability, architectural, and security defects were identified that prevent cross-device reliability and expose critical security vulnerabilities.

---

## 2. System Architecture & Component Inventory

| Component | Technology / Implementation | Source File(s) |
| :--- | :--- | :--- |
| **Notification Provider** | Web Push (`pywebpush` + VAPID) | `push_notifications.py`, `push_api.py` |
| **Database & ORM** | Supabase PostgreSQL (`notifications`, `push_subscriptions`) | `data/notifications.py`, `methods/supabase_helper.py` |
| **Frontend Framework** | Vanilla JS + Jinja2 Templates + HTML5 Notification API | `static/js/push-notifications.js`, `static/js/notification-bell.js`, `templates/` |
| **Service Worker** | Multi-worker split (`/sw.js` vs `/static/js/service-worker.js`) | `static/sw.js`, `static/js/service-worker.js` |
| **Background Scheduler**| APScheduler / Python background task | `scheduled_tasks.py`, `methods/upload_notifier.py` |
| **User Preferences** | Client-side `localStorage` only (disconnected from backend) | `templates/settings.html` |
| **HTTPS / Deployment** | Gunicorn behind HTTPS reverse proxy (`https://abhihub.com`) | `gunicorn.conf.py`, `app.py` |

---

## 3. Detailed Findings & Root Cause Analysis

### Finding 1: Broken Frontend Rendering (`ReferenceError: escapeHtml is not defined`)
- **Severity**: Critical (High Impact on UI)
- **Location**: `static/js/notification-bell.js` (lines 49-50)
- **Description**: When `renderNotifs` iterates over user notifications fetched from `/api/my-notifications`, it calls `escapeHtml(n.title)` and `escapeHtml(n.message)`. However, `escapeHtml` is not defined in `notification-bell.js` or in the global scope of `p_struct.html`.
- **Root Cause**: Missing utility function definition in `notification-bell.js`.
- **Impact**: Any user with 1 or more notifications experiences a JavaScript runtime exception when opening the notification panel, crashing the bell UI.

### Finding 2: Conflicting & Broken Service Worker Registrations
- **Severity**: Critical (High Impact on Push Delivery)
- **Locations**:
  - `templates/p_struct.html` registers `/sw.js` (scope: `/`)
  - `static/js/push-notifications.js` (line 41) registers `/static/js/service-worker.js` (scope: `/`)
  - `static/index.js` (line 271) registers `/service-worker.js` (returns HTTP 404)
- **Root Cause**: Three different service worker registration targets with conflicting scopes and handlers. Browser rejects registering `/static/js/service-worker.js` at root scope `/` due to missing `Service-Worker-Allowed: /` header on static file routes.
- **Impact**: Service worker registration fails intermittently, push events are routed to inconsistent handlers, and offline PWA caching conflicts with push listeners.

### Finding 3: Severe Security Hole — Unauthenticated Public Push Broadcast
- **Severity**: Critical (Vulnerability)
- **Location**: `push_api.py` (`@push_api.route('/api/push/send', methods=['POST'])`)
- **Description**: The endpoint `/api/push/send` allows any unauthenticated actor to POST arbitrary JSON and broadcast push messages to all registered devices in the database.
- **Root Cause**: Missing authentication (`@auth_required`), admin verification (`is_admin`), CSRF token validation, and rate limiting.
- **Impact**: Potential malicious spam broadcast to all subscribed users.

### Finding 4: Subscription ID & Parameter Mismatch in Push API
- **Severity**: High (Prevents Token Registration)
- **Locations**: `push_api.py` (line 48) and `push_notifications.py` (lines 45-64)
- **Description**: `push_api.py` retrieves `user.get('email')` and passes it as the first argument to `add_subscription(user_email, subscription)`. However, `add_subscription` treats parameter 1 as `user_id` (UUID) and invokes `Profile.get_email_by_id(user_id)`. Passing an email where a UUID is expected returns `None`, failing to register the subscription.
- **Root Cause**: Inconsistent parameter semantics (email vs UUID) between API layer and data helper.

### Finding 5: Disconnected User Preferences (Client-Only `localStorage`)
- **Severity**: Medium (Functional & Privacy Defect)
- **Location**: `templates/settings.html` (`saveNotifSetting`)
- **Description**: User notification toggles (Push, Email, Crush) are saved purely in browser `localStorage` under keys `notif_push`, `notif_email`, `notif_crush`.
- **Root Cause**: No backend API or database columns exist to persist user preferences to `abhihub.profiles` or `user_preferences`.
- **Impact**: Backend notification senders (`upload_notifier.py`, `app.py`) cannot inspect user opt-outs before sending push notifications.

### Finding 6: Syntax Error in Database Migration Script
- **Severity**: Medium (Migration Tooling Failure)
- **Location**: `migrations/026_add_missing_notification_types.sql` (line 1)
- **Description**: The SQL migration starts with Python docstring quotes `"""`, causing direct execution in `psql` or Supabase SQL editor to fail with a syntax error.

### Finding 7: Lack of Idempotent Outbox & Delivery Deduplication
- **Severity**: Medium (Reliability Risk)
- **Locations**: `push_notifications.py`, `methods/upload_notifier.py`, `app.py`
- **Description**: Notifications are sent directly via synchronous network calls without an idempotent outbox table or message deduplication keys.
- **Root Cause**: No delivery queue or state tracking for message dispatch.

---

## 4. Current Channel & Device Matrix

| Channel | Platform | Current State | Target State |
| :--- | :--- | :--- | :--- |
| **In-App Notifications** | Desktop & Mobile Web | Partially broken (`escapeHtml` bug) | Fully working with mark-read & badges |
| **Web Push (Desktop)** | Chrome, Firefox, Edge, Safari (macOS 16+) | Broken (SW conflict + param mismatch) | Fully working via unified `/sw.js` |
| **Web Push (Android)** | Android Chrome, Samsung Internet, PWA | Broken (SW conflict + param mismatch) | Fully working via unified `/sw.js` |
| **Web Push (iOS)** | iOS 16.4+ (Installed PWA only) | Unsupported (No standalone check/guidance) | Supported for Installed PWA |
| **Email Notifications** | All platforms | Not implemented for notifications (Auth only) | Planned / Documented as Out of Scope |
| **Native Push (FCM/APNS)** | Android / iOS Native Apps | Not applicable (No native apps in repo) | N/A |

---

## 5. Required Database Schema Enhancements

To support multi-device lifecycle tracking, the `abhihub.push_subscriptions` table must be enhanced:

```sql
-- Migration: enhance push_subscriptions table
ALTER TABLE abhihub.push_subscriptions
  ADD COLUMN IF NOT EXISTS platform text DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS browser text,
  ADD COLUMN IF NOT EXISTS permission_state text DEFAULT 'granted',
  ADD COLUMN IF NOT EXISTS enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS last_success_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_failure_at timestamptz,
  ADD COLUMN IF NOT EXISTS failure_code text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS revoked_at timestamptz;

-- Notification preference columns on profiles
ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS notif_push_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_email_enabled boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS notif_uploads_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_chat_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_crush_enabled boolean DEFAULT true;
```

---

## 6. Recommendations & Next Steps

1. **Unify Service Worker**: Consolidate push handling, caching, and background sync into `static/sw.js` served from `/sw.js`. Deprecate and remove redundant `static/js/service-worker.js`.
2. **Fix Bell UI**: Add local `escapeHtml` utility in `notification-bell.js`.
3. **Secure API Routes**: Protect `/api/push/send` with strict admin authentication; fix parameter handling in `/api/push/subscribe`.
4. **Sync Preferences**: Create `/api/user/notification-preferences` endpoint and persist settings to `profiles`.
5. **Implement Test Suite**: Add comprehensive offline unit and integration tests for push subscriptions, in-app notification creation, mark-read, and delivery error handling.
