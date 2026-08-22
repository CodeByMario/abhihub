# AbhiHub — Feature Inventory

> **Last sync:** 2026-08-22  •  **Sources:** `README.md`, `ARCHITECTURE.md`, `USER_GUIDE.md`, `ROUTES.md`, `DATA_MODEL_RELATIONS.md`, `app.py`

---

## 1. Core Platform

### What It Is
A community-powered study-material platform for engineering students. Upload and browse previous-year question papers, notes, and practicals — organised by **college → branch/department → semester → subject**.

### Document Types
| Type | Description |
|------|-------------|
| 📚 **Study Notes** | Subject-wise notes curated by contributors |
| 📝 **Previous Year Questions (PYQs)** | Real exam papers organised by year and exam type |
| 🔬 **Practical & Lab Guides** | Step-by-step lab manuals and practical records |
| 📋 **Papers** | Exam papers and question banks |

### Anti-Piracy Model (Non-Negotiable)
- **Preview in-browser only** via self-hosted **PDF.js** (`static/pdfjs-6.1.200-dist/`)
- No download buttons or links anywhere in templates (`resource.html`, `p_pdf_reader.html`)
- No `Content-Disposition: attachment` — only `inline`
- `X-Download-Options: noopen`, `no-store` headers on PDF delivery
- Referer check on `/pdf-proxy/` and `/api/view-doc/`
- **PDF.js is canonical** — never swap the viewer library silently
- JS-level: no `window.downloadImage` or compat download handlers

---

## 2. Authentication & Accounts

| Feature | Details |
|---------|---------|
| **Email + Password signup** | Classic registration flow with verification |
| **Google SSO** | "Continue with Google" quick sign-up/login |
| **Password recovery** | "Forgot Password?" → email reset link |
| **Profile management** | `/api/profile` (GET), `/api/profile/update` (POST) — full_name, college, department, role, etc. |
| **Profile status check** | `/api/profile-status` — airlock for client-side auth state |
| **Check auth** | `/api/check-auth` — lightweight auth probe |
| **Logout** | `/logout` — clears session |

### Onboarding
- **Welcome screen** — first-login onboarding flow
- `/api/onboarding/status` — check if user has seen welcome
- `/api/onboarding/welcome-seen` — mark welcome as seen

### Quota / Credits System
- Each **upload grants `QUOTA_PER_UPLOAD` (19) paper opens**
- Monthly quota reset (tracked via `last_quota_reset` on `profiles`)
- `_consume_credit()` gates every paper open — admins bypass
- `_check_and_log_view()` is the shared "check quota + log view" helper
- `/api/quota` — GET current quota remaining (auth required)
- **Credit economy:** upload → earn credits; daily credit earn; tasks (upload, referral, enable notifications, install PWA, disable adblocker) earn credits for viewing files

---

## 3. Academic Taxonomy (Discovery Hierarchy)

The platform is organised as a strict hierarchy: **College → Department/Branch → Subject → Documents**.

### Colleges
- `/api/colleges` — list all colleges
- `/api/colleges` (POST, admin) — add a college
- College landing page: `/college/<slug>`
- Fields: `name`, `abbreviation`, `popular_name`, `aliases` (TEXT[])

### Departments / Branches
- `/api/departments` — list departments
- `/api/branches` — list all branches (departments)
- `/api/departments` (POST, admin) — add a department
- Department landing page: `/college/<slug>/<dept>`
- Fields: `name`, `abbreviation`, `college_id` → colleges.id

### Subjects
- `/api/subjects` — list subjects (public)
- `/api/subjects` (POST, admin) — add a subject
- Subject page: `/subject/<slug>`
- Subject requests: `/api/subject-request` (auth) — users request new subjects; stored in `pending_subject_requests`
- Fields: `name`, `subject_code`, `semester` (CHECK 1-8), `department_id`
- **Subject aliases** (`subject_aliases` table) — for search tokenization (e.g. "DBMS" → "Database Management Systems")

### Waitlist
- `/api/waitlist/join` (public) — join a college waitlist
- `college_waitlist` table: `college_id`, `email`, `name`, `created_at`

---

## 4. Document Management

