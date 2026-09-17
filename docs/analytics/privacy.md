# AbhiHub Analytics Privacy & Data Protection Policy

**Version:** 1.0.0  
**Effective Date:** 2026-09-11  
**Regulatory Alignment:** Digital Personal Data Protection (DPDP) Act & GDPR Data Minimization Standards.

---

## 1. Core Privacy Commitments

1. **Zero Personally Identifiable Information (PII) Transmission:**
   - Raw email addresses, full legal names, phone numbers, roll numbers, and physical addresses are strictly excluded from all client-side and vendor analytics tracking.
2. **Pseudonymous Identity Management:**
   - Users are tracked using an immutable, non-reversible UUID (`user_id`). At no point is this identifier combined with unencrypted user credentials in analytics vendor requests.
3. **No Sensitive Content Logging:**
   - Note contents, student private messages, OCR raw text, passwords, session tokens, and raw search strings are forbidden in analytics payloads.
4. **Transparent Consent Lifecycle:**
   - Analytics cookies and measurement requests are executed only after user consent is granted via the consent banner (`localStorage` key: `abhihub-consent`).

---

## 2. Data Minimization & Parameter Schema Controls

| Field Type | Permitted Attributes | Prohibited Attributes |
| :--- | :--- | :--- |
| **User Identity** | `user_id` (UUID), `user_type`, `user_role`, `auth_method` | `user_email`, `user_name`, `mobile_number`, `avatar_url` |
| **Academic Context** | `user_college`, `user_branch`, `user_year_of_study` | `student_id`, `prn_number`, `roll_number` |
| **Search & Discovery** | `search_area`, `result_count`, `query_length`, `filter_name` | Full query text (`search_term`), sensitive keywords |
| **Error Telemetry** | `error_code`, `surface`, `route_group`, `status_class` | Stack traces with user data, auth headers, tokens |
| **Forms & Actions** | `form_name`, `action_status` | `form_data` input values, password fields |

---

## 3. Consent Management Workflow

1. **First-Time Visitors:**
   - Analytics SDK script loading is deferred.
   - `window.__ABHIHUB_ANALYTICS_DISABLED__ = true`.
   - Consent banner is rendered.
2. **Consent Granted (`Accept`):**
   - Value `granted` stored in `localStorage` under `abhihub-consent`.
   - Analytics initialized; consent update event emitted (`consent_updated: { analytics_allowed: true }`).
3. **Consent Denied (`Decline`):**
   - Value `denied` stored in `localStorage`.
   - Analytics script is omitted or unloaded; no vendor telemetry is transmitted.
4. **Consent Revocation:**
   - Users can reset consent at `/privacy` or through footer preferences.
