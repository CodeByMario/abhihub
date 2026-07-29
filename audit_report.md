# AbhiHub Codebase Audit Report
> **Generated**: 2026-07-11 | **Scanner**: audit_scan.py | **Raw findings**: audit_findings.json

## Executive Summary

| Metric | Count |
|--------|-------|
| Total Findings | **277** |
| CRITICAL | 0 |
| HIGH | **14** |
| MEDIUM | 140 |
| LOW | 123 |

| Category | Count | Description |
|----------|-------|-------------|
| BUG | 12 | Bare excepts, hardcoded dates, logic issues |
| SEC | 5 | Security — hardcoded emails, CSRF, SSRF |
| DUPE | 149 | Duplicate imports, copy-pasted blocks |
| OPT | 87 | `print()` in prod, O(N) loops, list passes |
| LIB | 4 | Custom code where libraries exist |
| DEAD | 20 | Unused files (136KB+ of dead JS alone) |

---

## Phase 3 Fix Backlog (Priority Ordered)

### STEP 1 — Critical Bugs (HIGH severity, BUG category)

| # | File | Line | Issue | Fix |
|---|------|------|-------|-----|
| 1 | `methods/supabase_helper.py` | 72 | Bare `except:` silently masks all errors | Replace with `except Exception as e: logger.error(...)` |
| 2 | `methods/supabase_helper.py` | 767 | Bare `except:` silently masks all errors | Same as above |
| 3 | `methods/supabase_helper.py` | 837 | Bare `except:` silently masks all errors | Same as above |
| 4 | `methods/supabase_helper.py` | 868 | Bare `except:` silently masks all errors | Same as above |
| 5 | `methods/supabase_helper.py` | 1112 | Bare `except:` silently masks all errors | Same as above |
| 6 | `methods/supabase_helper.py` | 1482 | Bare `except:` silently masks all errors | Same as above |
| 7 | `methods/supabase_helper.py` | 1807 | Bare `except:` silently masks all errors | Same as above |
| 8 | `methods/supabase_helper.py` | 1821 | Bare `except:` silently masks all errors | Same as above |
| 9 | `methods/upload_notifier.py` | 138 | Bare `except:` silently masks all errors | Same as above |

**Status**: `[ ]` Pending

---

### STEP 2 — Security Fixes (HIGH/MEDIUM, SEC category)

| # | File | Line | Issue | Fix |
|---|------|------|-------|-----|
| 1 | `app.py` | 194 | `WTF_CSRF_TIME_LIMIT = None` — tokens never expire | Set to `3600` |
| 2 | `app.py` | 273 | Admin email list hardcoded in source | Move to `ADMIN_EMAILS` env var, split on comma |
| 3 | `app.py` | 341 | Admin email list hardcoded again (second location) | Same as above |
| 4 | `app.py` | 260 | `ADMIN_EMAIL` loaded from env but hardcoded list ignores it | Use env var consistently |
| 5 | `app.py` | ~1634 | `/preview` + `/pdf-viewer` inline quota check — no rate-limit on SSRF proxy | Validate scheme explicitly |

**Status**: `[ ]` Pending

---

### STEP 3 — Deduplication (HIGH/MEDIUM, DUPE category)

#### 3a. Imports inside functions (app.py — 20+ occurrences)
All `from methods.supabase_helper import X` calls are inside route functions.
These should be moved to the top of `app.py`.

Key repeated imports found at lines:
`509, 757, 776, 799, 823, 848, 891, 909, 932, 980, 1006, 1033, 1046, 1055, 1069, 1243, 1257...`

**Fix**: Consolidate all `supabase_helper` imports into one block at the top of `app.py`.

#### 3b. Symbol imported multiple times at module level

| Symbol | Import Count | Lines |
|--------|-------------|-------|
| `init_supabase` | 9× | 602, 615, 687, 757, 776... |
| `get_student_profile` | 3× | 2016, ... |
| `storage` | 4× | 25, 3420, ... |
| `Image` | 2× | 373, 4254 |
| `datetime` | 2× in app.py | 10, 1113 |
| `datetime` | 2× in supabase_helper.py | 8, 1537 |

**Fix**: Keep one import per symbol at the top.

#### 3c. Device detection logic duplicated
- `app.py:425-430` (authorize)
- `app.py:1208-1213` (api_log_document_view)

**Fix**: Extract to `get_device_type(user_agent)` in `methods/`