### Upload
- **Route:** `/upload` (GET + POST, auth required)
- Multi-step upload with metadata form: subject, year, type, unit/practical name
- **AI metadata prediction:** `/api/ai/predict-metadata` (auth) — uses OpenRouter to auto-tag uploaded files
- **Duplicate check:** `/api/check-duplicate` (auth) — checks by `file_hash` before upload
- Storage: **Cloudinary** (canonical) with **Firebase Storage** as legacy fallback
- Upload flow goes through `storage_assets` table (PENDING → PROCESSING → LABELED → ERROR)

### Preview & Viewing
| Route | Auth | Purpose |
|-------|------|---------|
| `/preview` (POST) | Yes | Preview a document via signed URL |
| `/api/view-doc/<doc_id>` | No | Serve document PDF (with anti-piracy headers) |
| `/pdf-proxy/<path:pdf_name>` | No | Proxy PDF from storage |
| `/view_pdf` | No | Legacy PDF view page |
| `/resource/<slug>` | No | Resource landing page |

### Document Catalog
- `/api/recent-documents` — recent documents (public)
- `/api/files/all` — all approved documents (public)
- `/api/file-access-history` (auth) — user's own file access history
- `/pyq` — PYQ listing page

### Document Metadata (on `documents` table)
- `title`, `document_category`, `description` (JSON text)
- `file_url`, `file_type`, `file_size_bytes`
- `storage_provider`, `provider_public_id`
- `status`: `pending` | `approved` | `rejected`
- `view_count`, `like_count`, `bookmark_count`, `comment_count`
- `exam_type`, `file_hash`
- Uniqueness: `(storage_provider, provider_public_id)`

### Store Room (Content Moderation Queue)
A moderation/labeling workflow for ingested but unlabeled assets:
| Route | Purpose |
|-------|---------|
| `/store-room` | Main store-room page (auth) |
| `/store-room/api/sync` | Sync storage assets |
| `/store-room/api/unlabeled` | List unlabeled assets |
| `/store-room/api/rename-file` | Rename a file in queue |
| `/store-room/api/verify` | Verify/mark a file as labeled |
| `/store-room/api/verification-queue` | Verification queue view |
| `/store-room/api/label` | Label a store-room paper (auth) |

---

## 5. Search

### Smart Search v2
- **Route:** `/api/v2/search` — primary search endpoint
- **Route:** `/dashboard/search` — dashboard search (auth)
- **Route:** `/dashboard/static/search.json` — pre-built search index (auth)
- **Route:** `/dashboard/save_search` (POST, auth) — save favourite searches
- **Route:** `/dashboard/suggest` — search suggestions

### Advanced Search Syntax
| Filter | Example | Description |
|--------|---------|-------------|
| `type:` | `type:notes` | Filter by resource type |
| `subject:` | `subject:dbms` | Filter by subject name |
| `author:` | `author:john` | Filter by contributor |
| `year:` | `year:2024` | Filter by year |
| `exam:` | `exam:midsem` | Filter by exam type |

**Combined example:** `dbms type:notes year:2024`

### Search Intelligence
- **Fuzzy matching** — slight misspellings auto-corrected
- **Synonyms** — `pyq` → Previous Year Questions, `prac` → Practicals, `imp` → important, `paper` → pyq
- **Abbreviations work**
- Search index table: `search_documents` (pre-indexed, 1:1 with `documents`)
- Search manifest: `search_manifest` — tracks pipeline version, tokenizer, OCR, embedding versions
- Search analytics: `search_analytics` — query, results_count, clicked_file_id, response_time_ms

### OCR & AI Extraction
- `/api/extract-ocr` (auth) — OCR extraction from uploaded documents
- `/api/ask-paper` (auth) — AI-powered paper querying

---

## 6. Social & Interactions

| Feature | Route | Auth |
|---------|-------|------|
| **Like / Unlike** | `/api/interactions/like` (POST) | Yes |
| **Bookmark / Unbookmark** | `/api/interactions/bookmark` (POST) | Yes |
| **Comments** | `/api/interactions/comments/<doc_id>` (GET + POST) | Yes (auth for POST) |
| **Legacy like** | `/api/like` (POST) | Yes |
| **Legacy bookmark** | `/api/bookmark` (POST) | Yes |
| **Legacy comments** | `/api/interactions/comments/<document_id>` (GET + POST) | Auth varies |

