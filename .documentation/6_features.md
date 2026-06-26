# Features Documentation — AbhiHub

## Feature Status Legend
- ✅ Built & Live
- 🔄 In Progress
- 📋 Planned

---

## 1. User Authentication & Profiles ✅

**What it does:**
Handles user registration, login, logout, password reset, and profile management. Supports student and teacher roles.

**How it works:**
- Supabase Auth for identity management
- Flask session stores `{ uid, email, name, provider }`
- `@auth_required` decorator protects all private routes
- Profile data stored in `abhihub.profiles` + `abhihub.students`/`abhihub.teachers`

**Key routes:** `/login`, `/signup`, `/account`, `/profile`, `/update-account`

**Status:** ✅ Fully built and live

---

## 2. Document Upload & Management ✅

**What it does:**
Students/teachers upload academic documents (notes, papers, practicals). Files are stored on Cloudinary and metadata in Supabase.

**How it works:**
- Upload form with subject, category, year, college, branch selection
- File encrypted before storage via `methods/encryption.py`
- Cloudinary stores the actual file (`methods/cloudinary_upload.py`)
- Document record saved in `abhihub.documents`
- Upload triggers push notification to subscribers

**Key routes:** `/upload`, `/upload-gate`

**Status:** ✅ Fully built and live

---

## 3. Document Viewer (PDF Reader) ✅

**What it does:**
In-browser PDF viewer with encryption support. Users can view documents without downloading.

**How it works:**
- `static/encrypted_pdf_viewer.js` handles AES decryption client-side
- PDF rendered using browser PDF renderer
- Access controlled by quota system

**Key routes:** `/pdf-reader`, `/view`

**Status:** ✅ Fully built and live

---

## 4. Search & Filtering ✅

**What it does:**
Search documents by title, subject, category, college, branch, year.

**How it works:**
- Pre-built search index in `static/search.json`
- Client-side search via `search-worker.js` (web worker for performance)
- Server-side filtering via Supabase queries

**Key routes:** `/search`

**Status:** ✅ Fully built and live

---

## 5. Ranking / Leaderboard ✅

**What it does:**
Ranks users based on reputation score, upload count, views, and engagement. Displays a public leaderboard.

**How it works:**
- `reputation_score` tracked in `abhihub.profiles`
- `rank_title` updated based on score thresholds (e.g. "Beginner", "Pro")
- Real-time ranking updates via Supabase
- `static/premium/rank.json` stores cached rank data

**Key routes:** `/ranking`

**Status:** ✅ Fully built and live

---

## 6. Paper Quota System ✅

**What it does:**
Limits how many papers a free-tier user can access per month (default: 19). Resets monthly.

**How it works:**
- `paper_quota_remaining` column in `abhihub.profiles`
- `last_quota_reset` tracks last reset month
- Quota checked on document access via `/api/quota`
- `access-gates.js` enforces quota on client side

**Status:** ✅ Fully built and live

---

## 7. Subscription / Study Pass ✅

**What it does:**
Premium subscription tier (`study_pass`) gives unlimited document access, removes quota limits.

**How it works:**
- `subscription_tier` in `abhihub.profiles`: `free` | `premium`
- `subscription_expires_at` tracks expiry
- `static/css/study-pass.css` handles premium UI
- Access gates check subscription before quota

**Status:** ✅ Fully built and live

---

## 8. Bookmarks & Interactions ✅

**What it does:**
Users can like, bookmark, and comment on documents. Counts are tracked in real-time.

**How it works:**
- `abhihub.bookmarks` — user ↔ document
- `abhihub.document_votes` — upvote/downvote
- `abhihub.document_comments` — comments (soft delete)
- `view_count`, `like_count`, `bookmark_count` on `documents` table
- API: `POST /api/interactions/like`, `POST /api/interactions/bookmark`

**Status:** ✅ Fully built and live

---

## 9. Push Notifications ✅

**What it does:**
Web push notifications for new uploads, announcements, and engagement events.

