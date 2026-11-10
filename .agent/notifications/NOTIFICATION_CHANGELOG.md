# AbhiHub Notification Changelog (Quality & Reliability 2.0)

**Date:** 2026-11-10  
**Release:** v2.1.0  
**Author:** Antigravity Engineering  

---

## Changes Implemented

### 1. Security & Authorization
- **Fixed SEC-01 Auth Bypass ([`push_api.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py)):** Replaced insecure `(ADMIN_EMAILS and user_email not in ADMIN_EMAILS)` condition on `/api/push/send` with strict fail-closed role check `is_admin_user()`.
- **Fixed SEC-02 Endpoint Ownership Check ([`push_api.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py)):** Added ownership validation to `/api/push/unsubscribe` ensuring users cannot delete push endpoints registered to other user IDs.
- **Fixed SEC-04 Broadcast Flooding ([`methods/supabase_helper.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py)):** Decommissioned platform-wide push broadcasts on single document uploads; retained targeted in-app notices.

### 2. Content & Brand Quality
- **Decommissioned Clickbait Engine ([`push_notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py)):** Replaced `psychologize_notification()` with `format_notification()` adhering to WCAG and Google Safe Browsing anti-spam standards:
  - Stripped emojis (`👀`, `⚡`, `🎖️`, `💬`, `🔥`, `💸`, `📄`, `🎉`).
  - Added uniform brand prefix `AbhiHub · [Category / Event]`.
  - Replaced speculative curiosity text with factual, educational copy.
- **Deep-Linked File Uploads ([`methods/upload_notifier.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/upload_notifier.py)):** Directed upload success notifications straight to `/resource/{file_id}` instead of `/dashboard`.
- **Cleaned Financial Notices ([`methods/payment_engine.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/payment_engine.py)):** Removed currency emoji `💸` from payout alert titles.

### 3. Categories & User Preferences
- **Enforced Canonical Categories ([`push_notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py)):** Mapped dispatch categories (`academic`, `uploads`, `chat`, `crush`, `account`, `platform`) to user profile settings. Notifications are suppressed immediately if the recipient disabled that specific category.

### 4. Service Worker Consolidation
- **Deprecated Legacy Worker ([`static/js/service-worker.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/js/service-worker.js)):** Transformed orphaned service worker into a self-unregistering migration stub, leaving `static/sw.js` as the sole canonical PWA and push handler.

### 5. Automated Testing
- Added automated pytest coverage in [`tests/test_notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/tests/test_notifications.py) for fail-closed admin checks and category opt-out enforcement (23/23 tests passing).
