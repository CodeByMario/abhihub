# AbhiHub Notification Security Audit (Phase 7)

**Project:** AbhiHub  
**Module:** Notification System  
**Initiative:** Notification Quality & Reliability 2.0  
**Phase:** Security & Privacy Audit  
**Status:** Audit Complete  
**Date:** 2026-11-10  

---

## 1. Executive Summary

A security and privacy audit was performed on the notification ingestion, storage, VAPID signing, and delivery infrastructure.

### Critical Discovery
A **CRITICAL authorization bypass vulnerability** was discovered in the broadcast push endpoint (`/api/push/send` in `push_api.py`). The condition used to verify admin identity fails open when `ADMIN_EMAILS` environment configuration is empty or unset, allowing any authenticated user to broadcast push messages to all registered devices across the platform.

---

## 2. Vulnerability & Risk Matrix

| Finding ID | Severity | Category | Component | Description & Impact |
|---|---|---|---|---|
| **SEC-01** | **CRITICAL** | Authorization Bypass | `push_api.py:156` | `/api/push/send` admin check fails open if `ADMIN_EMAILS` env is empty list; any regular user can send platform-wide push broadcasts |
| **SEC-02** | **HIGH** | Privilege Escalation / Tampering | `push_api.py:91-125` | `/api/push/unsubscribe` allows deleting any subscription endpoint without verifying that the caller owns the endpoint |
| **SEC-03** | **HIGH** | Preference Bypass | `push_notifications.py:535` | `send_notification_to_all()` omits `category`, bypassing recipient category opt-out filters |
| **SEC-04** | **MEDIUM** | Denial of Service / Spam | `supabase_helper.py:2894` | Every single document upload triggers `send_notification_to_all()`, resulting in unthrottled broadcast flooding |
| **SEC-05** | **MEDIUM** | Insecure URL Redirection | `sw.js:1210-1218`, `upload_notifier.py:92` | Hardcoded fallback redirects to `/premium` and `/dashboard` instead of strict validation and resource deep-linking |
| **SEC-06** | **LOW** | User-Generated Content Injection | `methods/upload_notifier.py:91`, `app.py:2053` | Unsanitized file titles and message previews are formatted directly into push notification strings without length constraints |
| **SEC-07** | **INFORMATIONAL** | Ephemeral Rate Limiting | `push_notifications.py:90` | Daily limit and user delivery tracking are stored in volatile in-memory dictionary (`_USER_DELIVERY_TIMESTAMPS`), lost on Gunicorn worker restarts |

---

## 3. Deep Dive into Security Findings

### 3.1 SEC-01: Critical Authorization Bypass on Broadcast Push
- **Location:** [`push_api.py:156`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py#L156)
- **Vulnerable Code:**
  ```python
  # Check Admin authorization
  if not user_email or (ADMIN_EMAILS and user_email not in ADMIN_EMAILS):
      return jsonify({'error': 'Unauthorized: Admin privileges required'}), 403
  ```
- **Proof of Vulnerability:**
  When `ADMIN_EMAILS` is empty (default when `ADMIN_EMAILS` env var is missing or empty):
  1. `ADMIN_EMAILS` evaluates to `[]` (falsy in Python).
  2. For any logged-in user `user_email = "student@example.com"`, `not user_email` is `False`.
  3. `(ADMIN_EMAILS and user_email not in ADMIN_EMAILS)` evaluates to `[]` (falsy).
  4. `False or False` is `False`! The `if` condition fails to trigger, and authorization is bypassed.
- **Remediation:**
  Use the canonical `is_admin_user(session.get('user', {}))` from `methods/auth_helper.py` or fail-closed:
  ```python
  if not user_email or not ADMIN_EMAILS or user_email not in ADMIN_EMAILS:
      return jsonify({'error': 'Unauthorized: Admin privileges required'}), 403
  ```

---

### 3.2 SEC-02: Unauthenticated / Cross-User Unsubscribe
- **Location:** [`push_api.py:91-125`](file:///e:/Users/abhihub/New%20folder/abhihub/push_api.py#L91-L125)
- **Vulnerability:** The `/api/push/unsubscribe` endpoint accepts an `endpoint` string and invokes `remove_push_subscription_by_endpoint(endpoint)` without checking if the endpoint belongs to the authenticated `session['user']`.
- **Impact:** An attacker who discovers or predicts another user's push endpoint URL could deactivate their push notifications.
- **Remediation:** Add ownership validation: verify that the subscription record matching `endpoint` has `user_id == current_user_id` before deleting.

---

### 3.3 SEC-03: Category Preference Enforcement Bypass
- **Location:** [`push_notifications.py:535`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L535)
- **Vulnerability:**
  ```python
  if category and not prefs.get(category, True):
      return {'success': True, 'suppressed': True, 'reason': 'category_preference_disabled'}
  ```
  When `send_notification_to_all()` is called, `category` defaults to `None`.
  Because `category` is falsy, the preference check is skipped entirely, forcing notifications upon users who explicitly disabled that category in settings.
- **Remediation:** Ensure all callers provide an explicit category (e.g. `category='uploads'`, `category='academic'`, `category='account'`). If category is missing, default to `'platform'` and check `prefs.get('platform', True)`.

---

### 3.4 SEC-04: Denial of Service / Broadcast Flooding via Uploads
- **Location:** [`methods/supabase_helper.py:2894`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py#L2894)
- **Vulnerability:** Every document uploaded triggers a platform-wide Web Push broadcast to every device in `push_subscriptions`.
- **Impact:** Malicious or high-frequency uploads flood all user devices, causing notification fatigue, user churn, and triggering browser push spam blocks against the domain.
- **Remediation:** Eliminate global push broadcasts for regular file uploads. Reserve push for the uploader's confirmation and targeted subject/college subscribers.

---

## 4. Privacy & Data Protection Compliance

1. **No Sensitive PII in Payloads:** Notification payloads currently do not leak auth tokens, passwords, or encrypted keys.
2. **Payload Sanitization:** Filenames and chat previews must be stripped of control characters, HTML entities, and clamped to 80 characters maximum before dispatch.
3. **VAPID Key Security:** Private keys (`VAPID_PRIVATE_KEY`) are kept on the server and never exposed in client bundles or `/api/push/vapid-public-key`.

---

*Security audit completed under READ_ONLY_AUDIT rules.*
