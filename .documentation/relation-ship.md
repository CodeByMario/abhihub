# File Relationship Documentation — AbhiHub

This document maps the main files and folders in the repository to their dependencies and the features they support.

## 1. Root entrypoints

- `app.py`
  - Depends on: `push_api.py`, `cors.py`, `firebase_config.py`, `methods/*`, `data/*`, `templates/*.html`, `static/js/*.js`, `static/css/*.css`
  - Feature: Primary Flask server, routing, auth, UI rendering, API endpoints, page dispatch.

- `app_store_room_endpoint.py`
  - Depends on: `methods.supabase_helper`, `requests`, `json`
  - Feature: Store-room tagging API endpoint used by premium file store workflows.

- `package.json`
  - Depends on: Tailwind CLI dev dependency
  - Feature: CSS build tooling for pipeline styles.

## 2. Data layer

- `data/db.py`
  - Depends on: `dotenv`, `supabase`
  - Feature: Supabase client creation, database connection helpers, UUID validation, shared DB utilities.

- `data/__init__.py`
  - Depends on: `data.db`, `data.colleges`, `data.profiles`, `data.documents`, `data.interactions`, `data.analytics`, `data.notifications`
  - Feature: Single import gateway for app data models.

- `data/colleges.py`
  - Depends on: `data.db`
  - Feature: College/department/subject lookup and helper access for uploads and search.

- `data/profiles.py`
  - Depends on: `data.db`
  - Feature: User profile, student/teacher details, quota data, subscription state.

- `data/documents.py`
  - Depends on: `data.db`, `data.profiles`, `data.colleges`
  - Feature: Document metadata, file records, document counts, recent file queries.

- `data/interactions.py`
  - Depends on: `data.db`, `data.profiles`
  - Feature: Likes, bookmarks, comments, document interaction tracking.

- `data/notifications.py`
  - Depends on: `data.db`, `data.profiles`
  - Feature: In-app notifications and push subscription storage.

- `data/analytics.py`
  - Depends on: `data.db`, `data.profiles`
  - Feature: File view counting, security audit logs, analytics helpers.

## 3. Business logic and helper modules

- `methods/supabase_helper.py`
  - Depends on: `supabase`, `dotenv`, `data.*`, `json`, `datetime`
  - Feature: Core Supabase CRUD and business workflows for profiles, uploads, interactions, notifications, quotas, and file tracking.

- `methods/cloudinary_upload.py`
  - Depends on: `cloudinary`, `PIL`, `dotenv`, `os`, `io`
  - Feature: Cloudinary upload and image manipulation helper for file storage.

- `methods/encryption.py`
  - Depends on: `Crypto.Cipher.AES`, `Crypto.Random`, `hashlib`, `os`
  - Feature: AES encryption/decryption helpers for secure file view flow.

- `methods/know_me.py`
  - Depends on: `methods.supabase_helper`, `datetime`, `hashlib`, `random`, `string`
  - Feature: Know Me / MemoryWall creation, submission handling, spam protection, response aggregation.

- `methods/know_me_generator.py`
  - Depends on: `PIL`, `wordcloud`, `requests`, `firebase_admin.storage`
  - Feature: Word cloud and signature image generation for MemoryWall.

- `methods/get_user_uploaded_files.py`
  - Depends on: `methods.supabase_helper`, `data.db`
  - Feature: Fetch user-uploaded file list and metadata.

- `methods/upload_notifier.py`
  - Depends on: `methods.supabase_helper`, `json`, `datetime`
  - Feature: Sends upload-related notifications.

- `methods/storage.py`
  - Depends on: `firebase_admin`, `dotenv`, `os`
  - Feature: Firebase storage helper functions.

- `methods/viewer.css`
  - Depends on: PDF viewer template styles
  - Feature: Embedded viewer styling for encrypted PDFs.

## 4. Frontend templates and UI files

- `templates/p_index.html`
  - Depends on: `app.py` route `/dashboard`, `static/css/pages/dashboard.css`, `static/js/p_index.js`, `static/js/pwa-install.js`
  - Feature: Dashboard UI, recent documents, file action cards, onboarding, modals, PWA popup.

