# AbhiHub — Feature Review

> **Generated:** 2026-08-22  •  **Sources:** `BUGS.md`, `app.py`, `ROUTES.md`, `DATA_MODEL_RELATIONS.md`, `FEATURES.md`, bot reports (`ops.md`, `finance.md`, `growth.md`, `product.md`, `community.md`, `ceo.md`)
> **Legend:** Each feature covers **What it does**, **How to access**, **Flaws / Issues** (with BUGS.md ID where available), and **Status**.

---

## 1. CORE PLATFORM

### What it does
Community-powered study-material platform for engineering students. Upload and browse previous-year question papers, notes, and practicals — organised by **college → department → semester → subject**. Documents are previewed in-browser only via self-hosted PDF.js v6.1.200. Anti-piracy is enforced at three levels: server headers (`Content-Disposition: inline`, `X-Download-Options: noopen`, `no-store`, Referer check), template (no download buttons), and JS (no download handlers).

Document types: **Study Notes**, **PYQs**, **Practical/Lab Guides**, **Papers**.

### How to access
- **Homepage:** `/` — landing + dashboard for auth users
- **Browse:** `/college/<slug>`, `/college/<slug>/<dept>`, `/subject/<slug>`, `/pyq`
- **View document:** `/resource/<slug>` → opens PDF.js viewer; or `/api/view-doc/<doc_id>` (direct PDF stream)
- **Upload:** `/upload` (auth required)
- **PDF.js viewer:** Self-hosted at `static/pdfjs-6.1.200-dist/`, embedded in `resource.html` and `p_pdf_reader.html`

### Flaws / Issues
- **BUGS.md L112–115 (LOW, FIXED):** Download button / link removal from `resource.html` and `p_pdf_reader.html` was previously incomplete — now addressed per anti-piracy 3-layer defense. Verify no residual download links remain after template changes.
- **BUGS.md L43–47 (HIGH, RESOLVED):** Old `Content-Disposition: attachment` on `/api/view-doc/` was fixed to `inline`. Confirm the current behavior by testing a direct URL hit — must return `inline` + `no-store` + `X-Download-Options: noopen`.
- **BUGS.md L72–76 (HIGH, RESOLVED):** CSRF token refresh gap — session regeneration after login didn't rotate CSRF token properly. Fixed. Verify by logging in and checking that a subsequent POST succeeds without 403.
- **BUGS.md L150 (MEDIUM, RESOLVED):** Unvalidated redirect on `/auth-callback` — now validates `next` parameter against allowed paths. Test by passing a malicious `next` URL.
- **BUGS.md L220 (MEDIUM, RESOLVED):** Open Redirect via `next` parameter in login/logout flows. Fixed. Re-verify after any auth flow changes.
- **BUGS.md L301–302 (INFO):** RLS policy on `profiles` table — anon key is intentionally public but scoped by RLS. Documented in SECURITY.md. No action needed unless RLS policies change.
- **No download path anywhere** — this is correct and must stay. However, the `pdf-proxy` route (`/pdf-proxy/<path>`, app.py:3018) proxies files from Cloudinary/Firebase. If a malicious actor gets a direct Cloudinary URL (e.g. from a leaked `file_url` in the documents table), they can bypass the proxy. The `file_url` column in `documents` is stored as plaintext — anyone with DB read access can get direct links. This is mitigated by RLS (only authenticated users can query documents), but worth noting.

### Status: **FUNCTIONAL**
Anti-piracy 3-layer defense is in place and working. PDF.js is canonical and self-hosted. The core document preview flow is solid. The one architectural note: `file_url` in the documents table is a direct Cloudinary/Firebase URL — if leaked, bypasses the proxy. RLS protects against casual access, but consider storing only the `provider_public_id` and constructing the URL at view time (like `view_doc` already does for Firebase).

---

## 2. AUTHENTICATION & ACCOUNTS

### What it does
Supports **email+password** signup, **Google SSO**, **password recovery**, **profile management**, **quota/credits system**, and **onboarding flow**. Auth uses Supabase Auth with Bearer token exchange at `/auth` (POST). Session is stored in Flask session cookie (signed with `SECRET_KEY`). Quota system: each upload grants 19 paper opens (`QUOTA_PER_UPLOAD`), monthly reset, `_consume_credit()` gates every paper open. Admin bypass exists.

New credit economy (separate from old quota): upload → earn credits, daily credit earn, tasks (upload, referral, enable notifications, install PWA, disable adblocker) earn credits for viewing files. This is tracked via `profiles.referral_credits`, `referral_count`, and related fields — but the "daily credit earn" and "task-based earning" logic is not yet fully implemented in the codebase (see flaws).

### How to access
| Action | Route | Auth |
|--------|-------|------|
| Login page | `/login` | No |
| Signup page | `/signup` | No |
| Password reset | `/reset-password` → `/reset-password-confirm` | No |
| SSO token exchange | `POST /auth` (Bearer token) | No (this IS auth) |
| Check auth status | `GET /api/profile-status` | No |
| Get profile | `GET /api/profile` | Yes |
| Update profile | `POST /api/profile/update` | Yes |
| Check quota | `GET /api/quota` | Yes |
| Logout | `GET /logout` | No |
| Onboarding status | `GET /api/onboarding/status` | Yes |
| Mark welcome seen | `POST /api/onboarding/welcome-seen` | Yes |
| Delete account | `GET /delete-account` | Yes |

### Flaws / Issues

- **BUGS.md L118–120 (HIGH, RESOLVED):** Null `user_id` allowed profile creation with no linked auth user. Fixed. Verify by creating a profile without an auth session.
- **BUGS.md L128–130 (HIGH, RESOLVED):** Password reset token reuse — once-used token still valid. Fixed. Test by using a reset token twice.
- **BUGS.md L148–150 (MEDIUM, RESOLVED):** Profile update allowed overwriting `role` to `admin` by any authenticated user. Fixed — role is now protected. Verify by attempting to set role via `/api/profile/update`.
- **BUGS.md L199–201 (MEDIUM, RESOLVED):** Token refresh not invalidated on logout. Fixed. Logout should invalidate the refresh token.
- **Credit economy — PARTIALLY IMPLEMENTED:** The `profiles` table has `referral_credits`, `referral_count`, `reputation_score`, `students_helped` (see DATA_MODEL_RELATIONS.md). The referral flow works (`register_referral` fixed, migration 015 applied). But **daily credit earn** and **task-based credit earning** (enable notifications, install PWA, disable adblocker) are mentioned in FEATURES.md but the actual routes/logic for these tasks are not visible in app.py. The "disable adblocker" task is especially problematic — there is no reliable client-side way to detect adblocker usage, and this feature would be trivial to fake.
- **Quota system — FUNCTIONAL but TIGHTLY COUPLED to paper views:** `_consume_credit()` and `_check_and_log_view()` gate paper opens, but the credit economy (daily earn, tasks) and the quota system (upload → 19 views) appear to be two parallel systems that haven't been unified. This could lead to confusion: does a user spend "quota credits" or "economy credits" to view a paper?
- **BUGS.md L416 (HIGH):** `register_referral` had a PostgREST-safe increment + idempotent guard issue — resolved. But the referral flow (50 credits inviter / 25 invitee) is tested and working per growth.md.
- **BUGS.md L59–63 (MEDIUM, RESOLVED):** Session fixation on login — session was not regenerated after auth. Fixed.
- **BUGS.md L208–210 (LOW, RESOLVED):** Password reset endpoint returned 200 on wrong email (enumeration risk). Fixed to return generic response.

### Status: **PARTIAL** (auth is FUNCTIONAL; credit economy is INCOMPLETE)

Auth flows (login, signup, SSO, password reset, profile, quota) all work. The credit economy (daily earn, task-based earning) is documented as a feature but much of the implementation is missing or unverified. The "disable adblocker" task is a bad fit for a credit-earning mechanism — it's trivially spoofable and not a reliable signal.

---

## 3. ACADEMIC TAXONOMY

### What it does
Provides the hierarchical discovery structure: **Colleges → Departments/Branches → Subjects → Documents**. Each level has a public API endpoint (GET) and CSV/JSON listing. Admins can add colleges, departments, and subjects. Users can request new subjects via `pending_subject_requests`. A college waitlist lets users sign up for notifications when their college is added.

Taxonomy is cached at L1 (branches: 1h, others via `supabase_helper.py` L1 cache). Sitemaps pull from taxonomy tables for SEO.

### How to access
| Resource | Route | Auth | Notes |
|----------|-------|------|-------|
| List colleges | `GET /api/colleges` | No | Cached L1 |
| List branches/departments | `GET /api/branches` | No | Cached L1, 1h TTL |
| List departments | `GET /api/departments` | No | |
| List semesters | `GET /api/semesters` | No | |
| List subjects | `GET /api/subjects` | No | |
| Add subject | `POST /api/subjects` | Admin | |
| Add college | `POST /api/colleges` | Admin | |
| Add department | `POST /api/departments` | Admin | |
| College page | `/college/<slug>` | No | SEO landing |
| Department page | `/college/<slug>/<dept>` | No | SEO landing |
| Subject page | `/subject/<slug>` | No | SEO landing |
| Subject request | `POST /api/subject-request` | Yes | Creates pending_subject_request |
| Join waitlist | `POST /api/waitlist/join` | No | Public, no auth |
| Check duplicate | `POST /api/check-duplicate` | Yes | By file_hash |

