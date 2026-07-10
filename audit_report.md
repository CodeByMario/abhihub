# Comprehensive Application Audit Report

## 1. app.py (Lines 1-800)

### Security Issues
- **Local Dev Credentials Fallback**: `app.py` lines 34-37. Falling back to `firebase-auth.json` in local is common, but it has a note. This is okay, but `firebase-auth.json` is present in the root folder according to directory list (`{"name":"firebase-auth.json", "sizeBytes":"2364"}`). Ensure it is gitignored.
- **CSRF Token without Time Limit**: `app.config['WTF_CSRF_TIME_LIMIT'] = None` (line 194). This disables expiration for CSRF tokens, which increases the window of opportunity for a captured token to be used.

### Bugs / Logic Flaws
- **Session Reset Condition**: In `_get_quota()` (line 303), the condition `if last_reset != current_month:` checks against the current month string. However, if the quota is not found (and defaults to '2026-05'), it will forcefully reset the quota and `last_reset`. This is correct logically, but a minor flaw is hardcoding `'2026-05'` as the default fallback in multiple places (lines 295, 300).
- **Hardcoded Emails for Admin**: Lines 273 and 341 hardcode admin emails. This should ideally be a role checked in the database or an environment variable `ADMIN_EMAILS` (though `ADMIN_EMAIL` is loaded on line 260 but not used for the check list, which hardcodes two emails).

### Code Optimization & Unnecessary Code
- **Custom Fuzzy Search (`_similar`, `_parse_query`, etc.)**: Lines 43-170 contain custom tokenization, synonym mapping, and fuzzy search logic. This is highly inefficient in Python for a large dataset and should be offloaded to a proper search engine (like Meilisearch, Algolia, or Postgres Full Text Search/pg_trgm) or Supabase's built-in full-text search.
- **Redundant Database Calls**: `_get_quota()` (line 293) and `_grant_upload_credits()` (line 324) and `_consume_credit()` (line 356) all make synchronous calls to Supabase on every single operation. For heavily accessed endpoints, this will slow down the application significantly.
- **Multiple Imports of Same Module**: `import json` on line 9 and again on line 31, line 374. `from datetime import datetime` on line 10 and again inside `_recent_year_boost` on line 137. `import logging` on line 11 and again on line 372.

### Duplicate Code
- Route `/reset-password-confirm` (line 489) does not actually handle the token logic but assumes the client will handle it. This might be correct for SPA but is mixed within standard Flask routes.

---

## 2. app.py (Lines 801-1600)

### Security Issues
- **Missing Input Length Validation**: The endpoints `/api/subjects`, `/api/colleges`, `/api/departments` directly insert user input into the database. While they use `.strip()`, they do not check for maximum length or valid character patterns, potentially leading to payload size issues or database errors.

### Bugs / Logic Flaws
- **Late Imports Inside Functions**: There are multiple instances of imports inside functions (e.g., `import traceback` on lines 1123, 1240, 1287, 1337, 1410). While sometimes used to prevent circular imports, standard library modules like `traceback` should be imported at the top of the file to save overhead.

### Code Optimization & Unnecessary Code
- **Duplicate Device Detection Logic**: Lines 1208-1213 (`api_log_document_view`) are exactly identical to lines 425-430 (`authorize`). This device detection logic should be extracted into a shared helper function (e.g., `get_device_type(user_agent)`).
- **Giant Monolithic Route**: The `/upload` route starting at line 1420 is extremely long and handles everything from file validation, Cloudinary uploading, database insertion, event tracking, indexing, to reputation score calculations. This is a massive violation of the Single Responsibility Principle and should be broken down into smaller helper functions in `methods/`.

---

## 3. app.py (Lines 1601-2400)

### Security Issues
- **SSRF via Proxy endpoints**: The `/api/proxy-file` endpoint validates hostnames via `_ALLOWED_PROXY_HOSTS` which is good, but does not strictly restrict schemes (though the requests library will fail on `file://`).

### Bugs / Logic Flaws
- **Redundant Global Searches (O(N) operations)**: In the `/dashboard` route (line 1930), there is a linear search (`for entry in rank_list:`) over the entire ranking list to find the current user's rank. If `rank_list` grows, this will cause significant performance degradation. It should be converted to a dictionary lookup or processed at the database query level.

### Code Optimization & Unnecessary Code
- **Duplicate Quota Check & Logging**: Both `/preview` (line 1634) and `/pdf-viewer` (line 1693) contain exact duplicate blocks of code for checking the quota (`_consume_credit()`) and logging the file access (`save_file_access()`). This should be moved to a shared function or decorator.
- **Inefficient List Comprehensions**: In the `/dashboard` route (lines 1880-1883), multiple list comprehensions iterate over the large `files` array repeatedly to extract subjects, count papers, count notes, etc. This should be combined into a single pass to improve efficiency.
- **Giant Dashboard Route**: Similar to `/upload`, the `/dashboard` route (line 1874) is a monolithic controller handling data processing, ranking logic, profile enforcement, SEO generation, and rendering.
