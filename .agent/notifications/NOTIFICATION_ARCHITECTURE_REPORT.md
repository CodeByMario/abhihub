# AbhiHub Notification Architecture Report (Phase 1 Discovery)

**Project:** AbhiHub  
**Module:** Notification System  
**Initiative:** Notification Quality & Reliability 2.0  
**Status:** Read-Only Audit Complete  
**Date:** 2026-11-10  

---

## 1. Executive Summary

A comprehensive, read-only architectural audit was performed on AbhiHub's notification system across client, service worker, backend application, background workers, and Supabase database schema.

### Key Discoveries
1. **Actual Provider:** Standard IETF / W3C **Web Push with VAPID authentication** via Python `pywebpush`. Push notifications are delivered through native browser push gateways (Google FCM for Chrome/Edge, Mozilla autopush for Firefox, Apple WebPush for Safari/iOS). Firebase Admin SDK is installed in the project for auth, but **FCM SDK is NOT used for push messaging**.
2. **In-App Notifications:** Backed by the Supabase PostgreSQL table `abhihub.notifications` and consumed via `data/notifications.py` and `static/js/notification-bell.js`.
3. **Service Worker Fragmentation:** The application has an active, production-grade root service worker (`/static/sw.js`, served at `/sw.js` via `routes/seo.py`), but also retains an orphaned legacy worker (`/static/js/service-worker.js`) with an older cache schema (`abhihub-v1`), creating dual-maintenance and potential split-brain risks.
4. **Duplicate Service Worker Registrations:** `/sw.js` is registered independently in 4 client scripts (`templates/p_struct.html`, `static/index.js`, `static/js/push-notifications.js`, and `static/js/pwa-install.js`).
5. **Content Quality & Clickbait Generation:** `push_notifications.py` contains a function `psychologize_notification()` that transforms standard notifications into clickbait hooks with emojis (`👀`, `⚡`, `🎖️`, `💬`, `🔥`) and speculative claims ("Students in your branch are preparing right now").
6. **No Database Push Triggers:** PostgreSQL database triggers do not emit notifications directly. All events are dispatched through Python application routes or APScheduler background jobs (`methods/upload_notifier.py`).

---

## 2. Notification Architecture & Data Flow

```
[Browser Client]
   │
   ├── Permission Prompt (`Notification.requestPermission()`)
   ├── Service Worker Registration (`navigator.serviceWorker.register('/sw.js')`)
   ├── PushManager Subscription (`swReg.pushManager.subscribe({ applicationServerKey })`)
   └── Register Subscription (POST `/api/push/subscribe`)
          │
          ▼
[Flask Backend (`push_api.py`)]
   │
   ├── Authenticates session user
   ├── Detects User-Agent platform & browser
   └── Calls `add_subscription()` (`push_notifications.py`)
          │
          ▼
[Supabase Database (`abhihub.push_subscriptions`)]
   │
   └── Upserts endpoint, p256dh, auth, device_type, platform, browser

─── Outbound Push Delivery ───

[Trigger Source: Upload Notifier / Admin Panel / Chat / System]
   │
   ▼
[Push Dispatcher (`push_notifications.py`)]
   ├── 1. Deduplication Check (`_DEDUPE_CACHE` 30s window)
   ├── 2. Frequency Cap (`MAX_PUSH_PER_24H = 6`, 10 min cooldown)
   ├── 3. Psychologize / Transform Content (`psychologize_notification()`)
   ├── 4. Fetch Subscriptions (`get_user_push_subscriptions()`)
   └── 5. `pywebpush.webpush()` with VAPID Claims
          │
          ├── Google FCM (`fcm.googleapis.com`) ──> Chrome / Edge (Desktop & Android)
          ├── Mozilla Autopush (`updates.push.services.mozilla.com`) ──> Firefox
          └── Apple Push Service (`web.push.apple.com`) ──> Safari (macOS / iOS PWA)
                 │
                 ▼
          [Client Device: `/sw.js` `push` event]
                 │
                 ├── `self.registration.showNotification(title, options)`
                 └── User Clicks ──> `notificationclick` ──> Deep-link navigation
```

