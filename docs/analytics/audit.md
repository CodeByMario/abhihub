# AbhiHub Analytics Audit

**Generated:** 2026-09-11  
**Target Environment:** AbhiHub Web Platform (Flask + Supabase + Firebase Storage)  
**Measurement ID:** `G-EH5BGS9BEG`  
**Status:** Pre-Implementation Baseline Audit  

---

## 1. Executive Summary

AbhiHub's current analytics setup is an ad-hoc hybrid of Google Analytics 4 (GA4 via `gtag.js`), client-side DOM helpers (`analytics-helper.js`), and server-side logging routes (`/api/analytics/*`) backed by Supabase tables (`document_views`, `security_audit_logs`, `user_sessions`).

While the tracking infrastructure captures high-level traffic, several critical architectural, privacy, and data-integrity defects compromise measurement quality:
1. **Critical PII & Identifier Leakage:** Raw email addresses are passed as the `userId` in authentication events from `static/login-auth.js` (`window.AbhiHubTracking.trackLogin('email', user?.email)`), violating Google Analytics Terms of Service and data protection standards. User display names are also sent as user properties.
2. **Missing Authoritative Reconciliation:** Key conversion and lifecycle events (such as upload success, paper opens deducted from quotas, account registration, bookmark saves) are triggered client-side before or independent of authoritative server-side confirmation.
3. **Event Duplication & Namespace Collisions:** Multiple legacy event names (`upload_funnel`, `file_upload`, `upload_completed`, `view_item`, `file_view`, `select_content`, `file_download`) coexist without canonical schemas, resulting in double counting.
4. **Environment Pollution:** Developer actions on `localhost` or preview environments trigger live GA4 hits because debug mode is only set conditionally without a distinct test measurement ID or stream filter.
5. **Ad-Blocker Vulnerability & Unhandled Offline Sync:** Client-only events fail silently when content blockers or spotty connectivity intercept `gtag.js`.

---

## 2. Current Architecture & Analytics Implementation

### 2.1 Technology Stack & Architecture
- **Backend Framework:** Python Flask 2.0.1 (WSGI) with `Flask-SocketIO` under Gunicorn (`GeventWebSocketWorker`).
- **Database & Auth:** Supabase (PostgreSQL schema `abhihub`, Supabase GoTrue Auth for email + Google OAuth).
- **Storage:** Firebase Cloud Storage (PDF documents and images) & Cloudinary.
- **Frontend:** Server-rendered Jinja2 templates (`templates/p_struct.html`, `templates/google_tag.html`, etc.) paired with vanilla JavaScript (`static/js/*`).

### 2.2 Analytics Tag & Loading Conditions
- **Tag Template:** `templates/google_tag.html` included via Jinja2 in layout headers (`p_struct.html`, `team.html`, `know_me/*.html`, etc.).
- **Tag Injection:** Dynamic `<script async src="https://www.googletagmanager.com/gtag/js?id=G-EH5BGS9BEG">`.
- **Consent Mechanism:** Custom banner writing `abhihub-consent` (`granted` / `denied`) to `localStorage`. When absent, tag defaults to disabled (`window.__ABHIHUB_ANALYTICS_DISABLED__ = true`) until accepted, triggering a full page reload.
- **Context Injection:** In `app.py`, `@app.context_processor` injects `get_full_profile_json()` into `window.ABHIHUB_USER_PROFILE`.
- **Global Abstraction:** `window.AbhiHubTracking` object and `window.gtag()` defined in `templates/google_tag.html`.

---

## 3. Inventory of Existing Analytics Events