**How it works:**
- VAPID keys via `generate_vapid.py`
- `pywebpush` library for sending
- Subscriptions stored in `abhihub.push_subscriptions`
- `static/js/push-notifications.js` handles client subscription
- Admin panel to send manual notifications

**Status:** ✅ Fully built and live

---

## 10. Admin Dashboard ✅

**What it does:**
Admin-only panel for user management, document moderation, analytics, and push notifications.

**How it works:**
- `@admin_required` decorator (email-based check)
- Document verification (approve/reject) updates `documents.status`
- Security audit logs viewable
- Notification sending interface

**Key routes:** `/admin`, `/admin/notifications`

**Status:** ✅ Fully built and live

---

## 11. Know Me / MemoryWall ✅

**What it does:**
Students create a public "MemoryWall" page. Friends visit without login, submit 3 words describing the creator, draw a signature, and leave a memory. Creator sees a word cloud + signature composite.

**How it works:**
- 1 wall per user, unique slug-based URL (`/m/<slug>`)
- Word cloud generated with `wordcloud` + `Pillow`
- Signature composite built with `Pillow`
- Signatures stored in Firebase Storage
- Rate limited: 5 submissions per IP per hour (SHA256 hash)
- Honeypot spam protection
- GA4 tracking

**Key routes:** `/memorywall`, `/memorywall/create`, `/m/<slug>`, `/memorywall/reveal/<id>`

**Phase 1 Status:** ✅ MVP complete

**Roadmap:**
- Phase 2 📋: QR codes, Instagram story card, email notifications on milestones, wall expiry
- Phase 3 📋: AI personality summary (GPT/Gemini)
- Phase 4 📋: PDF memory book, poster generator
- Phase 5 📋: Multiple walls, templates, batch sharing

---

## 12. Store Room ✅

**What it does:**
Personal file storage area where users can organize and label their uploaded/accessed files.

**Key routes:** `/store-room`

**Status:** ✅ Fully built and live

---

## 13. File Access History ✅

**What it does:**
Tracks which files a user has previously accessed. Shows a "previously accessed" list.

**How it works:**
- `public.file_access_history` table
- `static/js/file-history-tracker.js` sends access events
- `static/js/previously-accessed-files.js` renders history panel

**Status:** ✅ Fully built and live

---

## 14. Analytics (GA4) ✅

**What it does:**
Tracks user behavior — file views, uploads, shares, MemoryWall events, search queries.

**How it works:**
- GA4 ID: `G-EH5BGS9BEG`
- `window.AbhiHubTracking` object in `google_tag.html`
- `analytics-helper.js` for deduplication and batching
- `data/analytics.py` for server-side analytics

**Status:** ✅ Fully built and live

---

## 15. Promo / Notification System ✅

**What it does:**
Shows promotional cards and feature announcements to users in-app.

**How it works:**
- `includes/promo_card.html` included in `p_struct.html`
- `overlay-manager.js` handles show/hide logic
- Admin controls promo content

**Status:** ✅ Fully built and live

---

## 16. PWA (Progressive Web App) ✅

**What it does:**
AbhiHub works as an installable app on mobile and desktop. Supports offline mode.

**How it works:**
- `static/manifest.json` — app metadata
- `static/sw.js` — service worker for caching
- `pwa-install.js` + `pwa-install.css` — install prompt
- `templates/offline.html` — offline fallback

**Status:** ✅ Fully built and live

---

## 17. Referral System ✅

**What it does:**
Users get a unique referral code. Referred users are tracked for rewards/reputation.

**How it works:**
- `referral_code` (unique) and `referred_by` in `abhihub.profiles`
- Referral code generated on signup

**Status:** ✅ Built (rewards logic may be partial)

---

## 18. College / Department Onboarding ✅

**What it does:**
Users select their college, branch, and year during signup/profile setup. Used to personalize content.

**How it works:**
- `data/colleges.py` loads college list
- Stored in `abhihub.profiles.college_id` + `department_id`
- `students.pursuing_year`, `students.year_of_joining`

**Status:** ✅ Fully built and live
