# AbhiHub Notification Implementation Plan (Quality & Reliability 2.0)

**Project:** AbhiHub  
**Module:** Notification System  
**Initiative:** Notification Quality & Reliability 2.0  
**Status:** Plan Proposed — Awaiting User Approval to Implement  
**Date:** 2026-11-10  

---

## 1. Overview & Goals

Transform AbhiHub's notification system into an official, reliable, privacy-compliant, and secure service adhering to:
- WCAG 2.2 AA accessibility standards.
- Zero clickbait, zero fake urgency, and zero spam.
- Strict authorization (resolving CRITICAL vulnerability SEC-01).
- Accurate deep-linking and granular category preference enforcement.

---

## 2. Prioritized Implementation Phases

```
┌─────────────────────────────────────────────────────────────┐
│ Priority 0 (Immediate Security & Critical Fixes)            │
│ 1. Fix SEC-01 Auth Bypass on /api/push/send                 │
│ 2. Fix SEC-02 Endpoint Ownership Check on unsubscribe       │
│ 3. Fix SEC-04 Stop Platform Broadcast on every upload       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Priority 1 (Content Quality & Preference Engine)            │
│ 4. Decommission psychologize_notification() clickbait       │
│ 5. Enforce 4 Official Categories: academic, uploads,        │
│    account, platform with strict opt-out checking           │
│ 6. Fix upload deep-linking from /dashboard to /resource/<id>│
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Priority 2 (Service Worker & Client Harmonization)          │
│ 7. Deprecate orphaned static/js/service-worker.js           │
│ 8. Centralize SW registration in static/js/push-notif.js    │
│ 9. Refine /settings/notifications user controls             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Concrete Action Items by Phase

### Phase A: Security & Authorization (P0)
1. **Fix Broadcast Auth Bypass ([`push_api.py:156`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py#L156)):**
   - Replace flawed condition with canonical fail-closed admin verification:
     ```python
     user = session.get('user', {})
     from methods.auth_helper import is_admin_user
     if not is_admin_user(user):
         return jsonify({'error': 'Unauthorized: Admin privileges required'}), 403
     ```
2. **Enforce Endpoint Ownership on Unsubscribe ([`push_api.py:91`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py#L91)):**
   - Verify that the endpoint requested for deletion belongs to the authenticated user ID before executing `delete()`.
3. **Disable Global Upload Push Flooding ([`methods/supabase_helper.py:2894`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py#L2894)):**
   - Remove `send_notification_to_all()` on file uploads. Replace with targeted in-app notification to uploader and subject peers only.

---

### Phase B: Content & Brand Quality (P1)
1. **Neutralize Clickbait Mutations ([`push_notifications.py:140-196`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L140-L196)):**
   - Replace `psychologize_notification()` with a clean, deterministic formatter:
     - No emojis (`👀`, `⚡`, `🎖️`, `💬`, `🔥`, `💸`, `📄`).
     - Standardized title format: `AbhiHub · [Event Category]`.
     - Concise, informative body without fake urgency.
2. **Deep-Link File Uploads ([`methods/upload_notifier.py:92`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/upload_notifier.py#L92)):**
   - Change `url = "/dashboard"` to `url = f"/resource/{file_id}"`.
3. **Clean Transactional Financial Notices ([`methods/payment_engine.py:689`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/payment_engine.py#L689)):**
   - Change `title='Payout Requested 💸'` to `title='AbhiHub · Payout Requested'`.

---

### Phase C: Notification Categories & Preferences (P1)
1. **Map Notification Types to 4 Canonical Categories:**
   - `academic`: `new_notes`, `pyq_upload`, `practical_upload`, `exam_alert`
   - `uploads`: `upload_success`, `upload_rejected`, `upload_published`
   - `account`: `auth_event`, `security_alert`, `payout_status`
   - `platform`: `feature_release`, `maintenance`
2. **Strict Category Enforcement ([`push_notifications.py:535`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L535)):**
   - Require explicit `category` parameter in all dispatch methods.
   - If user opted out of `category` in `profiles`, suppress delivery immediately with `suppressed: True, reason: 'category_preference_disabled'`.

---

### Phase D: Service Worker Harmonization (P2)
1. **Consolidate Service Workers:**
   - Remove or deprecate `static/js/service-worker.js`.
   - Maintain `static/sw.js` as the sole canonical PWA and push handler.
2. **Deduplicate Client Registrations:**
   - Coordinate SW registration through `static/js/push-notifications.js` to avoid redundant register calls from multiple script tags.

---

## 4. Verification & Testing Strategy

1. **Automated Unit & Regression Tests:**
   - Run `pytest tests/test_notifications.py` and `pytest tests/test_feature_notifications.py`.
   - Add test case verifying non-admin access to `/api/push/send` returns 403 even when `ADMIN_EMAILS` is empty.
   - Add test case verifying category opt-out suppresses notifications.
   - Add test case verifying emoji-free content output.
2. **Security & Privacy Verification:**
   - Verify unauthenticated calls to `/api/push/subscribe`, `/api/push/unsubscribe`, and `/api/push/send` are rejected.
   - Verify payload sanitization on long user inputs and special characters.

---

## 5. Rollback Strategy

1. All code changes will be modular and localized to `push_api.py`, `push_notifications.py`, and `methods/upload_notifier.py`.
2. Git diffs are strictly trackable. If any regression occurs, instant rollback is achieved via `git checkout -- <file>`.
3. No schema modifications or irreversible table drops are required; existing Supabase tables (`push_subscriptions`, `notifications`, `profiles`) are reused without alteration.

---

*Awaiting explicit user approval before executing any code modifications.*