| Event Name | Current Trigger / Source | Parameters / Properties | Assessment & Defect |
| :--- | :--- | :--- | :--- |
| `page_view` | Initial load in `google_tag.html` + `sendEnhancedPageView()` | `page_title`, `page_path`, `page_location`, `page_category`, `user_id`, `user_name`, `user_college`, `user_branch`, `session_id`, `time_on_site_seconds`, etc. | **Flawed:** Sends PII-adjacent display names; duplicates browser auto page_views. |
| `session_start_custom` | Auth user detected in `google_tag.html` on load | `logged_in`, `user_id`, `user_name`, `college`, `branch`, `year_of_study` | **Redundant:** GA4 automatically generates `session_start`. Sends `user_name`. |
| `page_performance` | `trackPagePerformance()` on window load | `page_load_time_ms`, `dom_content_loaded_ms`, `time_to_first_byte_ms`, `device_type` | **Suboptimal:** Uses deprecated `window.performance.timing` instead of Navigation Timing Level 2. |
| `session_end` | `beforeunload` & `visibilitychange` via `navigator.sendBeacon` | `session_id`, `session_duration_seconds`, `session_page_views`, `engagement_quality`, `exit_page` | **Unreliable:** Often double-fired when switching tabs and closing window; non-standard GA4 event. |
| `file_view` | Throttled click on file card / open in viewer | `file_name`, `file_type`, `document_id`, `subject`, `college`, `branch`, `year`, `user_id`, `user_name`, `time_spent_seconds` | **Duplicate/PII:** Fired in parallel with `view_item`; sends `user_name`. Client-triggered before render. |
| `view_item` | Throttled click on file card / open in viewer | `items: [{item_id, item_name, item_category, item_category2, item_category3, item_variant, ...}]` | **Ecommerce Overload:** Fired concurrently with `file_view`. Non-standard usage for education content. |
| `file_download` | Click on download button (`analytics-helper.js`) | `file_name`, `file_type`, `document_id`, `subject`, `college`, `branch`, `user_id`, `user_name` | **Inaccurate:** Fires on click before file download completes or succeeds. |
| `select_content` | Click on download button (`analytics-helper.js`) | `content_type: 'file'`, `item_id`, `items: [...]` | **Duplicate:** Redundant duplicate of `file_download`. |
| `search` | Form submit (`analytics-helper.js`) | `search_term`, `search_type`, `result_count`, `search_refinement_level`, `zero_results` | **Data Risk:** Sends raw search text which may contain student roll numbers or sensitive queries. |
| `subject_access` | Click on subject link/card | `subject_name`, `content_type`, `college`, `branch`, `user_id` | **Fragmented:** Should be consolidated under unified content navigation taxonomy. |
| `login` | `static/login-auth.js` | `method`, `user_id`, `user_name` | **CRITICAL BUG:** `login-auth.js` passes `user?.email` as the `userId` parameter → PII leak into GA4! |
| `sign_up` | `static/login-auth.js` | `method`, `user_id`, `user_name` | **CRITICAL BUG:** `login-auth.js` passes `user?.email` as the `userId` parameter → PII leak into GA4! |
| `logout` | Logout button click | `user_id`, `session_duration_seconds` | **Incomplete:** Misses server-side session termination flows. |
| `premium_interaction` | Upgrade/premium button click | `action`, `plan_type` | **Legacy/Dead:** AbhiHub uses Study Pass/quota system, not paid tiers. |
| `share` | Referral/share buttons | `method`, `content_type`, `content_name`, `user_id` | **Valid:** Needs standard taxonomy parameter naming (`engagement_type: 'share'`). |
| `file_upload` | Legacy upload handler | `file_name`, `file_type`, `file_size_kb`, `document_id` | **Inconsistent:** Collides with `upload_started` / `upload_completed` / `upload_funnel`. |
| `upload_funnel` | `p_upload.html` and `inline-handler-compat.js` | `funnel_step` (`3_upload_started`, `4_upload_completed`) | **Fragmented:** Ad-hoc strings bypassing `AbhiHubTracking`. |
| `upload_started` | Bulk upload initiation in `bulk_upload.js` | `count`, `method`, `category` | **Valid:** Needs canonical parameter standardization. |
| `upload_completed` | Bulk upload finish in `bulk_upload.js` | `count`, `method`, `types`, `total_size_kb`, `user_id` | **Incomplete:** Client-side only; does not reconcile with server upload confirmation. |
| `upload_failed` | Bulk upload failure in `bulk_upload.js` | `reason`, `error_type`, `method` | **Valid:** High utility for friction monitoring; needs standard failure codes. |
| `upload_abandoned` | User leaves upload modal | `stage` | **Valid:** High utility for friction monitoring. |
| `filter_applied` | Dropdown change | `filter_type`, `filter_value`, `result_count` | **Valid:** High utility for query navigation. |
| `filter_combination` | Multiple filter changes | `combination`, `filter_count`, `result_count` | **High Cardinality Risk:** Creates explosive unique parameter values in GA4. |
| `section_engagement` | IntersectionObserver on sections | `section_name`, `scroll_depth` | **Noisy:** Can inflate event counts with generic scrolls. |
| `element_click` | Generic button click | `element_name`, `element_type`, `action_value` | **Anti-Pattern:** Unbounded tracking of generic UI clicks. |
| `feature_usage` | Specific feature click | `feature_name`, `feature_status`, `experience_rating`, `feedback_message` | **Valid:** Good for product telemetry; parameters need typing. |
| `app_error` | Client error catch & server logging | `error_type`, `error_message`, `severity`, `page_path` | **Valid:** Dual-logged to GA4 and Supabase `security_audit_logs`. |
| `form_submit` | Form submission event | `form_name`, `form_data` | **Data Risk:** `form_data` dictionary can capture sensitive form inputs. |
| `engagement_time` | Periodic timer | `time_on_site_seconds`, `session_page_views`, etc. | **Redundant:** GA4 native `user_engagement` handles time metrics automatically. |
| `api_latency` | Ad-hoc latency tracker | `endpoint`, `latency_ms`, `status_code` | **Rarely Used:** Unwired across most fetch calls. |
| `notification_open` | Notification bell opened | `unread_count`, `user_id` | **Valid:** UI feature usage signal. |
| `study_pass_*` | Study pass popup/gate actions | Dismissed, ignored, popup, upload_click, store_room_click | **Valid:** Measures conversion and friction on upload gating. |
| `camera_upload` | Mobile camera button | None | **Consolidate:** Fold into `upload_started` (`method: 'camera'`). |
| `xp_earned` / `badge_unlocked` | Gamification triggers | `xp`, `score`, `count`, `badge` | **Valid:** Telemetry on engagement mechanics. |
| `ad_click` | Ad banner click in `ad-manager.js` | `ad_type`, `slot_id` | **Valid:** Ad revenue and interaction telemetry. |
| `pwa_install` | PWA install banner click in `pwa-install.js` | Platform context | **Valid:** Mobile app installation telemetry. |