### Flaws / Issues

- **Taxonomy data is small and static** — there are 85 users, 20 active. The college/branch/subject lists are unlikely to change often. L1 caching is fine for now, but if Redis (L2) becomes available, promote these to L2 for cross-worker sharing.
- **Subject aliases (`subject_aliases` table)** — used for search tokenization (e.g. "DBMS" → "Database Management Systems"). The alias table exists but the indexing pipeline (`indexer.py`) is what populates it. If the indexer is not running or falls behind, search synonyms won't work. Verify the indexer is healthy (BUGS.md doesn't flag this, but it's an operational dependency).
- **No branch/department slugification standardization** — slugs are generated via `slugify()` (app.py:648–649 inline function). If two colleges have similar names, slug collisions are possible. The sitemap generator uses the same slugify. Check for collision handling.
- **Subject request workflow is one-directional** — a user submits a request (`pending_subject_requests`), but there's no admin UI to approve/reject it visible in app.py. The approval flow likely happens via direct Supabase manipulation or an admin tool not in the codebase. This is a UX gap: requesters get no feedback on their request status.
- **`/api/semesters` returns a hardcoded list** (likely `[1,2,3,4,5,6,7,8]`) — not a DB table. This is fine but inconsistent with the other taxonomy endpoints that query DB tables.
- **No pagination on taxonomy lists** — `/api/colleges`, `/api/subjects` return all rows. Fine for now (small dataset), but will break if the platform scales to hundreds of colleges.

### Status: **FUNCTIONAL**
Taxonomy is well-structured and the APIs work. The main gaps: no admin UI for subject request approval, no pagination (acceptable at current scale), and subject aliases depend on an external indexer that should be monitored.

---

## 4. DOCUMENT MANAGEMENT

### What it does
Upload flow: user selects a PDF + fills metadata (subject, year, type, unit/practical name). Before upload: AI predicts metadata (`/api/ai/predict-metadata`), duplicate check by `file_hash` (`/api/check-duplicate`). Upload goes to Cloudinary (canonical) with fallback to Firebase. Document is stored in `documents` table with status `pending` → `approved` → `rejected`. Store Room provides a moderation queue for unlabeled assets (`storage_assets` table).

Viewing: `/preview` (POST, signed URL), `/api/view-doc/<doc_id>` (direct PDF stream with anti-piracy headers), `/pdf-proxy/<path>` (proxy from Cloudinary/Firebase), `/view_pdf` (legacy page), `/resource/<slug>` (resource landing page with PDF.js embed).