- `templates/p_account.html`
  - Depends on: `app.py` route `/account`, `static/css/pages/p_account.css`, `static/js/p_index.js` or shared JS as applicable
  - Feature: Account settings page.

- `templates/p_store_room.html`
  - Depends on: `app.py` route `/store-room`, `static/js/store_room.js`, `static/css/*`
  - Feature: Store Room listing and file management.

- `templates/know_me/*.html`
  - Depends on: `/memorywall` routes in `app.py`, `methods/know_me.py`, `methods/know_me_generator.py`, `static/js/know-me.js`, `static/css/know-me.css`
  - Feature: MemoryWall creation, public wall display, reveal page.

- `templates/p_login.html`, `templates/p_signup.html`, `templates/forgot_password.html`, `templates/p_profile.html`, `templates/p_upload.html`
  - Depends on: `app.py` authentication routes, `static/css/*.css`, `static/js/*.js`
  - Feature: Authentication and profile/upload forms.

- `templates/p_file_receiver.html`, `templates/p_share_receiver.html`
  - Depends on: `app.py` premium share routes, `static/js/*`, `static/css/*`
  - Feature: File sharing and receiver screens.

## 5. Static assets and JS/CSS dependencies

- `static/js/p_index.js`
  - Depends on: `templates/p_index.html`, API endpoints under `/api/*`, `static/js/pwa-install.js` if PWA install is used.
  - Feature: Dashboard interaction behaviors and AJAX event handling.

- `static/js/p_landing.js`, `static/js/p_login.js`, `static/js/pwa-install.js`, `static/js/push-notifications.js`, `static/js/file-history-tracker.js`, `static/js/previously-accessed-files.js`
  - Depends on: corresponding page templates and `app.py` endpoints.
  - Feature: Landing page behavior, login form actions, PWA flow, push subscription, file access history.

- `static/css/pages/dashboard.css`
  - Depends on: `templates/p_index.html`
  - Feature: Dashboard-specific page styling.

- `static/css/pages/p_account.css`
  - Depends on: `templates/p_account.html`
  - Feature: Account page styling.

- `static/css/know-me.css`
  - Depends on: `templates/know_me/*.html`
  - Feature: MemoryWall page styling.

- `static/css/p_index.css`, `static/css/p_login.css`, `static/css/p_signup.css`, `static/css/p_profile.css`, `static/css/p_landing.css`
  - Depends on: matching page templates
  - Feature: Page-specific styling.

- `static/css/pwa-install.css`, `static/css/overlay-system.css`, `static/css/common.css`, `static/css/abhihub-theme.css`
  - Depends on: all pages using global app shell styles and overlays.
  - Feature: Global UI design, overlays, theming, PWA install styling.

- `static/premium/*`
  - Depends on: app premium pages and the legacy premium UI build
  - Feature: Premium assets, premium store logic, and legacy premium CSS/JS.

## 6. Scripts, migration, and support files

- `migrations/*.sql`
  - Depends on: Supabase schema and `data/*` expectations
  - Feature: Database schema setup and updates.

- `generate_vapid.py`
  - Depends on: `cryptography`
  - Feature: Generates VAPID keys for push notifications.

- `sync_firebase_documents.py`
  - Depends on: `firebase_admin`, `firebase_config.py`
  - Feature: Firebase document synchronization.

- `move_css.py`, `append_helpers.py`, `append_routes.py`, `inject_actions.py`, `inject_script.py`
  - Depends on: repository templates and asset files
  - Feature: automation utilities for injecting CSS/JS and managing routes.

- `check_docs.py`, `check2.py`, `verify_db.py`, `verify_migration.py`
  - Depends on: `methods.supabase_helper`, `data/*`
  - Feature: validation and environment checks.

- `push_api.py`, `push_notifications.py`, `scheduled_tasks.py`
  - Depends on: push notification infrastructure, Supabase auth, scheduled workflows.

- `firebase_config.py`
  - Depends on: Firebase environment setup and `firebase-auth.json` (development)
  - Feature: Firebase service configuration.

## 7. Documentation and support files

