# AbhiHub Canonical Analytics Event Taxonomy

**Version:** 2.0.0  
**Status:** Approved Specification  
**Naming Convention:** Lowercase `snake_case` for event names and parameter keys.  

---

## 1. Global Standards & Policy

1. **Zero PII Guarantee:** No event payload may contain email addresses, full names, phone numbers, auth tokens, passwords, raw note text, or sensitive user-generated content.
2. **User Identification:** Authenticated users are identified exclusively via non-reversible pseudonymous IDs (`user_id`: UUID). Anonymous users use ephemeral session tokens.
3. **Trigger Principle:** Log events after an action is completed or confirmed by the backend, rather than on preliminary button clicks.
4. **Environment Tagging:** Every payload inherits the environment context (`env`: `production` | `staging` | `development`).

---

## 2. Global Event Context & User Properties

Every event automatically includes or inherits the following context:

| Context Attribute | Type | Description | Permitted Values |
| :--- | :--- | :--- | :--- |
| `user_id` | String | Pseudonymous user identifier (UUID) | UUID or `anonymous` |
| `user_type` | String | Authentication state | `authenticated`, `anonymous` |
| `user_role` | String | Academic role | `student`, `faculty`, `admin`, `guest` |
| `user_college` | String | College name (sanitized) | Standard college string |
| `user_branch` | String | Department/branch | `Computer Science`, `Mechanical`, etc. |
| `user_year_of_study`| String | Current academic year | `1`, `2`, `3`, `4`, `alumni` |
| `creator_status` | String | Content upload lifecycle cohort | `never_uploaded`, `uploader`, `active_uploader` |
| `reader_status` | String | Content reading lifecycle cohort | `never_read`, `reader`, `active_reader` |
| `engagement_stage` | String | User activity tier | `new`, `activated`, `returning`, `dormant` |
| `platform` | String | Client form factor | `mobile`, `tablet`, `desktop` |
| `session_id` | String | Ephemeral session token | String |

---

## 3. Canonical Event Dictionary

### 3.1 Acquisition & Authentication

#### `page_view`
- **Description:** Standard page view emitted once per logical page or SPA route change.
- **Trigger:** Page load / client-side route completion.
- **Required Parameters:** `page_title`, `page_path`, `page_category`.
- **Optional Parameters:** `referrer`.
- **Validation Rule:** Must not fire multiple times for the same URL path without a route change.

#### `sign_up`
- **Description:** New account registered.
- **Trigger:** Supabase Auth registration confirmation.
- **Required Parameters:** `method` (`email`, `google`).
- **Optional Parameters:** None.
- **Validation Rule:** Must never pass email or raw identity metadata.

#### `login`
- **Description:** User successfully authenticated.
- **Trigger:** Supabase Auth session establishment.
- **Required Parameters:** `method` (`email`, `google`).
- **Optional Parameters:** None.
- **Validation Rule:** Strictly exclude `user_email` and `user_name` parameter fields.

#### `login_failed`
- **Description:** User failed an authentication attempt.
- **Trigger:** Auth endpoint rejection.
- **Required Parameters:** `method` (`email`, `google`), `reason_code` (`invalid_credentials`, `user_not_found`, `rate_limited`, `network_error`).
- **Optional Parameters:** None.
- **Validation Rule:** Never log passwords, attempted emails, or raw exception strings.

#### `logout`
- **Description:** Active user session terminated.
- **Trigger:** User clicks logout or session invalidated.
- **Required Parameters:** None.
- **Optional Parameters:** `session_duration_seconds`.

#### `consent_updated`
- **Description:** User accepted or declined analytics tracking in the consent banner.
- **Trigger:** Consent banner action button click.
- **Required Parameters:** `analytics_allowed` (Boolean).
- **Optional Parameters:** None.

---

### 3.2 Activation & Navigation

#### `dashboard_viewed`
- **Description:** User accessed their primary personalized dashboard.
- **Trigger:** Navigation to `/dashboard`.
- **Required Parameters:** `surface` (`student_dashboard`, `admin_dashboard`).
- **Optional Parameters:** None.

#### `feature_viewed`
- **Description:** User exposed to a key product feature or interactive panel.
- **Trigger:** Feature modal opened or section visible in viewport.
- **Required Parameters:** `feature_name` (`study_pass`, `ocr_scanner`, `exam_timer`, `ai_explainer`, `leaderboard`).
- **Optional Parameters:** `source` (`banner`, `nav_menu`, `direct`).

