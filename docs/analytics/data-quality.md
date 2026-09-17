# AbhiHub Analytics Data Quality & Reconciliation Guide

**Version:** 1.0.0  
**Scope:** Data integrity, anomaly detection, deduplication, and database-to-GA4 reconciliation.

---

## 1. Data Quality Principles

1. **Deterministic Cohorts:** User classifications (viewer, reader, uploader, contributor-reader) must be derived from verifiable server-side events, not arbitrary frontend clicks.
2. **Deduplication:** Pageviews and file interactions must be deduplicated across SPA route changes and re-renders using session and transaction keys.
3. **Environment Isolation:** Telemetry from `localhost`, PR preview deployments, and automated testing must never enter production GA4 streams.

---

## 2. Automated Reconciliation Queries

To ensure analytics accuracy, scheduled jobs and database audits compare Supabase transactional records against analytics totals.

### 2.1 Daily Document Views Reconciliation
Verify client-reported `content_viewed` events against authoritative `abhihub.document_views` inserts:

```sql
-- Supabase SQL Query: Total authoritative views per day by document
SELECT 
    DATE(accessed_at) AS view_date,
    document_id,
    COUNT(*) AS server_view_count,
    COUNT(DISTINCT user_id) AS unique_readers
FROM abhihub.document_views
WHERE accessed_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(accessed_at), document_id
ORDER BY view_date DESC, server_view_count DESC;
```
*Acceptable Tolerance:* Client GA4 `content_viewed` events should match `server_view_count` within $\pm 5\%$ (accounting for ad-blockers and offline drops).

### 2.2 Upload Completion Reconciliation
Verify GA4 `upload_completed` counts against newly created documents in `abhihub.documents`:

```sql
-- Supabase SQL Query: Authoritative uploads per day
SELECT 
    DATE(created_at) AS upload_date,
    COUNT(*) AS authoritative_uploads,
    COUNT(DISTINCT uploader_id) AS active_uploaders
FROM abhihub.documents
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY upload_date DESC;
```
*Acceptable Tolerance:* GA4 `upload_completed` count must not exceed `authoritative_uploads`. A discrepancy where GA4 > DB indicates frontend firing before backend commit.

### 2.3 User Cohort Distribution Check
Classify active users into distinct behavioral cohorts over rolling 30-day windows:

```sql
-- Cohort analysis query
WITH user_activity AS (
    SELECT 
        p.id AS user_id,
        COALESCE(u.upload_count, 0) AS total_uploads,
        COALESCE(v.view_count, 0) AS total_views
    FROM abhihub.profiles p
    LEFT JOIN (
        SELECT uploader_id, COUNT(*) AS upload_count 
        FROM abhihub.documents 
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY uploader_id
    ) u ON p.id = u.uploader_id
    LEFT JOIN (
        SELECT user_id, COUNT(*) AS view_count 
        FROM abhihub.document_views 
        WHERE accessed_at >= NOW() - INTERVAL '30 days'
        GROUP BY user_id
    ) v ON p.id = v.user_id
)
SELECT 
    CASE 
        WHEN total_uploads > 0 AND total_views > 0 THEN 'contributor_reader'
        WHEN total_uploads > 0 AND total_views = 0 THEN 'uploader_only'
        WHEN total_uploads = 0 AND total_views > 0 THEN 'reader_only'
        ELSE 'dormant_or_new'
    END AS cohort_segment,
    COUNT(*) AS user_count
FROM user_activity
GROUP BY 1;
```

---

## 3. Anomaly Detection & Quality Thresholds

| Metric | Normal Range | Alert Threshold | Action Required |
| :--- | :--- | :--- | :--- |
| **Duplicate Event Rate** | $< 1\%$ | $> 3\%$ | Inspect route listener bindings and event throttling. |
| **Missing Parameter Rate** | $0\%$ | $> 0.5\%$ | Verify client form validation and required parameter contracts. |
| **Server vs GA4 Divergence** | $3\% - 8\%$ | $> 15\%$ | Check ad-blocker rates, CSP violations, or broken SDK loading. |
| **Client Error Rate** | $< 0.5\%$ | $> 2\%$ | Inspect client error logs for breaking JS exceptions. |
| **Zero Search Rate** | $10\% - 20\%$ | $> 35\%$ | Review search indexing, fuzzy match weights, and query synonyms. |

---

## 4. Test Environment Isolation Strategy

1. **Host-Based Gating:** The client analytics library checks `window.location.hostname`. If the hostname is `localhost`, `127.0.0.1`, or ends with `.local`, live GA4 network requests are suppressed.
2. **Debug Logger:** In development, calls to `AbhiHubAnalytics.track(...)` output formatted, color-coded diagnostic logs in the browser developer console without transmitting network requests.
3. **Automated Testing Mode:** In pytest / Playwright suites, `window.__ABHIHUB_TEST_MODE__ = true` ensures events are pushed to an in-memory test queue (`window.__ABHIHUB_EVENT_LOG__`) for automated assertion.
