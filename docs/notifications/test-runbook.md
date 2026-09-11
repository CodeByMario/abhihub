# AbhiHub Notification Manual Verification Runbook

**Date:** 2026-09-11  
**Branch:** `fix/notifications-cross-platform`  
**Purpose:** Standard operating procedure for verifying notification delivery, in-app bell fallback, permission states, and deep-linking across desktop and mobile platforms.

---

## Prerequisites

1. Active staging or local environment running over HTTPS (or `localhost` for local dev).
2. Valid `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` set in environment.
3. Supabase database initialized with migrations `026_add_missing_notification_types.sql` and `027_notification_reliability_enhancements.sql`.
4. Staging test account created (`test_student@example.com`).

---

## Verification Test Cases

### 1. User Authentication & Initial State
- **Action:** Open `https://abhihub.com` (or `http://localhost:5000`) in Chrome/Edge. Log in with test account.
- **Expected:** In-app notification bell is visible in the top header. No aggressive or unsolicited browser permission prompt appears on page load.

### 2. User-Gesture Permission & Push Subscription
- **Action:** Navigate to `/settings` -> **Notifications** section (or click "Enable Notifications" on profile nudge).
- **Expected:** Browser permission dialog is presented. Upon clicking "Allow", subscription endpoint is registered via `POST /api/push/subscribe`. Unredacted keys are not logged to browser console or network reports.

### 3. Self-Test Notification (Foreground)
- **Action:** While on `/settings`, click **"🧪 Send Test Notification"**.
- **Expected:**
  1. Instant toast: *"🔔 Test notification dispatched!"*.
  2. Native OS notification banner appears: *"AbhiHub Test Notification"*.
  3. In-app bell badge increments with dynamic unread indicator.

### 4. Background Delivery (Tab Minimized / Unfocused)
- **Action:** Minimize the browser tab or switch to another window. Trigger a test notification or send a message from a secondary account.
- **Expected:** OS native notification banner displays in the desktop notification center / system tray.

### 5. Closed Tab Delivery (Laptop / Desktop)
- **Action:** Close all AbhiHub browser tabs while keeping the browser process active. Trigger an announcement from admin or test script.
- **Expected:** Service Worker wakes up via Web Push daemon; notification banner appears with AbhiHub icon and "Open" / "Dismiss" action buttons.

### 6. Notification Click & Deep-Link Navigation
- **Action:** Click the notification banner or the "Open" action button.
- **Expected:**
  1. If an existing tab is open, it focuses and navigates to the target route (`/settings` or `/dashboard`).
  2. If no tab is open, a new window launches directly into the target route.
  3. Notification open event is tracked (`POST /api/notifications/{id}/open`).
  4. Disallowed or external URLs (e.g. `https://evil.com`) are automatically sanitized to `/dashboard`.

### 7. Mobile Android Verification (Chrome / Samsung Internet)
- **Action:** Log in on Android Chrome. Grant permission. Put phone on lock screen and send test notification.
- **Expected:** Native Android push notification appears with vibration and badge icon. Tapping it wakes the browser to the deep-link destination.

### 8. iOS Safari PWA Verification (iOS 16.4+)
- **Action:** Open AbhiHub in iOS Safari.
- **Expected:**
  1. Settings page displays the blue guidance banner: *"🍎 iOS Notifications Setup"*.
  2. User taps **Share** -> **"Add to Home Screen"**.
  3. Launching from the Home Screen PWA icon enables push notifications seamlessly.

### 9. Permission Denied & In-App Center Fallback
- **Action:** Set notification permission to "Block" in browser site settings. Reload the app.
- **Expected:**
  1. App does not crash or throw unhandled exceptions.
  2. In-app notification bell continues working 100% via periodic polling of `/api/my-notifications`.
  3. Clicking bell shows dropdown with recent notifications and "Mark all read" button.

### 10. Deduplication & Idempotency Check
- **Action:** Send 3 rapid duplicate test requests with the same title/tag within 5 seconds.
- **Expected:** First request is delivered; subsequent 2 requests return `{"success": true, "suppressed": true, "reason": "deduplicated"}` and do not trigger extra OS banners.

### 11. Stale Subscription Pruning (404/410)
- **Action:** Unsubscribe device or simulate expired endpoint. Dispatch notification.
- **Expected:** Backend catches HTTP 410 (Gone), automatically prunes the endpoint from `push_subscriptions`, and increments `expired` count.

### 12. Security & Privacy Inspection
- **Action:** Inspect browser network tab, server logs, and analytics events.
- **Expected:**
  - VAPID private key is never transmitted or logged.
  - Payloads contain only non-sensitive summary text (no passwords, private notes, or student PII).
  - `/api/push/send` rejects all non-admin requests with HTTP 403.

---

## Rollback & Emergency Procedures

If notification delivery issues arise in production:
1. **Disable Push Globally:** Toggle `notif_push_enabled = false` in database profiles or set environment variable `VAPID_PUBLIC_KEY=""`.
2. **In-App Resiliency:** In-app notification center operates independently of push provider health and remains fully active.
3. **Provider Rotation:** Update `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in environment; clients will seamlessly re-subscribe on their next session.