### Interaction Tables
- `document_votes` — likes (user_id, document_id, vote_type)
- `bookmarks` — bookmarks (user_id, document_id)
- `document_comments` — comment threads (document_id, user_id, content, is_deleted, created_at)
- `document_views` — view logging (document_id, user_id, accessed_at, ip_address, device_type)

---

## 7. Notifications

| Feature | Route | Details |
|---------|-------|---------|
| **In-app notifications** | `/api/my-notifications` (GET, auth) | List user notifications |
| **Mark read** | `/api/my-notifications/read` (POST, auth) | Mark notifications as read |
| **Web push subscriptions** | `push_subscriptions` table | endpoint, p256dh, auth, device_type |
| **Push delivery** | `push_notifications.py` + `push_api.py` | Flask-SocketIO + web push |
| **Upload notifier** | `upload_notifier.py` | Post-upload push notification job |

### Notification Fields (`notifications` table)
- `type`, `title`, `message`, `action_url`, `is_read`, `created_at`

---

## 8. Dashboard & UI

### Dashboard Pages
| Route | Auth | Purpose |
|-------|------|---------|
| `/dashboard` | No (public) / Yes (premium) | Main dashboard with stats |
| `/dashboard/` (POST) | No | Index/landing action |
| `/dashboard/search` | Yes | Search within dashboard |
| `/dashboard/view` | Yes | View resource from dashboard |
| `/dashboard/share-receiver` | Yes | Handle shared links |
| `/dashboard/about` | Yes | About/premium info |
| `/dashboard/profile/old` | Yes | Redirect to profile |
| `/dashboard/setting` | No | Settings page |
| `/dashboard/suggest` | No | Suggestions |

### Top Navigation
- 🏠 **Home** — main dashboard
- 🔍 **Search** — quick search
- 📁 **Upload** — contribute resources
- 👤 **Profile** — view contributions and account info
- ⚙️ **Settings** — account preferences

### File Cards
Each resource card displays:
- **Subject** — the subject area
- **File Name** — document title
- **Author** — contributor who shared it
- **Date** — upload date
- **Type** — Notes, Papers, Practical, PYQ etc.

### Quick Actions
- Click any file card to view in PDF.js
- "Show More" buttons to reveal additional files
- Filter dropdowns by subject, year, or type

---

## 9. Progressive Web App (PWA)

| Feature | Route/File | Purpose |
|---------|-----------|---------|
| **Service Worker** | `/sw.js` | Offline caching, push delivery |
| **PWA Manifest** | `/manifest.json` | App metadata for install |
| **Widget data** | `/api/widget-data` | Embedded widget data |
| **Install overlay** | Interactive PWA installation overlay | Guides users to install |

### Installable On
- **Chrome (Desktop)** — install icon (➕) in address bar
- **Android** — Chrome → three-dot menu → "Add to Home Screen"
- **iOS (Safari)** — Share button → "Add to Home Screen"

### PWA Benefits
- 🚀 Faster loading from home screen
- 📴 Offline access to cached resources
- 📱 App-like experience without app store
- 🔔 Stay updated with latest resources

---

## 10. Memory Wall

A social feature where users create "memory walls" — publicly accessible nostalgia/sentiment boards.

| Route | Auth | Purpose |
|-------|------|---------|
| `/memorywall` | Yes | Memory wall dashboard |
| `/memorywall/create` | Yes | Create a new memory wall |
| `/m/<slug>` | No | Public memory wall view |
| `/memorywall/reveal/<wall_id>` | Yes | Reveal responses (auth) |
| `/api/memorywall/submit` | No | Submit a response |
| `/api/memorywall/upload-signature` | No | Upload signature image |
| `/api/memorywall/stats/<wall_id>` | Yes | Get wall stats (auth) |

### Tables
- `memory_wall` — id, user_id (text), slug (UNIQUE), title, photo_url, college, branch, graduation_year, status (active/closed), response_count, view_count
- `memory_response` — id, wall_id → memory_wall.id, friend_name, word_1, word_2, word_3, memory_message, emoji, anonymous, ip_hash
- `signature` — id, response_id → memory_response.id, signature_url

---

