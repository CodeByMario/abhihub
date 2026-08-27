# Code Refactoring Patterns for AbhiHub

**Trigger:** When auditing `app.py` for duplicate/redundant code patterns.

**What to look for:**
  • Duplicate route handlers bound to the same path (e.g., two `@app.route('/sw.js')` definitions)
  • Identical `slugify` or utility functions defined at module level and re-declared inside other functions
  • Local re-imports of modules already imported at the top of the file
  • duplicated file-read patterns (load JSON, swallow exceptions) across multiple route handlers
  • Identical Firebase signed-URL resolution blocks across multiple API endpoints
  • Duplicate PDF detection logic (`is_pdf` checks) in multiple handlers
  • Hand-written security header dicts duplicated across proxy/view routes
  • Identical storage provider fallback + asset labeling patterns in success/conflict branches

**General approach:**
  1. Extract the duplicated logic into a single helper function at module level
  2. Replace all call sites with calls to the helper
  3. Verify all references still work after the change
  4. Run any existing tests to confirm no regressions

**Examples from recent audit:**
  • `_load_contact_messages()` — extracted from 3 duplicated contact-file-read blocks
  • `_resolve_signed_url()` — extracted from Firebase signed-URL resolution in `api_ask_paper()` and `api_extract_ocr()`
  • `_looks_like_pdf()` — extracted from duplicate `is_pdf` detection in `api_ask_paper()` and `api_extract_ocr()`
  • `_secure_file_headers()` — extracted from duplicated security header dicts in `proxy_file()`, `view_doc()`, and `pdf_proxy()`
  • `_mark_labeled()` — extracted from duplicated `storage_provider` fallback + `mark_storage_asset_labeled` in `label_store_room_paper()`
  • Removed duplicate `service_worker()` route handler (kept first definition only)
  • Removed duplicate `slugify()` inside `college_landing()` (use module-level version)

**Verification:**
  After applying each refactoring, run the app and test the affected endpoints to confirm behavior is preserved.