#### `search_submitted`
- **Description:** User executed a search query.
- **Trigger:** Search form submit / enter pressed.
- **Required Parameters:** `search_area` (`global`, `notes`, `pyq`, `subject`), `result_count` (Integer), `query_length` (Integer).
- **Optional Parameters:** `is_refinement` (Boolean).
- **Validation Rule:** **CRITICAL:** Do NOT send raw query text. Send `query_length` and token count only.

#### `filter_applied`
- **Description:** User modified a list filter or sort dropdown.
- **Trigger:** Filter dropdown/tag changed.
- **Required Parameters:** `area` (`notes_list`, `pyq_list`, `storeroom`), `filter_name` (`semester`, `year`, `exam_type`, `sort_order`).
- **Optional Parameters:** `result_count` (Integer).

---

### 3.3 Notes & PYQs (Content Lifecycle)

#### `content_list_viewed`
- **Description:** User viewed a catalogue or list of study resources.
- **Trigger:** Resource listing page rendered.
- **Required Parameters:** `content_type` (`notes`, `pyq`, `practicals`, `mixed`), `source` (`subject_page`, `search_results`, `browse`), `result_count` (Integer).
- **Optional Parameters:** `subject` (String).

#### `content_viewed`
- **Description:** User opened a specific note, paper, or practical file in viewer.
- **Trigger:** Document viewer rendered with content loaded.
- **Required Parameters:** `content_type` (`notes`, `pyq`, `practicals`), `content_id` (Document UUID or coarse key), `category` (Subject name).
- **Optional Parameters:** `branch` (String), `academic_year` (String).

#### `content_engaged`
- **Description:** User performed meaningful engagement with educational content.
- **Trigger:** Threshold reading time met ($\ge 15\text{s}$), file downloaded, bookmark added, or link shared.
- **Required Parameters:** `content_type` (`notes`, `pyq`, `practicals`), `engagement_type` (`read`, `download`, `bookmark`, `share`).
- **Optional Parameters:** `duration_seconds` (Integer), `share_channel` (`whatsapp`, `copy_link`).

#### `content_reported`
- **Description:** User reported inappropriate or incorrect content.
- **Trigger:** Content report modal submitted.
- **Required Parameters:** `content_type` (`notes`, `pyq`), `reason_code` (`wrong_subject`, `poor_quality`, `copyright`, `inappropriate`).
- **Optional Parameters:** None.

#### `upload_started`
- **Description:** User initiated an upload sequence.
- **Trigger:** Upload button clicked or files dropped into dropzone.
- **Required Parameters:** `content_type` (`notes`, `pyq`, `syllabus`), `method` (`drag_drop`, `file_picker`, `camera`).
- **Optional Parameters:** `file_count` (Integer).

#### `upload_completed`
- **Description:** Upload successfully written and confirmed by server.
- **Trigger:** Server response `200 OK` on `/api/bulk-upload` or `/api/upload`.
- **Required Parameters:** `content_type` (`notes`, `pyq`), `file_type` (`pdf`, `image`), `file_size_bucket` (`small_<1mb`, `medium_1-5mb`, `large_>5mb`), `category` (Subject), `duration_ms` (Integer).
- **Optional Parameters:** `file_count` (Integer), `points_awarded` (Integer).

#### `upload_failed`
- **Description:** Upload attempt aborted or rejected.
- **Trigger:** Client validation error or server 4xx/5xx upload error.
- **Required Parameters:** `content_type` (`notes`, `pyq`), `failure_code` (`file_too_large`, `invalid_extension`, `server_error`, `quota_exceeded`), `stage` (`client_validation`, `network_transfer`, `server_ingestion`).
- **Optional Parameters:** None.

#### `upload_abandoned`
- **Description:** User closed the upload dialog after selecting files without submitting.
- **Trigger:** Modal close / page navigation with active pending files.
- **Required Parameters:** `stage` (`file_selected`, `metadata_entry`).
- **Optional Parameters:** None.

---

### 3.4 Profile, Storeroom & Saves

#### `profile_viewed`
- **Description:** User accessed profile settings or user card.
- **Trigger:** Navigation to `/profile`.
- **Required Parameters:** None.
- **Optional Parameters:** `is_own_profile` (Boolean).

#### `profile_updated`
- **Description:** Profile fields modified.
- **Trigger:** Save profile action.
- **Required Parameters:** `changed_fields` (Array of field names, e.g., `['college', 'branch']`).
- **Optional Parameters:** None.
- **Validation Rule:** Never send updated field values (e.g. phone numbers or names).