---

## 3. Inventory of Notification-Related Files

| Layer | File Path | Purpose |
|---|---|---|
| **API** | [`push_api.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py) | REST routes for VAPID key, subscribe, unsubscribe, preferences, status, test |
| **Engine** | [`push_notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py) | Core VAPID Web Push delivery, deduplication, rate limiting, subscription lifecycle |
| **In-App Model** | [`data/notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/data/notifications.py) | In-app notification creation, retrieval, and read-state management |
| **DB Helper** | [`methods/supabase_helper.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py) | Subscriptions persistence, queries, and deletion helpers |
| **Scheduler** | [`methods/upload_notifier.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/upload_notifier.py) | Scans for files uploaded >= 55 mins ago to notify creators |
| **Scheduler** | [`scheduled_tasks.py`](file:///e:/Users/abhihub/New%20folder/abhihub/scheduled_tasks.py) | APScheduler task configuration (runs `upload_notifier` every 10 min) |
| **SW Delivery** | [`static/sw.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/sw.js) | Active root service worker handling `push` and `notificationclick` |
| **SW Legacy** | [`static/js/service-worker.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/js/service-worker.js) | Orphaned legacy service worker (candidate for cleanup) |
| **Frontend Client** | [`static/js/push-notifications.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/js/push-notifications.js) | Client-side VAPID fetch, permission request, and subscription POST |
| **In-App Bell** | [`static/js/notification-bell.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/js/notification-bell.js) | UI bell icon, unread badge counter, and dropdown notification feed |
| **UI Templates** | [`templates/notifications.html`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/notifications.html) | Notification center page with tabs and pagination |
| **UI Templates** | [`templates/settings/_notifications.html`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/settings/_notifications.html) | User preference toggles (Push, Email, Uploads, Chat, Quiet Hours) |
| **UI Templates** | [`templates/admin_notification_panel.html`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/admin_notification_panel.html) | Admin broadcast and direct test notification tool |

---

## 4. Detailed Component & Lifecycle Findings

### 4.1 Actual Notification Provider
- **Provider:** Direct Web Push (RFC 8030 / RFC 8291 / RFC 8292).
- **Authentication:** VAPID (Voluntary Application Server Identification) using ECDSA P-256 keys configured via `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_CLAIMS_EMAIL`.
- **Relay Mechanism:** The application calls `pywebpush.webpush()` directly to the endpoint supplied by the browser vendor during subscription.
- **Third-Party Services:** No reliance on OneSignal, Pusher, or proprietary SaaS push vendors.

### 4.2 Service Worker Registrations & Duplicate Handlers
- **Active Worker:** `static/sw.js` (served at `/sw.js` via `routes/seo.py`). Scope: `/`.
- **Duplicate Worker Found:** `static/js/service-worker.js` defines an independent `push` event handler and older cache `abhihub-v1`. It is no longer registered by active templates but remains in the static tree.
- **Multiple Registration Calls:**
  - `templates/p_struct.html` registers `/sw.js` on DOMContentLoaded.
  - `static/index.js` registers `/sw.js`.
  - `static/js/push-notifications.js` registers `/sw.js` on `registerServiceWorker()`.
  - `static/js/pwa-install.js` registers `/sw.js`.
  *Impact:* Calling `navigator.serviceWorker.register` multiple times is handled idempotently by the browser, but creates unnecessary promise overhead and inconsistent ready state handling.

### 4.3 Notification Content & Branding Issues
- **Clickbait Mutation:** `psychologize_notification()` in `push_notifications.py`:
  - Upload Success: Injects `"Your notes are live! 👀 First views rolling in..."` and `"Students in your branch are preparing right now"`.
  - Approval: Injects `"You just unlocked a verified boost! 🎖️"`.
  - Credit Deduction: Injects `"Resource unlocked! ⚡ Quick tip inside..."`.
  - Peer Messages: Injects `"...left you a study note... 💬"`.
  - Announcements: Injects `"Did you catch this yet? 👀"`.
- **Violation:** Violates the initiative's requirements for professional, non-promotional, educational, and emoji-free notification copy.

### 4.4 URL Redirection & Destination Handling
- `static/sw.js` includes an allowlist:
  ```javascript
  const ALLOWED = ['/dashboard', '/profile', '/resource', '/chat', '/settings', '/notifications', '/pyqs', '/notes', '/college'];
  ```
- **Issue:** In `upload_notifier.py`, when a file upload is notified, the URL is hardcoded to `/dashboard` instead of deep-linking directly to `/resource/<id>`.

### 4.5 Subscription Lifecycle & Error Handling
- **Dead Subscription Pruning:** In `push_notifications.py`, HTTP 404 (Not Found) and HTTP 410 (Gone) responses from push services cleanly trigger `remove_push_subscription_by_endpoint()`.
- **Upsert Deduplication:** `push_subscriptions` uses `endpoint` as unique conflict key, preventing duplicate records for the same browser endpoint.
- **Frequency Cap:** Enforces a maximum of 6 notifications per 24 hours per user and a 10-minute cooldown between non-chat pushes (`_USER_DELIVERY_TIMESTAMPS`).

---

## 5. Identified Problem Areas & Severity Matrix

| ID | Issue Description | Location | Severity |
|---|---|---|---|
| **ISSUE-01** | **Clickbait & Emoji Content Generation:** Notification copy is systematically modified with emojis and speculative claims | `push_notifications.py:140-196` | **HIGH** |
| **ISSUE-02** | **Orphaned Duplicate Service Worker:** Legacy `static/js/service-worker.js` exists alongside `static/sw.js` | `static/js/service-worker.js` | **MEDIUM** |
| **ISSUE-03** | **Quadruple SW Registration:** 4 distinct scripts invoke `navigator.serviceWorker.register('/sw.js')` | `p_struct.html`, `index.js`, `push-notifications.js`, `pwa-install.js` | **LOW** |
| **ISSUE-04** | **Sub-optimal Deep-linking for Uploads:** Upload notifications redirect to `/dashboard` instead of the specific resource | `methods/upload_notifier.py:92` | **MEDIUM** |
| **ISSUE-05** | **Dual Data Access Layer for Notifications:** Queries for notifications and subscriptions are split between `data/notifications.py` and `methods/supabase_helper.py` | `data/notifications.py` & `methods/supabase_helper.py` | **LOW** |

---

## 6. Recommendations for Phase 2 Implementation (Pending Approval)

1. **Disable `psychologize_notification()` or replace with clean, informative templates:**
   - Standardize titles to official AbhiHub format (e.g. `AbhiHub · Document Published`, `AbhiHub · Examination Update`).
   - Remove all speculative phrasing and decorative emojis.
2. **Consolidate Service Worker:**
   - Archive or deprecate `static/js/service-worker.js`.
   - Ensure `static/sw.js` remains the single canonical source of truth for caching, background sync, and push events.
3. **Harmonize Client Registration:**
   - Use a single centralized initialization hook in `push-notifications.js` that coordinates with `p_struct.html`.
4. **Deep-Link File Uploads:**
   - Update `methods/upload_notifier.py` to target `/resource/<file_id>` directly.
5. **Add Notification Category & Preference Check in Dispatcher:**
   - Verify recipient's category preferences (`notif_uploads_enabled`, `notif_chat_enabled`) prior to invoking `pywebpush`.

---

*Report generated in strict compliance with READ_ONLY_AUDIT execution rules. No code, database schemas, or production settings were modified.*
