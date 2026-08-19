# AbhiHub Bug Inventory & Fix Plan

> **Generated:** 2026-08-16 | **Sources:** `audit_report.md`, `security_scan.py`, `adv_security_scan.py`, manual code review
> **Total findings tracked:** 277 raw (audit) + new manual findings = consolidated into ~25 actionable items below

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **HIGH** | Security hole, data integrity risk, or production-breaking behavior. Fix before any new feature work. |
| **MEDIUM** | Code quality / maintainability / performance issue. Fix in a dedicated cleanup pass. |
| **LOW** | Cosmetic, dead code, or minor inconsistency. Fix when convenient or as part of a broader cleanup. |

---

## HIGH — Security & Data Integrity

These must be fixed first. They represent real risk to the platform and its users.

### H1. Bare `except:` silently swallows all errors (no logging)

- **Files:** `methods/supabase_helper.py` (lines 75, 163, 201, 530, and ~7 more), `methods/upload_notifier.py` (line 138)
- **Impact:** Database errors, auth failures, network timeouts, and Firebase exceptions are all silently discarded. The caller sees a generic "failed" response with no way to know what went wrong. Production incidents are invisible.
- **Fix:** Replace every bare `except:` with `except Exception as e: log.error(f"[context] {e}", exc_info=True); return {"success": False, "error": str(e)}` (or re-raise if the caller can't handle it). Keep one intentional bare `except:` only if you genuinely want to catch `KeyboardInterrupt`/`SystemExit` — and add a comment explaining why.

### H2. `/delete-account` has no authentication guard

- **File:** `app.py:2866`
- **Impact:** Any anonymous visitor can call `DELETE /delete-account` and wipe an account. The route is missing `@auth_required`.
- **Fix:** Add `@auth_required` decorator to the `delete_account` function definition. Verify with a quick curl test before deploying.

### H3. Public PDF proxy `/pdf-proxy/<path:pdf_name>` serves raw files with no auth

- **File:** `app.py:3018` (route), `app.py:3169-3231` (handler)
- **Impact:** Anyone who guesses or scrapes a PDF filename can download the raw file directly via `/pdf-proxy/<filename>`. No session check, no rate limit, no Referer validation. This is a direct piracy vector — a user can bypass the in-page viewer entirely.
- **Fix:**
  1. Add `@auth_required` to the `pdf_proxy` route (this is the primary fix — only logged-in users can proxy).
  2. Add Referer check matching `BASE_DOMAIN` (same pattern as `view_doc` at `app.py:2211-2224`).
  3. Add rate limiting per user (e.g. 50 proxied downloads per hour) to prevent abuse.
  4. Set `Content-Disposition: inline` and `Cache-Control: private, no-store, must-revalidate` on the response (already done for `view_doc` but missing here).
  5. When PDF quota is fully implemented, gate this route behind the same quota check as `/preview`.

### H4. Hardcoded admin email fallback in `ADMIN_EMAILS` default

- **File:** `app.py:420`
- **Impact:** If `ADMIN_EMAILS` env var is not set, the code falls back to `['abhijeetshende4053@gmail.com', 'codebymario@gmail.com']`. These are real personal emails embedded in source code. If the env var is set elsewhere (e.g. Heroku config), the fallback is dormant — but the default is still a secret in the repo.
- **Fix:** Change the default to an empty list: `os.getenv('ADMIN_EMAILS', '').split(',')`. Then ensure the Heroku environment has `ADMIN_EMAILS` set. Any route that relies on `ADMIN_EMAILS` being non-empty should handle the empty-list case gracefully (e.g. admin routes return 403 or redirect to a "contact admin" page).

### H5. `WTF_CSRF_TIME_LIMIT = None` — CSRF tokens never expire

- **File:** `app.py:377`
- **Impact:** Once a user's CSRF token is issued, it remains valid indefinitely. If a token is ever leaked (e.g. via a referrer header, log file, or XSS), an attacker can reuse it forever.
- **Fix:** Set `WTF_CSRF_TIME_LIMIT = 3600` (1 hour). Existing tokens will still work until they expire naturally; new tokens will have the 1-hour limit. This is a one-line change.

### H6. `Access-Control-Allow-Origin: '*'` on proxy endpoints

- **Files:** `app.py:2188` (static proxy), `app.py:3220` (PDF proxy)
- **Impact:** Any website on the internet can embed these proxy responses via fetch/XHR. Combined with the public PDF proxy (H3), this means any site can programmatically download AbhiHub PDFs. Even after fixing H3, the wildcard CORS on the static proxy leaks the signed URLs' content to any origin.
- **Fix:** Replace `'*'` with origin-aware logic mirroring the Referer check:
  ```python
  allowed_origin = request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place'
  response.headers['Access-Control-Allow-Origin'] = allowed_origin
  ```
  (Already partially done for `view_doc` — apply the same pattern to the two remaining locations.)

---

## MEDIUM — Code Quality, Maintainability & Performance

These don't cause immediate harm but compound technical debt and make future debugging harder.

### M1. Quota + file access log block duplicated between `/preview` and `/pdf-viewer`

- **Files:** `app.py:~1634` (`/preview`), `app.py:~2600` (`/pdf-viewer`)
- **Impact:** Two copies of the same view-logging logic. A bug fix or feature addition must be applied in both places — easy to miss one.
- **Fix:** Extract to a helper function `_check_and_log_view(user_email, file_name, doc_id, file_type)` in `methods/quota_helper.py` (new file) or at the top of `app.py`. Both routes call the helper. Consider elevating to a `@require_view_quota` decorator for cleaner route definitions.

### M2. Device detection logic duplicated

- **Files:** `app.py:425-430` (in `authorize`), `app.py:1208-1213` (in `api_log_document_view`)
- **Impact:** Same User-Agent parsing copied in two places. Changes to device detection logic must be applied twice.
- **Fix:** Extract to `get_device_type(user_agent: str) -> str` in `methods/utils.py` (new file) or at module level in `app.py`. Both call sites import and use the single function.

### M3. `from methods.supabase_helper import X` inside 20+ route functions

- **File:** `app.py` (lines 509, 757, 776, 799, 823, 848, 891, 909, 932, 980, 1006, 1033, 1046, 1055, 1069, 1243, 1257, and more)
- **Impact:** Imports are re-evaluated on every request. Slightly slower, harder to audit what dependencies each route actually uses, and makes the top-of-file import section misleading (it looks like supabase_helper isn't used, when it's used everywhere).
- **Fix:** Add a single block at the top of `app.py`:
  ```python
  from methods.supabase_helper import (
      init_supabase, get_all_files_merged, get_document_by_id_rich,
      toggle_like, toggle_bookmark, save_file_access, get_user_file_history,
      get_sitemap_urls, get_document_by_id, ...  # 모든 symbol 한 번에
  )
  ```
  Then remove all the inline `from methods.supabase_helper import ...` lines inside route functions. Keep only the rare case where a route imports a symbol that's only needed in one path (e.g. heavy import inside a rarely-hit branch) — and add a comment explaining why.

### M4. `init_supabase` imported 9× at module level

- **File:** `app.py` (lines 602, 615, 687, 757, 776, and more)
- **Impact:** Same function imported multiple times — redundant, slightly increases module load time.
- **Fix:** Keep one `from methods.supabase_helper import init_supabase` at the top. Remove all duplicates.

### M5. `storage`, `Image`, `datetime` imported multiple times at module level

- **Files:** `app.py` (`storage` 4×, `Image` 2×, `datetime` 2×), `methods/supabase_helper.py` (`datetime` 2×)
- **Impact:** Redundant imports. Not a bug per se, but signals sloppy import hygiene.
- **Fix:** Deduplicate — one import per symbol at the top of each file.

### M6. 87 `print()` calls in production code

- **Files:** `app.py` (~80), `methods/supabase_helper.py` (7: lines 1786, 1788, 1789, and more)
- **Impact:** `print()` output goes to stdout, which on Heroku is captured as log output but without log level, timestamp, or structured format. In production, `print()` statements can leak sensitive data (e.g. `print(f"[FILE_ACCESS] ... {user_email}")`), clutter logs, and make it hard to filter by severity.
- **Fix:** Replace every `print()` with the appropriate `logging` call:
  - `print("something")` → `logging.info("something")`
  - `print(f"[FILE_ACCESS] ...")` → `logging.info(f"[FILE_ACCESS] ...")`
  - `print(f"Warning: ...")` → `logging.warning(f"...")`
  - `print(f"Error: ...")` → `logging.error(f"...")`
  Use `sed` or a Python script for the bulk replacement, then manually verify the top 20 most impactful ones.

### M7. Custom fuzzy search (~128 lines) where `rapidfuzz` exists

- **File:** `app.py:43-170` (`_similar()`, `_parse_query()`, `_tokenize()`, `_score_item()`, `_apply_filters()`)
- **Impact:** Custom implementation is ~128 lines, maintained manually, and probably slower than `rapidfuzz` which is already in `requirements.txt` (per `ROUTES.md` section 1.3 note about `rapidfuzz`). The custom tokenizer doesn't handle edge cases like punctuation, stop words, or multi-word phrases as well as a library would.
- **Fix:** Evaluate migrating to `rapidfuzz.process.extract` or Supabase Full-Text Search. This is a larger rewrite — flag as a separate project, not a quick fix. For now, leave the custom implementation but add a `# TODO: migrate to rapidfuzz/Supabase FTS` comment at the top of the block.

### M8. Manual CORS setup alongside `flask-cors` in `cors.py`

- **File:** `cors.py` (entire file)
- **Impact:** Two CORS mechanisms running in parallel — one manual, one via `flask-cors`. They may conflict or double-set headers. The `flask-cors` library is already installed and handles edge cases (preflight, credentials, etc.) better than a manual implementation.
- **Fix:** Audit `cors.py` against what `flask-cors` provides. If `flask-cors` covers all the same cases, delete `cors.py` and rely on `flask-cors` exclusively. If there are custom headers that `flask-cors` can't set, move those into a `flask-cors` `after_request` hook rather than maintaining a parallel system.

### M9. `traceback` imported inside functions in `supabase_helper.py`

- **File:** `methods/supabase_helper.py` (multiple locations)
- **Impact:** `traceback` is imported inside function bodies rather than at the top of the file. Slightly slower on first call, and makes it harder to see what the module depends on.
- **Fix:** Move `import traceback` to the top of `methods/supabase_helper.py` (it's already imported at line 9 — check if the inline imports are duplicates or if they're in functions that don't have access to the module-level import due to scoping).

### M10. `re` imported inside a function in `app.py`

- **File:** `app.py:509`
- **Impact:** Minor — `re` is a stdlib module, import is fast, but it's unusual to import it inside a function.
- **Fix:** Move `import re` to the top of `app.py` alongside the other stdlib imports.

### M11. Hardcoded date strings as fallback (e.g. `'2026-05'`)

- **Files:** Multiple locations in `app.py` and `methods/supabase_helper.py`
- **Impact:** When the code falls back to a hardcoded date, it becomes stale the moment the current month changes. A query for "last month's papers" in June 2026 would still get May 2026 data if the fallback isn't updated.
- **Fix:** Replace all hardcoded date fallbacks with `datetime.now().strftime('%Y-%m')` (or `datetime.utcnow()` if timezone-aware). Example:
  ```python
  # Before:
  default_month = '2026-05'
  # After:
  default_month = datetime.now().strftime('%Y-%m')
  ```

### M12. No input length validation on `/api/subjects`, `/api/colleges`, `/api/departments`

- **Files:** `app.py:~945` (`/api/subjects`), `app.py:~902` (`/api/branches`), `app.py:~922` (`/api/departments`)
- **Impact:** A malicious client can send a 10MB string as a subject name, college name, or department name. Supabase will store it (wasting storage), and the UI may break when rendering extremely long strings.
- **Fix:** Add a length guard at the top of each route:
  ```python
  name = request.json.get('name', '')
  if not name or len(name) > 200:
      return jsonify({'success': False, 'message': 'Name must be 1-200 characters'}), 400
  ```

### M13. Linear O(N) search for user's rank in leaderboard

- **File:** `app.py:~1930`
- **Impact:** For each request to the leaderboard/rank page, the code loops through the entire rank list to find the current user's entry. With N users, this is O(N) per request. Fine for small N, but degrades as the platform grows.
- **Fix:** Convert the rank list to a dict keyed by user ID:
  ```python
  rank_by_uid = {e['uid']: e for e in rank_list}
  user_rank = rank_by_uid.get(current_user_id)
  ```
  This is O(N) once to build the dict, then O(1) per lookup. If the rank list is large and only one user is queried, consider filtering at the Supabase level instead.

### M14. 4 separate list comprehensions over `files` in `/dashboard`

- **File:** `app.py:~1880`
- **Impact:** The dashboard route iterates over the entire files list 4 times (once per content type: notes, papers, etc.). With a large file list, this is 4× the work needed.
- **Fix:** Single-pass categorization:
  ```python
  notes, papers, others = [], [], []
  for f in files:
      t = (f.get('type', '') or '').lower()
      if t in NOTES_TYPE_VALUES: notes.append(f)
      elif t in PAPERS_TYPE_VALUES: papers.append(f)
      else: others.append(f)
  ```
  Then sort each list once.

### M15. `SocketIO(app, cors_allowed_origins="*")` — WebSocket open to all origins

- **File:** `app.py:187`
- **Impact:** Any website can open a WebSocket connection to the AbhiHub Socket.IO server. While the chat messages themselves require authentication, the connection itself is unrestricted. A malicious site could abuse this for DoS (opening many connections) or as a conduit for other attacks.
- **Fix:** Replace `"*"` with the specific origin(s):
  ```python
  SocketIO(app, cors_allowed_origins='https://app.abhihub.run.place')
  ```
  If local development needs `localhost`, use an environment variable:
  ```python
  import os
  cors_origins = os.getenv('SOCKETIO_CORS_ORIGINS', 'https://app.abhihub.run.place')
  SocketIO(app, cors_allowed_origins=cors_origins)
  ```

---

## LOW — Cosmetic, Dead Code & Minor Issues

These don't affect security or functionality but should be cleaned up for a polished codebase.

### L1. Dead code files (~180KB)

- **Files:** `old_store_room.js` (136KB), `migrate_main_data.py`, `migrate_final_data.py`, `migrate_data.py`, `migrate_data_and_rank.py`, `migrate_data_json.py`, `migrate_search_index.py`, `verify_db.py`, `verify_migration.py`, `check2.py`, `check_docs.py`, `replace.py`, `inspect_db.py`, `test_stats.py`, `test_supabase.py`, `test_supabase2.py`, `test_ts.js`, `test_ts2.js`, `test_ts3.js`
- **Impact:** Clutters the repo, confuses new developers, and bloats git history. Some are migration scripts that ran once and are never needed again; others are test stubs.
- **Fix:** Move all dead files to a `/trash` directory first (one commit), then delete them in a second commit after confirming nothing imports them. Use `git log --all --full-history -- <file>` to verify each file is truly dead before deletion.

### L2. Supabase anon key in `static/supabase-config.js`

- **File:** `static/supabase-config.js:8`
- **Impact:** The Supabase anonymous key is meant to be public (it's used by the client-side JS to talk to Supabase with RLS). However, it's still a credential that appears in the repo. If RLS policies are ever weakened, this key could be abused.
- **Fix:** This is expected for client-side Supabase usage — no action needed unless RLS policies change. Document in `SECURITY.md` that the anon key is intentionally public but scoped by RLS.

### L3. `test_dashboard_auth.py` has hardcoded Flask secret key

- **File:** `tests/test_dashboard_auth.py:64, 109`
- **Impact:** Test file only — no production impact. But it's a bad pattern that could be copied into production code by a careless developer.
- **Fix:** Replace with `os.getenv('FLASK_SECRET_KEY', 'test-secret')` in the test file. Add a comment: "Test only — never use this pattern in production."

### L4. Cloudflare Turnstile sitekey hardcoded in `contact.html` and `forgot_password.html`

- **Files:** `templates/contact.html:206`, `templates/forgot_password.html:165`
- **Impact:** The Turnstile sitekey is a public identifier (not a secret), so this is not a security issue. But hardcoding it in two template files means a sitekey rotation requires editing two files.
- **Fix:** Move the sitekey to a single template include or a config variable:
  ```html
  <div class="cf-turnstile" data-sitekey="{{ TURNSTILE_SITEKEY }}"></div>
  ```
  Then set `TURNSTILE_SITEKEY` in `app.py` from env var.

### L5. `ROUTES.md` lists dead links (ROUTE-104 through ROUTE-110)

- **File:** `ROUTES.md` (lines 192-198)
- **Impact:** Documentation drift — these routes no longer exist in `app.py` but are still listed in the route map. Anyone using `ROUTES.md` as a reference will hit 404s.
- **Fix:** Either remove the dead routes from `ROUTES.md`, or add a `[DEPRECATED]` tag with a note explaining they were removed and when.

### L6. `|tojson|safe` in `p_store_room.html:82` and `_card_file.html:8`

- **Files:** `templates/p_store_room.html:82`, `templates/_card_file.html:8`
- **Impact:** The `|tojson` filter in Jinja2 produces JSON-safe output (it escapes quotes, slashes, and control characters). Adding `|safe` after it tells Jinja2 to skip HTML escaping on the result. Since `tojson` already produces safe output, `|safe` is redundant but not harmful — unless the filter's behavior changes in a future Jinja2 version.
- **Fix:** Remove `|safe` from both `|tojson|safe` chains. Keep only `|tojson`. Verify the templates still render correctly after the change.

### L7. CSS conflict resolution doc lives in `templates/_CSS_CONFLICTS_RESOLVED.md`

- **File:** `templates/_CSS_CONFLICTS_RESOLVED.md`
- **Impact:** Documentation about CSS architecture is inside the `templates/` folder, which is semantically wrong (templates contain HTML, not docs). A new developer might not find it.
- **Fix:** Move to `docs/CSS_CONFLICTS_RESOLVED.md` or merge into a central `docs/ARCHITECTURE.md`. Leave a redirect comment in the original location if needed.

### L8. `print()` used in `supabase_helper.py` for file access logging (lines 1786, 1788, 1789)

- **File:** `methods/supabase_helper.py`
- **Impact:** Same as M6 — `print()` instead of `logging`. These specific lines log file access events, which should be `logging.info()` for consistent log formatting.
- **Fix:** Replace with `logging.info()` calls. Part of the broader M6 fix.

---

## Fix Plan — Ordered by Priority

### Phase 1: Security Hotfixes (HIGH — H1 through H6)
**Timeline:** 1-2 days. Must be done before any new feature work.

| Step | Bug | Action | Est. effort |
|------|-----|--------|-------------|
| 1.1 | H1 | Replace all bare `except:` in `supabase_helper.py` and `upload_notifier.py` with `except Exception as e: log.error(...)` | 1 hr |
| 1.2 | H2 | Add `@auth_required` to `delete_account` in `app.py:2866` | 10 min |
| 1.3 | H3 | Add `@auth_required` + Referer check + rate limit + inline headers to `/pdf-proxy/` route | 1 hr |
| 1.4 | H4 | Change `ADMIN_EMAILS` default to empty list; ensure Heroku env has the var set | 15 min |
| 1.5 | H5 | Set `WTF_CSRF_TIME_LIMIT = 3600` | 5 min |
| 1.6 | H6 | Replace `Access-Control-Allow-Origin: '*'` with origin-aware logic in 2 locations | 30 min |

**Verification after Phase 1:**
- `python3 -c "from app import app"` imports without error
- curl `GET /pdf-proxy/somefile.pdf` without session → 401
- curl `POST /delete-account` without session → 401
- CSRF token expires after 1 hour (test by setting time limit to 1 second and checking)

### Phase 2: Code Quality Consolidation (MEDIUM — M1 through M15)
**Timeline:** 3-5 days. Can be done in parallel with Phase 1 by a second engineer, but coordinate to avoid merge conflicts in `app.py`.

| Step | Bug | Action | Est. effort |
|------|-----|--------|-------------|
| 2.1 | M1 | Extract quota + view log to `_check_and_log_view()` helper | 1 hr |
| 2.2 | M2 | Extract `get_device_type()` to single function | 30 min |
| 2.3 | M3 | Consolidate all `supabase_helper` imports to top of `app.py` | 2 hrs |
| 2.4 | M4, M5 | Deduplicate `init_supabase`, `storage`, `Image`, `datetime` imports | 30 min |
| 2.5 | M6 | Replace 87 `print()` with `logging.*` calls | 2 hrs |
| 2.6 | M7 | Add TODO comment for fuzzy search migration (don't rewrite yet) | 10 min |
| 2.7 | M8 | Audit `cors.py` vs `flask-cors`; delete or consolidate | 1 hr |
| 2.8 | M9, M10 | Move `traceback` and `re` imports to top of their files | 15 min |
| 2.9 | M11 | Replace hardcoded date fallbacks with `datetime.now()` | 1 hr |
| 2.10 | M12 | Add input length validation to 3 admin creation routes | 30 min |
| 2.11 | M13 | Convert rank list to dict for O(1) lookup | 30 min |
| 2.12 | M14 | Single-pass file categorization in `/dashboard` | 30 min |
| 2.13 | M15 | Restrict SocketIO CORS to specific origin | 10 min |

**Verification after Phase 2:**
- `python3 -c "from app import app; print(len(app.url_map._rules))"` runs without error
- All routes still return expected status codes (spot-check 10 routes)
- No `print()` calls remain in production `.py` files (grep for `print(` in `app.py`, `methods/*.py`, `data/*.py`)

### Phase 3: Cleanup (LOW — L1 through L8)
**Timeline:** 1-2 days. Can be done after Phase 2, or deferred to a maintenance window.

| Step | Bug | Action | Est. effort |
|------|-----|--------|-------------|
| 3.1 | L1 | Move dead files to `/trash`, then delete after verification | 1 hr |
| 3.2 | L2 | Document in `SECURITY.md` that anon key is intentionally public | 10 min |
| 3.3 | L3 | Fix test file's hardcoded secret | 5 min |
| 3.4 | L4 | Move Turnstile sitekey to config variable | 15 min |
| 3.5 | L5 | Remove or tag dead routes in `ROUTES.md` | 15 min |
| 3.6 | L6 | Remove `|safe` after `|tojson` in 2 templates | 10 min |
| 3.7 | L7 | Move CSS doc out of `templates/` | 5 min |
| 3.8 | L8 | Replace `print()` with `logging.info()` in `supabase_helper.py:1786-1789` | 10 min |

### Phase 4: Documentation Update
**Timeline:** 1 day (can overlap with Phase 3).

After all phases complete:
1. Update `CHANGELOG.md` under `## [Unreleased]` → `### Fixed` with a summary of all fixes
2. Update `audit_report.md` to reflect the new status of each step (change `[ ] Pending` to `[x] Done`)
3. Add a `SECURITY.md` file documenting the security model (auth, CSRF, CORS, Referer checks, signed URLs, rate limits, RLS)
4. Update `ROUTES.md` if any routes were added/removed during the fixes

---

## Open Questions / Decisions Needed

1. **PDF quota system:** The user's out-of-band message mentions a credit/earning system (upload files → earn credits → view files, daily credit earn, tasks like uploading/referring/enabling notifications/disabling adblocker/install PWA). This is a larger feature, not a bug fix. It should be designed as a separate project after Phase 1 security fixes are in place. The `/pdf-proxy/` auth fix (H3) is a prerequisite — without it, the quota system can be bypassed via the public proxy.

2. **`cors.py` vs `flask-cors`:** Need to read `cors.py` to determine if it provides headers that `flask-cors` can't. If it's truly redundant, delete it. If it has custom logic, consolidate into a `flask-cors` `after_request` hook.

3. **Fuzzy search migration (M7):** This is a larger rewrite. The current custom implementation works. Migration to `rapidfuzz` or Supabase FTS should be a separate project with its own testing plan — don't attempt it as part of this cleanup.

4. **`/trash` directory:** Should we create `/trash` at the repo root for dead file archival, or delete outright? The audit report recommends `/trash` first. This is a judgment call — if the dead files are clearly migration/test stubs with no chance of needing them again, delete outright. If there's any doubt, use `/trash` and delete after 30 days.

---

## Verification Checklist (Post-Fix)

Run these after each phase to confirm fixes landed correctly:

```bash
# Phase 1 verification
python3 -c "from app import app; print('Import OK')"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/pdf-proxy/test.pdf  # expect 401
curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:5000/delete-account  # expect 401
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/view-doc/test  # expect 404 (not 401)

# Phase 2 verification
grep -r "print(" app.py methods/ data/ --include="*.py" | grep -v "logging\|test_" | wc -l  # expect 0
grep -c "from methods.supabase_helper import" app.py  # expect 1 (top-of-file block)

# Phase 3 verification
ls trash/  # confirm dead files moved
grep -r "tojson|safe" templates/ --include="*.html" | wc -l  # expect 0
```
