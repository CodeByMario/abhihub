
# Phase 1: Discovery & Inventory (Read-Only)

### 1. Admin File Inventory
| File Path | Type | Purpose |
| :--- | :--- | :--- |
| `routes/admin.py` | Python / Blueprint | Main admin blueprint managing view rendering, user moderation, document approvals, economy config, file report deletion, and payment/payout management. |
| `routes/auth.py` | Python / Utility & Blueprint | Authentication and role-check decorators (`@admin_required`, `@auth_required`, `is_admin_user`, `log_admin_action`) and session handling. |
| `methods/analytics_reporter_routes.py` | Python / Routes | Registers protected `/api/admin/analytics/*` REST endpoints (KPIs, trending files, demographics, errors). |
| `methods/analytics_reporter.py` | Python / Service | Computes aggregations, device analytics, trending file reports, and user demographics from Supabase. |
| `methods/audit_service.py` | Python / Service | Generates multi-sheet Excel workbooks (`build_audit_export`) for payment and payout audits. |
| `methods/admin_db_helper.py` | Python / Helper | Currently empty (`0 bytes`) placeholder module. |
| `templates/admin_base.html` | Jinja2 Template | Master layout for all admin dashboards, including top navigation, sidebar, Socket.IO handlers, and shared modals. |
| `templates/admin_notification_panel.html` | Jinja2 Template | Primary admin dashboard view (`/admin`) for student lookup, bulk notifications, document verification, and user management. |
| `templates/admin_payments.html` | Jinja2 Template | Admin finance dashboard (`/admin/payments`) handling transaction reconciliation, creator payout approvals, and KYC verifications. |
| `templates/admin_analytics.html` | Jinja2 Template | Platform analytics dashboard (`/admin/analytics`) displaying view counts, trending subjects, and device breakdown. |
| `templates/admin_file_reports.html` | Jinja2 Template | Moderation panel (`/admin/file-reports`) for triaging broken documents and viewer failure reports. |
| `templates/admin_economy.html` | Jinja2 Template | Economy control panel (`/admin/economy`) for viewing credit circulation, CCR ratios, and adjusting reward rules. |
| `templates/admin_developer.html` | Jinja2 Template | Developer health hub (`/admin/developer`) for system health, cloud metrics, feature flags, and live logs. |
| `static/js/admin-dashboard.js` | JavaScript Asset | Currently empty (`0 bytes`) placeholder asset. |

---

### 2. Existing Admin Features & Endpoints Map

#### A. View Endpoints (HTML Pages)
- `GET /admin` (`admin.admin_control_panel`) $\rightarrow$ Renders `admin_notification_panel.html`
- `GET /admin/notification-panel` & `/admin/file-updates` $\rightarrow$ 301 redirects to `/admin`
- `GET /admin/analytics` (`admin.admin_analytics_dashboard`) $\rightarrow$ Renders `admin_analytics.html`
- `GET /admin/economy` (`admin.admin_economy_dashboard`) $\rightarrow$ Renders `admin_economy.html`
- `GET /admin/developer` (`admin.admin_developer_panel`) $\rightarrow$ Renders `admin_developer.html` (blocked in production)
- `GET /admin/file-reports` (`admin.admin_file_reports_page`) $\rightarrow$ Renders `admin_file_reports.html`
- `GET /admin/payments` (`admin.admin_payments_dashboard`) $\rightarrow$ Renders `admin_payments.html`

#### B. User Management & Moderation Endpoints
- `GET /api/admin/users` $\rightarrow$ Query and filter student/user profiles with pagination
- `GET /api/admin/users/<user_id>/stats` $\rightarrow$ View detailed user profile statistics (uploads, view history, quotas)
- `POST /api/admin/verify-user` $\rightarrow$ Mark user as verified/unverified
- `POST /api/admin/update-user-role` $\rightarrow$ Change role (`admin`, `student`, `creator`, etc.)
- `POST /api/admin/update-user-level` $\rightarrow$ Adjust user access/contributor level
- `POST /api/admin/update-user-credits` $\rightarrow$ Credit/quota adjustments
- `POST /api/admin/economy/user/<user_id>` $\rightarrow$ Adjust economy scores & contribution multipliers

#### C. Content & File Moderation Endpoints
- `GET /api/admin/pending-documents` $\rightarrow$ Fetch pending uploaded documents for approval
- `POST /api/admin/approve-document` $\rightarrow$ Approve pending document & award XP/credits to uploader
- `POST /api/admin/reject-document` $\rightarrow$ Reject document with rejection reason (and optional purge)
- `GET /api/admin/file-reports` $\rightarrow$ List viewer failure reports and broken file complaints
- `POST /api/admin/file-reports/<report_id>/status` $\rightarrow$ Update status of file report (`pending`, `resolved`, `dismissed`)
- `POST, DELETE /api/admin/file-reports/<report_id>/delete-file` $\rightarrow$ Delete reported file record from database and clean dependencies