#### `storeroom_viewed`
- **Description:** User viewed their saved/bookmarked documents in Storeroom.
- **Trigger:** Navigation to `/store-room` or `/storeroom`.
- **Required Parameters:** `saved_items_count` (Integer).
- **Optional Parameters:** None.

#### `item_saved`
- **Description:** Document saved/bookmarked for offline or later access.
- **Trigger:** Bookmark toggle active.
- **Required Parameters:** `content_type` (`notes`, `pyq`), `content_id` (Document UUID).
- **Optional Parameters:** None.

#### `item_removed`
- **Description:** Document removed from bookmarks.
- **Trigger:** Bookmark toggle inactive.
- **Required Parameters:** `content_type` (`notes`, `pyq`), `content_id` (Document UUID).
- **Optional Parameters:** None.

---

### 3.5 Reliability, Errors & Friction

#### `client_error`
- **Description:** Client-side JavaScript exception caught.
- **Trigger:** `window.onerror` or catch block in critical UI components.
- **Required Parameters:** `error_code` (e.g., `PDF_RENDER_FAIL`, `STORAGE_UNAVAILABLE`), `surface` (UI component name), `recoverable` (Boolean).
- **Optional Parameters:** None.

#### `api_error`
- **Description:** Client fetch encountered non-2xx HTTP response or network drop.
- **Trigger:** API fetch rejection.
- **Required Parameters:** `route_group` (`auth`, `upload`, `documents`, `search`), `status_class` (`4xx`, `5xx`, `network_fail`), `operation` (`fetch_notes`, `submit_upload`).
- **Optional Parameters:** None.
- **Validation Rule:** Strictly prohibit logging request payloads, tokens, or URL parameters with sensitive IDs.

#### `empty_state_viewed`
- **Description:** User encountered an empty content screen or zero search results.
- **Trigger:** Render of zero-results container.
- **Required Parameters:** `surface` (`search`, `subject_notes`, `storeroom`, `notifications`), `reason_code` (`no_results_found`, `no_uploads_yet`, `empty_storeroom`).
- **Optional Parameters:** None.

#### `feature_blocked`
- **Description:** User attempted an action blocked by permission, quota, or study pass.
- **Trigger:** Quota gate or study pass modal triggered.
- **Required Parameters:** `feature_name` (`document_view`, `document_download`, `chat`), `reason_code` (`quota_exhausted`, `unauthenticated`, `restricted_role`).
- **Optional Parameters:** None.

#### `feedback_submitted`
- **Description:** User submitted rating or structured feedback.
- **Trigger:** Feedback widget submission.
- **Required Parameters:** `feedback_type` (`bug_report`, `feature_request`, `content_quality`), `rating_bucket` (`1_star`, `2_star`, `3_star`, `4_star`, `5_star`, `positive`, `negative`).
- **Optional Parameters:** None.
- **Validation Rule:** Do not pass raw free-text feedback into GA4 payloads.

---

## 4. Legacy Event Compatibility & Migration Map

| Legacy Event Name | Canonical Replacement | Migration Action |
| :--- | :--- | :--- |
| `upload_funnel` (`3_upload_started`) | `upload_started` | Replace string event with canonical typed event. |
| `upload_funnel` (`4_upload_completed`) | `upload_completed` | Replace string event with server-confirmed event. |
| `file_upload` | `upload_completed` | Deprecate duplicate event. |
| `file_view` / `view_item` | `content_viewed` | Consolidate duplicate events into `content_viewed`. |
| `file_download` / `select_content` | `content_engaged` (`engagement_type: 'download'`) | Consolidate into standard engagement taxonomy. |
| `subject_access` | `content_list_viewed` (`source: 'subject_page'`) | Route through canonical list view event. |
| `filter_combination` | `filter_applied` | Remove composite string creation; emit single filter changes. |
| `session_start_custom` | (Dropped) | Rely on native GA4 `session_start`. |
| `engagement_time` | `content_engaged` (`engagement_type: 'read'`) | Replace periodic polling with threshold engagement. |
| `camera_upload` | `upload_started` (`method: 'camera'`) | Pass `method` parameter in `upload_started`. |
| `study_pass_*` | `feature_viewed` / `feature_blocked` | Standardize with `feature_name: 'study_pass'`. |
| `app_error` | `client_error` / `api_error` | Type errors into client vs API categories. |
