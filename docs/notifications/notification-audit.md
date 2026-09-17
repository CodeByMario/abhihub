# AbhiHub Notification Reliability & Architecture Audit

**Date:** 2026-09-11  
**Agent:** Notification Reliability Agent (AbhiHub)  
**Branch:** `fix/notifications-cross-platform`  
**Status:** Audit Completed — Pending User Review & Approval  

---

## 1. Executive Summary

This comprehensive audit evaluates the end-to-end notification ecosystem of AbhiHub across frontend clients, backend orchestration, data persistence, service workers, web push providers, and cross-platform browser support.

AbhiHub utilizes a hybrid notification architecture:
1. **In-App Notifications (Notification Center / Bell)**: Backed by the PostgreSQL `notifications` table in Supabase, queried through `/api/my-notifications`, rendered via `static/js/notification-bell.js`.
2. **Web Push Notifications (Foreground, Background & PWA)**: Backed by standard Web Push (IETF RFC 8030 / RFC 8291 / RFC 8292) using `pywebpush` and VAPID authentication, with subscriptions stored in PostgreSQL `push_subscriptions`.

While previous fixes addressed high-priority syntax and escape errors, our deep audit identified architectural enhancements, provider isolation needs, idempotent outbox patterns, and platform-specific reliability hardening required for production readiness.

---

## 2. Notification Provider & Architecture