## 11. Peer-to-Peer Features

### Peer Chat (Real-Time via SocketIO)
| Route/Event | Auth | Purpose |
|-------------|------|---------|
| `/chat` | Yes | Chat listing page |
| `/chat/<peer_id>` | Yes | Chat with a specific peer |
| `/api/chat/send` (SocketIO) | Yes | Send a chat message |
| `/api/chat/request-history` (SocketIO) | Yes | Chat request history |
| `/api/chat/resend-history` (SocketIO) | Yes | Resend chat history |
| `/api/chat/online` | Yes | Online users list |
| `/api/chat/user-info/<user_id>` | Yes | Peer user info |
| `/api/users/search` | Yes | Search users |
| `/profile/<user_id>` | Yes | View peer profile |

### Material Requests (Peer Sharing)
| Route | Purpose |
|-------|---------|
| `/api/request-material` (POST, auth) | Request a material from a peer |
| `/api/material-requests` (GET, auth) | List your material requests |
| `/api/material-request/respond` (POST, auth) | Respond to a material request |
| `/api/user/<target_user_id>/materials` (GET, auth) | View peer's uploaded materials |

### Gamification Hooks
- `contribution_logs` — XP tracking per action
- `user_achievements` — badges unlocked
- `leaderboard_view` — SQL view aggregating XP + reputation
- `reputation_score`, `students_helped`, `referral_credits`, `referral_count` on `profiles`

---

## 12. Admin Panel

| Route | Auth | Purpose |
|-------|------|---------|
| `/admin/analytics` | Admin | Admin analytics dashboard |
| `/api/admin/*` | Admin | Admin API endpoints |
| `/api/admin/entity/add` | Auth | Add an entity |
| `/api/subjects` (POST) | Admin | Add a subject |
| `/api/colleges` (POST) | Admin | Add a college |
| `/api/departments` (POST) | Admin | Add a department |
| `/indexnow` (POST) | Admin | Submit to Bing IndexNow |
| **IndexNow key file** | — | `GET /<key>.txt` serves IndexNow key |

### Admin Config
- `ADMIN_EMAILS` — env var, comma-separated admin email list
- `@admin_required` — decorator checking email against `ADMIN_EMAILS`

---

## 13. Gamification & Credits Economy

### Credit Earning
- **Upload → earn credits**
- **Daily credit earn** — periodic credit accrual
- **Task-based earning:**
  - Upload a document
  - Referral signup
  - Enable notifications
  - Install PWA
  - Disable adblocker
- Credits used for **viewing files** (paper quota system)

### Reputation & Leaderboard
- `reputation_score` on `profiles`
- `students_helped` on `profiles`
- `contribution_logs` — XP awarded per action (UPLOAD, etc.)
- `user_achievements` — badges with `badge_name`, `badge_icon`, `unlocked_at`
- `leaderboard_view` — SQL VIEW ranking users by total XP

### Referral System
- `referral_code` (UNIQUE) on `profiles`
- `referred_by` → profiles.id
- `referral_credits`, `referral_count`

---

## 14. Analytics & SEO

### Analytics
| Component | Purpose |
|-----------|---------|
| `analytics_tracker.py` | GA4-style event capture; registers own routes |
| `analytics_reporter.py` / `_routes.py` | Reporting queries + their routes |
| `analytics_analyzer.py` | Aggregation helpers |
| `user_events` table | UPLOAD / DOWNLOAD / SUBJECT_REQUEST events |
| `search_analytics` table | Search query feedback |

### SEO
| Feature | Route/File | Purpose |
|---------|-----------|---------|
| **Sitemap** | `/sitemap.xml` | Dynamic XML sitemap (colleges, depts, subjects, docs) |
| **IndexNow** | `/indexnow` (POST, admin) + `<key>.txt` | Bing IndexNow submissions |
| **SEO helper** | `methods/seo_helper.py` | Slug/canonical helpers |
| **SEO landings** | `/college/<slug>`, `/subject/<slug>`, `/pyq` | Search-engine-friendly landing pages |

### Standard Files
- `/ads.txt` — ad publisher IDs
- `/robots.txt` — crawl rules
- `/favicon.ico` — site icon

---

## 15. Static Pages & Utilities