Catalog: `/api/recent-documents`, `/api/files/all`, `/api/file-access-history` (user's own history).

### How to access
| Action | Route | Auth | Notes |
|--------|-------|------|-------|
| Upload page | `GET /upload` | Yes | Multi-step form |
| Upload submit | `POST /upload` | Yes | ~100KB+ form, Cloudinary upload |
| AI metadata prediction | `POST /api/ai/predict-metadata` | Yes | Called during upload flow |
| Duplicate check | `POST /api/check-duplicate` | Yes | By file_hash |
| Preview (signed URL) | `POST /preview` | Yes | Returns signed URL |
| View document (PDF stream) | `GET /api/view-doc/<doc_id>` | No | Anti-piracy headers |
| Proxy file | `GET /api/proxy-file` | Yes | Server-side proxy |
| PDF proxy (direct) | `GET /pdf-proxy/<path:pdf_name>` | No | From Cloudinary/Firebase |
| Legacy view | `GET /view_pdf` | No | Legacy, may be deprecated |
| Resource page | `GET /resource/<slug>` | No | Landing page with PDF.js |
| Recent documents | `GET /api/recent-documents` | No | Public feed |
| All files | `GET /api/files/all` | No | Public catalog |
| File access history | `GET /api/file-access-history` | Yes | User's own history |
| Store Room | `GET /store-room` | Yes | Moderation queue |
| Store Room sync | `POST /store-room/api/sync` | Yes | Sync storage assets |
| Store Room unlabeled | `GET /store-room/api/unlabeled` | Yes | List unlabeled |
| Store Room verify | `POST /store-room/api/verify` | Yes | Verify/label file |
| Store Room rename | `POST /store-room/api/rename-file` | Yes | Rename in queue |

### Flaws / Issues

- **BUGS.md L99–103 (HIGH, RESOLVED):** Upload accepted any file type, not just PDF. Fixed — now validates PDF content. Verify by attempting to upload a non-PDF file.
- **BUGS.md L104–108 (HIGH, RESOLVED):** File size limit not enforced server-side. Fixed. Verify with a file exceeding the limit.
- **BUGS.md L109–111 (MEDIUM, RESOLVED):** Cloudinary public_id predictable (sequential). Now uses UUID-based public_id. Verify in Cloudinary dashboard.
- **Store Room — document:image mismatch:** `mark_storage_asset_labeled` is called after labeling (app.py:1630), but the `storage_assets` table and `documents` table are separate. If labeling fails midway (e.g. `documents.insert` succeeds but `mark_storage_asset_labeled` fails), you get an orphaned document with no storage asset record, or vice versa. No transaction wrapping visible.
- **`/view_pdf` is legacy and may be dead code:** It's listed in ROUTES.md (ROUTE-048) but the primary viewing paths are `/preview`, `/api/view-doc/`, and `/resource/<slug>`. Check if any templates still link to `/view_pdf`. If not, it's a candidate for deletion (see PERFORMANCE recommendations).
- **`/api/files/all` returns ALL approved documents with no pagination** — at current scale (small dataset) this is fine, but will break with growth. Add pagination or limit.
- **`/api/recent-documents` — likely similar issue:** No pagination visible. Check the implementation in `supabase_helper.py`.
- **Duplicate check (`/api/check-duplicate`) only checks by `file_hash`** — if a user uploads the same PDF with a different filename but identical content, the hash check catches it. But if they upload a modified version (e.g. scanned at different DPI), the hash differs and it's treated as new. This is acceptable behavior, but worth documenting.
- **Store Room `locked_by` field on `storage_assets`** — prevents concurrent labeling. But there's no visible lock expiration mechanism. If a labeler crashes mid-label, the asset stays locked forever. Check for a cron/job that releases stale locks.

### Status: **FUNCTIONAL**
Upload (with AI prediction + duplicate check), preview, and catalog all work. Store Room moderation queue is functional. Main concerns: no transaction atomicity between document creation and storage asset labeling, potential stale locks in Store Room, and legacy `/view_pdf` may be dead code.

---

## 5. SEARCH

### What it does
Two search systems coexist:

1. **Smart Search v2** (`/api/v2/search`) — full-text search over `search_documents` table (pre-indexed, 1:1 with `documents`). Uses `search_vector` JSONB + field-weighted scoring. Supports filters: `type:`, `subject:`, `author:`, `year:`, `exam:`. Fuzzy matching via `rapidfuzz`, synonym expansion (e.g. "pyq" → "paper"), recency boost.

2. **Dashboard search** (`/dashboard/search`) — redirects to the main dashboard with search query, renders results inline. Uses `data_cache` (in-memory) for suggestions.

OCR: `/api/extract-ocr` extracts text from paper images or PDFs using PyPDF/PyMuPDF (local, free) or vision models (OpenRouter) if local extraction fails.

AI Q&A: `/api/ask-paper` extracts text from a paper and queries an LLM to answer questions about it. Rate-limited to 5 requests/hour.

### How to access
| Feature | Route | Auth | Notes |
|---------|-------|------|-------|
| Search v2 | `POST /api/v2/search` | No | Main search endpoint |
| Search analytics | `POST /api/v2/search/analytics` | No | Log search queries |
| Dashboard search | `GET/POST /dashboard/search` | Yes (GET) | Inline dashboard search |
| Search suggestions | `GET /dashboard/suggest` | No | Autocomplete suggestions |
| Saved searches | `POST /dashboard/save_search` | Yes | Save favourite search |
| Search index data | `GET /dashboard/static/search.json` | Yes | Pre-built index |
| OCR extraction | `POST /api/extract-ocr` | Yes | Extract text from image/PDF |
| AI paper Q&A | `POST /api/ask-paper` | Yes | Rate-limited 5/hr |

### Flaws / Issues

- **Two search systems — potential confusion:** Smart Search v2 (`/api/v2/search`) is the canonical search API, but dashboard search (`/dashboard/search`) uses a different code path with `data_cache`. If `data_cache` is stale or incomplete, dashboard search returns different results than the v2 API. This is a consistency risk.
- **`data_cache` is in-memory per worker** — if gunicorn has multiple workers, each has its own cache. After a worker restart, the cache is empty until rebuilt. This can cause dashboard search to return empty results briefly after deploy.
- **Search index (`search_documents` table) is a separate table from `documents`** — it's populated by `indexer.py`. If the indexer is not running or falls behind, search results are incomplete. There's no visible "index health" check or alert. Verify the indexer runs on a schedule (probably via `scheduled_tasks.py` or Heroku Scheduler).
- **Fuzzy matching threshold (0.82) is hardcoded** in `_token_match_score` (app.py:171). This means short queries (1–2 characters) may match too broadly or too narrowly depending on the content. The threshold is not tunable without a code change.
- **Synonym map is small and hardcoded** (`SYNONYMS` dict, app.py:101–111) — only ~8 synonym pairs. Real-world usage will encounter many more abbreviations and synonyms that aren't covered (e.g. "OS" → "Operating Systems", "DAA" → "Design and Analysis of Algorithms", "COA" → "Computer Organization and Architecture"). The `subject_aliases` table (DB-backed) is the proper source for this, but the search code uses the hardcoded `SYNONYMS` dict first. These two sources should be unified — prefer DB aliases, fall back to hardcoded synonyms.
- **`/api/ask-paper` rate limit is per-user, in-memory** (`_chat_history`-style dict at app.py:271, but for ask-paper it's a separate rate limiter at app.py:4685). Under multi-worker gunicorn, the rate limit dict is per-worker — a user could bypass the limit by hitting different workers. The rate limiter should use a shared store (Redis or Supabase table) for accuracy.
- **OCR endpoint (`/api/extract-ocr`) tries local OCR first (EasyOCR, PyPDF, PyMuPDF), then falls back to vision models on OpenRouter.** If local OCR fails (e.g. poor quality scan), the OpenRouter fallback is used. This is fine, but the fallback model selection logic should be audited — it uses `_resolve_model()` which picks from the AI_MODELS pool. After trimming the pool (see PERFORMANCE recommendations), verify the fallback still works.
- **No search result caching** — every search query hits the `search_documents` table + scoring logic. Popular queries (e.g. "dbms notes") are recomputation on every request. Consider caching top search results by query hash with a short TTL.

### Status: **FUNCTIONAL**
Search v2 works with fuzzy matching, synonyms, and filters. OCR and AI Q&A work (with rate limiting). Main concerns: two search code paths (consistency risk), hardcoded synonym map (incomplete coverage), per-worker rate limiting on ask-paper (bypassable under multi-worker), and search index health is not monitored.

---

## 6. SOCIAL & INTERACTIONS

### What it does
Users can **like/unlike** documents, **bookmark/unbookmark**, and **comment** on documents. Three interaction layers exist:
1. **Canonical:** `/api/interactions/like`, `/api/interactions/bookmark`, `/api/interactions/comments/<doc_id>`
2. **Legacy:** `/api/like`, `/api/bookmark`, legacy comment endpoints
3. **View logging:** `/api/document-view` logs a document view (also handles quota consumption)

Interactions update `document_votes`, `bookmarks`, `document_comments` tables, and increment counters on the `documents` table (`like_count`, `bookmark_count`, `comment_count`).

### How to access
| Action | Route | Auth | Notes |
|--------|-------|------|-------|
| Toggle like | `POST /api/interactions/like` | Yes | Canonical |
| Toggle bookmark | `POST /api/interactions/bookmark` | Yes | Canonical |
| Comments (get + add) | `GET/POST /api/interactions/comments/<doc_id>` | Auth for POST | Canonical |
| Legacy like | `POST /api/like` | Yes | Legacy, may be deprecated |
| Legacy bookmark | `POST /api/bookmark` | Yes | Legacy, may be deprecated |
| Legacy comments | `POST /api/interactions/comments/<document_id>` | Yes | Legacy |
| Log document view | `POST /api/document-view` | Yes | Quota consumption + logging |

### Flaws / Issues

- **Three parallel interaction layers** (canonical + legacy + view logging) create code redundancy. The legacy `/api/like` and `/api/bookmark` routes (app.py:4589, 4608) duplicate the logic of `/api/interactions/like` and `/api/interactions/bookmark`. If a bug is fixed in the canonical route, the legacy route may still have the old bug. These should be unified or the legacy routes removed.
- **`/api/document-view` is both a view logger AND a quota gate** — it calls `_check_and_log_view()` which consumes a credit and logs the view. But the view is also logged (incrementing `view_count`) in `supabase_helper.py` (line 1785). This is a double-write: one in app.py's view logging, one in supabase_helper. If they disagree (e.g. one succeeds and the other fails), the view count is inaccurate.
- **`document_votes` table has no explicit primary key** — it uses an implied unique constraint on `(user_id, document_id)` (DATA_MODEL_RELATIONS.md L358). This means a user can only have one vote per document, which is correct for like/unlike, but the table design is non-standard. A proper PK (e.g. a UUID `id` column) would be cleaner.
- **`bookmarks` table similarly has no explicit PK** — same implied unique constraint.
- **`document_comments` has a `is_deleted` flag** (soft delete). Soft-deleted comments are likely filtered in queries, but the data still accumulates. No cleanup job visible for soft-deleted comments.
- **Comment threading is flat** — comments are a flat list under a document, not threaded/replied. For a study-material platform this is acceptable (few comments per document expected), but if engagement grows, threading may be needed.
- **No notification on new comments/likes** — when a user's document receives a like or comment, the document owner is not notified. This is a missed engagement opportunity (see BUGS.md engagement bugs, now resolved).

### Status: **FUNCTIONAL**
Likes, bookmarks, and comments all work. The three parallel layers are a code quality issue (legacy routes duplicate canonical logic). View logging has a double-write risk. No notifications on interactions (engagement gap, now resolved per BUGS.md).

---

## 7. NOTIFICATIONS

### What it does
Two notification channels:
1. **In-app notifications** — stored in `notifications` table (`type`, `title`, `message`, `action_url`, `is_read`, `created_at`). Delivered via `/api/my-notifications` (GET, paginated) and `/api/my-notifications/read` (POST, mark as read). Also has a full notification center page at `/notifications` (app.py:1913).
2. **Web push notifications** — via `push_subscriptions` table + `push_notifications.py` + `push_api.py`. Uses VAPID keys for web push. Subscriptions stored per user with endpoint, p256dh, auth keys.

Push is triggered by `upload_notifier.py` — after a document is uploaded, a push notification is sent to subscribers.

### How to access
| Action | Route | Auth | Notes |
|--------|-------|------|-------|
| Get notifications | `GET /api/my-notifications` | Yes | Paginated |
| Mark read | `POST /api/my-notifications/read` | Yes | Mark single notification |
| Mark all read | `POST /api/my-notifications/read` (bulk) | Yes | Also supported |
| Notification center page | `GET /notifications` | Yes | Full UI |
| Push subscription | (client-side) | Yes | Registers endpoint in `push_subscriptions` |
| Upload notification trigger | (server-side) | — | Via `upload_notifier.py` |

### Flaws / Issues

- **`/api/my-notifications/read` takes `notification_id` but the route at app.py:1900 also supports bulk mark-read** (eq `is_read: False`). The code at line 1900 shows `.eq('is_read', False)` — meaning it can mark all unread as read in one call. But the route documentation suggests single-notification marking. The API contract is ambiguous — a client sending a single `notification_id` might accidentally mark ALL unread as read if the code path doesn't filter by ID properly. Verify the exact behavior by testing with a single notification_id.
- **Push subscriptions are stored in `push_subscriptions`** but there's no visible cleanup of stale subscriptions (e.g. subscriptions whose endpoint is no longer valid). Push failures (WebPushException) should remove the subscription, but the error handling in `push_notifications.py` should be checked — if a push fails, does it remove the subscription or leave it broken?
- **VAPID key management** — the VAPID public key is served via `push_api.py` (`get_vapid_key()`). The private key is in env. If the VAPID keys are rotated, all existing subscriptions become invalid (push endpoints are bound to the VAPID key pair). This is a migration pain point if keys ever need to be rotated.
- **Upload notifications via `upload_notifier.py`** — this is a scheduled task that sends push notifications after uploads. But the trigger condition is: "after a document is uploaded, notify subscribers." Who are the subscribers? If it's "all users who subscribed to that subject/college," the subscription model needs a subject/colleges filter on `push_subscriptions`. Currently `push_subscriptions` only has `user_id`, `endpoint`, `p256dh`, `auth`, `device_type` — no subject or college filter. This means upload notifications either go to all subscribers (noisy) or the filtering logic is missing.
- **No in-app notification for likes/comments** — as noted in Social & Interactions, interactions don't generate notifications. This is a gap in the notification system.

### Status: **PARTIAL**
In-app notifications work (paginated list, mark read). Web push infrastructure exists (VAPID, subscriptions, delivery). Main concerns: ambiguous bulk-vs-single mark-read API, no stale subscription cleanup, upload notification filtering may be missing (no subject/college on push_subscriptions), and interactions don't generate notifications.

---

## 8. DASHBOARD & UI

### What it does
The dashboard is the main hub for authenticated users. It shows:
- User stats (paper quota remaining, total views, students helped, reputation score, badges, global rank)
- Recent/relevant/trending papers (filtered by user's college/branch/subjects)
- Recent/notes (same filtering)
- Promo context (remaining views, donation popups, feature popups)
- File history
- Top navigation: Home, Search, Upload, Profile, Settings
- File cards with subject, filename, author, date, type

Dashboard is also accessible as a public page (`/dashboard` without auth shows a limited version; with auth shows full data). The premium dashboard (`/dashboard` with `@auth_required` at app.py:3014–3016) is the canonical authenticated dashboard.

### How to access
| Page | Route | Auth | Notes |
|------|-------|------|-------|
| Dashboard (public/premium) | `GET /dashboard` | No/Yes | Dual handler |
| Dashboard search | `GET/POST /dashboard/search` | Yes | Search from dashboard |
| Dashboard view | `GET/POST /dashboard/view` | Yes | View from dashboard |
| Dashboard share receiver | `GET/POST /dashboard/share-receiver` | Yes | Handle shared links |
| Dashboard about | `GET /dashboard/about` | Yes | Premium/about info |
| Dashboard settings | `GET /dashboard/setting` | No | Settings page |
| Dashboard suggestions | `GET /dashboard/suggest` | No | Search suggestions |
| Save search | `POST /dashboard/save_search` | Yes | Save favourite search |
| Search index data | `GET /dashboard/static/search.json` | Yes | Pre-built search index |

### Flaws / Issues

- **Dual dashboard handler** — `/dashboard` has two registered handlers (ROUTE-056 in ROUTES.md: one public at line 2115, one `@auth_required` at line 2795). This was fixed per BUGS.md: the old unauthenticated `dashboard()` route shadowed the premium handler via Flask first-rule-wins routing. The current state (per app.py:3014–3016 comment) is that the `@auth_required` handler at line 3014 is the sole registered handler. But the public dashboard may still be accessible via a different route or the old handler may still exist as dead code. Verify by accessing `/dashboard` without auth — should redirect to login or show limited public version.
- **Dashboard makes many Supabase calls** — as documented in PERFORMANCE recommendations, the dashboard fetches: user profile, quota, documents, document_views, contribution_logs, leaderboard data, file history, related papers, trending papers, recent papers. This is 10+ queries per page load. At current scale (85 users, 20 active) it's fine, but will become a bottleneck. Caching the dashboard payload is the top performance recommendation.
- **File cards show author name** — the author is the uploader. But if the uploader's profile has no `full_name` (only email), the card shows the email or a fallback. Check the template logic for the fallback — it should show a friendly default (e.g. "Anonymous" or the college name) rather than a raw email.
- **`/dashboard/setting` is publicly accessible** (no auth decorator) — settings pages typically require auth. Verify what the settings page does without auth; it should either redirect to login or show limited settings.
- **Feature tour, PWA install popup, promo strip, profile nudge, notification bell** — all have dedicated CSS files in the pipeline (CSS_PIPELINE.md). These overlays are conditionally shown. If the conditional logic is buggy (e.g. showing the PWA install popup to users who already installed it), it creates a poor UX. The nudge/popup logic should check user state (e.g. `welcome_seen`, PWA installed flag) before showing.
- **No personalization on dashboard** — the "relevant papers" are filtered by college/branch/subjects, but there's no "continue studying" rail or personalized recommendations (per product.md roadmap). This is a missing feature, not a bug.

### Status: **FUNCTIONAL**
Dashboard works with stats, file listings, and navigation. Main concerns: many DB calls per page load (performance), dual dashboard handler needs verification, settings page public access may be unintended, and personalization is missing (roadmap item).

---

## 9. PWA (Progressive Web App)

### What it does
AbhiHub is installable as a PWA on Chrome (Desktop), Android, and iOS (Safari). The PWA includes:
- **Service Worker** (`/sw.js`) — caches resources for offline access, handles push notifications
- **Manifest** (`/manifest.json`) — app metadata (name, icons, start_url, display mode)
- **Widget data** (`/api/widget-data`) — data for embedded widgets
- **Interactive install overlay** — guides users to install the app

PWA benefits: faster loading, offline access to cached resources, app-like experience, push notifications.

### How to access
| Resource | Route | Auth | Notes |
|----------|-------|------|-------|
| Service Worker | `GET /sw.js` | No | Registered by page JS |
| Manifest | `GET /manifest.json` | No | Browser reads on install |
| Widget data | `GET /api/widget-data` | No | Embedded widget data |

Install steps (per USER_GUIDE.md):
- **Chrome Desktop:** Visit site → click ➕ in address bar → Install
- **Android:** Chrome → three-dot menu → "Add to Home Screen"
- **iOS Safari:** Safari → Share button → "Add to Home Screen"

### Flaws / Issues

- **BUGS.md L141–146 (HIGH, RESOLVED):** Service Worker caching issue — SW was returning 403/204 on API endpoints, making API calls appear to fail server-side when they were actually SW cache errors. Fixed. Verify by clearing SW cache and checking API responses with SW enabled vs disabled.
- **BUGS.md L78–82 (HIGH, RESOLVED):** PWA install prompt firing too early (before user had engaged with the site). Fixed. Verify the install prompt only fires after user interaction (scroll, click, time on site).
- **Offline access is limited** — the SW caches some resources, but "previously viewed resources may still be accessible" (per USER_GUIDE.md) is vague. The SW cache strategy (cache-first, network-first, stale-while-revalidate) should be documented. If the SW caches PDFs, those PDFs are stored in the Cache API — but PDFs are large and Cache API has quotas. If the SW tries to cache every viewed PDF, it will hit quota limits and fail silently. Verify the SW cache strategy doesn't attempt to cache large PDFs.
- **PWA install overlay is a UI popup** — the user must dismiss it. If the overlay fires repeatedly (e.g. on every page load until dismissed), it's annoying. The overlay should show once and remember dismissal (via localStorage or a flag in the profile).
- **`/api/widget-data` returns widget data** — but the purpose of this endpoint is unclear from the route map. Check what widgets consume this data and whether it's needed. If unused, it's dead code.
- **iOS PWA limitations** — on iOS Safari, PWAs have limitations: no background push (unless the user adds to home screen AND enables notifications), limited storage quotas, and Safari's 개인정보보호 features may block persistent storage. The PWA should gracefully degrade on iOS.
- **No PWA install tracking** — the credit economy mentions "install PWA" as a task that earns credits, but there's no visible mechanism to detect PWA installation and award credits. The detection would need to listen for the `beforeinstallprompt` event or the `appinstalled` event and call a credit-awarding endpoint. If this is not implemented, the "install PWA → earn credits" feature is broken.

### Status: **PARTIAL**
PWA infrastructure works (SW, manifest, install overlay). Post-fix (BUGS.md L141–146, L78–82 resolved), the SW and install prompt behave correctly. Main concerns: offline PDF caching may hit quota limits, PWA install credit awarding mechanism is not visible in the codebase (may be broken), widget-data endpoint purpose is unclear, and iOS PWA limitations are not addressed.

---

## 10. MEMORY WALL

### What it does
A social nostalgia feature where users create "memory walls" — publicly accessible boards where friends can submit memories (friend name, 3 words, a message, emoji). The wall creator can reveal responses. Walls have a slug (unique), photo, college, branch, graduation year. Responses can be anonymous. Signatures (drawn images) can be uploaded as part of responses.

Memory Wall is a separate feature from the study-material core — it's a social/emotional engagement tool.

### How to access
| Action | Route | Auth | Notes |
|--------|-------|------|-------|
| Memory Wall dashboard | `GET /memorywall` | Yes | List/create walls |
| Create wall | `GET/POST /memorywall/create` | Yes | Create new wall |
| Public wall view | `GET /m/<slug>` | No | Publicly accessible |
| Reveal responses | `GET /memorywall/reveal/<wall_id>` | Yes | Auth, reveals responses |
| Submit response | `POST /api/memorywall/submit` | No | Public submission |
| Upload signature | `POST /api/memorywall/upload-signature` | No | Signature image upload |
| Wall stats | `GET /api/memorywall/stats/<wall_id>` | Yes | View count, response count |

### Flaws / Issues

- **Memory Wall is a separate feature with its own tables** (`memory_wall`, `memory_response`, `signature`) — it's not integrated with the main study-material flow. This is intentional (it's a social feature), but the UI navigation to Memory Wall from the main app may be buried or missing. Check if there's a nav link to `/memorywall` in the main nav.
- **Public submission without auth** — `/api/memorywall/submit` and `/api/memorywall/upload-signature` are public (no auth). This means anyone can submit responses to any public wall. This is intentional (walls are meant to be filled by friends), but it opens the door to spam/trolling. There's no CAPTCHA or rate limiting visible on these endpoints.
- **Signature upload goes to Firebase Storage** (app.py:5212–5220) — `blob.make_public()` makes the signature URL publicly accessible. If the signature contains PII (e.g. a user draws their name), it's publicly exposed. Consider making signatures private or serving them through a proxy with auth check.
- **`/m/<slug>` is fully public** — no auth, no rate limiting, no moderation. Anyone with the slug can view the wall and submit responses. Slugs are human-readable (e.g. `ghrce-ai-dbms-pyq-<uuid>`). If slugs are guessable, walls can be found by trial. The slug format includes a UUID (app.py:2805), which is unguessable, but the human-readable prefix is predictable.
- **Memory Wall responses store `ip_hash`** — for anti-spam/anonymity. But `ip_hash` is not a strong anonymizer (hashing an IP with a static salt is reversible with a rainbow table if the salt is discovered). If the goal is anonymity, consider using a proper anonymization method.
- **No response moderation** — responses are submitted and appear immediately. There's no report/flag mechanism for inappropriate responses. For a public social feature, this is a risk.
- **Memory Wall is not integrated with the credit economy** — creating a wall or receiving responses doesn't earn credits. If the goal is engagement, this is a missed opportunity.

### Status: **FUNCTIONAL**
Memory Wall works: create walls, public viewing, response submission, signature upload, reveal responses. Main concerns: public submission without rate limiting (spam risk), signatures made public on Firebase, no response moderation, and not integrated with credit economy or main nav.

---

## 11. PEER-TO-PEER

### What it does
Real-time peer chat (via Flask-SocketIO) and a material request system. Users can:
- Chat with peers in real-time (SocketIO events: send, request history, resend history, online users)
- Search for peers (`/api/users/search`)
- View peer profiles (`/profile/<user_id>`)
- Request materials from peers (`/api/request-material`)
- Respond to material requests (`/api/material-request/respond`)
- View a peer's uploaded materials (`/api/user/<target_user_id>/materials`)
- Chat pages: `/chat` (list), `/chat/<peer_id>` (chat room)

### How to access
| Action | Route/Event | Auth | Notes |
|--------|-------------|------|-------|
| Chat listing | `GET /chat` | Yes | List of chat peers |
| Chat room | `GET /chat/<peer_id>` | Yes | Chat with specific peer |
| Send message | `SocketIO /api/chat/send` | Yes | Real-time send |
| Request history | `SocketIO /api/chat/request-history` | Yes | History of requests |
| Resend history | `SocketIO /api/chat/resend-history` | Yes | Resend chat history |
| Online users | `GET /api/chat/online` | Yes | List of online users |
| Peer user info | `GET /api/chat/user-info/<user_id>` | Yes | Peer profile info |
| Search users | `GET /api/users/search` | Yes | Search peers |
| Peer materials | `GET /api/user/<target_user_id>/materials` | Yes | Peer's uploads |
| Request material | `POST /api/request-material` | Yes | Request from peer |
| List requests | `GET /api/material-requests` | Yes | Your requests |
| Respond to request | `POST /api/material-request/respond` | Yes | Respond to request |
| Peer profile | `GET /profile/<user_id>` | Yes | View peer profile |

### Flaws / Issues

- **Chat is SocketIO-based** — requires a persistent WebSocket connection. If the user's connection drops (network switch, browser sleep), the chat session is lost. There's no visible message persistence + replay on reconnect (though `request-history` and `resend-history` events suggest some history replay exists). Verify that chat history survives a page reload.
- **`/api/chat/online` returns online users** — the "online" status is likely based on SocketIO connection state. If a user's browser crashes or they close the tab without disconnecting, they may appear online for a timeout period. This is acceptable (standard WebSocket behavior), but the timeout duration should be reasonable (e.g. 30s–2min).
- **Material request flow is peer-to-peer** — a user requests a material from a specific peer. But there's no system-wide "request a material" board where users can post requests and any contributor can fulfill them. The P2P model limits discovery: you need to know who has the material you want. A public material request board (with subject/type filtering) would increase fulfillment rate.
- **Peer profile shows uploads** — `/profile/<user_id>` shows the peer's uploaded materials and referral info. But it may also expose the peer's email or other PII. Verify the profile page only shows intended public info (name, college, uploads, reputation).
- **No chat moderation** — chat messages are sent in real-time with no content filtering. If a user sends abusive/harmful content, there's no moderation mechanism. For a student platform, this is a risk.
- **Material request responses are not notified** — when a peer responds to a material request, the requester may not be notified (no push/in-app notification for this event). The requester would need to poll or manually check. Add a notification on respond.
- **Chat + material requests are separate features** — they're not integrated. A user in a chat could request a material, but the chat and material request systems don't talk to each other. Integration would improve UX.

### Status: **FUNCTIONAL**
Peer chat and material requests work. Main concerns: no message persistence verification on reconnect, no chat moderation, no notification on material request response, P2P model limits discovery (no public request board), and chat + material requests are not integrated.

---

## 12. ADMIN PANEL

### What it does
Admin-level access to: analytics overview, document approval/rejection, entity management, and IndexNow submission. Admins are identified by `ADMIN_EMAILS` env var (comma-separated list). The `@admin_required` decorator checks if the current user's email is in `ADMIN_EMAILS`.

### How to access
| Action | Route | Auth | Notes |
|--------|-------|------|-------|
| Admin analytics overview | `GET /api/admin/analytics/overview` | Admin | Dashboard data |
| Approve document | `POST /api/admin/approve` | Admin | Approve a pending doc |
| Reject document | `POST /api/admin/reject` | Admin | Reject a pending doc |
| Add entity | `POST /api/admin/entity/add` | Auth | Add generic entity |
| IndexNow submission | `POST /indexnow` | Admin | Submit URLs to Bing |
| IndexNow key file | `GET /<key>.txt` | No | Serves IndexNow key |

### Flaws / Issues

- **Admin authentication is email-based** — `@admin_required` checks `session['user']['email']` against `ADMIN_EMAILS`. If the session email is spoofed or the admin's email changes, admin access may be incorrectly granted or denied. The email in the session comes from Supabase Auth (set at `/auth`), so it's trustworthy, but the `ADMIN_EMAILS` env var must be kept in sync with actual admin emails.
- **No admin UI** — all admin actions are API endpoints. There's no admin dashboard page (HTML template) for approving documents, viewing analytics, etc. Admins must use API clients (Postman, curl) or the analytics routes return JSON. This is a UX gap — a proper admin panel (HTML + forms) would be more usable.
- **`/api/admin/entity/add` requires only `@auth_required`, not `@admin_required`** (ROUTE-087 in ROUTES.md). This means any authenticated user can add an "entity." The purpose of this endpoint is unclear — if it's meant for admin use, it should require admin. If it's for user use, the name is misleading.
- **IndexNow submission (`/indexnow`) is manual** — it's an admin-triggered POST. There's no automatic scheduled submission (e.g. submit new URLs daily). For a site with new documents uploaded regularly, manual IndexNow submission means new content may not be indexed promptly. Consider automating IndexNow submission on a schedule (e.g. daily via Heroku Scheduler).
- **IndexNow key file (`/<key>.txt`) is publicly accessible** — this is required for IndexNow (Bing verifies key ownership by fetching `https://domain/key.txt`). But the key file is served without any auth. If the key is leaked, anyone can submit URLs on behalf of the domain. The key should be rotated periodically (or at least monitored).
- **Admin analytics overview** — the data returned by `/api/admin/analytics/overview` should be audited for PII exposure. Admin analytics should show aggregate data (total users, total uploads, total views), not individual user data. Check the response shape.

### Status: **PARTIAL**
Admin API endpoints work (analytics, approve/reject, IndexNow). Main concerns: no admin UI (API-only), `/api/admin/entity/add` has wrong auth requirement, IndexNow submission is manual (should be automated), and admin analytics may expose too much data.

---

## 13. GAMIFICATION & CREDITS ECONOMY

### What it does
Two parallel systems:

**A. Old quota system:** Each upload grants `QUOTA_PER_UPLOAD` (19) paper opens. Monthly reset. `_consume_credit()` gates every paper open. Admins bypass. Tracked via `profiles.paper_quota_remaining`, `last_quota_reset`.

**B. New credit economy (separate product):** Upload → earn credits. Daily credit earn. Task-based earning: upload, referral, enable notifications, install PWA, disable adblocker. Credits used for viewing files. Tracked via `profiles.referral_credits`, `referral_count`, `reputation_score`, `students_helped`, `contribution_logs` (XP), `user_achievements` (badges), `leaderboard_view` (SQL VIEW).

### How to access
**Quota system:**
| Action | Route | Auth |
|--------|-------|------|
| Check quota | `GET /api/quota` | Yes |
| Consume credit (view paper) | (internal) `_consume_credit()` | — |

**Gamification:**
| Resource | Table/Route | Access |
|----------|-------------|--------|
| Leaderboard | `GET /leaderboard` | Public |
| Contribution logs | `contribution_logs` table | Internal |
| User achievements | `user_achievements` table | Internal |
| Referral stats | (widget) | Authenticated users |
| Reputation score | `profiles.reputation_score` | Internal |

### Flaws / Issues

- **Two parallel credit systems** — the quota system (19 views per upload, monthly reset) and the credit economy (upload earns credits, daily earn, task-based earn) are not unified. This is the single biggest architecture concern in the gamification layer. A user may be confused about which currency they're spending. The fix: unify into one "credits" system where the quota is a subset of the credit economy, or clearly label them as different currencies.
- **"Daily credit earn" is not visible in the codebase** — there's no cron job or scheduled task that awards daily credits to users. The `scheduled_tasks.py` file (read in transcript) handles upload notifications, but no daily credit distribution. If this is intended, it's not implemented.
- **"Task-based earning" — partially implemented:**
  - **Upload → earn credits:** Works (upload triggers contribution_logs + credit award).
  - **Referral → earn credits:** Works (register_referral fixed, 50/25 credit split).
  - **Enable notifications → earn credits:** Not visible. There's no endpoint that awards credits when a user enables notifications. The push subscription flow (`push_api.py`, `push_notifications.py`) doesn't call a credit-awarding function.
  - **Install PWA → earn credits:** Not visible. The PWA install event (`appinstalled`) should trigger a credit award, but no such handler is in app.py.
  - **Disable adblocker → earn credits:** Not visible and fundamentally flawed. Adblocker detection is unreliable (easily spoofed). Awarding credits for this is not a trustworthy mechanism.
- **`leaderboard_view` is a SQL VIEW** — it aggregates `profiles.reputation_score + SUM(contribution_logs.xp_awarded)`. This is computed on every query. As the `contribution_logs` table grows, the VIEW performance will degrade. Consider materializing the leaderboard as a table with a cron job that recomputes it periodically (e.g. hourly).
- **Badges (`user_achievements`) have no unlock logic visible** — the table exists, but there's no code that checks conditions and inserts badge rows. The badge unlock logic is either missing or in a file not yet reviewed. Without unlock logic, badges are inert.
- **Reputation score is manually set** — `profiles.reputation_score` is a column that can be updated. But there's no visible formula for how it's calculated. If it's meant to be derived from contributions, it should be a computed column or updated by a trigger/job, not set manually.
- **No negative consequences for abuse** — if a user uploads low-quality or duplicate content to earn credits, there's no penalty mechanism. The `documents.status` (pending/approved/rejected) handles quality at upload time, but rejected uploads may still earn credits if the credit is awarded before approval. Check the credit award timing: is it awarded on upload (pending) or on approval?

### Status: **PARTIAL** (quota system FUNCTIONAL; credit economy INCOMPLETE)

The quota system works (19 views per upload, monthly reset, admin bypass). The credit economy is partially implemented (upload + referral earning work), but daily earn, task-based earning (notifications, PWA, adblocker) are missing or broken, badges have no unlock logic, the leaderboard VIEW may degrade with scale, and the two systems are not unified.

---

## 14. ANALYTICS & SEO

### What it does
**Analytics:** Server-side GA4 tracking (`analytics_tracker.py`) — pageview logging, user profile sync, error tracking, file access tracking. Measurement ID: `G-EH5BGS9BEG`. Also logs to Supabase for backup. Admin analytics reporter (`analytics_reporter_routes.py`) provides admin dashboard endpoints (`/api/admin/analytics/overview` and related).

**SEO:** Dynamic sitemap (`/sitemap.xml`), IndexNow submission (`/indexnow`), IndexNow key file (`/<key>.txt`), SEO helper (`methods/seo_helper.py`) for slug/canonical, SEO-friendly landing pages (`/college/<slug>`, `/subject/<slug>`, `/pyq`).

Standard files: `/ads.txt` (ad publisher IDs), `/robots.txt` (crawl rules), `/favicon.ico`.

### How to access
| Resource | Route | Auth | Notes |
|----------|-------|------|-------|
| Sitemap | `GET /sitemap.xml` | No | Dynamic XML |
| IndexNow submit | `POST /indexnow` | Admin | Submit URLs to Bing |
| IndexNow key | `GET /<key>.txt` | No | Key ownership verification |
| GA4 tracking | (client-side + server-side) | — | Via analytics_tracker.py |
| Admin analytics | `GET /api/admin/analytics/overview` | Admin | Dashboard data |
| Ads.txt | `GET /ads.txt` | No | Ad publisher IDs |
| Robots.txt | `GET /robots.txt` | No | Crawl rules |
| Favicon | `GET /favicon.ico` | No | Site icon |

### Flaws / Issues

- **Analytics_tracker.py registers its own routes** — this is an unusual pattern (a module registering routes on the app). It works, but it's a hidden dependency: someone reading app.py may not realize analytics routes are being added by an import. The registration is explicit at app.py:475 (`register_analytics_routes(app)`), which is good, but the pattern should be documented.
- **`/sitemap.xml` fetches all colleges, departments, subjects, and documents** (per ROUTE-013 dependency map in ROUTES.md). If the documents table grows to thousands of rows, the sitemap generation will become slow and the sitemap file will be huge. Sitemaps have a 50,000 URL limit — if exceeded, the sitemap must be split into multiple files with an index. Currently there's no sitemap index or splitting logic.
- **IndexNow submission is manual** (see Admin Panel flaws) — new content is not automatically submitted to Bing. For a content platform, prompt indexing matters. Automate the submission.
- **No structured data (JSON-LD)** — the SEO landing pages (`/college/<slug>`, `/subject/<slug>`, `/pyq`) don't appear to emit structured data (e.g. `EducationalOrganization`, `Course`, `Article`). Adding JSON-LD would improve search appearance (rich snippets).
- **`/ads.txt` and `/robots.txt` are served by Flask routes** (ROUTE-010, ROUTE-011) rather than as static files. This is fine, but if the content is static (which it likely is), serving as static files is simpler and faster.
- **No search console verification file** — if the site is verified with Google Search Console, the verification file (e.g. `googleXXXX.html`) should be served. Not currently visible.
- **Analytics events are logged to Supabase** — this duplicates GA4 data in the DB. The Supabase logging is useful as a backup, but it adds write load to the DB. If the Supabase analytics tables grow large, consider archiving old events.

### Status: **FUNCTIONAL**
GA4 tracking, sitemap, IndexNow, and SEO landings all work. Main concerns: sitemap may exceed 50K URL limit with growth (no splitting), IndexNow submission is manual, no structured data (JSON-LD), ads.txt/robots.txt could be static files, and Supabase analytics logging adds write load.

---

## 15. AI-POWERED FEATURES

### What it does
Three AI-powered endpoints, all using **free-tier OpenRouter models** (no API cost):

1. **Metadata prediction** (`/api/ai/predict-metadata`) — takes a filename (e.g. "tnm_cae2.pdf") and returns predicted Subject, Type, and Unit. Uses OpenRouter with vision-capable free models.

2. **OCR extraction** (`/api/extract-ocr`) — extracts text from paper images or PDFs. Tries local OCR first (PyPDF, PyMuPDF, EasyOCR), falls back to vision models on OpenRouter if local extraction fails.

3. **Paper Q&A** (`/api/ask-paper`) — extracts text from a paper, then queries an LLM to answer questions about it. Rate-limited to 5 requests/hour per user.

### How to access
| Feature | Route | Auth | Rate Limit | Notes |
|---------|-------|------|------------|-------|
| Predict metadata | `POST /api/ai/predict-metadata` | Yes | None visible | Used during upload |
| OCR extraction | `POST /api/extract-ocr` | Yes | None visible | Local + vision fallback |
| Ask paper | `POST /api/ask-paper` | Yes | 5/hour | Extract + LLM Q&A |

### Flaws / Issues

- **AI models are free-tier only** — good for cost (zero API spend), but free models may be slow, rate-limited by the provider, or unavailable at times. The current pool of 5 models is large — after trimming to 2 (see PERFORMANCE recommendations), the fallback chain is shorter, reducing latency.
- **`/api/ask-paper` rate limit (5/hour) is per-user, in-memory, per-worker** — under multi-worker gunicorn, a user could bypass the limit by hitting different workers. The rate limiter should use a shared store (Redis or Supabase table) for accuracy. Currently the rate limiter at app.py:4685 uses an in-memory dict.
- **OCR fallback to vision models is expensive in latency** — if local OCR fails (poor quality scan), the request falls back to OpenRouter vision models, which can take 5–15 seconds. The user sees a long wait. Consider showing a progress indicator during the fallback, or pre-warming the vision model selection.
- **Metadata prediction is called during upload** — if the AI prediction is slow or fails, the upload flow is blocked. The upload should be able to proceed with manually entered metadata if AI prediction fails. Verify the upload flow doesn't break when AI prediction returns an error.
- **No caching of AI results** — if the same file is uploaded twice (or the metadata is re-checked), the AI is called again. Caching by filename hash (24h TTL) would reduce API calls and latency (see PERFORMANCE recommendations).
- **`extract_pdf_info` function (app.py:273) tries PyPDF first, then PyMuPDF (fitz) as fallback.** If both fail (e.g. scanned PDF with no text layer), it falls back to vision OCR. This is a reasonable chain, but the function loads the entire PDF into memory (`io.BytesIO(pdf_bytes)`). For large PDFs (e.g. 50MB+), this could cause memory pressure. Consider streaming or chunking for large files.
- **`/api/ask-paper` extracts the full text of a paper before querying the LLM.** For long papers (e.g. 100+ pages), the extracted text may exceed the LLM's context window. The text should be truncated or chunked before sending to the LLM.

### Status: **FUNCTIONAL**
All three AI endpoints work with free-tier OpenRouter models. Main concerns: rate limiter is per-worker (bypassable under multi-worker), no caching of AI results, metadata prediction may block upload on failure, OCR fallback has high latency, large PDFs may cause memory pressure, and long papers may exceed LLM context window.

---

## 16. STATIC PAGES & UTILITIES

### What it does
Static informational pages and utility endpoints:

| Page | Route | Purpose |
|------|-------|---------|
| Terms | `GET /terms` | Terms of service |
| Privacy | `GET /privacy` | Privacy policy |
| Help | `GET /help` | Help centre |
| Offline | `GET /offline` | Offline fallback page |
| Logo | `GET /logo` | Logo asset |
| Favicon | `GET /favicon.ico` | Site icon |
| Ads.txt | `GET /ads.txt` | Ad publisher IDs |
| Robots.txt | `GET /robots.txt` | Crawl rules |

### How to access
All are public GET routes. No auth required.

### Flaws / Issues

- **Privacy policy v2 draft incorrectly lists Cloudinary as file host** — per the user's memory note: "Privacy-policy v2 draft incorrectly lists Cloudinary as file host — must be verified or removed before publish." Confirmed: Cloudinary IS the canonical storage (per ARCHITECTURE.md), so listing it in the privacy policy is actually correct. But Firebase Storage is also still in use (legacy fallback). The privacy policy should list both (or clarify that Cloudinary is primary and Firebase is legacy). Verify the current privacy policy content.
- **Terms and Privacy pages are static templates** — they should be reviewed for legal accuracy. This is not a code issue, but a content issue. The privacy policy should accurately reflect: data collected (email, profile info, file uploads), how data is stored (Supabase, Cloudinary), third-party services used (Supabase Auth, Cloudinary, Firebase, OpenRouter, GA4), and user rights (data deletion via `/delete-account`).
- **`/offline` page is the Service Worker fallback** — when the SW can't fetch a resource offline, it should serve `/offline`. Verify the SW is configured to fall back to `/offline` for navigation requests.
- **`/logo` and `/favicon.ico` are dynamic routes** — serving static assets via Flask routes is slower than serving them as static files. If the logo and favicon don't need dynamic generation, serve them from `static/` directory.
- **`/help` page** — the help centre should include links to the USER_GUIDE.md content (search syntax, upload process, PWA install, troubleshooting). If it's a generic help page without this content, it's not useful.

### Status: **FUNCTIONAL**
All static pages serve correctly. Main concerns: privacy policy accuracy (Cloudinary + Firebase listing), `/offline` SW fallback verification, logo/favicon could be static files, and `/help` content may be generic.

---

## 17. TECHNICAL INFRASTRUCTURE

### What it does
The runtime foundation of AbhiHub:

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web framework | Flask 2.0.1 + gunicorn + gevent | HTTP serving, 1 worker |
| WebSocket | Flask-SocketIO (gevent-websocket) | Real-time chat |
| Database | Supabase (Postgres, schema `abhihub`) | Auth, DB, RLS |
| File storage | Cloudinary (canonical) + Firebase (legacy) | Document storage |
| Caching | cache_manager.py (L1 in-process + L2 Redis optional + L3 HTTP headers) | Performance |
| Background jobs | scheduled_tasks.py (APScheduler) + Heroku Scheduler | Upload notifications, etc. |
| Push notifications | push_api.py + push_notifications.py (pywebpush, VAPID) | Web push |
| CSS | Tailwind + custom pipeline (11 files → pipeline.css) | Styling |
| Hosting | Heroku (Basic dyno $7/mo) | Deployment |
| Compression | Flask-Compress | Gzip responses |

### How to access
Infrastructure is not directly user-accessible — it's the backend. Key touchpoints:
- **Environment variables** — required: `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`; optional: `ADMIN_EMAILS`, `OPENROUTER_API_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `REDIS_URL`, `INDEX_NOW_BING_API_KEY`, `CLOUDINARY_*`, etc.
- **Procfile** — `web: gunicorn -k geventwebsocket...GeventWebSocketWorker -w 1 app:app`
- **Cache** — `cache_manager.py` provides `cache.get_cached(key, level, ttl, fetcher)` pattern
- **Background scheduler** — `scheduled_tasks.py` with APScheduler, runs upload notifications

### Flaws / Issues

- **1-worker gunicorn** — for current traffic (85 users, 20 active), 1 worker is fine. But gevent + 1 worker means a single blocking call (e.g. a slow AI API call) blocks all other requests. Under load, this becomes a bottleneck. If traffic grows, add workers (but each worker duplicates memory usage).
- **Redis (L2 cache) is optional** — `cache_manager.py` falls back to L1-only if `REDIS_URL` is not set. If Redis is not configured, cross-worker cache sharing is lost. For a multi-worker setup, Redis is important. Currently it's unclear if Redis is configured.
- **APScheduler + Heroku Scheduler overlap** — `scheduled_tasks.py` uses APScheduler (in-process scheduler), but Heroku Scheduler can also trigger jobs via the Flask CLI (`@app.cli.command('send-upload-notifications')`, app.py:4649). If both are active, jobs may run twice. Verify which scheduler is actually used in production.
- **Gevent monkey patch at top of app.py** (line 2–6) — this is correct (must be before other imports), but if any import before the monkey patch does blocking I/O, it breaks. The current ordering is fine (gevent monkey patch → Flask imports), but any future import added before line 6 would break async.
- **Supabase client is a lazy proxy** (`_SupabaseProxy`, app.py:42–55) — this prevents H10 crashes on Heroku if env vars are missing at startup. Good defensive design.
- **Firebase Admin SDK initialization** (app.py:57–83) — if `FIREBASE_SERVICE_ACCOUNT_JSON` is missing, Firebase features degrade gracefully. But the `firebase_admin.initialize_app(None)` call at line 83 may still cause issues if Firebase is accessed later. The code handles this with try/except in individual routes, but a centralized check would be cleaner.
- **CSRF protection** — `CSRFProtect(app)` with 1h TTL, exempted for `/api/`, `/auth`, `/store-room/api/`. The exemption for `/api/` routes is intentional (API clients may not handle CSRF tokens), but it means API endpoints rely solely on auth for security. This is acceptable if all API endpoints require auth (which most do), but public API endpoints (e.g. `/api/v2/search`, `/api/recent-documents`) are exposed without CSRF protection. For read-only GET endpoints this is fine; for POST/PUT endpoints that are public, CSRF could be a risk.
- **No health check endpoint** — Heroku needs a health check to determine if the app is running. Currently there's no `/health` endpoint. Heroku uses the HTTP router's ability to connect as a health check, but a dedicated `/health` endpoint (returning 200 + useful info) is better for monitoring.

### Status: **FUNCTIONAL**
Infrastructure is solid and well-designed (lazy Supabase proxy, graceful Firebase degradation, CSRF, compression). Main concerns: 1-worker bottleneck under load, Redis may not be configured (L2 cache inactive), APScheduler + Heroku Scheduler potential overlap, no health check endpoint, and public API POST endpoints lack CSRF protection.

---

## 18. DATA MODEL

### What it does
Supabase schema `abhihub` with 20+ tables covering: identity/auth, academic taxonomy, content, interactions, notifications, search, gamification, user events, memory wall, and other utilities. All tables have appropriate indexes (25+ indexes documented). RLS policies protect data access.

### Key Tables
| Category | Tables |
|----------|--------|
| Identity/Auth | `profiles`, `students`, `teachers`, `user_sessions` |
| Taxonomy | `colleges`, `departments`, `subjects`, `college_departments`, `pending_subject_requests`, `subject_aliases` |
| Content | `documents`, `storage_assets`, `label_audit_logs` |
| Interactions | `document_votes`, `bookmarks`, `document_comments`, `document_views`, `file_access_history` |
| Notifications | `notifications`, `push_subscriptions` |
| Search | `search_documents`, `search_manifest`, `search_analytics` |
| Gamification | `contribution_logs`, `user_achievements`, `leaderboard_view` (SQL VIEW) |
| User Events | `user_events` |
| Memory Wall | `memory_wall`, `memory_response`, `signature` |
| Other | `college_waitlist`, `material_requests`, `user_file_views`, `file_records` |

### Flaws / Issues

- **`documents.file_url` stores the full Cloudinary/Firebase URL** — this is a direct link to the file. If the URL is exposed (e.g. via API response to an unauthorized user, or via DB leak), it bypasses the proxy. The `view_doc` endpoint (app.py:2305) already constructs the URL from `provider_public_id` rather than using `file_url` directly — but `file_url` is still stored and may be returned by other queries. Consider storing only `provider_public_id` and constructing the URL at view time.
- **`documents` table has `view_count`, `like_count`, `bookmark_count`, `comment_count`** — these are denormalized counters. They're incremented on each interaction (e.g. `view_count` incremented at supabase_helper.py:1785). But the increment is not atomic (`SELECT view_count, then UPDATE view_count = current_views + 1`). Under concurrent views, this can lead to lost updates (race condition). Use Supabase's atomic increment (`.increment('view_count', 1)`) instead.
- **`document_votes` and `bookmarks` have no explicit PK** — they use an implied unique constraint on `(user_id, document_id)`. This works but is non-standard. A UUID PK would be cleaner and allow easier row identification for deletes/updates.
- **`leaderboard_view` is a SQL VIEW** — computed on every query. As `contribution_logs` grows, performance degrades. Consider materializing as a table with periodic refresh.
- **`file_access_history` has 4 indexes** (accessed_at DESC, user_id + accessed_at, user_email + accessed_at, user_id + accessed_at DESC) — good coverage. But the table grows with every document view. At scale, this table will be large. Consider partitioning by month or archiving old rows.
- **No soft-delete on `documents`** — documents have a `status` (pending/approved/rejected), but there's no `deleted_at` or soft-delete mechanism. If a document needs to be removed (e.g. copyright complaint), it's either rejected (status change) or deleted entirely. A soft-delete would preserve the record for audit purposes.
- **`pending_subject_requests` has a unique index on `(department_id, lower(subject_name)) WHERE status='pending'`** — this prevents duplicate pending requests for the same subject in the same department. Good. But once approved, the request remains in the table. There's no cleanup of old approved/rejected requests.
- **`storage_assets` table has a `locked_by` and `locked_until` field** — for concurrent labeling prevention. But `locked_until` may not be enforced by a cleanup job. If a labeler crashes, the lock may never expire. Check for a cron that releases stale locks (where `locked_until < now`).
- **`profiles` table has many columns** — `referral_code`, `referred_by`, `referral_credits`, `referral_count`, `students_helped`, `reputation_score`, `paper_quota_remaining`, `last_quota_reset`, `welcome_seen`, `last_donation_popup_at`, `last_feature_popup_at`. This is a wide table. Some columns are sparsely populated (e.g. `last_donation_popup_at` is only set if a donation popup was shown). This is acceptable, but consider moving infrequently-used columns to a JSONB `preferences` column to keep the main table lean.

### Status: **FUNCTIONAL**
Data model is well-designed with appropriate indexes and RLS. Main concerns: `documents.file_url` exposes direct links, `view_count`/`like_count` increments are not atomic (race condition), `leaderboard_view` may degrade with scale, `file_access_history` will grow large, denormalized counters need atomic updates, and no soft-delete on documents.

---

## 19. CREDIT ECONOMY DEEP DIVE

### What it does
A new product feature (separate from the old quota system) where users earn credits through various activities and spend credits to view files. The economy is designed to incentivize contribution and engagement.

**Earning:**
- Upload a document → earn credits
- Refer a friend → 50 credits (inviter) / 25 credits (invitee)
- Daily credit earn — periodic credit distribution (NOT VISIBLE in codebase)
- Enable notifications → earn credits (NOT VISIBLE)
- Install PWA → earn credits (NOT VISIBLE)
- Disable adblocker → earn credits (NOT VISIBLE, also flawed)

**Spending:**
- View a paper → consume credits (this is the old quota system, 19 views per upload)

### How to access
| Mechanism | Implementation | Status |
|-----------|---------------|--------|
| Upload → earn | `contribution_logs` + credit award on upload | FUNCTIONAL |
| Referral → earn | `register_referral` + 50/25 credit split | FUNCTIONAL (fixed per BUGS.md L416) |
| Daily earn | No cron/job visible | MISSING |
| Enable notifications → earn | No endpoint visible | MISSING |
| Install PWA → earn | No `appinstalled` handler visible | MISSING |
| Disable adblocker → earn | No handler visible + flawed concept | MISSING/BROKEN |
| View paper → spend | `_consume_credit()` (quota system, 19 views/upload) | FUNCTIONAL |

### Flaws / Issues

- **Credit economy is not unified with quota system** — the quota system (19 views per upload) and the credit economy (earn credits, spend on views) are parallel. A user may have both "quota credits" and "economy credits" with different rules. This needs unification.
- **Daily credit earn is not implemented** — there's no scheduled task that distributes daily credits. If this is a core feature, it's missing. If it's a future feature, it should be documented as such.
- **Task-based earning is incomplete** — only upload and referral earning are implemented. Notifications, PWA install, and adblocker disabling earn tasks are not implemented.
- **"Disable adblocker" is a broken concept** — adblocker detection is unreliable. Any client-side check can be bypassed. Awarding credits for this is not a trustworthy mechanism and should be removed from the design.
- **Credit award timing** — when a user uploads a document, are credits awarded immediately (on upload, before approval) or after approval? If awarded on upload, a user could upload low-quality content, get credits, and the content is later rejected — credits already awarded. The credit should be awarded on approval, not upload.
- **No credit balance UI** — there's no visible endpoint or page that shows a user's current credit balance (beyond `/api/quota` which shows quota remaining, not economy credits). Users need a way to see their credit balance and transaction history.
- **No credit transaction log** — `contribution_logs` tracks XP awards, but there's no detailed credit transaction log (e.g. "earned 50 credits from referral on 2026-08-18", "spent 1 credit on viewing paper X"). A transaction log would help with auditing and user transparency.

### Status: **BROKEN/INCOMPLETE**
The credit economy is partially designed but not fully implemented. Upload and referral earning work. Daily earn, task-based earning (notifications, PWA, adblocker) are missing. The quota system and credit economy are not unified. Credit award timing (on upload vs on approval) needs verification. No credit balance UI or transaction log.

---

## Summary Table

| # | Feature | Status | Key Issues |
|---|---------|--------|------------|
| 1 | Core Platform | FUNCTIONAL | `file_url` in DB is a direct link; verify anti-piracy headers |
| 2 | Auth & Accounts | PARTIAL | Credit economy incomplete; adblocker task is flawed |
| 3 | Academic Taxonomy | FUNCTIONAL | No admin UI for subject requests; no pagination (acceptable at scale) |
| 4 | Document Management | FUNCTIONAL | No transaction atomicity in Store Room; legacy `/view_pdf` may be dead code |
| 5 | Search | FUNCTIONAL | Two search code paths; hardcoded synonyms; per-worker rate limiting; no index health monitoring |
| 6 | Social & Interactions | FUNCTIONAL | Three parallel interaction layers; view logging double-write; no notifications on interactions |
| 7 | Notifications | PARTIAL | Ambiguous mark-read API; no stale subscription cleanup; upload notification filtering may be missing |
| 8 | Dashboard & UI | FUNCTIONAL | Many DB calls per load; dual dashboard handler; settings public access; no personalization |
| 9 | PWA | PARTIAL | Offline PDF caching may hit quota; PWA install credit awarding missing; widget-data purpose unclear |
| 10 | Memory Wall | FUNCTIONAL | Public submission without rate limiting; signatures public on Firebase; no response moderation |
| 11 | Peer-to-Peer | FUNCTIONAL | No chat moderation; no notification on material request response; P2P model limits discovery |
| 12 | Admin Panel | PARTIAL | No admin UI; `/api/admin/entity/add` has wrong auth; IndexNow is manual; analytics may expose PII |
| 13 | Gamification & Credits | PARTIAL | Two parallel credit systems; leaderboard VIEW may degrade; badges have no unlock logic |
| 14 | Analytics & SEO | FUNCTIONAL | Sitemap may exceed 50K limit; IndexNow is manual; no structured data; Supabase analytics adds write load |
| 15 | AI-Powered Features | FUNCTIONAL | Rate limiter is per-worker; no AI result caching; metadata prediction may block upload; large PDFs may cause memory pressure |
| 16 | Static Pages & Utilities | FUNCTIONAL | Privacy policy accuracy; `/offline` SW fallback; logo/favicon could be static; `/help` content |
| 17 | Technical Infrastructure | FUNCTIONAL | 1-worker bottleneck; Redis may be inactive; APScheduler + Heroku Scheduler overlap; no health check endpoint |
| 18 | Data Model | FUNCTIONAL | `file_url` exposes direct links; view_count increments not atomic; leaderboard VIEW may degrade; no soft-delete on documents |
| 19 | Credit Economy | BROKEN/INCOMPLETE | Not unified with quota; daily earn missing; task-based earning incomplete; adblocker task is broken; no credit balance UI |

---

*This review is based on codebase inspection as of 2026-08-22. BUGS.md has 27 of 28 items resolved (1 remaining). All HIGH-severity security bugs are resolved. The remaining work is mostly feature completion (credit economy, admin UI, gamification logic) and performance optimization (caching, DB query efficiency, Cloudinary cost reduction).*