### 2.1 Provider Details
- **Current Primary Provider:** Web Push (`pywebpush` 2.0.0+) using standard VAPID (Voluntary Application Server Identification) key pairs (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_EMAIL`).
- **Persistence Layer:** Supabase PostgreSQL (`push_subscriptions`, `notifications`, `profiles`).
- **Adapter Design:** Currently, push logic is tightly coupled within `push_notifications.py`. Phase 2 will introduce a provider-independent `NotificationService` interface backed by a modular `WebPushAdapter` (and ready for future FCM/OneSignal/APNs plugins).

### 2.2 Frontend & Backend Codebase Inventory

| Area | Component / File | Purpose & Status |
| :--- | :--- | :--- |
| **Backend Core** | `push_notifications.py` | Web push dispatching, in-memory deduplication, preference validation, retry & 404/410 eviction. |
| **Backend API** | `push_api.py` | REST endpoints for VAPID key delivery, subscription lifecycle, unsubscribe, status, preference management, and admin broadcast. |
| **Data Access** | `data/notifications.py` | High-level data models (`Notification`, `PushSubscription`) wrapping Supabase client. |
| **Helper Methods** | `methods/supabase_helper.py` | Direct CRUD queries for `push_subscriptions` and `notifications`. |
| **Service Worker** | `static/sw.js` (served at `/sw.js`) | Unified service worker handling offline caching, encrypted PDFs, `push`, `notificationclick`, `notificationclose`, and background sync. |
| **Push Client** | `static/js/push-notifications.js` | Client-side capability detection, VAPID subscription, platform metadata collection, server sync. |
| **In-App Bell** | `static/js/notification-bell.js` | Polling `/api/my-notifications`, badge updates, dropdown rendering, mark-read interaction. |
| **Triggers** | `methods/upload_notifier.py`, `app.py` | Event-based dispatches for note uploads, chat messages, and administrative announcements. |
| **Settings UI** | `templates/settings.html` | User preference toggles connected to `/api/user/notification-preferences`. |

---

## 3. Detailed Component Audit

### 3.1 Service Worker & Registration Scope
- **File:** `static/sw.js` served at `/sw.js` with root scope (`/`).
- **Headers:** Handled via Flask route `@app.route('/sw.js')` with `Service-Worker-Allowed: /` and `Cache-Control: no-cache, no-store, must-revalidate`.
- **Status:** Unified service worker consolidation is active. Legacy references to `/static/js/service-worker.js` and `/service-worker.js` have been eliminated.
- **Push Handlers:**
  - `push` event: Extracts JSON payload (or text fallback), displays persistent notification via `self.registration.showNotification` with badge, icon, tag, and actions.
  - `notificationclick` event: Closes notification, checks if an existing AbhiHub client window is open to navigate and focus, or opens a new window via `clients.openWindow(url)`.
  - `notificationclose` event: Logs analytics event for notification dismissal.

### 3.2 VAPID & Push Configuration
- Public key provided to clients via `GET /api/push/vapid-public-key`.
- Application server key converted from URL-safe Base64 to `Uint8Array` before invoking `pushManager.subscribe`.
- `userVisibleOnly: true` strictly enforced.
- Private key resides exclusively in server environment variables (`VAPID_PRIVATE_KEY`), never exposed to frontend bundles or client logs.

### 3.3 Device & Subscription Storage
- Stored in `abhihub.push_subscriptions` with fields:
  - `id` (UUID), `user_id` (UUID foreign key to `profiles.id`)
  - `endpoint` (Unique text), `p256dh` (text), `auth` (text)
  - `device_type` (`desktop`, `mobile`, `tablet`)
  - `platform` (`windows`, `macos`, `linux`, `android`, `ios`, `unknown`)
  - `browser` (`chrome`, `firefox`, `edge`, `safari`, `unknown`)
  - `permission_state` (`granted`, `denied`, `unknown`)
  - `enabled` (boolean), `created_at`, `last_seen_at`, `last_success_at`, `last_failure_at`, `failure_code`
- **Multi-Device Support:** A single user can have multiple subscription endpoints (e.g. laptop Chrome + Android mobile). `push_notifications.py` dispatches to all active endpoints for that user.

### 3.4 Notification Triggers Inventory
1. **Upload Approvals & New Materials:** Triggered via `methods/upload_notifier.py` when notes, PYQs, or syllabus files are published.
2. **Chat Messages:** Direct peer-to-peer or server-notified chat message events in `app.py`.
3. **Admin Broadcast Announcements:** `/api/push/send` triggered by authenticated admins.
4. **Account & System Alerts:** Profile milestone achievements, system maintenance alerts.

### 3.5 Permission Request Flow & UX
- **No Aggressive Prompts:** Application never requests notification permission automatically on initial page load.
- **User-Initiated Nudge:** Permission is requested only after explicit user interaction:
  - Clicking "Enable notifications" on the profile completion card.
  - Clicking the notification toggle in user settings (`/settings`).
  - Clicking "Enable push" within the in-app notification dropdown.
- **Permission States Handled:**
  - `default`: Prompts user with explanation modal/nudge.
  - `granted`: Subscribes via PushManager and syncs subscription to backend.
  - `denied`: Suppresses browser prompt, informs user in UI with browser-specific instructions to unblock.

### 3.6 Foreground & Background Handlers
- **Foreground (Tab Open):**
  - In-app notification bell polls `/api/my-notifications` every 60 seconds (or immediately on user events).
  - Badge counter updates dynamically.
  - Web Push service worker also displays notification banner if push is enabled.
- **Background (Tab Minimized / Browser in Background):**
  - Push service worker wakes up in background, displays native OS notification banner.
- **Closed Tab / Browser Terminated:**
  - On Desktop (Chrome, Edge) with background process enabled: Notification displays reliably.
  - On Android: Notification displays via system notification tray.
  - On iOS: Requires PWA installed to Home Screen (iOS 16.4+).

### 3.7 Click & Deep-Link Behavior
- Destination URLs sanitized via `sanitize_url()` in `push_notifications.py` and strictly validated in `static/sw.js`.
- Restricted to allowlisted relative routes: `/dashboard`, `/profile`, `/resource`, `/chat`, `/settings`, `/notifications`, `/pyqs`, `/notes`.
- Disallows protocol-relative URLs (`//evil.com`), backslashes, and external schemes.
- Navigates existing open tab if available, avoiding duplicate tab spawns.

### 3.8 Retries & Duplicate Prevention
- **In-Memory Deduplication:** 30-second sliding window cache (`_DEDUPE_CACHE`) prevents duplicate dispatches of identical notifications to the same recipient.
- **Transient Retry:** 1 retry with backoff for HTTP 5xx errors from push endpoints.
- **Stale Token Pruning:** HTTP 404 and 410 (Gone) responses from push service immediately mark the subscription inactive or delete it from the database.

---

## 4. Platform & Browser Limitations Matrix

| Platform / Browser | Support Level | Requirements & Known Limitations |
| :--- | :--- | :--- |
| **Windows — Chrome / Edge** | Full | Works in foreground, background, and closed tab (with background apps enabled). Full action buttons supported. |
| **Windows / Linux — Firefox** | Full | Standard Web Push support. Requires browser process running for closed-tab receipt. |
| **macOS — Chrome / Edge / Firefox** | Full | OS notification permission must be enabled in macOS System Settings. |
| **macOS — Safari 16+** | Full | Supported via standard Web Push VAPID on macOS Ventura+. |
| **Android — Chrome / Samsung Internet** | Full | Full push support in foreground, background, and closed browser. Battery optimization may delay delivery on aggressive OEM skins (Xiaomi, Huawei, Samsung). |
| **Android — Firefox** | Full | Supported with active service worker. |
| **iOS / iPadOS 16.4+ (Safari)** | Conditional | Push requires web app to be **Added to Home Screen (PWA)**. Standard browser tabs cannot receive Web Push when Safari is closed. |
| **iOS / iPadOS < 16.4** | In-App Only | Web Push not supported by Apple OS. Falls back gracefully to in-app bell notification. |

---

## 5. Security, Privacy & Compliance Audit

1. **VAPID Credentials Security:**
   - Public key is publicly readable (`/api/push/vapid-public-key`).
   - Private key is restricted to environment variable `VAPID_PRIVATE_KEY` and never logged or exposed in client payloads.
2. **Access Control on Send Endpoints:**
   - Broadcast endpoint `/api/push/send` is strictly restricted to authenticated administrators (`ADMIN_EMAILS`).
   - In-app notification mark-read endpoints require session authentication and validate ownership (`user_id == session.user.uid`).
3. **Payload Sanitization & PII Protection:**
   - Notification titles and bodies contain only non-sensitive summary text.
   - Never transmits passwords, auth tokens, session IDs, private notes, or student PII in push payloads.
4. **Deep-Link URL Injection Protection:**
   - Strict allowlist filtering prevents open redirect vulnerabilities.
5. **Privacy & Preference Respect:**
   - Users can toggle Push notifications and specific categories (Uploads, Chat, Crush alerts) in `/settings`.
   - Backend verifies preference before dispatching push.

---

## 6. Identified Gaps & Production-Readiness Plan

While foundational capabilities are operational, the following enhancements are planned for full production hardening:

1. **Provider-Independent Notification Service Layer (`NotificationService`):**
   - Formalize adapter interface to isolate Web Push, FCM, or future providers.
2. **Persistent Idempotent Outbox & Delivery Logging:**
   - Track notification delivery lifecycle (`queued`, `sent`, `failed`, `opened`, `expired`) with non-sensitive metadata.
3. **iOS PWA Installation Guidance UI:**
   - Display contextual prompt for iOS Safari users explaining how to "Add to Home Screen" to enable push notifications.
4. **Comprehensive Automated Test Coverage:**
   - Unit and integration tests for preference checking, deduplication, URL sanitization, stale token pruning, and error recovery.
5. **Production Test Runbook:**
   - Detailed step-by-step verification guide across mobile and desktop devices.