---

## 4. Key Application Flows & Instrumentation Points

### 4.1 Authentication Flow
- **Paths:**
  - Google OAuth: Redirects via Supabase Auth → `/auth-callback` → session established.
  - Email/Password: Supabase Auth client in `static/login-auth.js` → `/api/auth/login` or `/auth`.
  - Signup: Supabase Auth client → `/signup` → profile onboarding.
  - Logout: `/logout` clears session.
  - Account Deletion: `/delete-account` (purges profile and user records).
- **Current Defect:** `login-auth.js` passes user email into `trackLogin()` and `trackSignup()`.
- **Target Instrumentation:** Send pseudonymous user ID (`auth_method: 'google' | 'email'`), zero email/name leakage, capture `login_failed` reason codes safely without sensitive tokens.

### 4.2 Document & PYQ Consumption Flow
- **Paths:** `/notes`, `/pyq`, `/subject/<name>`, `/resource/<id>`, `/preview/<id>`, `/view_pdf/<id>`.
- **Backend View Logger:** `log_document_view()` in `app.py:525` checks quota, deducts 1 view credit (unless owner or already viewed today), logs to `document_views`, and sends quota deduction notifications.
- **Current Defect:** Browser triggers `file_view` on link click before backend verification; viewer modal close emits duration based on wall-clock time even if the tab was in the background.
- **Target Instrumentation:** Distinguish accidental link click from true "meaningful reading engagement" (e.g., active reading duration $\ge 15\text{s}$ or scroll depth in PDF viewer).

### 4.3 Upload & Ingestion Flow
- **Paths:** `/upload`, `/api/upload`, `/api/bulk-upload`, `bulk_upload.js`.
- **Workflow:** File selection (or camera capture) $\rightarrow$ metadata tagging (subject, branch, year, semester) $\rightarrow$ chunked upload to Firebase/Supabase $\rightarrow$ quota allocation (`QUOTA_PER_UPLOAD = 19`).
- **Current Defect:** `upload_completed` is sent from frontend JS before server database insertion finishes; if the server fails during final verification, an erroneous completed event was already logged to GA4.
- **Target Instrumentation:** Frontend logs `upload_started` and `upload_abandoned`; server or confirmed API response triggers `upload_completed` with file type, bucket size, and duration.

### 4.4 Search & Browse Flow
- **Paths:** Global search bar in `p_struct.html`, `/search`, `search_api.py`.
- **Current Defect:** Full free-text `searchTerm` is sent directly to GA4. If a user pastes a phone number, email, or private question, it lands in GA4 reports.
- **Target Instrumentation:** `search_submitted` records `search_area`, `result_count`, `query_length`, and sanitized non-sensitive category/subject keywords only.

### 4.5 Profile, Storeroom & Dashboard Flows
- **Paths:** `/dashboard`, `/profile`, `/store-room` (`/storeroom`), bookmark routes (`/api/interactions/bookmark`, `/api/bookmark`).
- **Target Instrumentation:** `dashboard_viewed`, `profile_viewed`, `storeroom_viewed`, `item_saved`, `item_removed`.

