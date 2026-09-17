# AbhiHub Analytics Dashboard & Custom Dimensions Specification

**Version:** 1.0.0  
**Target Platforms:** Google Analytics 4 (GA4 Console) & Admin Internal Dashboard (`/admin/analytics`)

---

## 1. Google Analytics 4 Custom Definitions

To enable reporting in GA4 Explore and standard reports, the following Custom Dimensions and Metrics must be registered in the Google Analytics Console (*Admin $\rightarrow$ Custom Definitions*).

### 1.1 Custom Dimensions (User Scope)

| Dimension Name | Scope | Event Parameter / Property | Description |
| :--- | :--- | :--- | :--- |
| `User Role` | User | `user_role` | Student, faculty, admin, or guest |
| `User College` | User | `user_college` | Standardized college name |
| `User Branch` | User | `user_branch` | Engineering branch / department |
| `User Year of Study` | User | `user_year_of_study` | Academic year (1, 2, 3, 4, alumni) |
| `Creator Status` | User | `creator_status` | `never_uploaded`, `uploader`, `active_uploader` |
| `Reader Status` | User | `reader_status` | `never_read`, `reader`, `active_reader` |
| `Engagement Stage` | User | `engagement_stage` | `new`, `activated`, `returning`, `dormant` |
| `Auth Method` | User | `auth_method` | `google`, `email` |

### 1.2 Custom Dimensions (Event Scope)

| Dimension Name | Scope | Event Parameter | Description |
| :--- | :--- | :--- | :--- |
| `Content Type` | Event | `content_type` | `notes`, `pyq`, `practicals`, `syllabus` |
| `Content Category` | Event | `category` | Subject name |
| `Engagement Type` | Event | `engagement_type` | `read`, `download`, `bookmark`, `share` |
| `Search Area` | Event | `search_area` | `global`, `notes`, `pyq`, `subject` |
| `Filter Name` | Event | `filter_name` | `semester`, `year`, `exam_type`, `sort_order` |
| `File Size Bucket` | Event | `file_size_bucket` | `small_<1mb`, `medium_1-5mb`, `large_>5mb` |
| `Failure Code` | Event | `failure_code` | Categorical error reason |
| `Feature Name` | Event | `feature_name` | `study_pass`, `ocr_scanner`, `exam_timer` |

### 1.3 Custom Metrics

| Metric Name | Scope | Event Parameter | Unit | Description |
| :--- | :--- | :--- | :--- | :--- |
| `Reading Duration (s)` | Event | `duration_seconds` | Seconds | Time spent actively reading notes |
| `Upload Duration (ms)` | Event | `duration_ms` | Milliseconds | End-to-end upload transfer latency |
| `Search Result Count` | Event | `result_count` | Standard | Number of search results returned |
| `Query Character Length` | Event | `query_length` | Standard | Character length of search query |

---

## 2. GA4 Audience Definitions

Configure the following dynamic audiences in GA4 to analyze behavioral segments:

1. **Active Readers:** Users who triggered $\ge 3$ `content_engaged` (`engagement_type: 'read'`) events in the last 14 days and $0$ `upload_completed` events.
2. **Active Uploaders:** Users who triggered $\ge 1$ `upload_completed` event in the last 30 days and $< 3$ `content_engaged` events.
3. **Core Contributors (Contributor-Readers):** Users with $\ge 1$ `upload_completed` and $\ge 5$ `content_engaged` events in the last 30 days.
4. **Friction Cohort (Upload Dropoffs):** Users who triggered `upload_started` or `upload_failed` without a subsequent `upload_completed` within 24 hours.
5. **Dormant Users:** Registered users with $0$ sessions in the past 28 days.

---

## 3. Core Funnel & Dashboard Specifications

### 3.1 Reader Funnel
```
Step 1: content_list_viewed (Catalogue / Subject Page)
  ↓
Step 2: content_viewed (Viewer Opened)
  ↓
Step 3: content_engaged (Read >= 15s)
  ↓
Step 4: content_engaged (Bookmark / Download / Share)
```

### 3.2 Contributor Funnel
```
Step 1: feature_viewed (Upload Screen / Modal)
  ↓
Step 2: upload_started (File Selected)
  ↓
Step 3: upload_completed (Server Confirmed)
  ↓
Step 4: profile_viewed (XP / Points Earned Verification)
```

### 3.3 Study Pass & Quota Friction Dashboard
- **Impression Volume:** Count of `feature_viewed` (`feature_name: 'study_pass'`).
- **Quota Blocks:** Count of `feature_blocked` (`reason_code: 'quota_exhausted'`).
- **Conversion Rate:** `study_pass_upload_click` / `feature_blocked` ratio.
