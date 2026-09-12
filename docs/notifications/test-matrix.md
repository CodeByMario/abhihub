# AbhiHub Notification Test Matrix & Verification Plan

**Version:** 1.0.0  
**Target Environments:** Local Dev (`127.0.0.1:5000`), Staging (`https://staging.abhihub.com`), Production (`https://abhihub.com`)  
**Scope:** In-App Notifications, Web Push (VAPID), Service Worker Lifecycle, Preference Controls, Security Bounds.

---

## 1. Platform & Device Matrix

| Target Platform / Device | Browser Engine | In-App Bell | Web Push | Standalone PWA | Current Status |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Windows / macOS Laptop** | Chromium (Chrome, Edge, Brave) | Supported | Supported | Supported | ⚠️ SW Conflict / Render Bug |
| **Windows / macOS Laptop** | Gecko (Firefox) | Supported | Supported | N/A | ⚠️ SW Conflict / Render Bug |
| **macOS Laptop (16+)** | WebKit (Safari Desktop) | Supported | Supported | Supported | ⚠️ SW Scope Mismatch |
| **Android Phone / Tablet** | Chrome Mobile | Supported | Supported | Supported | ⚠️ SW Conflict |
| **Android Phone / Tablet** | Samsung Internet / Firefox Mobile | Supported | Supported | Supported | ⚠️ SW Conflict |
| **iOS / iPadOS (16.4+)** | Safari Mobile (Installed PWA) | Supported | Supported | Required | ⚠️ Requires PWA Install |
| **iOS / iPadOS (Any)** | Safari Browser (Non-PWA Tab) | Supported | Untenable (Apple Policy) | N/A | Fallback to In-App Bell |

---

## 2. Comprehensive Test Scenarios

### A. Permission & Subscription Lifecycle

| ID | Test Scenario | Preconditions | Expected Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-SUB-01** | Prompt User on Click | User clicks "Enable notifications" button | Benefit explanation shown, browser permission prompt appears | Untested |
| **TC-SUB-02** | Permission Granted Flow | User accepts browser prompt | VAPID public key fetched, endpoint registered via `/api/push/subscribe`, bell icon updates to active (🔔) | ⚠️ Fails (Param Mismatch) |
| **TC-SUB-03** | Permission Denied Flow | User blocks permission | Bell UI shows disabled icon (🔕), no API error spam, preferences reflect denied state | Untested |
| **TC-SUB-04** | Blocked in Browser Settings | Permission was previously blocked | UI informs user how to reset permissions in browser settings without crashing | Untested |
| **TC-SUB-05** | Unsupported Browser | PushManager absent | UI gracefully disables push toggles and provides in-app fallback without JS exceptions | Untested |
| **TC-SUB-06** | Insecure / Non-HTTPS | HTTP protocol | Push registration rejected gracefully, warning logged, in-app bell remains functional | Pass |
| **TC-SUB-07** | Device Unsubscribe | User toggles push off in settings | Subscription revoked locally via `pushManager.unsubscribe()`, removed from backend via `/api/push/unsubscribe` | Untested |
| **TC-SUB-08** | Multi-Device Registration | User logs into Laptop and Android phone | Two distinct endpoints saved under same `user_id` in `push_subscriptions` | ⚠️ Fails (Only 1 entry supported cleanly) |
| **TC-SUB-09** | Logout Cleanup | User logs out | Subscription marked unlinked or preserved based on shared device setting | Untested |
| **TC-SUB-10** | Stale / Expired Endpoint | Provider returns 404/410 Gone | Expired endpoint automatically pruned from `push_subscriptions` | Untested |

---

### B. Delivery & State Verification

| ID | Test Scenario | Execution Method | Expected Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-DEL-01** | In-App Bell List Render | User has 3 notifications | Notifications listed cleanly with icons and relative timestamps, no `escapeHtml` error | ❌ Fails (ReferenceError) |
| **TC-DEL-02** | Mark Single Notification Read | Click on unread item | Item marked read in DB via POST `/api/notifications/<id>/read`, unread badge count decrements | Pass |
| **TC-DEL-03** | Mark All Read | Click "Mark all read" in bell panel | All notifications updated in DB via POST `/api/my-notifications/read`, badge hidden | Pass |
| **TC-DEL-04** | Foreground Tab Push | Push received while tab is open | Push handled without duplicate noisy alert, in-app badge updates | ⚠️ Fails (SW Conflict) |
| **TC-DEL-05** | Background Tab Push | Push received with tab backgrounded | System OS notification banner displayed with icon, title, and body | ⚠️ Fails (SW Conflict) |
| **TC-DEL-06** | Closed Browser Push | Push received with browser closed | Notification delivered via OS push service; clicking opens app to destination URL | ⚠️ Fails (SW Conflict) |
| **TC-DEL-07** | Notification Click Navigation | User clicks notification banner | Active tab focused or new window opened to allowlisted route | ⚠️ Fails (SW Conflict) |
| **TC-DEL-08** | Preference Opt-Out Honor | User disables upload notifications | Event occurs (file uploaded), in-app logged but push suppressed | ❌ Fails (Prefs Not in DB) |
| **TC-DEL-09** | Upload Scheduler Trigger | File uploaded > 55 min ago | Background task runs, dispatches notification, updates document status | Pass |

---

### C. Security & Integrity Verification

| ID | Test Scenario | Attack / Edge Vector | Expected Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-SEC-01** | Cross-User Notification Leak | User A queries `/api/my-notifications` | Returns only records where `user_id == session.user.id` | Pass |
| **TC-SEC-02** | Unauthorized Push Broadcast | Public unauthenticated POST to `/api/push/send` | Must return 401 Unauthorized / 403 Forbidden | ❌ Fails (Publicly Open) |
| **TC-SEC-03** | Malicious Redirect in Click URL | Payload contains `url: "https://evil.com"` | Service worker sanitizes URL and redirects to allowlisted relative route | ⚠️ Needs Hardening |
| **TC-SEC-04** | Subscription Hijacking | User A attempts to register User B's endpoint | Endpoint bound strictly to authenticated session user ID | ⚠️ Fails (Param Bug) |
| **TC-SEC-05** | Sensitive Data in Logs | Dispatch notification containing student data | Server logs and analytics contain only notification ID and type, zero secrets or tokens | Pass |

---

## 3. Automated Test Strategy

The automated test suite (`tests/test_notifications.py`) will test:
1. `test_push_api_auth_required`: Validates that unauthorized calls to `/api/push/send` return 401/403.
2. `test_push_subscribe_parameter_binding`: Validates that `add_subscription` correctly accepts UUID and stores device metadata.
3. `test_in_app_notification_crud`: Validates creation, pagination, and mark-as-read workflows.
4. `test_preference_sync_and_filtering`: Validates that user preferences are stored in the database and respected during send dispatch.
5. `test_stale_subscription_pruning`: Validates automatic removal of expired push endpoints when mock webpush raises HTTP 410.