#### D. Financial & Payout Management Endpoints
- `GET /api/admin/incidents/top` $\rightarrow$ Fetch top failed transactions and rejected payouts
- `GET /api/admin/payment/transactions` $\rightarrow$ List recent credit transactions and orders
- `POST /api/admin/payment/transaction` $\rightarrow$ Manually reconcile/update transaction status
- `GET /api/admin/payouts` $\rightarrow$ List creator withdrawal requests
- `POST /api/admin/payout/action` $\rightarrow$ Approve or reject creator payouts
- `GET /api/admin/kyc/list` & `GET /admin/api/kyc/pending` $\rightarrow$ Query KYC submissions
- `POST /admin/api/kyc/<kyc_id>/verify` $\rightarrow$ Approve or reject creator identity verification
- `GET /api/admin/creator/wallets` $\rightarrow$ Creator wallet balances and ledger overview
- `POST /api/admin/creator/wallet/adjust` $\rightarrow$ Balance adjustment for creator wallets
- `GET /admin/api/audit/export` $\rightarrow$ Download multi-sheet Excel financial report

#### E. System, Notifications & Analytics Endpoints
- `POST /api/admin/send-notification` $\rightarrow$ Broadcast push / in-app notifications
- `GET /api/admin/notification-history` $\rightarrow$ Retrieve sent broadcast log
- `GET /api/admin/broadcast-stats` $\rightarrow$ Real-time delivery and click stats
- `GET /api/admin/system-health` $\rightarrow$ Ping Supabase DB, Redis/Cache, Disk, and CPU
- `GET /api/admin/cloud-stats` $\rightarrow$ Storage and cloud usage metrics
- `GET /api/admin/feature-health` $\rightarrow$ Test external dependency health (Firebase, Gemini AI, Resend)
- `GET /api/admin/logs` $\rightarrow$ Server runtime log streaming
- `GET /api/admin/stats` $\rightarrow$ Platform summary counters (users, approved files, views)
- `GET /api/admin/economy/config` & `POST /api/admin/economy/config` $\rightarrow$ Read and edit dynamic scoring config
- `GET /api/admin/economy/overview` $\rightarrow$ Overall token circulation, reserve ratio, and level distribution
- `POST /api/indexnow/submit` $\rightarrow$ Submit URLs to Bing IndexNow
- `GET /api/admin/analytics/*` (`overview`, `trending-files`, `demographics`, `usage-patterns`, `traffic-sources`, `devices`, `recent-activity`, `trending-subjects`, `errors`, `daily-views`, `sentiment`) $\rightarrow$ Detailed platform metrics

---

### Ready for Next Phase
Phase 1 discovery is complete with zero modifications made. Please confirm to proceed to **Phase 2 (Security, Logic, Jinja & Architecture Audit)**.

[Why Minimal]:
Completes read-only discovery, inventory mapping, and endpoint cataloging without modifying any code, awaiting user confirmation before auditing.


Viewed admin.py:120-250
Viewed admin.py:250-380
Viewed admin.py:380-550
Viewed admin.py:820-970
Viewed admin.py:1220-1330
Viewed admin.py:1469-1590
Viewed admin_base.html:1-120
Viewed admin_base.html:400-600
Viewed admin_base.html:600-701
Viewed admin_payments.html:1-150
Viewed admin.py:770-815
Viewed admin.py:1060-1115
Viewed admin.py:1610-1769
Searched for "url_for\("
Searched for "context_processor"
Viewed app.py:825-850
Viewed app.py:385-405
Viewed admin_payments.html:140-260
Searched for "fetch("
Searched for "export"
Searched for "fetch("
Searched for "fetch("
Viewed admin_economy.html:445-518
Searched for ".innerHTML ="

[Task Type]: C

# Phase 2: Security, Logic & Architecture Audit Report

### Audit Findings Table