| Page | Route | Purpose |
|------|-------|---------|
| **Terms** | `/terms` | Terms of service |
| **Privacy** | `/privacy` | Privacy policy |
| **Help** | `/help` | Help centre |
| **Logo** | `/logo` | Logo asset |
| **Offline** | `/offline` | Offline fallback page (also service worker fallback) |

---

## 16. AI-Powered Features

| Feature | Route | Details |
|---------|-------|---------|
| **AI metadata prediction** | `/api/ai/predict-metadata` (POST, auth) | Uses OpenRouter API to auto-tag uploaded document metadata (subject, type, etc.) |
| **OCR extraction** | `/api/extract-ocr` (POST, auth) | Extract text via OCR from uploaded documents |
| **Ask paper** | `/api/ask-paper` (POST, auth) | AI-powered querying of paper content |
| **OpenRouter integration** | `app.py` with `OPENROUTER_API_KEY` | Backend for AI features |

---

## 17. Technical Infrastructure

### Stack
| Layer | Technology |
|-------|------------|
| Web framework | Flask (gunicorn + gevent) |
| Database / auth | Supabase (Postgres, schema `abhihub`) |
| File storage | Cloudinary (canonical), Firebase Storage (legacy fallback) |
| PDF viewer | PDF.js, self-hosted (v6.1.200) |
| Realtime | Flask-SocketIO (gevent-websocket) |
| Styling | Tailwind + custom CSS pipeline |
| Hosting | Heroku |
| Background jobs | `scheduled_tasks.py` (scheduler) |
| Caching | `cache_manager.py` — L1 (in-process), L2 (shared), L3 (HTTP headers) |

### Key Infrastructure Components
- **CSRF protection** — `CSRFProtect(app)`, 1h TTL, exempted for `/api/`, `/auth`, `/store-room/api/`
- **Gzip compression** — `Compress(app)`
- **Supabase client** — schema `abhihub`, module-level singleton
- **Firebase Admin** — `firebase_admin.initialize_app()` for push notifications
- **SocketIO** — `SocketIO(app, cors_allowed_origins="*")`

### Environment Variables (Required)
| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |

### Additional Env Vars
`BASE_DOMAIN`, `INDEXNOW_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `FLASK_ENV`, `ADMIN_EMAILS`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `TURNSTILE_SECRET`, `INDEX_NOW_BING_API_KEY`, `CLOUDINARY_*` (multiple)

---

## 18. Data Model Summary

### Core Identity & Auth
- `profiles` — main user profile (id = auth.users.id)
- `students` (public) — student-specific fields (registration_number, college_id, branch_id, etc.)
- `teachers` (public) — teacher-specific fields
- `user_sessions` — login/logout session logging

### Academic Taxonomy
- `colleges`, `departments`, `subjects`
- `college_departments` — many-to-many linking table
- `pending_subject_requests` — subject request workflow
- `subject_aliases` — search tokenization aliases

### Content
- `documents` — all content (15+ indexed columns)
- `storage_assets` — ingestion queue for unlabeled files
- `label_audit_logs` — audit trail for moderation actions

### Interactions
- `document_votes` (likes), `bookmarks`, `document_comments`, `document_views`, `file_access_history`

### Notifications & Push
- `notifications`, `push_subscriptions`

### Search
- `search_documents` (pre-indexed), `search_manifest`, `search_analytics`

### Gamification
- `contribution_logs`, `user_achievements`, `leaderboard_view` (SQL VIEW)

### User Events
- `user_events` — UPLOAD / DOWNLOAD / SUBJECT_REQUEST tracking

### Memory Wall
- `memory_wall`, `memory_response`, `signature`

### Other
- `college_waitlist`, `material_requests`, `user_file_views`, `file_records` (legacy)

---

## 19. Route Count

- **148 REST routes** discovered via `@app.route`
- **6 Socket.IO events** for real-time chat
- **2 error handlers** (404, 500)
- **Total: 156 route-like registrations**

---

*This inventory is generated from the current codebase state. For the full route map, see [`docs/reference/ROUTES.md`](docs/reference/ROUTES.md). For the data model, see [`docs/reference/DATA_MODEL_RELATIONS.md`](docs/reference/DATA_MODEL_RELATIONS.md).*