---

## 5. Database Entities & Backend Routes Relevant to Analytics

### 5.1 Database Entities (Supabase `abhihub` schema)
- `abhihub.profiles`: User identity, college, department, graduation year, points, level, upload count.
- `abhihub.documents`: Uploaded notes & PYQs (`uploader_id`, `file_url`, `subject`, `branch`, `view_count`, `like_count`, `download_count`).
- `abhihub.document_views`: Authoritative view log (`document_id`, `user_id`, `ip_address`, `device_type`, `accessed_at`).
- `abhihub.document_votes`: Likes/upvotes.
- `abhihub.bookmarks`: Saved documents.
- `abhihub.user_sessions`: Session duration and device records.
- `abhihub.security_audit_logs`: Error events and security audits.

### 5.2 Backend Analytics Routes
- `POST /api/analytics/pageview`: Server-side pageview logger (`analytics_tracker.py:156`).
- `GET /api/analytics/user-properties`: User context endpoint (`analytics_tracker.py:194`).
- `POST /api/analytics/error`: Client error logger (`analytics_tracker.py:212`).
- `POST /api/analytics/file-access`: File access telemetry (`analytics_tracker.py:254`).
- `POST /api/analytics/session-end`: Unload beacon handler (`analytics_tracker.py:293`).
- `GET /api/admin/analytics/*`: 10 reporting endpoints for the admin dashboard.

---

## 6. Privacy & Data-Quality Risks

| Risk Category | Current State | Impact | Required Remediation |
| :--- | :--- | :--- | :--- |
| **PII in GA4 Payloads** | `static/login-auth.js` passes `user?.email` into `trackLogin`/`trackSignup`. `google_tag.html` sets `user_name`. | Severe violation of Google Analytics Terms of Service; GDPR/DPDP non-compliance. | Strip all names and emails from analytics payloads. Use pseudonymous UUIDs only. |
| **Raw Search Queries** | `analytics-helper.js` sends raw `searchTerm` string. | Sensitive personal searches or roll numbers logged to 3rd party. | Send query length, token count, and category filters only. Redact free-text. |
| **Form Data Logging** | `trackFormSubmission` serializes all `FormData` into GA4 event payload. | Potential leak of contact details, passwords, or feedback text. | Restrict form tracking to `form_name` and status flags. Never serialize input fields. |
| **Development Data Contamination** | `localhost` events are sent to production GA4 measurement ID `G-EH5BGS9BEG` with only `debug_mode: true`. | Pollutes production dashboards with developer test traffic. | Disable GA4 in local development unless explicitly overridden; route to test stream or console stub. |
| **High Cardinality Dimensions** | `filter_combination` generates composite string combinations. | Hits GA4 unique dimension limits; breaks custom reporting. | Standardize to individual `filter_applied` events. |
| **Discrepancy with Database** | Frontend sends `file_view` on click; database records view only if quota check passes in `log_document_view()`. | GA4 shows 3x–5x more views than the authoritative database record. | Align client `content_viewed` with actual document rendering and server acknowledgment. |

---

## 7. Action Plan & Files Scheduled for Modification

1. **`templates/google_tag.html`**: Complete rewrite to establish the unified, privacy-safe `AbhiHubAnalytics` API (`track`, `setUser`, `clearUser`, `trackError`), eliminate PII parameters, implement environment detection, and provide typed fallbacks.
2. **`static/js/analytics-helper.js`**: Refactor auto-tracking to use canonical taxonomy names (`content_viewed`, `content_engaged`, `search_submitted`, `filter_applied`) and remove PII / high-cardinality payloads.
3. **`static/login-auth.js`**: Fix login/signup tracking calls to pass `auth_method` without exposing `user?.email`.
4. **`static/js/bulk_upload.js`**: Update upload lifecycle instrumentation to fire `upload_started`, `upload_completed`, `upload_failed`, `upload_abandoned` with structured schemas.
5. **`methods/analytics_tracker.py`**: Update server-side payload handling to ensure user emails are never stored in client analytics tables, enforce strict input validation, and enhance reconciliation.
6. **Documentation Suite (`docs/analytics/`)**:
   - `docs/analytics/audit.md` (Created)
   - `docs/analytics/event-taxonomy.md` (Next)
   - `docs/analytics/data-quality.md`
   - `docs/analytics/dashboard-spec.md`
   - `docs/analytics/privacy.md`
   - `docs/analytics/rollout-and-rollback.md`
