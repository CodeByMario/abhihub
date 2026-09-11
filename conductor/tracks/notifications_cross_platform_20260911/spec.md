# Specification: Cross-Platform Notification Reliability Hardening

**Track ID:** `notifications_cross_platform_20260911`  
**Status:** Draft / Planned  
**Auditor/Author:** Notification Reliability Agent  

---

## 1. Overview & Objective

The objective of this track is to harden and formalize AbhiHub's cross-platform notification subsystem. The system must operate seamlessly on supported desktop (Windows, macOS, Linux) and mobile (Android, iOS PWA) browsers, providing reliable foreground, background, and offline receipt, with persistent in-app fallback, strict privacy protection, and bounded deduplication.

---

## 2. Functional Requirements

1. **Provider-Independent Architecture (`NotificationService`):**
   - Provide an abstract notification dispatch interface with standard methods:
     - `send_notification(user_id, title, body, url, category, tag, dedupe_key)`
     - `send_notification_to_all(title, body, url, category, tag)`
     - `get_user_preferences(user_id)` / `update_user_preferences(user_id, prefs)`
     - `register_subscription(user_id, sub_info, metadata)`
     - `remove_subscription(endpoint)`
   - Implement a modular `WebPushAdapter` backed by `pywebpush` and VAPID.

2. **Dual-Channel Synchronization:**
   - Every system event (upload publication, chat message, announcement) must generate an in-app database record (`abhihub.notifications`) and dispatch push notifications to all active device endpoints for users with push opt-in enabled.

3. **Lifecycle & Device Storage:**
   - Record and update device metadata (`platform`, `browser`, `device_type`, `permission_state`, `last_seen_at`, `last_success_at`, `last_failure_at`, `failure_code`).
   - Clean up expired / unregistered subscriptions immediately upon receiving HTTP 404/410 from push services.

4. **Sanitized Deep-Link Routing:**
   - All notification clicks must resolve to safe, allowlisted relative paths within the AbhiHub origin (`/dashboard`, `/profile`, `/notes/...`, `/resource/...`, `/chat`, `/settings`, `/notifications`, `/pyqs`).
   - Reuse/focus existing open windows when available; avoid duplicate tab clutter.

5. **User Preferences & Privacy:**
   - Backend-enforced category toggles (Uploads, Chat, Crush, System) persisted in Supabase `profiles`.
   - Never send tokens, passwords, private notes, or unredacted personal details in notification payloads or analytics events.

6. **In-App Notification Center:**
   - Polling / real-time badge updates on bell icon with dynamic counter.
   - Dropdown list with unread markers, relative timestamps, and single/bulk mark-as-read actions.
   - Safe HTML escaping for all user-generated content.

---

## 3. Non-Functional & Reliability Requirements

1. **Idempotency & Deduplication:**
   - Suppress duplicate notifications within a 30-second window using composite deduplication keys (`user_id:tag:title`).
2. **Bounded Retries:**
   - Up to 1 retry with exponential backoff on HTTP 5xx errors; zero retries on client/permanent errors (400, 404, 410).
3. **Graceful Degradation:**
   - Complete isolation of notification failures from core workflows (uploads, document viewing, authentication).
4. **Platform Compliance:**
   - iOS 16.4+ standalone PWA guidance and fallback to in-app bell.

---

## 4. Acceptance Criteria

- [ ] All automated notification tests pass (`pytest tests/test_notifications.py`).
- [ ] End-to-end flow verified on Windows Chrome/Edge and Android Chrome.
- [ ] Stale subscriptions (404/410) are pruned automatically.
- [ ] Preference toggles in `/settings` take immediate effect on push dispatching.
- [ ] Deep-links open correct authenticated routes without open redirect risks.
- [ ] Zero secrets or PII emitted in push payloads or client-side logs.