| File | Line | Issue | Severity | Fix |
| :--- | :--- | :--- | :--- | :--- |
| `routes/admin.py` | 923-953 | **Admin Self-Lockout & Privilege Escalation:** Any admin can demote themselves or demote the last superadmin to student, locking themselves out. Also lacks superadmin role validation to assign admin privileges. | **Critical** | Block self-demotion (`target_id == current_admin_id`), ensure at least one superadmin remains active, and restrict admin-tier role assignments to superadmins only. |
| `routes/admin.py` | 1308-1322 | **Orphaned Storage Files on Hard Delete:** Hard deleting a rejected document purges database records but leaves the binary payload orphaned in Cloudinary, Firebase, and Supabase storage. | **Critical** | Integrate multi-provider storage deletion (`delete_file_from_cloudinary`, Firebase `delete_file`, Supabase storage `remove`) before deleting database rows. |
| `templates/admin_notification_panel.html` | 1468, 1708, 2183 | **Stored DOM XSS Vulnerability:** User feedback messages (`m.message`, `m.name`), student full names (`u.full_name`), and document titles are interpolated directly into `element.innerHTML` without escaping. | **Critical** | Implement an HTML escape utility function or assign text safely via `textContent` / sanitized template interpolation. |
| `templates/admin_economy.html` | 458-483 | **Stored DOM XSS in Payout Table:** User-supplied UPI / bank account details (`p.payout_details`) are injected into `tbody.innerHTML` unescaped. | **Critical** | Sanitize and escape all creator payout details before rendering. |
| `routes/auth.py` | 26-66 | **Auth Response Mismatch on `/admin/api/*` Endpoints:** Endpoints starting with `/admin/api/*` (e.g., KYC verify, audit export) trigger HTML 302/403 redirects instead of JSON `{success: false, error: ...}`, breaking AJAX/fetch callers. | **High** | Update `auth_required` and `admin_required` path matching to check `request.path.startswith(('/api/', '/admin/api/', '/store-room/api/'))`. |
| `routes/admin.py` | 205-238, 871-970 | **Missing CSRF & Rate-Limiting on State-Changing Actions:** POST endpoints for financial transactions, user verification, roles, and levels lack CSRF token checks and brute-force rate-limiting. | **High** | Implement CSRF header verification (`X-CSRF-Token`) on all state-altering POST/DELETE admin routes. |
| `routes/admin.py` | 788-796 | **Out-Of-Memory (OOM) Risk on Log Streaming:** `f.readlines()` loads the entire log file into memory to read the last `N` lines, which will crash the worker process on large production logs. | **High** | Use reverse seek buffer reading (tail generator) or `collections.deque(f, maxlen=n)` without loading the whole file into RAM. |
| `routes/admin.py` | 380-453 | **N+1 Query Storm & Unbounded Scans in Wallets:** `admin_creator_wallets` queries all records from `documents` and spawns 10 threads executing individual `get_creator_wallet` calls per user without cursor pagination. | **High** | Add pagination (`limit`/`offset`) and batch user wallet balance calculation instead of launching unthrottled thread pools. |
| `routes/admin.py` | 128, 144, 194, 205 | **Inconsistent Decorator Application:** Several routes only use `@admin_required` while others use both `@auth_required` and `@admin_required`. | **Medium** | Unify under a single composable decorator `@role_required('admin')` or apply both consistently across all endpoints. |
| `routes/admin.py` | 211, 219 | **Status String Casing Inconsistency:** `admin_set_payment_transaction` stores status in lowercase (`status.lower()`), while incident aggregators check uppercase (`FAILED`, `VERIFIED`). | **Medium** | Standardize status codes to canonical uppercase enums (`PENDING`, `VERIFIED`, `FAILED`, `REFUNDED`). |
| `routes/admin.py` | 878 | **Missing UUID Format Validation:** `admin_verify_user` passes `user_id` directly to Supabase queries without verifying UUID format, unlike `admin_update_user_level`. | **Medium** | Enforce `validate_uuid(user_id)` before database query dispatch. |
| `routes/auth.py` | 68-88 | **Non-Persistent Audit Logging:** `log_admin_action` only outputs to Python standard logger (`logging.info`), meaning audit trails vanish upon container restarts or log rotation. | **Medium** | Persist audit events to an append-only `admin_audit_logs` database table (admin ID, target, action, diff, IP, user-agent). |
| `templates/admin_economy.html` | 448-512 | **Duplicate Payout Review & Action Logic:** Duplicate payout table and approve/reject logic in `admin_economy.html` overlapping entirely with `admin_payments.html`. | **Medium** | Consolidate payout reconciliation exclusively in `admin_payments.html` and link to it from economy overview. |
| `methods/admin_db_helper.py` | 1 | **Dead File:** Empty 0-byte placeholder file unused in codebase. | **Low** | Implement unified DB helper service or remove if unneeded. |
| `static/js/admin-dashboard.js` | 1 | **Dead Asset:** Empty 0-byte script unused by any template. | **Low** | Consolidate common admin vanilla JS utilities into this file or remove. |

---

### Duplicate & Dead Code Identified for Removal
1. **Dead Files:**
   - `methods/admin_db_helper.py` (0 bytes)
   - `static/js/admin-dashboard.js` (0 bytes)
2. **Duplicate Routes & UI:**
   - Redundant duplicate route `@admin_bp.route('/admin/api/kyc/pending')` duplicate of `/api/admin/kyc/list`.
   - Redundant payout management table and JavaScript action handlers in `templates/admin_economy.html` which duplicates `templates/admin_payments.html`.
3. **Repeated Logic:**
   - Redundant status badge HTML rendering across `admin_payments.html`, `admin_notification_panel.html`, and `admin_economy.html`.
   - Repeated inline modal backdrops and notification toasts across multiple templates instead of utilizing shared Jinja macros/components.

---

### Confirmation to Proceed
Audit is complete. Next is **Phase 3 (Cleanup & Refactor)** followed by **Phase 4 (Feature Completion)**:
- Consolidate routes and clean dead code.
- Implement reusable RBAC decorators (`@role_required`), persistent append-only audit logging table, safe file deletion service, and anti-lockout safeguards.

Please confirm to start Phase 3 refactoring.

[Why Minimal]:
Delivers the complete audit findings table with severity ratings and specific file/line references, highlighting duplicates and vulnerabilities while awaiting confirmation before code modifications.