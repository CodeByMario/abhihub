# AbhiHub - Comprehensive Project Master Report

**Generated:** Production-Grade Architecture, Route & File Reference  
**Total Tracked Files:** 852 files across all modules  
**Total Active Application Routes & Endpoints:** 223 endpoints (REST API, Web Views, WebSockets)  
**Core Architecture:** Flask (WSGI + Gevent WebSocket) + Supabase (PostgreSQL 15, RLS) + Cloudinary Storage + Firebase Auth/Legacy + Self-Hosted PDF.js + PWA Service Worker

---

## Table of Contents

1. [Executive Summary & Product Vision](#1-executive-summary--product-vision)
2. [System Architecture & Technology Stack](#2-system-architecture--technology-stack)
3. [Comprehensive Route-by-Route Reference](#3-comprehensive-route-by-route-reference)
   - [3.1 Web Pages & HTML Views](#31-web-pages--html-views)
   - [3.2 Authentication & User Profiles](#32-authentication--user-profiles)
   - [3.3 Document Discovery, Upload & Store Room](#33-document-discovery-upload--store-room)
   - [3.4 AI Features (OCR, Paper Q&A, Metadata Prediction)](#34-ai-features-ocr-paper-qa-metadata-prediction)
   - [3.5 Social, Memory Wall, Crushes & Encrypted Chat](#35-social-memory-wall-crushes--encrypted-chat)
   - [3.6 Gamification, Economy, XP & Leaderboard](#36-gamification-economy-xp--leaderboard)
   - [3.7 Web Push Notifications & Reliability](#37-web-push-notifications--reliability)
   - [3.8 Analytics, Reporting & Administration](#38-analytics-reporting--administration)
   - [3.9 SEO, IndexNow, PWA & Health Checks](#39-seo-indexnow-pwa--health-checks)
4. [File-by-File Detailed System Catalog](#4-file-by-file-detailed-system-catalog)
   - [4.1 Core Backend & Entry Points](#41-core-backend--entry-points)
   - [4.2 Data Layer (data/)](#42-data-layer-data)
   - [4.3 Service Helpers & Subsystems (methods/)](#43-service-helpers--subsystems-methods)
   - [4.4 Background Jobs & Cron Tasks](#44-background-jobs--cron-tasks)
   - [4.5 Database Migrations & SQL Schemas (migrations/)](#45-database-migrations--sql-schemas-migrations)
   - [4.6 Jinja2 HTML Templates (templates/)](#46-jinja2-html-templates-templates)
   - [4.7 Frontend JS, CSS & PWA Assets (static/)](#47-frontend-js-css--pwa-assets-static)
   - [4.8 Scripts, Tooling, Configs & Docker](#48-scripts-tooling-configs--docker)
5. [Data Flow, Security & Cache Architecture](#5-data-flow-security--cache-architecture)
6. [Deployment & Production Runbook](#6-deployment--production-runbook)

---

## 1. Executive Summary & Product Vision

**AbhiHub** is an academic resource and student-collaboration platform built specifically for engineering and college students. It provides a community-curated digital repository for previous year question papers (PYQs), study notes, practical manuals, syllabi, and assignment solutions, organized strictly by college, department/branch, semester, and subject.

### Core Pillars:
- **Zero-Download Document Security:** Documents are strictly previewed within a self-hosted, customized PDF.js viewer with watermarking, client-side rendering restrictions, and security overlays.
- **Direct Cloudinary Architecture:** Uploads leverage pre-signed client signatures directly to Cloudinary with automated background WebP/PDF compression, OCR extraction, and storage audit logging.
- **Real-time Student Engagement:** Includes End-to-End Encrypted Peer Chat (WebSockets), Memory Wall (anonymous digital autograph walls for graduating batches), Secret Admirer / College Crushes, and Peer Material Exchange.
- **Gamification & Quota Economy:** Tiered user scoring, reputation points, upload XP, badges, daily quotas with monthly resets, referral rewards, and college leaderboards.
- **Reliable Push Notifications:** VAPID Web Push delivery with automated dead-subscription cleanup, backoff retry queues, and multi-channel notification dispatch.
- **Instant Search & Real-time Indexing:** Multi-tier search API (Supabase Postgres full-text + fuzzy fallback + in-memory static cache) and Bing IndexNow instant SEO pinging on document uploads.

---

## 2. System Architecture & Technology Stack

| Layer | Technology / Service | Responsibility |
|---|---|---|
| **Web Framework** | Python 3.11+, Flask 2.0.1, Flask-Compress, Flask-WTF | HTTP Routing, CSRF, Session Auth, Template Rendering |
| **WSGI / Concurrency** | Gunicorn + Gevent / Gevent-WebSocket | Async IO concurrency, WebSocket long-polling support |
| **Primary Database** | Supabase (PostgreSQL 15, `abhihub` schema) | Relational store, Row Level Security (RLS), Postgres Functions |
| **Auth & Security** | Supabase Auth + Flask Signed Sessions | Token verification, Session cookie signing, CSRF protection |
| **Storage & CDN** | Cloudinary (Primary) + Firebase Storage (Legacy) | Secure asset storage, image optimization, raw PDF storage |
| **Real-time Comms** | Flask-SocketIO + Gevent | Real-time chat messaging, online presence tracking |
| **PDF Rendering** | Self-hosted PDF.js v6.1.200 | In-browser canvas/SVG rendering, page virtualization, copy protection |
| **Caching Hierarchy** | L1 (In-memory dict) -> L2 (File cache) -> L3 (Supabase) | Sub-millisecond response for colleges, depts, subjects, quotas |
| **AI Services** | OpenRouter (Google Gemini / DeepSeek / Mistral) | Document OCR fallback, AI paper question answering, metadata prediction |
| **Push Notifications** | pywebpush + VAPID | Browser push notifications, dead subscription reaping |
| **Frontend & PWA** | Vanilla JS (Modular) + Tailwind CSS + Service Worker | Offline fallback, PWA install prompt, zero heavy SPA bloat |
| **Background Workers** | APScheduler (`scheduled_tasks.py`) | Quota resets, dead token pruning, file verification, leaderboard scoring |

---

## 3. Comprehensive Route-by-Route Reference

Below is the complete catalogue of all routes registered across the application.

### Master Route Table

| # | Methods | Route Path | Handler Name | File:Line | Access Level | Description |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/health` | `health_check()` | `app.py:277` | **Public** | Lightweight health check endpoint for monitoring without secret leakage. |
| 2 | `GET` | `/api/health` | `health_check()` | `app.py:277` | **Public** | Lightweight health check endpoint for monitoring without secret leakage. |
| 3 | `GET` | `/<key>.txt` | `indexnow_key_file()` | `app.py:924` | **Public** | Serve the IndexNow key verification file dynamically based on .env configuration. |
| 4 | `POST` | `/api/indexnow/submit` | `submit_indexnow()` | `app.py:933` | **Admin** | Submit URLs to Bing IndexNow |
| 5 | `GET` | `/api/quota` | `api_get_quota()` | `app.py:958` | **Auth Required** | Return the current quota for the logged-in user — cached at L1 for 60s. |
| 6 | `GET` | `/api/cache-health` | `api_cache_health()` | `app.py:971` | **Public** | Cache system health check — returns stats for all cache layers. |
| 7 | `POST` | `/api/get-upload-signature` | `get_upload_signature()` | `app.py:982` | **Auth Required** | Generates a presigned Cloudinary upload signature for client-side direct uploads. |
| 8 | `GET` | `/api/version` | `version_info()` | `app.py:1041` | **Public** | Return current app version for footer and cache management |
| 9 | `POST` | `/api/webhooks/cloudinary-upload` | `webhook_cloudinary_upload()` | `app.py:1046` | **Public** | Webhook triggered on storage upload completion to run async background compression. |
| 10 | `GET` | `/static/<path:filename>` | `static_files()` | `app.py:1077` | **Public** | No docstring provided |
| 11 | `POST` | `/auth` | `authorize()` | `app.py:1084` | **Public** | No docstring provided |
| 12 | `POST` | `/api/referral/register` | `api_referral_register()` | `app.py:1141` | **Public** | Capture a referral code at signup and credit both sides. |
| 13 | `GET` | `/api/referral/my-code` | `api_referral_my_code()` | `app.py:1169` | **Auth Required** | Return the logged-in user's shareable referral code + link + progress. |
| 14 | `POST` | `/api/buy-credits` | `api_buy_credits()` | `app.py:1202` | **Auth Required** | Endpoint to purchase credit packs (50, 100, 500 views @ ₹2/view). |
| 15 | `GET` | `/api/credit-history` | `api_credit_history()` | `app.py:1256` | **Auth Required** | Retrieve user credit transactions (spend & earn history) and current quota balance. |
| 16 | `GET` | `/auth-callback` | `auth_callback()` | `app.py:1281` | **Public** | Handle OAuth callback from Supabase |
| 17 | `GET` | `/login` | `login()` | `app.py:1298` | **Public** | No docstring provided |
| 18 | `GET` | `/signup` | `signup()` | `app.py:1305` | **Public** | No docstring provided |
| 19 | `GET` | `/reset-password` | `reset_password()` | `app.py:1313` | **Public** | No docstring provided |
| 20 | `GET` | `/reset-password-confirm` | `reset_password_confirm()` | `app.py:1320` | **Public** | Handle password reset confirmation from Supabase email link |
| 21 | `GET` | `/terms` | `terms()` | `app.py:1332` | **Public** | No docstring provided |
| 22 | `GET` | `/ads.txt` | `ads_txt()` | `app.py:1336` | **Public** | No docstring provided |
| 23 | `GET` | `/robots.txt` | `robots_txt()` | `app.py:1340` | **Public** | Expose crawler directives with a sitemap URL for the active host. |
| 24 | `GET` | `/<key>.txt` | `index_now_key()` | `app.py:1355` | **Public** | No docstring provided |
| 25 | `GET` | `/sitemap.xml` | `sitemap()` | `app.py:1361` | **Public** | Generate canonical sitemap URLs for the public host serving this request. |
| 26 | `GET` | `/sitemap-audit` | `sitemap_audit()` | `app.py:1451` | **Public** | List unclassified static GET routes while running in debug mode. |
| 27 | `GET` | `/privacy` | `privacy()` | `app.py:1466` | **Public** | No docstring provided |
| 28 | `GET` | `/help` | `help_center()` | `app.py:1471` | **Public** | No docstring provided |
| 29 | `GET` | `/logout` | `logout()` | `app.py:1475` | **Public** | No docstring provided |
| 30 | `GET` | `/api/profile-status` | `profile_status()` | `app.py:1491` | **Auth Required** | Lightweight endpoint for access-gates.js — returns profile completion state. |
| 31 | `GET` | `/api/profile` | `get_profile()` | `app.py:1507` | **Auth Required** | Get current user profile |
| 32 | `POST` | `/api/profile/update` | `api_update_profile()` | `app.py:1567` | **Auth Required** | Update profile's default college and department selection. |
| 33 | `GET` | `/api/check-auth` | `check_auth()` | `app.py:1600` | **Public** | Check if user is authenticated |
| 34 | `POST` | `/api/report-suspect` | `report_suspect()` | `app.py:1612` | **Public** | Log a suspect action (screenshot / screen-record attempt) to Supabase. |
| 35 | `GET` | `/api/colleges` | `api_get_colleges()` | `app.py:1645` | **Public** | Get all colleges for dropdown — cached at L1 for 1 hour (L3: browser/CDN 1hr). |
| 36 | `GET` | `/api/branches` | `api_get_branches()` | `app.py:1663` | **Public** | Get all branches for dropdown — cached at L1 for 1 hour (L3: browser/CDN 1hr). |
| 37 | `GET` | `/api/departments` | `api_get_departments()` | `app.py:1682` | **Public** | Return departments for a college (cascading dropdown, T1/T8). |
| 38 | `GET` | `/api/semesters` | `api_get_semesters()` | `app.py:1692` | **Public** | Return semesters for a department (unified API). |
| 39 | `GET` | `/api/subjects` | `api_get_subjects()` | `app.py:1704` | **Public** | Return subjects for a department, optionally filtered by semester — cached at L1 for 30min. |
| 40 | `POST` | `/api/subjects` | `api_add_subject()` | `app.py:1728` | **Auth Required** | No docstring provided |
| 41 | `POST` | `/api/colleges` | `api_add_college()` | `app.py:1782` | **Auth Required** | No docstring provided |
| 42 | `POST` | `/api/check-duplicate` | `api_check_duplicate()` | `app.py:1801` | **Auth Required** | No docstring provided |
| 43 | `POST` | `/api/ai/predict-metadata` | `api_predict_metadata()` | `app.py:1820` | **Auth Required** | Phase 5: AI Metadata Prediction. |
| 44 | `POST` | `/api/departments` | `api_add_department()` | `app.py:1869` | **Auth Required** | No docstring provided |
| 45 | `POST` | `/api/subject-request` | `api_create_subject_request()` | `app.py:1896` | **Auth Required** | Create a pending_subject_requests row (T2). Duplicate-safe via DB index. |
| 46 | `POST` | `/api/waitlist/join` | `api_waitlist_join()` | `app.py:1921` | **Public** | Public endpoint — join college waitlist. No auth required. |
| 47 | `GET` | `/api/onboarding/status` | `api_onboarding_status()` | `app.py:1941` | **Auth Required** | No docstring provided |
| 48 | `POST` | `/api/onboarding/welcome-seen` | `api_onboarding_welcome_seen()` | `app.py:1949` | **Auth Required** | No docstring provided |
| 49 | `POST` | `/api/events` | `api_track_event()` | `app.py:1958` | **Auth Required** | Tracks only UPLOAD, DOWNLOAD, SUBJECT_REQUEST. Returns 200 always. |
| 50 | `POST` | `/store-room/api/label` | `label_store_room_paper()` | `app.py:1970` | **Auth Required** | Label a paper from store room and save to file_records table. |
| 51 | `POST` | `/api/interactions/like` | `api_toggle_like()` | `app.py:2140` | **Auth Required** | No docstring provided |
| 52 | `POST` | `/api/interactions/bookmark` | `api_toggle_bookmark()` | `app.py:2153` | **Auth Required** | No docstring provided |
| 53 | `GET, POST` | `/api/interactions/comments/<doc_id>` | `api_comments()` | `app.py:2165` | **Public** | No docstring provided |
| 54 | `POST` | `/api/document-view` | `api_log_document_view()` | `app.py:2189` | **Auth Required** | Log a document view to track file access history. |
| 55 | `GET` | `/api/recent-documents` | `api_get_recent_documents()` | `app.py:2271` | **Auth Required** | Get recently accessed documents for the logged-in user. |
| 56 | `GET` | `/api/file-access-history` | `api_get_file_access_history()` | `app.py:2318` | **Auth Required** | Get file access history for the logged-in user. |
| 57 | `GET` | `/api/my-notifications` | `api_get_my_notifications()` | `app.py:2365` | **Auth Required** | Return paginated notifications for the logged-in user. |
| 58 | `POST` | `/api/my-notifications/read` | `api_mark_notifications_read()` | `app.py:2379` | **Auth Required** | Mark all notifications as read for the logged-in user. |
| 59 | `POST` | `/api/notifications/<notif_id>/read` | `api_mark_single_notification_read()` | `app.py:2390` | **Auth Required** | Mark a single notification as read by its ID. |
| 60 | `GET` | `/notifications` | `notifications_page()` | `app.py:2416` | **Auth Required** | Full notification center page with all notifications (paginated). |
| 61 | `GET` | `/api/files/all` | `get_all_files()` | `app.py:2431` | **Public** | API endpoint to get all files exclusively from the abhihub.documents table. |
| 62 | `GET, POST` | `/upload` | `upload()` | `app.py:2475` | **Auth Required** | No docstring provided |
| 63 | `GET` | `/local-viewer` | `local_viewer()` | `app.py:2758` | **Auth Required** | Standalone page: open a local image/PDF, preview it, then upload to Cloudinary. |
| 64 | `GET` | `/upload-gate` | `upload_gate()` | `app.py:2765` | **Auth Required** | Shown when a user has exhausted their paper-access credits. |
| 65 | `GET` | `/logo` | `logo()` | `app.py:2778` | **Public** | No docstring provided |
| 66 | `GET` | `/api/proxy-file` | `proxy_file()` | `app.py:2813` | **Auth Required** | Server-side proxy for Firebase/Cloudinary files to bypass browser CORS. |
| 67 | `GET` | `/api/view-doc/<doc_id>` | `view_doc()` | `app.py:2850` | **Public** | Clean proxy endpoint for viewing docs — no URL encoding needed in PDF.js file= param. |
| 68 | `GET` | `/api/view-doc/<doc_id>/<filename>` | `view_doc()` | `app.py:2850` | **Public** | Clean proxy endpoint for viewing docs — no URL encoding needed in PDF.js file= param. |
| 69 | `GET` | `/profile` | `profile()` | `app.py:3166` | **Auth Required** | No docstring provided |
| 70 | `GET` | `/dashboard/profile` | `p_profile_redirect()` | `app.py:3201` | **Auth Required** | No docstring provided |
| 71 | `GET` | `/leaderboard` | `leaderboard()` | `app.py:3205` | **Public** | Phase 19: Global Gamification Leaderboard — cached at L1 for 10min. |
| 72 | `GET` | `/account` | `account()` | `app.py:3228` | **Auth Required** | Display account management page |
| 73 | `POST` | `/account/update` | `update_account()` | `app.py:3254` | **Auth Required** | Handle account profile updates |
| 74 | `GET` | `/api/check-profile` | `api_check_profile()` | `app.py:3300` | **Auth Required** | API endpoint to check if profile is complete |
| 75 | `GET` | `/settings` | `settings()` | `app.py:3318` | **Auth Required** | Display user settings page with account, notification, credit, and privacy controls. |
| 76 | `GET` | `/earnings` | `earnings()` | `app.py:3326` | **Auth Required** | Eligibility and earnings info page. |
| 77 | `GET` | `/support` | `support()` | `app.py:3333` | **Auth Required** | No docstring provided |
| 78 | `GET` | `/about` | `about()` | `app.py:3339` | **Public** | About page |
| 79 | `GET` | `/open-source` | `open_source()` | `app.py:3345` | **Public** | Open source page |
| 80 | `GET` | `/` | `features()` | `app.py:3351` | **Public** | Root route - handles OAuth callbacks and home page |
| 81 | `GET` | `/features-tour` | `features_tour()` | `app.py:3364` | **Public** | No docstring provided |
| 82 | `GET` | `/pyq` | `pyq_landing()` | `app.py:3368` | **Public** | SEO landing page targeting 'PYQ' and '[college] PYQ' searches |
| 83 | `GET` | `/search` | `search_page()` | `app.py:3392` | **Public** | Public search page (renders the orphaned p_search.html UI). |
| 84 | `GET` | `/college/<college_slug>` | `college_landing()` | `app.py:3401` | **Public** | Dynamic SEO-optimized college landing page. |
| 85 | `GET` | `/pyq/<college_slug>` | `college_landing()` | `app.py:3401` | **Public** | Dynamic SEO-optimized college landing page. |
| 86 | `GET` | `/college/<college_slug>/files` | `college_files()` | `app.py:3460` | **Public** | College files listing with filters, search, and pagination (16 per page). |
| 87 | `GET` | `/pyq/<college_slug>/files` | `college_files()` | `app.py:3460` | **Public** | College files listing with filters, search, and pagination (16 per page). |
| 88 | `GET` | `/college/<college_slug>/<department_slug>` | `department_landing()` | `app.py:3546` | **Public** | Dynamic SEO-optimized department landing page |
| 89 | `GET` | `/pyq/<college_slug>/<department_slug>` | `department_landing()` | `app.py:3546` | **Public** | Dynamic SEO-optimized department landing page |
| 90 | `GET` | `/subject/<subject_slug>` | `subject_landing()` | `app.py:3574` | **Public** | Dynamic SEO-optimized subject landing page (aggregated across colleges) |
| 91 | `GET` | `/resource/<path:slug>-view` | `resource_landing_redirect()` | `app.py:3596` | **Public** | Redirect resource slug with -view suffix to clean URL |
| 92 | `GET` | `/resource/<path:slug>` | `resource_landing()` | `app.py:3601` | **Public** | Dynamic SEO-optimized resource landing page |
| 93 | `GET` | `/join` | `join_team()` | `app.py:3734` | **Public** | Collaborator recruitment landing page |
| 94 | `GET` | `/team` | `team()` | `app.py:3740` | **Public** | Team page |
| 95 | `GET` | `/contact` | `contact()` | `app.py:3746` | **Public** | Contact page |
| 96 | `POST` | `/api/report-issue` | `api_report_issue()` | `app.py:3757` | **Public** | Submit a document issue report from within a viewer page. |
| 97 | `POST` | `/api/contact` | `api_contact()` | `app.py:3803` | **Public** | No docstring provided |
| 98 | `GET` | `/delete-account` | `delete_account()` | `app.py:3858` | **Auth Required** | Account deletion request page |
| 99 | `GET` | `/register` | `register()` | `app.py:3863` | **Public** | Register page (alias for signup) |
| 100 | `GET` | `/dashboard` | `dashboard()` | `app.py:3869` | **Auth Required** | Dashboard for authenticated users. |
| 101 | `GET` | `/abhijeetupdate` | `abhijeet_updae()` | `app.py:4080` | **Auth Required** | No docstring provided |
| 102 | `GET` | `/view_pdf` | `view_pdf()` | `app.py:4101` | **Auth Required** | No docstring provided |
| 103 | `GET` | `/pdf-proxy/<path:pdf_name>` | `pdf_proxy()` | `app.py:4155` | **Auth Required** | Proxy PDF from Firebase Storage or redirect if absolute URL |
| 104 | `POST` | `/indexnow` | `indexnow()` | `app.py:4294` | **Public** | No docstring provided |
| 105 | `GET` | `/dashboard/suggest` | `suggest()` | `app.py:4387` | **Auth Required** | No docstring provided |
| 106 | `GET` | `/dashboard/` | `index()` | `app.py:4416` | **Auth Required** | No docstring provided |
| 107 | `POST, GET` | `/dashboard/search` | `search()` | `app.py:4422` | **Auth Required** | No docstring provided |
| 108 | `POST, GET` | `/dashboard/view` | `view()` | `app.py:4431` | **Auth Required** | Handle file viewing - supports both form POST and file handler GET |
| 109 | `POST, GET` | `/dashboard/share-receiver` | `share_receiver()` | `app.py:4455` | **Auth Required** | Handle shared files from other apps via PWA share_target. |
| 110 | `GET` | `/dashboard/about` | `premium_about()` | `app.py:4511` | **Auth Required** | No docstring provided |
| 111 | `GET` | `/dashboard/profile/old` | `p_profile_deprecated()` | `app.py:4516` | **Auth Required** | No docstring provided |
| 112 | `GET` | `/dashboard/setting` | `p_setting()` | `app.py:4519` | **Public** | No docstring provided |
| 113 | `GET` | `/dashboard/static/search.json` | `search_in()` | `app.py:4525` | **Auth Required** | No docstring provided |
| 114 | `POST` | `/dashboard/save_search` | `save_search()` | `app.py:4536` | **Auth Required** | No docstring provided |
| 115 | `GET` | `/sw.js` | `service_worker_root()` | `app.py:4561` | **Public** | Serve service worker from root with proper headers |
| 116 | `GET` | `/manifest.json` | `premium_manifest()` | `app.py:4569` | **Public** | No docstring provided |
| 117 | `GET` | `/api/widget-data` | `widget_data()` | `app.py:4573` | **Public** | API endpoint for widget data updates. |
| 118 | `GET` | `/favicon.ico` | `favicon()` | `app.py:4607` | **Public** | No docstring provided |
| 119 | `GET` | `/admin/controle` | `admin_control_panel()` | `app.py:4618` | **Admin** | Admin notification control panel - restricted to admin email only |
| 120 | `GET` | `/api/admin/contact-messages` | `get_contact_messages()` | `app.py:4625` | **Admin** | No docstring provided |
| 121 | `GET` | `/api/admin/subscribers` | `get_admin_subscribers()` | `app.py:4632` | **Admin** | Get all push notification subscribers with metadata |
| 122 | `POST` | `/api/admin/send-notification` | `send_admin_notification()` | `app.py:4659` | **Admin** | Send push notification to selected users or all users |
| 123 | `GET` | `/api/admin/notification-history` | `get_admin_notification_history()` | `app.py:4715` | **Admin** | Get notification history (last 10 entries) |
| 124 | `GET` | `/api/admin/broadcast-stats` | `get_admin_broadcast_stats()` | `app.py:4728` | **Admin** | Get broadcast delivery stats (sent vs read) for admin notifications. |
| 125 | `GET` | `/api/admin/system-health` | `get_system_health()` | `app.py:4742` | **Admin** | Live system health dashboard: DB, storage, cache, CPU, memory, active users. |
| 126 | `GET` | `/api/chat/search-peers` | `chat_search_peers()` | `app.py:4836` | **Auth Required** | Peer search for chat — available to all authenticated users. |
| 127 | `GET` | `/api/admin/users` | `admin_get_users()` | `app.py:4898` | **Admin** | Get list of users for admin dashboard |
| 128 | `GET` | `/api/admin/users/<user_id>/stats` | `admin_get_user_stats()` | `app.py:4910` | **Admin** | Get detailed stats for a specific user |
| 129 | `GET` | `/api/admin/stats` | `get_admin_stats()` | `app.py:4941` | **Admin** | No docstring provided |
| 130 | `GET` | `/api/admin/pending-documents` | `get_pending_documents()` | `app.py:4983` | **Admin** | No docstring provided |
| 131 | `POST` | `/api/indexnow/submit` | `api_indexnow_submit()` | `app.py:5004` | **Admin** | No docstring provided |
| 132 | `GET` | `/admin/analytics` | `admin_analytics_dashboard()` | `app.py:5022` | **Admin** | Admin analytics dashboard page. |
| 133 | `GET` | `/api/my-access` | `api_my_access()` | `app.py:5031` | **Auth Required** | Current user's access level, feature gate limits, and ad density. |
| 134 | `GET` | `/admin/economy` | `admin_economy_dashboard()` | `app.py:5057` | **Admin** | Admin economy dashboard: edit scoring config, view level distribution. |
| 135 | `GET` | `/api/admin/economy/config` | `api_admin_economy_get_config()` | `app.py:5065` | **Admin** | Return all scoring_config entries. |
| 136 | `POST` | `/api/admin/economy/config` | `api_admin_economy_update_config()` | `app.py:5077` | **Admin** | Update one scoring_config key's JSONB value. Body: {key, value}. |
| 137 | `GET` | `/api/admin/economy/overview` | `api_admin_economy_overview()` | `app.py:5109` | **Admin** | Level distribution + top contributors/consumers + recent scored events. |
| 138 | `POST` | `/api/admin/economy/user/<user_id>` | `api_admin_economy_override_user()` | `app.py:5148` | **Admin** | Manually override a user's access level. Body: {access_level}. |
| 139 | `POST` | `/api/admin/approve-document` | `approve_document()` | `app.py:5174` | **Admin** | No docstring provided |
| 140 | `POST` | `/api/admin/reject-document` | `reject_document()` | `app.py:5202` | **Admin** | No docstring provided |
| 141 | `GET` | `/prepair/<subject>` | `exam_prep()` | `app.py:5242` | **Public** | No docstring provided |
| 142 | `GET` | `/UHV` | `uhv_notes()` | `app.py:5249` | **Public** | No docstring provided |
| 143 | `GET` | `/rank` | `calculate_rank()` | `app.py:5253` | **Public** | No docstring provided |
| 144 | `GET` | `/show_rank` | `show_rank()` | `app.py:5265` | **Public** | Legacy route: redirect to new leaderboard |
| 145 | `POST` | `/verify-file` | `verify_file()` | `app.py:5270` | **Public** | Verify a file and ensure it's properly added to data.json |
| 146 | `POST` | `/get-file-url` | `get_file_url()` | `app.py:5347` | **Public** | Generate a signed URL for a file without storing it |
| 147 | `POST` | `/update-file-metadata` | `update_file_metadata()` | `app.py:5379` | **Admin** | Update file metadata in Supabase (Admin Only) |
| 148 | `GET` | `/store-room` | `store_room()` | `app.py:5533` | **Auth Required** | Store Room page - displays unsorted papers from Cloudinary |
| 149 | `POST` | `/store-room/api/sync` | `store_room_api_sync()` | `app.py:5570` | **Auth Required** | Triggers a manual synchronization from physical storage to the storage_assets table. |
| 150 | `GET` | `/store-room/api/unlabeled` | `store_room_api_unlabeled()` | `app.py:5593` | **Auth Required** | API endpoint for fetching unlabeled queue files |
| 151 | `POST` | `/store-room/api/rename-file` | `store_room_api_rename_file()` | `app.py:5657` | **Auth Required** | API endpoint for renaming files with metadata in filename |
| 152 | `POST` | `/store-room/api/verify` | `store_room_api_verify()` | `app.py:5705` | **Auth Required** | API endpoint for verifying a labeled paper |
| 153 | `GET` | `/store-room/api/verification-queue` | `store_room_api_verification_queue()` | `app.py:5739` | **Auth Required** | API endpoint to get papers pending verification |
| 154 | `POST` | `/api/track-file-access` | `track_file_access_api()` | `app.py:5755` | **Auth Required** | API endpoint for tracking file access from client-side JavaScript |
| 155 | `POST` | `/api/report-broken-file` | `report_broken_file()` | `app.py:5792` | **Auth Required** | API endpoint for users to report broken/missing files with detailed logging to Supabase. |
| 156 | `GET` | `/api/admin/file-reports` | `admin_file_reports()` | `app.py:5856` | **Admin** | API endpoint for admin to view all file reports/logs. |
| 157 | `GET` | `/admin/file-reports` | `admin_file_reports_page()` | `app.py:5891` | **Admin** | Admin page for viewing all file reports and logs. |
| 158 | `GET` | `/offline` | `offline_page()` | `app.py:5924` | **Public** | No docstring provided |
| 159 | `POST` | `/api/ask-paper` | `api_ask_paper()` | `app.py:5930` | **Auth Required** | Ask a question about a paper. Extracts text via pypdf/fitz or vision OCR first, then queries any LLM. |
| 160 | `POST` | `/api/extract-ocr` | `api_extract_ocr()` | `app.py:6068` | **Auth Required** | Extract OCR text from paper image or PDF using free PyPDF/PyMuPDF or Vision models. |
| 161 | `POST` | `/api/like` | `toggle_like_route()` | `app.py:6128` | **Auth Required** | No docstring provided |
| 162 | `POST` | `/api/bookmark` | `toggle_bookmark_route()` | `app.py:6146` | **Auth Required** | No docstring provided |
| 163 | `POST` | `/api/interactions/comments/<document_id>` | `add_comment_route()` | `app.py:6164` | **Auth Required** | No docstring provided |
| 164 | `GET` | `/api/interactions/comments/<document_id>` | `get_comments_route()` | `app.py:6181` | **Public** | No docstring provided |
| 165 | `GET` | `/memorywall` | `memorywall_dashboard()` | `app.py:6197` | **Auth Required** | Creator dashboard — shows wall status, share link, stats, and recent activity. |
| 166 | `GET, POST` | `/memorywall/create` | `memorywall_create()` | `app.py:6223` | **Auth Required** | Create a new MemoryWall. |
| 167 | `GET` | `/m/<slug>` | `memorywall_public()` | `app.py:6260` | **Public** | Public submission page — no auth required. |
| 168 | `GET` | `/memorywall/reveal/<wall_id>` | `memorywall_reveal()` | `app.py:6274` | **Auth Required** | Reveal page — authenticated wall owner only. |
| 169 | `POST` | `/api/memorywall/submit` | `api_memorywall_submit()` | `app.py:6343` | **Public** | Public response submission — no auth, rate-limited by IP hash. |
| 170 | `POST` | `/api/memorywall/upload-signature` | `api_memorywall_upload_signature()` | `app.py:6390` | **Public** | Upload a signature PNG to Firebase Storage. Returns public URL. |
| 171 | `GET` | `/api/memorywall/stats/<wall_id>` | `api_memorywall_stats()` | `app.py:6431` | **Auth Required** | Wall stats — auth required, owner only. |
| 172 | `POST` | `/api/admin/entity/add` | `api_add_entity()` | `app.py:6450` | **Auth Required** | No docstring provided |
| 173 | `GET` | `/api/users/search` | `api_search_users()` | `app.py:6474` | **Auth Required** | Search student profiles by query string. |
| 174 | `GET` | `/api/user/<target_user_id>/materials` | `api_get_peer_materials()` | `app.py:6484` | **Auth Required** | Get target student's uploaded & referred study materials. |
| 175 | `GET` | `/api/chat/peer/<target_user_id>/materials-summary` | `api_chat_peer_materials_summary()` | `app.py:6492` | **Auth Required** | Quick material summary for chat — uploads count + recent 5 viewed files. |
| 176 | `POST` | `/api/request-material` | `api_request_material()` | `app.py:6510` | **Auth Required** | Submit a material request to another student. |
| 177 | `GET` | `/api/material-requests` | `api_get_material_requests()` | `app.py:6546` | **Auth Required** | Return pending material requests for the logged-in user. |
| 178 | `POST` | `/api/material-request/respond` | `api_respond_material_request()` | `app.py:6590` | **Auth Required** | No docstring provided |
| 179 | `GET` | `/api/chat/history/<peer_id>` | `api_chat_history()` | `app.py:6778` | **Auth Required** | No docstring provided |
| 180 | `SOCKET_EVENT` | `chat_delivered` | `chat_delivered()` | `app.py:6789` | **Public** | No docstring provided |
| 181 | `SOCKET_EVENT` | `chat_read` | `chat_read()` | `app.py:6807` | **Public** | No docstring provided |
| 182 | `SOCKET_EVENT` | `connect` | `chat_connect()` | `app.py:6825` | **Public** | No docstring provided |
| 183 | `SOCKET_EVENT` | `disconnect` | `chat_disconnect()` | `app.py:6837` | **Public** | No docstring provided |
| 184 | `SOCKET_EVENT` | `reconnect` | `chat_reconnect()` | `app.py:6844` | **Public** | No docstring provided |
| 185 | `SOCKET_EVENT` | `join_admin_room` | `join_admin_room()` | `app.py:6851` | **Public** | Admin joins the admin-room namespace to receive real-time updates. |
| 186 | `SOCKET_EVENT` | `heartbeat` | `chat_heartbeat()` | `app.py:6902` | **Public** | No docstring provided |
| 187 | `SOCKET_EVENT` | `chat_join` | `chat_join()` | `app.py:6928` | **Public** | No docstring provided |
| 188 | `SOCKET_EVENT` | `chat_send` | `chat_send()` | `app.py:6979` | **Public** | No docstring provided |
| 189 | `POST` | `/api/chat/messages` | `api_chat_send_message()` | `app.py:6985` | **Auth Required** | HTTP fallback when a network blocks WebSocket upgrades. |
| 190 | `SOCKET_EVENT` | `chat_request_history` | `chat_request_history()` | `app.py:7011` | **Public** | No docstring provided |
| 191 | `SOCKET_EVENT` | `chat_history_resend` | `chat_history_resend()` | `app.py:7018` | **Public** | No docstring provided |
| 192 | `GET` | `/api/chat/online` | `chat_online_users()` | `app.py:7027` | **Auth Required** | Returns currently online users for the dashboard widget, registering the caller's online heartbeat. |
| 193 | `GET` | `/chat` | `chat_page()` | `app.py:7046` | **Auth Required** | No docstring provided |
| 194 | `GET` | `/chat/<peer_id>` | `chat_with_peer()` | `app.py:7051` | **Auth Required** | No docstring provided |
| 195 | `GET, POST` | `/api/chat/keys` | `chat_keys()` | `app.py:7059` | **Auth Required** | Generate or retrieve user's NaCl key pair for E2E encryption. |
| 196 | `GET` | `/profile/<user_id>` | `peer_profile()` | `app.py:7087` | **Public** | Legacy peer profile route — redirects to the new /u/<user_id> URL. |
| 197 | `POST` | `/api/crush/<target_id>` | `api_crush_toggle()` | `app.py:7096` | **Auth Required** | Toggle a crush on target_id. Max 2 crushes per calendar year. |
| 198 | `GET` | `/api/crush/status/<target_id>` | `api_crush_status()` | `app.py:7136` | **Auth Required** | Return crush/match state between current user and target. |
| 199 | `GET` | `/u/<user_id>` | `instagram_profile()` | `app.py:7163` | **Public** | Public, Instagram-friendly profile page with OG meta tags for sharing. |
| 200 | `GET` | `/api/chat/user-info/<user_id>` | `chat_user_info()` | `app.py:7312` | **Auth Required** | Returns profile context shown in chat message badges. |
| 201 | `GET` | `/api/push/vapid-public-key` | `vapid_public_key()` | `push_api.py:23` | **Public** | Return VAPID public key for push subscriptions. |
| 202 | `POST` | `/api/push/subscribe` | `subscribe()` | `push_api.py:32` | **Public** | Subscribe current authenticated user to push notifications. |
| 203 | `POST, DELETE` | `/api/push/unsubscribe` | `unsubscribe()` | `push_api.py:92` | **Public** | Unsubscribe a device from push notifications. |
| 204 | `GET` | `/api/push/status` | `status()` | `push_api.py:119` | **Public** | Get subscription status for current authenticated user. |
| 205 | `POST` | `/api/push/send` | `send()` | `push_api.py:146` | **Public** | Send broadcast push notification to all subscribers. |
| 206 | `POST` | `/api/push/test` | `send_test_notification()` | `push_api.py:177` | **Public** | Send a test notification to the authenticated user's registered devices. |
| 207 | `GET, POST` | `/api/user/notification-preferences` | `user_notification_preferences()` | `push_api.py:216` | **Public** | Get or update user notification preferences stored in Supabase profiles. |
| 208 | `POST` | `/api/notifications/<notif_id>/open` | `track_notification_opened()` | `push_api.py:296` | **Public** | Record that a notification was opened/clicked by user. |
| 209 | `GET` | `/api/admin/analytics/overview` | `api_admin_analytics_overview()` | `methods/analytics_reporter_routes.py:13` | **Public** | Return overview KPIs for the analytics dashboard. |
| 210 | `GET` | `/api/admin/analytics/trending-files` | `api_admin_trending_files()` | `methods/analytics_reporter_routes.py:22` | **Public** | Return most viewed files. |
| 211 | `GET` | `/api/admin/analytics/demographics` | `api_admin_demographics()` | `methods/analytics_reporter_routes.py:32` | **Public** | Return user demographics breakdown. |
| 212 | `GET` | `/api/admin/analytics/usage-patterns` | `api_admin_usage_patterns()` | `methods/analytics_reporter_routes.py:41` | **Public** | Return hourly/daily usage patterns. |
| 213 | `GET` | `/api/admin/analytics/traffic-sources` | `api_admin_traffic_sources()` | `methods/analytics_reporter_routes.py:50` | **Public** | Return top referrer URLs. |
| 214 | `GET` | `/api/admin/analytics/devices` | `api_admin_devices()` | `methods/analytics_reporter_routes.py:60` | **Public** | Return device type distribution. |
| 215 | `GET` | `/api/admin/analytics/recent-activity` | `api_admin_recent_activity()` | `methods/analytics_reporter_routes.py:69` | **Public** | Return recent file view activity feed. |
| 216 | `GET` | `/api/admin/analytics/trending-subjects` | `api_admin_trending_subjects()` | `methods/analytics_reporter_routes.py:78` | **Public** | Return most viewed subjects. |
| 217 | `GET` | `/api/admin/analytics/errors` | `api_admin_errors()` | `methods/analytics_reporter_routes.py:88` | **Public** | Return recent errors. |
| 218 | `GET` | `/api/admin/analytics/daily-views` | `api_admin_daily_views()` | `methods/analytics_reporter_routes.py:98` | **Public** | Return daily view counts for chart. |
| 219 | `POST` | `/api/analytics/pageview` | `analytics_pageview()` | `methods/analytics_tracker.py:158` | **Public** | Server-side pageview logging with rate limiting. |
| 220 | `GET` | `/api/analytics/user-properties` | `analytics_user_properties()` | `methods/analytics_tracker.py:196` | **Public** | Returns the current user's profile data as JSON with rate limiting. |
| 221 | `POST` | `/api/analytics/error` | `analytics_error()` | `methods/analytics_tracker.py:214` | **Public** | Server-side error tracking with rate limiting. |
| 222 | `POST` | `/api/analytics/file-access` | `analytics_file_access()` | `methods/analytics_tracker.py:256` | **Public** | Track file access with duration, with rate limiting. |
| 223 | `POST` | `/api/analytics/session-end` | `analytics_session_end()` | `methods/analytics_tracker.py:295` | **Public** | Track session end with total duration, with rate limiting. |

### Categorized Route Details

#### 3.1 Web Pages & HTML Views
- `/` (or `/dashboard`): Main dashboard displaying colleges, branches, recent materials, and quick action cards.
- `/college/<college_name>`: College-specific landing page listing associated departments.
- `/department/<dept_name>`: Department page displaying semesters and subject directory.
- `/subject/<subject_name>`: Subject file explorer with tabs for PYQs, Notes, Practicals, Books, and Syllabus.
- `/view_pdf` & `/api/view-doc/<doc_id>`: Secured in-browser PDF reader invoking the self-hosted PDF.js viewer.
- `/upload`: Interactive file upload interface supporting single/batch files with hierarchy auto-detection.
- `/login`, `/signup`, `/reset-password`, `/reset-password-confirm`: Auth forms integrating with Supabase Auth.
- `/profile` & `/profile/<user_id>`: User contribution showcase, badges, reputation score, and peer viewer.
- `/leaderboard`: College and student rankings based on upload contributions and peer downloads.
- `/terms`, `/privacy`, `/about`, `/help`, `/brand`, `/contact`, `/team`, `/open-source`: Informational & legal pages.
- `/dino`: Offline Easter egg minigame.

#### 3.2 Authentication & User Profiles
- `POST /auth`: Exchanges Supabase bearer tokens for a secure Flask session cookie and initializes `UserSession`.
- `GET /auth-callback`: Handles OAuth redirect callbacks.
- `GET /api/check-auth`: Fast authentication verification endpoint.
- `GET /api/profile`: Retrieves current user profile, reputation metrics, badges, and contribution history.
- `POST /api/profile/update`: Updates bio, avatar, college, branch, graduation year, and public social handles.
- `GET /api/quota`: Returns remaining monthly paper preview quotas with L1 cache acceleration.

#### 3.3 Document Discovery, Upload & Store Room
- `GET /api/colleges`, `/api/branches`, `/api/departments`, `/api/subjects`: Cascading hierarchy metadata.
- `POST /api/get-upload-signature`: Generates authenticated Cloudinary direct-upload signatures.
- `POST /upload`: Handles multipart document upload, hierarchy validation, thumbnail creation, and XP allocation.
- `POST /api/check-duplicate`: SHA256 file hashing verification to prevent redundant uploads.
- `GET /api/search` & `/dashboard/search`: Instant search engine supporting fuzzy matching across papers.
- `GET /store-room`: Admin/Moderator file triage area for sorting unlabeled raw storage assets.
- `POST /store-room/api/label`: Confirms metadata and publishes a store room file into the live directory.

#### 3.4 AI Features (OCR, Paper Q&A, Metadata Prediction)
- `POST /api/ai/predict-metadata`: AI file inspection that reads initial bytes/title to suggest college, subject, and exam type.
- `POST /api/ask-paper`: Conversational Q&A on paper contents using OpenRouter LLM context injection.
- `POST /api/extract-ocr`: High-accuracy optical character recognition for scanned handwritten exam notes.

#### 3.5 Social, Memory Wall, Crushes & Encrypted Chat
- `GET /memorywall`: User dashboard for managing digital memory walls.
- `POST /memorywall/create`: Generates a shareable URL slug for peer memory signing.
- `GET /m/<slug>`: Public anonymous memory wall message submission form.
- `GET /memorywall/reveal/<wall_id>`: Batch reveal mechanism for graduation memory walls.
- `GET /chat` & `/chat/<peer_id>`: E2EE peer chat UI.
- `SOCKET_EVENT /api/chat/send`: Real-time WebSocket transmission of encrypted payloads.
- `POST /api/crush/submit`: Secret admirer matchmaking with mutual reveal triggers.

#### 3.6 Gamification, Economy, XP & Leaderboard
- `GET /leaderboard`: Live rankings sorted by upload XP, verification counts, and peer helpfulness score.
- `POST /api/referral/register`: Registers a referral code, crediting both referrer and referee with bonus preview quotas.
- `GET /api/referral/my-code`: Fetches personalized referral links and referral conversion statistics.
- `POST /api/buy-credits`: Simulated or razorpay-linked credit purchase for premium study material quotas.

#### 3.7 Web Push Notifications & Reliability
- `POST /api/push/subscribe`: Registers browser PushSubscription with VAPID keys.
- `POST /api/push/send-test`: Diagnostic push test for logged-in user.
- `GET /api/my-notifications`: Retrieves unread in-app alerts (likes, comments, approvals, chat messages).
- `POST /api/my-notifications/read`: Marks targeted alerts as read.

#### 3.8 Analytics, Reporting & Administration
- `GET /admin/analytics`: Full admin dashboard rendering daily views, trending files, and user demographics.
- `GET /api/admin/analytics/overview`: High-level platform KPIs (total files, users, active sessions).
- `POST /api/report-suspect`: Community moderation flagging for corrupted, incorrect, or copyrighted documents.

#### 3.9 SEO, IndexNow, PWA & Health Checks
- `GET /health` & `/api/health`: Health monitoring endpoint checking database and cache health.
- `GET /sitemap.xml`: Auto-generated dynamic XML sitemap indexing all college, subject, and document URLs.
- `POST /api/indexnow/submit`: Dispatches instant IndexNow crawling triggers to Bing/Yandex.
- `GET /sw.js` & `/manifest.json`: Progressive Web App (PWA) offline service worker and app manifest.

---

## 4. File-by-File Detailed System Catalog

This section documents **every single file** in the project, detailing its purpose, exports, dependencies, and role in the system architecture.

### Core Backend & Application Entry (4 files)

#### `app.py` (302,449 bytes)
- **Role:** Main application entry point & Flask router.
- **Key Responsibilities:** Initializes Flask, SocketIO, Supabase, Firebase Admin, registers all HTTP routes, sets up CSRF protection, error handlers (404, 500), and rate-limiting.
- **Dependencies:** `methods.supabase_helper`, `methods.cloudinary_upload`, `cache_manager`, `data.*`, `push_api`, `scheduled_tasks`.

#### `cache_manager.py` (24,427 bytes)
- **Role:** High-performance multi-tier caching engine.
- **Key Responsibilities:** Implements L1 (in-memory dict with TTL), L2 (disk serialized cache), and L3 (Supabase database cache) with automatic cache invalidation on uploads/updates.

#### `firebase_config.py` (2,035 bytes)
- **Role:** Firebase Admin SDK initialization helper.
- **Key Responsibilities:** Safe environment loading of service account credentials from `FIREBASE_SERVICE_ACCOUNT_JSON` or local file.

#### `push_api.py` (11,819 bytes)
- **Role:** Web Push subscription and broadcast management.
- **Key Responsibilities:** Stores VAPID endpoint subscriptions in Supabase, validates subscription integrity, dispatches payload chunks, and exposes push registration REST endpoints.

---

### Data Layer & DB Models (data/) (16 files)

#### `data/__init__.py` (991 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/analytics.py` (2,331 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/cache/README.md` (2,293 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/cache/cloudinary_files_cache.json` (2,221,020 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/colleges.py` (9,113 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/contact_messages.json` (1,914 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/db.py` (2,512 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/documents.py` (13,778 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/interactions.py` (11,986 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/notifications.py` (6,079 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/profiles.py` (8,428 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/raw/admin_users.json` (424 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/raw/data.json` (168,875 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/raw/notification_history.json` (2 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/raw/push_subscriptions.json` (1,545 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

#### `data/raw/suspects.json` (4,076 bytes)
- **Role:** Data access model layer for database entities.
- **Key Responsibilities:** Encapsulates Supabase queries, entity transformations, validation, and table CRUD operations.

---

### Service & Method Helpers (methods/) (20 files)

#### `methods/__init__.py` (0 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/admin_db_helper.py` (0 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/analytics_analyzer.py` (1,244 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/analytics_reporter.py` (25,005 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/analytics_reporter_routes.py` (4,750 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/analytics_tracker.py` (19,046 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/cloudinary_helper.py` (10,047 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/cloudinary_upload.py` (12,367 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/encrypted_chat.py` (12,197 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/get_user_uploaded_files.py` (2,184 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/indexer.py` (3,909 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/know_me.py` (17,882 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/know_me_generator.py` (4,314 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/scoring_engine.py` (18,064 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/search_api.py` (7,229 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/seo_helper.py` (1,254 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/storage.py` (7,253 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/storage_providers.py` (3,801 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/supabase_helper.py` (112,743 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

#### `methods/upload_notifier.py` (7,475 bytes)
- **Role:** Domain business logic & external integration service.
- **Key Responsibilities:** Provides helper functions for AI parsing, Cloudinary image upload, cryptographic chat hashing, analytics tracking, and Supabase interaction.

---

### Background Workers & Scheduling (4 files)

#### `bot.py` (28,607 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `push_notifications.py` (21,098 bytes)
- **Role:** Push notification transport & retry dispatcher.
- **Key Responsibilities:** Handles pywebpush VAPID signing, JSON payload formatting, exponential backoff retries, and dead endpoint cleanup.

#### `scheduled_tasks.py` (4,465 bytes)
- **Role:** APScheduler background cron orchestrator.
- **Key Responsibilities:** Runs periodic tasks including daily quota resets, orphan file cleanup, IndexNow bulk sitemap pings, and notification reliability verification.

#### `sync_firebase_documents.py` (12,431 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

### Database Migrations (migrations/) (28 files)

#### `migrations/008_all_features.sql` (5,103 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/009_add_exam_type.sql` (1,009 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/010_enterprise_ingestion.sql` (2,658 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/011_search_architecture.sql` (3,052 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/012_file_hashing.sql` (456 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/013_gamification.sql` (1,801 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/014_leaderboard.sql` (721 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/015_referral_system.sql` (1,459 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/016_referral_credit_columns.sql` (608 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/017_add_program_column.sql` (686 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/018_viewer_failure_reports.sql` (808 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/019_user_crushes.sql` (1,336 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/020_user_crushes_rls.sql` (1,496 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/021_enable_rls_all.sql` (4,186 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/022_scoring_config.sql` (2,087 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/023_extend_viewer_failure_reports.sql` (1,315 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/023_user_scores.sql` (3,443 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/024_chat_messages_table.sql` (2,181 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/025_add_chat_keys_to_profiles.sql` (736 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/026_add_missing_notification_types.sql` (477 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/027_notification_reliability_enhancements.sql` (1,674 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/add_college_popular_name.sql` (1,489 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/add_college_waitlist.sql` (957 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/add_quota_fields.sql` (212 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/add_student_profile_fields.sql` (1,831 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/add_upload_notification_columns.sql` (793 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/fix_file_access_history_rls.sql` (5,963 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

#### `migrations/know_me_tables.sql` (2,529 bytes)
- **Role:** Database schema versioning & SQL migration.
- **Key Responsibilities:** Contains DDL statements, table schemas, Postgres triggers, Row Level Security policies, and performance indexes.

---

### Templates & UI Views (templates/) (85 files)

#### `templates/abhijeetupdate.html` (40,996 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/about.html` (8,566 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/admin_analytics.html` (17,231 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/admin_economy.html` (13,893 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/admin_file_reports.html` (9,998 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/admin_notification_panel.html` (65,404 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/ads/banner.html` (4,170 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/ads/in_feed.html` (986 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/ads/sticky_mobile.html` (2,704 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/brand.html` (8,056 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/chat.html` (3,402 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/college.html` (11,822 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/college_coming_soon.html` (14,671 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/college_files.html` (11,804 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/contact.html` (12,979 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/delete_account.html` (7,113 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/department.html` (10,360 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/dino_game.html` (20,193 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/earnings.html` (4,542 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/exam_page.html` (6,516 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/favicon.html` (384 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/features.html` (21,855 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/forgot_password.html` (5,429 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/google_tag.html` (4,218 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/help.html` (5,447 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_auth_form.html` (2,389 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_card_feature.html` (698 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_card_file.html` (3,480 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_card_stat.html` (394 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_card_team_member.html` (1,404 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_file_drop_zone.html` (5,789 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_filter_search_bar.html` (2,018 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_form_contact.html` (2,619 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_hero_landing.html` (1,831 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_loading_spinner.html` (497 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_navbar_premium.html` (8,151 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_peer_search_modal.html` (13,641 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/_search_partial.html` (16,124 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/promo_card.html` (2,636 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/includes/seo_head.html` (3,777 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/join.html` (12,073 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/know_me/closed.html` (1,017 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/know_me/create.html` (3,198 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/know_me/dashboard.html` (11,599 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/know_me/public_wall.html` (9,528 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/know_me/reveal.html` (22,056 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/leaderboard.html` (9,349 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/logout_clear.html` (1,544 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/notifications.html` (10,874 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/offline.html` (4,278 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/open_source.html` (16,652 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_about.html` (1,155 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_account.html` (19,244 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_error.html` (3,150 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_file_receiver.html` (4,641 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_footer.html` (8,630 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_index.html` (92,861 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_landing.html` (16,455 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_local_preview.html` (30,213 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_login.html` (4,423 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_nav.html` (8,784 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_pdf_reader.html` (37,845 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_profile.html` (29,274 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_search.html` (113 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_share_receiver.html` (6,509 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_signup.html` (3,121 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_store_room.html` (17,204 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_struct.html` (46,438 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_support.html` (10,054 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_upload.html` (26,132 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_upload_gate.html` (3,328 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/p_view.html` (4,961 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/peer_profile.html` (9,720 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/preview.html` (16,394 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/privacy.html` (8,372 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/profile_instagram.html` (23,344 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/pyq_landing.html` (10,760 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/reset_password_form.html` (11,620 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/resource.html` (67,510 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/settings.html` (30,617 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/sitemap.xml` (475 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/subject.html` (11,300 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/team.html` (12,555 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/terms.html` (8,248 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

#### `templates/video_page.html` (3,603 bytes)
- **Role:** Jinja2 presentation template.
- **Key Responsibilities:** Renders responsive server-side HTML views, injects SEO meta tags, and mounts frontend interactive JS widgets.

---

### Static Assets (CSS, JS, PWA) (static/) (536 files)

#### `static/css/abhihub-select.css` (5,094 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/know-me.css` (18,142 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/overlay-system.css` (1,691 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/dashboard.css` (30,151 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_account.css` (9,236 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_file_receiver.css` (2,372 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_profile.css` (9,293 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_store_room.css` (21,942 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_upload.css` (27,534 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/p_upload_status_modal.css` (3,997 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pages/viewer.css` (41,950 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/00_design-tokens.css` (3,245 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/00_variables.css` (1,324 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/01_reset.css` (1,533 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/01_tokens.css` (6,425 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/02_base.css` (4,301 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/02_typography.css` (2,299 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/03_components.css` (10,253 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/04_layout.css` (12,831 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/05_utilities.css` (8,503 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/06_pages.css` (2,667 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/07_responsive.css` (2,455 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/08_animations.css` (10,717 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/MIGRATION.md` (3,934 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/app-shell.css` (3,456 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/chat.css` (7,612 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/dashboard-home.css` (5,113 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/feature-tour.css` (2,074 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/navbar.css` (8,533 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/notification-bell.css` (5,822 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/pipeline-master.css` (1,128 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/pipeline.css` (339 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/profile-nudge.css` (5,297 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/promo.css` (6,087 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/pwa-install.css` (3,862 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/support-page.css` (5,054 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/pipeline/upload-page.css` (25,689 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/study-pass.css` (1,189 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/tailwind-input.css` (791 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/css/tailwind.min.css` (14,273 bytes)
- **Role:** Cascading Style Sheets / UI Design tokens.
- **Key Responsibilities:** Defines color palettes, dark mode styling, layout grids, animations, and PDF viewer theme overlays.

#### `static/firebase-config.js` (420 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/android-chrome-192x192.png` (41,312 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/android-chrome-512x512.png` (311,920 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/apple-touch-icon.png` (37,493 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/default_logo.png` (41,638 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/favicon-16x16.png` (702 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/favicon-32x32.png` (1,970 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/favicon.ico` (15,406 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/google-icon.png` (2,450 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/images/logo.png` (41,638 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/index.html` (868 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/index.js` (8,304 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/js/abhihub-select.js` (20,879 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/access-gates.js` (10,457 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/ad-manager.js` (10,315 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/admin-dashboard.js` (0 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/analytics-helper.js` (6,749 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/analytics.js` (9,108 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/bulk_upload.js` (51,434 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/carousel-personalization.js` (8,493 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/chat.js` (30,503 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/file-history-tracker.js` (1,695 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/inline-handler-compat.js` (31,448 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/know-me.js` (32,657 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/notification-bell.js` (12,937 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/overlay-manager.js` (7,032 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/p_index.js` (77 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/p_landing.js` (961 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/p_login.js` (1,250 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/admin_dashboard.js` (170 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/p_index.js` (170 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/p_landing.js` (176 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/p_login.js` (161 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/p_profile.js` (11,371 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pages/p_upload.js` (164 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/01_utils.js` (503 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/02_ajax.js` (276 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/03_analytics.js` (161 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/04_api.js` (438 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/05_routes.js` (249 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/06_components.js` (571 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/07_login.js` (301 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pipeline/pipeline.js` (293 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/previously-accessed-files.js` (7,159 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/push-notifications.js` (13,249 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/pwa-install.js` (9,458 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/security.js` (7,066 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/js/service-worker.js` (4,504 bytes)
- **Role:** Client-side JavaScript module.
- **Key Responsibilities:** Handles DOM manipulation, AJAX API calls, client-side validation, UI state management, and real-time WebSocket messaging.

#### `static/know_me/generated/sw_a2cb3fc8-2c92-4729-800b-9a35167de3fc.png` (4,847 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/know_me/generated/sw_f70fe098-f0e7-4e29-b681-534475bf355b.png` (37,586 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/login-auth.js` (18,988 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/manifest.json` (3,658 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/navbar.js` (3,458 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/payment/Samsungpay Upi.jpeg` (67,253 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/LICENSE` (10,351 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.mjs` (877,899 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.mjs.map` (2,300,147 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.sandbox.mjs` (119,149 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.sandbox.mjs.map` (16,885 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.worker.mjs` (2,270,688 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/build/pdf.worker.mjs.map` (5,654,530 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-EUC-H.bcmap` (2,404 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-EUC-V.bcmap` (173 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-H.bcmap` (2,379 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-RKSJ-H.bcmap` (2,398 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-RKSJ-V.bcmap` (173 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78-V.bcmap` (169 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78ms-RKSJ-H.bcmap` (2,651 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/78ms-RKSJ-V.bcmap` (290 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/83pv-RKSJ-H.bcmap` (905 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90ms-RKSJ-H.bcmap` (721 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90ms-RKSJ-V.bcmap` (290 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90msp-RKSJ-H.bcmap` (715 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90msp-RKSJ-V.bcmap` (291 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90pv-RKSJ-H.bcmap` (982 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/90pv-RKSJ-V.bcmap` (260 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Add-H.bcmap` (2,419 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Add-RKSJ-H.bcmap` (2,413 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Add-RKSJ-V.bcmap` (287 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Add-V.bcmap` (282 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-0.bcmap` (317 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-1.bcmap` (371 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-2.bcmap` (376 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-3.bcmap` (401 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-4.bcmap` (405 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-5.bcmap` (406 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-6.bcmap` (406 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-CNS1-UCS2.bcmap` (41,193 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-0.bcmap` (217 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-1.bcmap` (250 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-2.bcmap` (465 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-3.bcmap` (470 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-4.bcmap` (601 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-5.bcmap` (625 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-GB1-UCS2.bcmap` (33,974 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-0.bcmap` (225 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-1.bcmap` (226 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-2.bcmap` (233 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-3.bcmap` (242 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-4.bcmap` (337 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-5.bcmap` (430 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-6.bcmap` (485 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Japan1-UCS2.bcmap` (40,951 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Korea1-0.bcmap` (241 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Korea1-1.bcmap` (386 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Korea1-2.bcmap` (391 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Adobe-Korea1-UCS2.bcmap` (23,293 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/B5-H.bcmap` (1,086 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/B5-V.bcmap` (142 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/B5pc-H.bcmap` (1,099 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/B5pc-V.bcmap` (144 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS-EUC-H.bcmap` (1,780 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS-EUC-V.bcmap` (1,920 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS1-H.bcmap` (706 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS1-V.bcmap` (143 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS2-H.bcmap` (504 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/CNS2-V.bcmap` (93 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETHK-B5-H.bcmap` (4,426 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETHK-B5-V.bcmap` (158 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETen-B5-H.bcmap` (1,125 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETen-B5-V.bcmap` (158 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETenms-B5-H.bcmap` (101 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/ETenms-B5-V.bcmap` (172 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/EUC-H.bcmap` (578 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/EUC-V.bcmap` (170 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Ext-H.bcmap` (2,536 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Ext-RKSJ-H.bcmap` (2,542 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Ext-RKSJ-V.bcmap` (218 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Ext-V.bcmap` (215 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GB-EUC-H.bcmap` (549 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GB-EUC-V.bcmap` (179 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GB-H.bcmap` (528 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GB-V.bcmap` (175 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBK-EUC-H.bcmap` (14,692 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBK-EUC-V.bcmap` (180 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBK2K-H.bcmap` (19,662 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBK2K-V.bcmap` (219 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBKp-EUC-H.bcmap` (14,686 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBKp-EUC-V.bcmap` (181 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBT-EUC-H.bcmap` (7,290 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBT-EUC-V.bcmap` (180 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBT-H.bcmap` (7,269 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBT-V.bcmap` (176 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBTpc-EUC-H.bcmap` (7,298 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBTpc-EUC-V.bcmap` (182 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBpc-EUC-H.bcmap` (557 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/GBpc-EUC-V.bcmap` (181 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/H.bcmap` (553 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKdla-B5-H.bcmap` (2,654 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKdla-B5-V.bcmap` (148 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKdlb-B5-H.bcmap` (2,414 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKdlb-B5-V.bcmap` (148 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKgccs-B5-H.bcmap` (2,292 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKgccs-B5-V.bcmap` (149 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKm314-B5-H.bcmap` (1,772 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKm314-B5-V.bcmap` (149 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKm471-B5-H.bcmap` (2,171 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKm471-B5-V.bcmap` (149 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKscs-B5-H.bcmap` (4,437 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/HKscs-B5-V.bcmap` (159 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Hankaku.bcmap` (132 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Hiragana.bcmap` (124 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-EUC-H.bcmap` (1,848 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-EUC-V.bcmap` (164 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-H.bcmap` (1,831 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-Johab-H.bcmap` (16,791 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-Johab-V.bcmap` (166 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSC-V.bcmap` (160 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCms-UHC-H.bcmap` (2,787 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCms-UHC-HW-H.bcmap` (2,789 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCms-UHC-HW-V.bcmap` (169 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCms-UHC-V.bcmap` (166 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCpc-EUC-H.bcmap` (2,024 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/KSCpc-EUC-V.bcmap` (166 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Katakana.bcmap` (100 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/LICENSE` (2,116 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/NWP-H.bcmap` (2,765 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/NWP-V.bcmap` (252 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/RKSJ-H.bcmap` (534 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/RKSJ-V.bcmap` (170 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/Roman.bcmap` (96 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UCS2-H.bcmap` (48,280 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UCS2-V.bcmap` (156 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF16-H.bcmap` (50,419 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF16-V.bcmap` (156 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF32-H.bcmap` (52,679 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF32-V.bcmap` (160 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF8-H.bcmap` (53,629 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniCNS-UTF8-V.bcmap` (157 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UCS2-H.bcmap` (43,366 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UCS2-V.bcmap` (193 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF16-H.bcmap` (44,086 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF16-V.bcmap` (178 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF32-H.bcmap` (45,738 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF32-V.bcmap` (182 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF8-H.bcmap` (46,837 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniGB-UTF8-V.bcmap` (181 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UCS2-H.bcmap` (25,439 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UCS2-HW-H.bcmap` (119 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UCS2-HW-V.bcmap` (680 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UCS2-V.bcmap` (664 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF16-H.bcmap` (39,443 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF16-V.bcmap` (643 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF32-H.bcmap` (40,539 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF32-V.bcmap` (677 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF8-H.bcmap` (41,695 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS-UTF8-V.bcmap` (678 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF16-H.bcmap` (39,534 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF16-V.bcmap` (647 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF32-H.bcmap` (40,630 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF32-V.bcmap` (681 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF8-H.bcmap` (41,779 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJIS2004-UTF8-V.bcmap` (682 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISPro-UCS2-HW-V.bcmap` (705 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISPro-UCS2-V.bcmap` (689 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISPro-UTF8-V.bcmap` (726 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISX0213-UTF32-H.bcmap` (40,517 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISX0213-UTF32-V.bcmap` (684 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISX02132004-UTF32-H.bcmap` (40,608 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniJISX02132004-UTF32-V.bcmap` (688 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UCS2-H.bcmap` (25,783 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UCS2-V.bcmap` (178 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF16-H.bcmap` (26,327 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF16-V.bcmap` (164 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF32-H.bcmap` (26,451 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF32-V.bcmap` (168 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF8-H.bcmap` (27,790 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/UniKS-UTF8-V.bcmap` (169 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/V.bcmap` (166 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/cmaps/WP-Symbol.bcmap` (179 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/compressed.tracemonkey-pldi-09.pdf` (1,016,315 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/debugger.css` (3,144 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/debugger.mjs` (25,198 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/download-guard.js` (238 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/iccs/CGATS001Compat-v2-micro.icc` (8,464 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/iccs/LICENSE` (6,669 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/altText_add.svg` (923 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/altText_disclaimer.svg` (3,400 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/altText_done.svg` (1,090 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/altText_spinner.svg` (2,740 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/altText_warning.svg` (1,535 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-check.svg` (426 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-comment.svg` (899 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-help.svg` (2,194 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-insert.svg` (418 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-key.svg` (1,463 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-newparagraph.svg` (437 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-noicon.svg` (165 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-note.svg` (1,083 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-paperclip.svg` (558 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-paragraph.svg` (1,159 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/annotation-pushpin.svg` (1,382 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/checkmark.svg` (569 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/comment-actionsButton.svg` (424 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/comment-closeButton.svg` (1,202 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/comment-editButton.svg` (916 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/comment-popup-editButton.svg` (1,639 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/cursor-editorFreeHighlight.svg` (2,942 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/cursor-editorFreeText.svg` (1,455 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/cursor-editorInk.svg` (1,327 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/cursor-editorTextHighlight.svg` (5,410 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/editor-toolbar-delete.svg` (913 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/editor-toolbar-edit.svg` (872 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/findbarButton-next.svg` (581 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/findbarButton-previous.svg` (581 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/gv-toolbarButton-download.svg` (785 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/loading-icon.gif` (2,545 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/loading.svg` (1,559 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/messageBar_closingButton.svg` (1,095 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/messageBar_info.svg` (1,079 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/messageBar_warning.svg` (814 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/pages_closeButton.svg` (286 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/pages_selected.svg` (361 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/pages_viewArrow.svg` (707 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/pages_viewButton.svg` (1,408 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-documentProperties.svg` (420 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-firstPage.svg` (263 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-handTool.svg` (1,347 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-lastPage.svg` (260 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-rotateCcw.svg` (599 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-rotateCw.svg` (579 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-scrollHorizontal.svg` (974 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-scrollPage.svg` (734 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-scrollVertical.svg` (972 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-scrollWrapped.svg` (1,231 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-selectTool.svg` (1,088 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-spreadEven.svg` (778 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-spreadNone.svg` (398 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/secondaryToolbarButton-spreadOdd.svg` (714 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-bookmark.svg` (864 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-currentOutlineItem.svg` (610 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-download.svg` (1,040 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-editorFreeText.svg` (503 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-editorHighlight.svg` (915 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-editorInk.svg` (1,193 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-editorSignature.svg` (1,583 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-editorStamp.svg` (742 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-menuArrow.svg` (684 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-openFile.svg` (1,403 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-pageDown.svg` (704 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-pageUp.svg` (685 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-presentationMode.svg` (684 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-print.svg` (930 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-search.svg` (1,237 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-secondaryToolbarToggle.svg` (1,083 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-viewAttachments.svg` (573 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-viewLayers.svg` (674 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-viewOutline.svg` (335 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-viewThumbnail.svg` (1,399 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-viewsManagerToggle.svg` (1,563 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-zoomIn.svg` (961 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/toolbarButton-zoomOut.svg` (475 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/treeitem-collapsed.svg` (93 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/images/treeitem-expanded.svg` (94 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ach/viewer.ftl` (7,458 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/af/viewer.ftl` (6,503 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/an/viewer.ftl` (9,421 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ar/viewer.ftl` (37,982 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ast/viewer.ftl` (6,507 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/az/viewer.ftl` (9,458 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/be/viewer.ftl` (41,117 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/bg/viewer.ftl` (19,872 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/bn/viewer.ftl` (11,762 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/bo/viewer.ftl` (8,617 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/bqi/viewer.ftl` (1,969 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/br/viewer.ftl` (13,018 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/brx/viewer.ftl` (9,822 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/bs/viewer.ftl` (26,401 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ca/viewer.ftl` (10,779 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/cak/viewer.ftl` (10,629 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ckb/viewer.ftl` (9,859 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/cs/viewer.ftl` (34,336 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/cy/viewer.ftl` (34,286 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/da/viewer.ftl` (32,281 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/de/viewer.ftl` (34,301 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/dsb/viewer.ftl` (34,937 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/el/viewer.ftl` (42,070 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/en-CA/viewer.ftl` (31,802 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/en-GB/viewer.ftl` (31,798 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/en-US/viewer.ftl` (30,587 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/eo/viewer.ftl` (33,280 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/es-AR/viewer.ftl` (33,589 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/es-CL/viewer.ftl` (33,805 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/es-ES/viewer.ftl` (33,809 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/es-MX/viewer.ftl` (33,740 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/et/viewer.ftl` (9,712 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/eu/viewer.ftl` (33,376 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/fa/viewer.ftl` (13,916 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ff/viewer.ftl` (8,691 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/fi/viewer.ftl` (33,350 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/fr/viewer.ftl` (34,522 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/fur/viewer.ftl` (29,061 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/fy-NL/viewer.ftl` (33,385 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ga-IE/viewer.ftl` (6,972 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/gd/viewer.ftl` (10,910 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/gl/viewer.ftl` (26,812 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/gn/viewer.ftl` (34,041 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/gu-IN/viewer.ftl` (11,962 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/he/viewer.ftl` (36,222 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hi-IN/viewer.ftl` (11,633 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hr/viewer.ftl` (32,096 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hsb/viewer.ftl` (34,944 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hu/viewer.ftl` (34,535 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hy-AM/viewer.ftl` (35,094 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/hye/viewer.ftl` (11,966 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ia/viewer.ftl` (33,492 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/id/viewer.ftl` (26,373 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/is/viewer.ftl` (25,735 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/it/viewer.ftl` (34,009 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ja/viewer.ftl` (35,282 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ka/viewer.ftl` (46,838 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/kab/viewer.ftl` (26,720 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/kk/viewer.ftl` (40,156 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/km/viewer.ftl` (12,318 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/kn/viewer.ftl` (9,762 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ko/viewer.ftl` (33,288 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/lij/viewer.ftl` (8,966 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/lo/viewer.ftl` (13,894 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/locale.json` (2,542 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/lt/viewer.ftl` (9,989 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ltg/viewer.ftl` (8,809 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/lv/viewer.ftl` (8,882 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/meh/viewer.ftl` (1,545 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/mk/viewer.ftl` (40,974 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ml/viewer.ftl` (30,693 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/mr/viewer.ftl` (11,050 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ms/viewer.ftl` (8,693 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/my/viewer.ftl` (9,279 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/nb-NO/viewer.ftl` (32,669 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ne-NP/viewer.ftl` (11,244 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/nl/viewer.ftl` (33,858 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/nn-NO/viewer.ftl` (32,686 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/oc/viewer.ftl` (15,948 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/pa-IN/viewer.ftl` (43,201 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/pl/viewer.ftl` (33,943 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/pt-BR/viewer.ftl` (33,748 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/pt-PT/viewer.ftl` (33,854 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/rm/viewer.ftl` (29,380 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ro/viewer.ftl` (34,375 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ru/viewer.ftl` (41,812 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sat/viewer.ftl` (15,212 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sc/viewer.ftl` (14,965 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/scn/viewer.ftl` (877 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sco/viewer.ftl` (9,120 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/si/viewer.ftl` (11,272 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sk/viewer.ftl` (34,777 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/skr/viewer.ftl` (24,044 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sl/viewer.ftl` (33,804 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/son/viewer.ftl` (6,150 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sq/viewer.ftl` (33,151 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sr/viewer.ftl` (40,090 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/sv-SE/viewer.ftl` (32,830 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/szl/viewer.ftl` (9,222 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ta/viewer.ftl` (11,157 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/te/viewer.ftl` (11,153 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/tg/viewer.ftl` (41,372 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/th/viewer.ftl` (43,202 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/tl/viewer.ftl` (9,331 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/tr/viewer.ftl` (33,118 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/trs/viewer.ftl` (6,469 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/uk/viewer.ftl` (39,454 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/ur/viewer.ftl` (9,685 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/uz/viewer.ftl` (5,670 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/vi/viewer.ftl` (34,484 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/wo/viewer.ftl` (3,094 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/xh/viewer.ftl` (6,907 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/zh-CN/viewer.ftl` (30,977 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/locale/zh-TW/viewer.ftl` (31,398 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitDingbats.pfb` (29,513 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitFixed.pfb` (17,597 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitFixedBold.pfb` (18,055 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitFixedBoldItalic.pfb` (19,151 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitFixedItalic.pfb` (18,746 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitSerif.pfb` (19,469 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitSerifBold.pfb` (19,395 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitSerifBoldItalic.pfb` (20,733 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitSerifItalic.pfb` (21,227 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/FoxitSymbol.pfb` (16,729 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LICENSE_FOXIT` (1,580 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LICENSE_LIBERATION` (4,516 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LiberationSans-Bold.ttf` (137,052 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LiberationSans-BoldItalic.ttf` (135,124 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LiberationSans-Italic.ttf` (162,036 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/standard_fonts/LiberationSans-Regular.ttf` (139,512 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/viewer.css` (207,596 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/viewer.html` (60,583 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/viewer.mjs` (679,216 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/viewer.mjs.map` (1,739,617 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_JBIG2` (13,058 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_OPENJPEG` (2,151 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_PDFJS_JBIG2` (568 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_PDFJS_OPENJPEG` (1,307 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_PDFJS_QCMS` (1,307 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/LICENSE_QCMS` (1,142 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/jbig2.wasm` (104,852 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/jbig2_nowasm_fallback.js` (145,718 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/openjpeg.wasm` (252,032 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/openjpeg_nowasm_fallback.js` (451,607 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/qcms_bg.wasm` (88,837 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/quickjs-eval.js` (6,248 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/pdfjs-6.1.200-dist/web/wasm/quickjs-eval.wasm` (469,105 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium-cards.css` (4,066 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/css/style.css` (80,725 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/data.json` (132,575 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/documents/Academic Calendar Summer 2025-UG.pdf` (2,070,453 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/documents/syllabus.pdf` (2,001,526 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/default.png` (228,304 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/logo.png` (228,304 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/notes.gif` (372,618 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/paper.gif` (314,098 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/papers.gif` (314,098 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/practical.gif` (466,148 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/practicals.gif` (466,148 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/icon/search.gif` (808,827 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/images/1.png` (54,580 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/images/6th_CAE1_2025_timetabel.jpg` (66,770 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/images/logo.png` (228,304 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/images/promotion/feature1.png` (25,664 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/images/promotion/update1.png` (286,549 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/interactions.js` (7,177 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/script.js` (41,120 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/search-worker.js` (1,983 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/store_room.js` (32,499 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/store_room_ai.js` (3,855 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/js/verification.js` (5,412 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/premium/rank.json` (1,246 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/robots.txt` (497 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/scripts.js` (1,261 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/search.json` (0 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/styles-books.css` (2,689 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/styles.css` (28,443 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/supabase-config.js` (1,126 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/sw.js` (29,018 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/viewer.css` (40,344 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/widget/data.json` (280 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `static/widget/template.json` (4,001 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

### Configuration & Metadata (38 files)

#### `EUsersabhihubNew` (0 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `ads.txt` (118 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `apply_migration_017.py` (2,020 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/notifications_cross_platform_20260911/metadata.json` (307 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_packaging_20260911/metadata.json` (338 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_readiness_20260911/metadata.json` (282 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `config.yml` (502 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `config/contributors.json` (297 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `config/labels.json` (2,701 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/ceo.json` (1,526 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/community.json` (717 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/company_consolidated.json` (8,816 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/engagement.json` (1,207 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/finance.json` (778 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/growth.json` (1,004 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/ops.json` (642 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/product.json` (701 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/revenue.json` (806 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/route_snapshot.json` (25,027 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `favicon.ico` (15,406 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `getSettings.ts` (5,175 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-144-144.png` (18,496 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-192-192.png` (29,497 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-48-48.png` (3,289 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-512-512.png` (144,956 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-72-72.png` (6,190 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/android/android-launchericon-96-96.png` (9,732 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/contact-request-svgrepo-com.svg` (817 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `icons/group.png` (23,075 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `package-lock.json` (63,426 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `package.json` (493 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `release/build-production-artifact.py` (7,157 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `release/production-manifest.json` (6,641 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `requirements-min.txt` (59 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `requirements.txt` (319 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `robots.txt` (406 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `setup.py` (15,455 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `tailwind.config.js` (416 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

### Developer & Automation Scripts (scripts/, dev/) (47 files)

#### `conductor/index.md` (219 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/product.md` (987 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tech-stack.md` (875 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks.md` (574 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/notifications_cross_platform_20260911/index.md` (411 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/notifications_cross_platform_20260911/plan.md` (2,725 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/notifications_cross_platform_20260911/spec.md` (3,746 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_packaging_20260911/index.md` (133 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_packaging_20260911/plan.md` (1,513 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_packaging_20260911/spec.md` (1,126 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_readiness_20260911/index.md` (143 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_readiness_20260911/plan.md` (1,329 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/tracks/production_readiness_20260911/spec.md` (1,412 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `conductor/workflow.md` (431 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/README.md` (1,511 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/bot.py` (4,602 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/config.py` (2,278 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/llm.py` (2,212 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/ceo.md` (1,001 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/community.md` (533 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/engagement.md` (914 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/finance.md` (654 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/growth.md` (1,788 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/ops.md` (448 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/product.md` (568 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/reports/revenue.md` (678 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/ceo.py` (2,716 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/community.py` (1,001 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/engagement.py` (2,121 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/finance.py` (1,778 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/growth.py` (2,093 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/ops.py` (1,065 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/product.py` (1,462 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/roles/revenue.py` (1,767 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/bots/run.py` (3,245 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/check_doc_links.py` (1,669 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/route_parity.py` (5,446 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/scripts/campaign_export.py` (4,853 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/scripts/campaign_report.py` (4,336 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/scripts/exam_pack_drip.py` (11,631 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/scripts/generate_vapid.py` (1,603 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/scripts/sync_abhihub_context.py` (2,629 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/verify_bugs.py` (6,471 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `dev/verify_model_graph.py` (6,503 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `scripts/auto_assign.py` (12,731 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `scripts/build-production-artifact.py` (361 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `scripts/feature_planner.py` (11,986 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

### Documentation & Guides (docs/) (57 files)

#### `CHANGELOG.md` (6,592 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `CONTRIBUTING.md` (2,271 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `README.md` (3,837 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `SECURITY.md` (3,628 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `STATUS_FIX_SUMMARY.md` (1,201 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `antigravity-instruction.md` (12,895 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `automation_test_report.md` (1,959 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/FEATURES.md` (20,311 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/FEATURES_REVIEW.md` (77,180 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/README.md` (3,991 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/audit.md` (17,398 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/dashboard-spec.md` (4,158 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/data-quality.md` (4,689 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/event-taxonomy.md` (13,037 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/privacy.md` (2,556 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/analytics/rollout-and-rollback.md` (2,289 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/architecture/ARCHITECTURE.md` (9,750 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/architecture/CSS_PIPELINE.md` (4,493 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/guides/COMPANY_SKILLS_AND_BOTS.md` (4,335 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/guides/FILE_HISTORY_SETUP.md` (9,624 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/guides/GA4_IMPLEMENTATION.md` (14,109 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/guides/USER_GUIDE.md` (9,051 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/history/ANALYTICS_CHANGES.md` (4,010 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/history/CSS_CONFLICTS_RESOLVED.md` (4,486 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/history/REORG_PROGRESS.md` (12,335 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/history/audit_report_2026-07-11.md` (7,543 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/audit.md` (9,115 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/catalog.md` (7,073 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/notification-audit.md` (11,551 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/production-runbook.md` (4,528 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/support-matrix.md` (6,690 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/test-matrix.md` (6,755 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/notifications/test-runbook.md` (5,404 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/product/IDEA.md` (5,514 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/production-readiness/audit.md` (8,126 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/production-readiness/baseline.md` (1,228 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/production-readiness/checklist.md` (2,260 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/production-readiness/deployment-runbook.md` (1,794 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/production-readiness/final-report.md` (3,010 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/pull_request_template.md` (774 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/reference/BUGS.md` (29,116 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/reference/DATA_MODEL_RELATIONS.md` (50,247 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/reference/ROUTES.md` (67,169 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/refrence/PERFORMANCE_COST_IMPROVEMENTS.md` (19,923 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/release/deployment-contract.md` (5,638 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/release/deployment-runbook.md` (2,890 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/release/production-inventory.md` (11,593 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `docs/release/rollback-runbook.md` (1,880 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `notification-production-agent-instruction.md` (11,985 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `notification-reliability-agent-instruction.md` (12,981 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `pdf_viewer_audit.md` (6,230 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `production-deployment-branch-agent-instruction.md` (12,965 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `production-ready-agent-instruction.md` (10,939 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `skills/code-refactoring/SKILL.md` (2,072 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `software-development/flask-security-audit/references/pdfjs-cors-fix.md` (3,220 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `work complete.md` (2,587 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `working on.md` (7,722 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

### Testing Suite (tests/) (13 files)

#### `tests/conftest.py` (817 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_analytics_redesign.py` (3,474 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_automation_suite.py` (15,616 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_cache_manager.py` (14,902 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_csrf.py` (894 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_dashboard_auth.py` (9,611 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_delete_account_form.py` (1,300 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_notifications.py` (9,447 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_production_artifact.py` (2,024 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_production_readiness.py` (4,471 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_production_smoke.py` (1,416 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_referral_flow.py` (8,069 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

#### `tests/test_storage_uploads.py` (11,722 bytes)
- **Role:** Automated unit & integration test suite.
- **Key Responsibilities:** Tests route parity, database models, caching behavior, and authentication flows using `pytest`.

---

### Deployment & Containerization (4 files)

#### `Dockerfile` (2,568 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `LICENSE` (2,496 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `Procfile` (84 bytes)
- **Role:** Configuration, project tooling, or documentation file.

#### `gunicorn.conf.py` (261 bytes)
- **Role:** Configuration, project tooling, or documentation file.

---

## 5. Data Flow, Security & Cache Architecture

### 5.1 Request Lifecycle & Security Pipeline
1. **Request Ingestion:** Request enters via Gunicorn/Gevent WSGI server.
2. **Domain Normalization:** `redirect_to_custom_domain` redirects legacy Heroku URLs to canonical custom domain.
3. **CSRF Verification:** `check_csrf` validates anti-CSRF tokens for all state-mutating requests (exempting `/api/` token endpoints).
4. **Authentication Decorator:** `@auth_required` checks `session['user']` or Bearer JWT.
5. **L1/L2 Cache Check:** High-frequency GET queries (e.g. `/api/colleges`, `/api/quota`) check in-memory cache before hitting Supabase.
6. **Database Execution:** Supabase PostgreSQL executes queries under active Row Level Security (RLS) policies.
7. **Response Compression:** `Flask-Compress` applies Gzip/Brotli encoding before sending bytes to client.

### 5.2 Storage & In-Browser PDF Protection
- Documents uploaded by students are sent via signed multipart POST directly to Cloudinary.
- URLs stored in `abhihub.documents` are protected; raw links are never exposed to clients.
- Document viewing routes (`/view_pdf`, `/api/view-doc/<id>`) stream or pass authenticated proxied streams into self-hosted PDF.js.
- Direct PDF download is disabled at the viewer UI layer to preserve academic author attribution and platform integrity.

---

## 6. Deployment & Production Runbook

### 6.1 Environment Variables Configuration
Key environment variables required for production:
```bash
SECRET_KEY=<flask_session_secret_key>
SUPABASE_URL=https://<your_supabase_project>.supabase.co
SUPABASE_KEY=<supabase_service_role_or_anon_key>
CLOUDINARY_CLOUD_NAME=<cloudinary_cloud_name>
CLOUDINARY_API_KEY=<cloudinary_api_key>
CLOUDINARY_API_SECRET=<cloudinary_api_secret>
FIREBASE_SERVICE_ACCOUNT_JSON=<firebase_service_account_json_content>
VAPID_PUBLIC_KEY=<web_push_vapid_public_key>
VAPID_PRIVATE_KEY=<web_push_vapid_private_key>
OPENROUTER_API_KEY=<openrouter_ai_key>
INDEXNOW_KEY=<bing_indexnow_api_key>
BASE_DOMAIN=abhihub.edu.eu.org
ADMIN_EMAILS=admin@abhihub.edu.eu.org,abhijeet@abhihub.edu.eu.org
```

### 6.2 Running Locally
```bash
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
```

### 6.3 Production Server Launch
```bash
gunicorn --config gunicorn.conf.py --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app
```

### 6.4 Verification Commands
```bash
pytest                                   # Run test suite
python dev/route_parity.py verify        # Verify route parity
```

---

*Master report compiled autonomously for AbhiHub repository.*