#### 3d. Quota + file access log block duplicated
- `/preview` route
- `/pdf-viewer` route

**Fix**: Extract to `@require_view_quota` decorator or `check_and_log_view()` helper.

**Status**: `[ ]` Pending

---

### STEP 4 — Dead Code Removal (LOW, DEAD category)

> Confirm before deleting — move to `/trash` if unsure.

| File | Size | Action |
|------|------|--------|
| `old_store_room.js` | **136KB** | Delete (replaced by new implementation) |
| `migrate_main_data.py` | 13KB | Delete (migration complete) |
| `migrate_final_data.py` | 8KB | Delete |
| `migrate_data.py` | 4KB | Delete |
| `migrate_data_and_rank.py` | 4KB | Delete |
| `sync_firebase_documents.py` | 12KB | Confirm if still needed |
| `migrate_data_json.py` | 3KB | Delete |
| `migrate_search_index.py` | 1KB | Delete |
| `verify_db.py` | 0KB | Delete |
| `verify_migration.py` | 1KB | Delete |
| `check2.py` | 0KB | Delete |
| `check_docs.py` | 0KB | Delete |
| `replace.py` | 0KB | Delete |
| `inspect_db.py` | 0KB | Delete |
| `test_stats.py` | 0KB | Delete |
| `test_supabase.py` | 0KB | Delete |
| `test_supabase2.py` | 0KB | Delete |
| `test_ts.js` | 0KB | Delete |
| `test_ts2.js` | 0KB | Delete |
| `test_ts3.js` | 0KB | Delete |

**Total savings**: ~180KB of dead files

**Status**: `[ ]` Pending (awaiting user confirmation on list)

---

### STEP 5 — Optimization (MEDIUM, OPT category)

| # | File | Line | Issue | Fix |
|---|------|------|-------|-----|
| 1 | `app.py` | ~1930 | Linear `for entry in rank_list:` to find user's rank | Convert to `{e['uid']: e for e in rank_list}` dict |
| 2 | `app.py` | ~1880 | 4 separate list comprehensions over `files` in `/dashboard` | Single pass: `for f in files: count by type` |
| 3 | `app.py` | ~1420 | Monolithic `/upload` route — file validation, upload, DB insert, indexing, XP all in one function | Extract to `methods/upload_handler.py` |
| 4 | `app.py` | ~1874 | Monolithic `/dashboard` route | Extract heavy logic to `methods/dashboard_handler.py` |
| 5 | `app.py` + `supabase_helper.py` | many | 87 `print()` calls in production code | Replace with `logging.info/debug/error` |

**Status**: `[ ]` Pending

---

### STEP 6 — Library Replacements (MEDIUM, LIB category)

| # | File | Lines | Current | Replacement |
|---|------|-------|---------|-------------|
| 1 | `app.py` | 43–170 | Custom `_similar()`, `_parse_query()`, `_tokenize()` — ~128 lines of fuzzy search | `rapidfuzz` (`pip install rapidfuzz`) or Supabase FTS |
| 2 | `cors.py` | all | Manual CORS setup alongside `flask-cors` | Confirm redundant, delete `cors.py` |
| 3 | `methods/supabase_helper.py` | many | `traceback` imported inside functions | Move to top-of-file import |
| 4 | `app.py` | ~509 | `re` imported inside function | Move to top-level |

**Status**: `[ ]` Pending (await user decision on fuzzy search approach)

---

### STEP 7 — Simplification (MEDIUM, SIMPLIFY category)

| # | Issue | Fix |
|---|-------|-----|
| 1 | Admin emails hardcoded in 2 places | `.env`: `ADMIN_EMAILS=a@b.com,c@d.com` → `os.getenv('ADMIN_EMAILS','').split(',')` |
| 2 | Hardcoded date strings like `'2026-05'` as fallback | Use `datetime.now().strftime('%Y-%m')` |
| 3 | `/api/subjects`, `/api/colleges`, `/api/departments` have no input length validation | Add `if len(name) > 100: return 400` guard |
| 4 | `WTF_CSRF_TIME_LIMIT = None` | Set to `3600` |

**Status**: `[ ]` Pending

---

## Files NOT Scanned Yet (future phases)

- `templates/` — HTML templates (XSS, template injection)
- `static/` — JS files (client-side security)
- `ts.js` (49KB) — TypeScript compiled output
- `push_notifications.py`, `scheduled_tasks.py`
- `methods/know_me.py` (17KB)
- `methods/admin_db_helper.py`