- `.documentation/*.md`
  - Depends on: repo architecture knowledge
  - Feature: internal architecture and document guides.

- `README.md`, `FILE_HISTORY_SETUP.md`
  - Depends on: project setup, runtime expectations.
  - Feature: public documentation and setup instructions.

- `.know_me/*.md`
  - Depends on: MemoryWall design and architecture
  - Feature: design notes, behavior guides, feature specs.

## 8. Notes on assets and generated files

- `.gitignore`, `runtime.txt`, `Procfile`, `requirements.txt`
  - Depends on: hosting and runtime environment
  - Feature: deployment configuration.

- `static/images/*`, `icons/*`, `static/files/*`
  - Depends on: UI templates and Progressive Web App metadata
  - Feature: static assets used across pages and PWA.

- `__pycache__/*`
  - Dependency: generated Python bytecode
  - Feature: runtime caching, safe to ignore in source tracking.

## 9. Feature summary table

| Feature | Root Template / Entry | Backend Files | JS Files | CSS Files |
|---|---|---|---|---|
| Dashboard | `templates/p_index.html` | `app.py`, `data/documents.py`, `data/profiles.py`, `methods/supabase_helper.py` | `static/js/p_index.js`, `static/js/pwa-install.js` | `static/css/pages/dashboard.css`, `static/css/p_index.css` |
| Account | `templates/p_account.html` | `app.py`, `data/profiles.py`, `methods/supabase_helper.py` | `static/js/p_index.js` (shared) | `static/css/pages/p_account.css` |
| Store Room | `templates/p_store_room.html` | `app.py`, `data/documents.py`, `data/interactions.py`, `methods/supabase_helper.py` | `static/premium/js/store_room.js`, `static/js/file-history-tracker.js` | `static/css/*` |
| MemoryWall / Know Me | `templates/know_me/*.html` | `app.py`, `methods/know_me.py`, `methods/know_me_generator.py` | `static/js/know-me.js` | `static/css/know-me.css` |
| Auth / Profile | `templates/p_login.html`, `templates/p_signup.html`, `templates/p_profile.html` | `app.py`, `data/profiles.py`, `methods/supabase_helper.py` | `static/js/p_login.js`, `static/js/p_index.js` | `static/css/p_login.css`, `static/css/p_signup.css`, `static/css/p_profile.css` |
| Upload / File Viewer | `templates/p_upload.html`, `templates/p_pdf_reader.html` | `app.py`, `methods/encryption.py`, `methods/cloudinary_upload.py` | `static/encrypted_pdf_viewer.js`, `static/js/p_index.js` | `static/css/p_upload.css`, `static/css/viewer.css` |
| Notifications / Push | N/A | `push_api.py`, `push_notifications.py`, `methods/supabase_helper.py` | `static/js/push-notifications.js` | `static/css/pwa-install.css` |
| Search | `templates/p_index.html` / `templates/p_landing.html` | `app.py`, `data/documents.py` | `static/js/search-worker.js`, `static/js/p_index.js` | `static/css/p_index.css`, `static/css/p_landing.css` |
| Quota / Subscription | `templates/p_index.html`, `templates/p_account.html` | `app.py`, `data/profiles.py`, `methods/supabase_helper.py` | `static/js/access-gates.js` | `static/css/study-pass.css` |
| Admin | `templates/admin_dashboard.html`, `templates/admin_notification_panel.html` | `app.py`, `methods/supabase_helper.py`, `data/analytics.py` | `static/js/admin-dashboard.js` | `static/css/common.css` |

## 10. How to use this document

Use this file as a quick reference when updating any feature.
- If you change `app.py`, check dependencies in `templates/`, `static/`, `methods/`, and `data/`.
- If you change a `data/*` module, verify any `methods/*` or `app.py` route using it.
- If you change a `templates/*.html` page, update matching `static/js/*` and `static/css/*` files.
- If you change a `methods/*` helper, inspect the app routes and feature templates that call it.

---

> This document is intentionally written as a high-level dependency map for key source files and feature boundaries. For exact import traces, inspect the file-level imports and route handlers in `app.py` and the `data/` and `methods/` folders.
