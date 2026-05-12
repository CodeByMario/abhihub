# File Access History System

## Overview
Tracks which files users access/view. Used to power the "Recently Accessed Files" feature and the Papo Meter.

## Architecture

### Data Flow
```
User opens file → /preview or /view_pdf route
  → save_file_access(user_email, file_name, ...)
    → Resolves document_id from record_id / file_url / file_path / title
    → Resolves user_id from email
    → Increments view_count on documents table
    → Logs to document_views table via DocumentView.log_view()
```

### Database Table: `abhihub.document_views`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `document_id` | UUID (FK → documents) | Document being viewed |
| `user_id` | UUID (FK → profiles) | User viewing the document |
| `ip_address` | TEXT | Optional IP |
| `device_type` | TEXT | Optional device type |
| `accessed_at` | TIMESTAMPTZ | Auto-set by DB default `NOW()` |

**Current rows:** ~2148 (as of May 2026)

### ⚠ Deprecated: `file_access_history` table
This table exists but has **RLS permission denied (42501)**. All code has been migrated to use `document_views` instead. Do NOT use `file_access_history`.

## Key Functions

### `save_file_access()` — `methods/supabase_helper.py`
Main entry point for logging file access. Called from:
- `/preview` route (line ~1178 in app.py)
- `/pdf-viewer` route (line ~1220)
- `/view_pdf` route (line ~1668)
- `/api/track-file-access` API endpoint (line ~2711)

**Logic:**
1. Resolve `document_id` from `record_id` → `file_url` → `file_path` → `file_name`
2. Resolve `user_id` from email
3. Increment `view_count` in `documents` table
4. Call `DocumentView.log_view()` to insert into `document_views`

### `DocumentView.log_view()` — `data/interactions.py`
Low-level insert into `document_views`. Validates UUIDs. Does NOT set `accessed_at` (DB default handles it).

### `get_user_file_history()` — `methods/supabase_helper.py`
Fetches recent files viewed by a user. Queries `document_views` with document details join. Returns deduplicated list with file_name, file_type, file_url, accessed_at.

### `DocumentView.get_recent_for_user()` — `data/interactions.py`
Alternative method for fetching recent views. Returns raw view records with nested document data.

## Client-Side Tracking
`static/js/file-history-tracker.js` defines `trackFileAccess()` which POSTs to `/api/track-file-access`. Exposed via `window.trackFileAccess`.

## Bugs Fixed (May 2026)
1. **`file_access_history` table permission denied** — Removed all inserts to this table; now uses `document_views` only
2. **`accessed_at: "now()"` sent as string** — Removed from `DocumentView.log_view()`; DB default `NOW()` handles it
3. **Missing `file_path` fallback** — Added lookup by `file_path` when `record_id` and `file_url` fail
4. **Invalid `record_id` not validated** — Added `validate_uuid()` check before using as `doc_id`
5. **`get_user_file_history` querying broken table** — Switched from `file_access_history` to `document_views`

## Files
- `methods/supabase_helper.py` — `save_file_access()`, `get_user_file_history()`, `get_papo_meter_data()`
- `data/interactions.py` — `DocumentView` class (log_view, get_recent_for_user)
- `static/js/file-history-tracker.js` — Client-side tracking helper
- `app.py` — Routes that call `save_file_access()`
