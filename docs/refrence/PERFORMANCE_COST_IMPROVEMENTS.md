# AbhiHub — Performance & Cost Improvement Recommendations

> **Generated:** 2026-08-22  •  **Based on:** `app.py`, `ARCHITECTURE.md`, `cache_manager.py`, `CSS_PIPELINE.md`, BUGS.md, ops/finance bot reports, Heroku pricing data
> **Goal:** reduce runtime cost, cut latency, shrink bundle, and eliminate waste — without breaking user-facing features

---

## 1. Summary of Current Cost Structure

| Layer | Current | Cost Driver | Notes |
|-------|---------|-------------|-------|
| **Heroku web dyno** | 1× Basic ($7/mo) or Standard-1X ($25/mo) | Always-on compute | Gevent + gunicorn, 1 worker |
| **Heroku scheduler / worker** | Heroku Scheduler add-on (free/cheap) or cron dyno | Background jobs: push notifications, IndexNow | |
| **Supabase** | Free tier (or Pro if over) | DB storage, RLS, Auth, API calls; billed by API calls and storage | ~30 tables, growing document count |
| **Cloudinary** | Pay-as-you-go | Storage + transformations; each upload and view costs | **Canonical storage** — biggest variable cost |
| **Firebase Storage** | Free/cheap | Legacy fallback; signature uploads | |
| **OpenRouter AI** | Free-tier models only | `/api/ai/predict-metadata`, `/api/extract-ocr`, `/api/ask-paper` | 5 free models in pool; vision models used for OCR |
| **Firebase Admin SDK** | Free | Push notification VAPID delivery | |
| **Flask-SocketIO** | Included in dyno | Real-time peer chat | Gevent-websocket worker |

### Estimated Monthly Baseline (conservative)

| Item | Est. Cost |
|------|-----------|
| Heroku Basic dyno (1×) | $7/mo |
| Supabase free tier | $0 (watch API call growth) |
| Cloudinary (moderate usage) | $0–$89/mo (depends on uploads + transformations) |
| OpenRouter free models | $0 |
| Heroku Scheduler | $0 (free tier) |
| **Total** | **~$7–96/mo** (Cloudinary is the swing factor) |

> The biggest controllable costs are **Cloudinary transformations on every view** and **unnecessary Supabase API calls** from missing/expired cache.

---

## 2. Performance & Cost Recommendations — Ranked by Impact

### Tier 1 — High Impact, Low Effort (Do First)

#### 2.1 Eliminate Redundant Supabase Calls with Aggressive Caching

**Current state:**
- `cache_manager.py` provides L1/L2/L3 but usage is inconsistent across routes.
- `get_all_colleges()`, `get_all_branches()`, `get_all_departments()`, `get_all_subjects()` are cached in `supabase_helper.py` (L1 `_cache_get`/`_cache_set`), but many dashboard queries hit the DB on every page load.
- The dashboard (`/dashboard`, ~line 3014) fetches: user profile, quota, documents, `document_views`, `contribution_logs`, leaderboard data, file history, related papers, trending papers, recent papers — **many separate queries**.

**What to do:**

1. **Cache the entire dashboard payload** — instead of 10+ individual Supabase calls per page load, build a single cached dashboard JSON keyed by `user_id` with a short TTL (e.g. 2–5 minutes). This turns N Supabase calls into 1 cache hit for repeat views.

2. **L2 (Redis) for shared taxonomy data** — if Redis is available (`REDIS_URL` env), promote `all_colleges`, `all_branches`, `all_departments`, `all_subjects` to L2 with a 1-hour TTL. Currently these are L1 only, meaning each gunicorn worker rediscovers them after worker restart.

3. **Cache `get_leaderboard_data`** — currently cached at L1 for 10 min (per `app.py:2499`). Promote to L2 since the leaderboard is read-heavy and shared across all viewers.

4. **Cache search suggestions** (`/dashboard/suggest`, ~line 3531) — already reads from `data_cache` in-memory, but that's per-worker. Move to L2 with a 5-minute TTL.

**Expected impact:**
- **Supabase API call reduction: 40–60%** on dashboard and taxonomy pages
- **Latency reduction:** dashboard page goes from ~200–500ms (multiple round-trips) to ~50ms (cache hit)
- **Supabase cost:** if on Pro tier, API calls are billed — fewer calls = lower bill

---

#### 2.2 Review Cloudinary Transformation Usage on Every Document View

**Current state:**
- Every PDF view through `/api/view-doc/<doc_id>` or `/pdf-proxy/<path>` fetches from Cloudinary, potentially triggering a transformation (resize, format conversion) each time.
- Cloudinary charges per transformation. If the same PDF is viewed 100 times, that's 100 transformations.

**What to do:**

1. **Use direct delivery URLs for frequently viewed PDFs** — instead of proxying through the app with transformation parameters each time, store the original `file_url` and serve it via `/pdf-proxy/` with **no transformation params** when the user just needs to view. Only apply transformations for thumbnails/previews.

2. **Add L3 (browser) caching for PDF responses** — currently `/api/view-doc/` and `/pdf-proxy/` set `no-store` headers (anti-piracy). This is correct for security, but consider: the **PDF.js worker** can cache rendered pages in the browser's IndexedDB. Ensure PDF.js's `disableAutoFetch` and `cMapUrl` are configured to minimize re-fetching.

3. **Pre-generate thumbnails, not on-demand** — if the dashboard shows paper thumbnails, generate them once at upload time (Cloudinary transformation stored as a separate `public_id`), then serve the static thumbnail URL. Don't transform on every dashboard load.

**Expected impact:**
- **Cloudinary transformation cost reduction: 30–70%** depending on view volume
- **Dashboard load time:** faster thumbnail loading

---

#### 2.3 Reduce the AI Model Pool to 2–3 Models

**Current state:**
- `AI_MODELS` (app.py:233–239) has 5 free models:
  ```
  google/gemma-4-31b-it:free
  google/gemma-4-26b-a4b-it:free
  nvidia/nemotron-nano-12b-v2-vl:free
  openai/gpt-oss-20b:free
  meta-llama/llama-3.1-8b-instruct:free
  ```
- `/api/ai/predict-metadata`, `/api/extract-ocr`, `/api/ask-paper` all call OpenRouter.
- More models = more retry logic + more latency while OpenRouter picks a working provider.

**What to do:**

1. **Trim to 2 models:** one vision-capable (for OCR/ask-paper) + one text-only (for metadata prediction). E.g.:
   - Vision: `google/gemma-4-31b-it:free` (covers OCR + vision Q&A)
   - Text: `meta-llama/llama-3.1-8b-instruct:free` (fast, reliable text)

2. **Remove retry fallback chains between models** — currently the code tries multiple models in sequence (implied by the large pool). With 2 models, fail fast to the secondary and return a clear error rather than spinning through 5.

3. **Cache AI results** — `predict-metadata` results for a given filename are deterministic. Cache by `filename` hash in L1 for 24h. Same file re-uploaded or re-checked hits cache, not API.

**Expected impact:**
- **AI latency:** from ~5–15s (multi-model retry) to ~2–5s (single model)
- **AI cost:** still $0 (free models), but fewer wasted calls to congested providers
- **User experience:** faster upload metadata tagging

---

#### 2.4 Kill Firebase Storage as a Live Path

**Current state:**
- Firebase Admin SDK is initialized (app.py:57–83) and used for:
  - `get_pdf_list()` (~line 3206) — lists Firebase blobs (legacy)
  - `proxy_file` (~line 2259) — proxies Firebase URLs
  - `view_doc` (~line 2305) — serves from Firebase signed URLs
  - Memory Wall signature uploads (~line 5212)
  - `/api/extract-ocr`, `/api/ask-paper` — fetch from Firebase
- `FIREBASE_SERVICE_ACCOUNT_JSON` is required env; if absent, Firebase features degrade.

**What to do:**

1. **Cloudinary is canonical** per ARCHITECTURE.md. Migrate all remaining Firebase-dependent flows to Cloudinary:
   - Memory Wall signatures → Cloudinary upload
   - `get_pdf_list()` → remove or point to Cloudinary
   - `/api/extract-ocr`, `/api/ask-paper` → fetch from Cloudinary `file_url`

2. **Remove Firebase Admin SDK initialization** once nothing depends on it. This removes the Firebase Admin dependency, reduces startup time, and eliminates a potential crash vector (Firebase init can fail on missing creds).

> This is a code cleanup that also reduces the "two storage systems" cognitive load. Not a direct cost saving (Firebase is cheap), but reduces operational complexity.

---

### Tier 2 — Medium Impact, Medium Effort

#### 2.5 Optimize the Dashboard Document Queries

**Current state:**
- `/dashboard` handler (~line 3014) calls `get_all_file_records_fo…` (truncated in read) and likely fetches all documents matching user context, then filters in Python.
- `app.py:3025` comment: "Use unified documents from database" — implies a `get_all_file_records_for_dashboard`-style function.

**What to do:**

1. **Push filtering to Supabase, not Python** — instead of `SELECT *` then filter `college_id`, `subject_id`, `exam_type` in Python, pass these as `.eq()`/`.in_()` clauses in Supabase. Supabase (Postgres) is far faster at filtering than loading 1000+ rows into Python.

2. **Pagination at the DB level** — if the dashboard shows "recent" or "relevant" papers, use `.limit()` + `.order()` in Supabase, not Python slicing. Currently `all_files[offset:offset+limit]` (app.py:4486) suggests Python-side pagination after a full load.

3. **Select only needed columns** — instead of `select('*')`, specify only the fields the template uses: `id`, `title`, `file_url`, `file_type`, `view_count`, `like_count`, `document_category`, `exam_type`, `year`, `subject_id`, `college_id`, `uploader_id`. This reduces payload size per row from ~500 bytes to ~200 bytes.

**Expected impact:**
- **Supabase payload reduction: 40–60% per query**
- **Dashboard render time:** faster with smaller data + server-side filtering
- **Supabase API cost:** fewer bytes transferred

---

#### 2.6 CSS Pipeline — Tree-Shake Unused Styles

**Current state:**
- `pipeline.css` imports 11 sub-stylesheets (CSS_PIPELINE.md): tokens, base, app-shell, components, layout, utilities, feature-tour, pwa-install, promo, profile-nudge, notification-bell
- Plus Tailwind (`tailwind.min.css`) + page-specific CSS (dashboard.css)
- Some pages are fully migrated; others still need their own CSS files extracted (p_landing.css, auth.css, profile.css, store-room.css, upload.css, ranking.css, viewer.css per CSS_PIPELINE.md line 48–58)

**What to do:**

1. **Audit which pages use which CSS** — run a build-step check: which CSS classes are actually used in which templates. Tools like PurgeCSS can tree-shake unused selectors from the pipeline per page.

2. **Load page-specific CSS only on that page** — currently `pipeline.css` is loaded globally (all pages). If `p_landing.html` doesn't use notification-bell styles, don't ship them. Load only the needed subset.

3. **Remove Tailwind if mostly unused** — if the project relies more on the custom pipeline than Tailwind utility classes, the Tailwind bundle may be dead weight. Check how many Tailwind classes are actually used in templates.

**Expected impact:**
- **CSS bundle size reduction: 30–50%** (from ~500KB+ to ~200–300KB)
- **First contentful paint:** faster on slow connections
- **Zero cost** (CSS is static, served from Flask static)

---

#### 2.7 Consolidate Duplicate Routes and Legacy Endpoints

**Current state (from ROUTES.md + app.py):**
- Legacy like: `/api/like` (line 4589) alongside `/api/interactions/like` (line 1387)
- Legacy bookmark: `/api/bookmark` (line 4608) alongside `/api/interactions/bookmark` (line 1401)
- Legacy comments: `/api/interactions/comments/<document_id>` (line 4627/4645) alongside old-style
- `/view_pdf` (line 2959) — legacy PDF view, alongside `/preview` and `/api/view-doc/`
- `/dashboard/profile/old` (line 3355) — redirect to profile
- Removed routes still in code: `/prepair/<subject>` (line 4161), `/UHV` (line 4168), `/rank` (line 3781), `/show_rank`, `/verify-file`, `/get-file-url`, `/update-file-metadata` — **marked as [REMOVED v?.?] in ROUTES.md but still present in app.py**
- `/register` (line 3009) — alias for signup, unnecessary redirect

**What to do:**

1. **Delete the [REMOVED] routes** — they're dead code. ROUTE-104 through ROUTE-110 in ROUTES.md are marked removed but still exist in app.py. Deleting them reduces app.py size, removes confusion, and eliminates any accidental exposure.

2. **Merge legacy interaction routes into the canonical ones** — make `/api/like` and `/api/bookmark` redirect (301) to `/api/interactions/like` and `/api/interactions/bookmark`, or just delete them if no client uses them. Check which routes are actually called (Supabase `document_views` or analytics can show usage).

3. **Delete `/view_pdf` legacy page** if all traffic uses `/preview` or `/api/view-doc/`.

**Expected impact:**
- **app.py size reduction:** ~200–400 lines removed
- **Security surface reduction:** fewer routes = fewer things to secure
- **Zero runtime cost** (routes are free), but reduces cognitive load and test burden

---

### Tier 3 — Lower Impact, Higher Effort (Future)

#### 2.8 Replace Heroku with a Lower-Cost Host (When Ready)

**Current state:** Heroku Basic dyno ($7/mo) + Heroku Scheduler.

**Options:**

| Option | Cost | Effort | Notes |
|--------|------|--------|-------|
| **Render** (web service + cron) | ~$7–12/mo | Medium | Similar dyno model; free tier available for low traffic |
| **Railway** | ~$5–10/mo | Medium | Simple deploy, includes PostgreSQL |
| **Fly.io** | ~$2–5/mo (shared CPU) | Higher | More control, closer to bare metal |
| **DigitalOcean App Platform** | ~$12/mo | Medium | Managed, predictable pricing |
| **Self-host on a $5 VPS** (DigitalOcean droplet, Hetzner, etc.) | $5/mo | High | Full control, but you manage everything (SSL, backups, updates) |

> Don't rush this. Heroku at $7/mo is reasonable for a project this size. Consider migration only if/when traffic grows or Heroku pricing changes make it unattractive. The app is a Flask monolith — portable to any host that runs Python + gunicorn.

---

#### 2.9 Database Index Audit

**Current state:** DATA_MODEL_RELATIONS.md line 347–435 lists ~25 indexes. Most are well-considered. But:

- `documents` table: queries often filter by `college_id`, `subject_id`, `department_id`, `exam_type`, `status`. Check slow-query logs (Supabase logs) for missing indexes on combinations like `(college_id, subject_id, status)`.
- `search_documents` table: indexed on `college_id`, `subject_id`, `status` — good. But if search queries filter by `semester` or `source`, those may need indexes.
- `file_access_history`: well-indexed (4 indexes on accessed_at, user_id, user_email) — good.

**What to do:**
1. Enable Supabase **pg_stat_statements** (if not already) to find slow queries.
2. Add composite indexes for the most common dashboard filter combinations.
3. Review `documents.view_count` + `documents.like_count` updates — these are incremented on every view/like. If traffic grows, consider batching these updates or using a counter cache table.

**Expected impact:**
- **Query latency:** 20–50% improvement on filtered document lists
- **Supabase cost:** faster queries = fewer round-trips

---

#### 2.10 PDF.js Configuration Tuning

**Current state:** Self-hosted PDF.js v6.1.200 at `static/pdfjs-6.1.200-dist/`.

**What to do:**
1. **Disable auto-fetch of all pages** — configure PDF.js to fetch pages on-demand (already implied by the viewer pattern), not preload the whole document.
2. **Enable w3c http range requests** — ensure the server supports `Range` headers (it does — `view_doc` handles Range at app.py:2311+). This lets PDF.js fetch only the page being viewed.
3. **Preload only page 1** — on document open, fetch page 1 immediately, then fetch subsequent pages as the user scrolls.
4. **Use PDF.js worker from the same origin** — already self-hosted, good. Ensure the worker is served with correct MIME type (`application/javascript`).

**Expected impact:**
- **Per-document view bandwidth:** reduced (only viewed pages fetched)
- **Per-document view latency:** faster initial render

---

## 3. Cost-Specific Quick Wins

| Action | Estimated Savings | Effort |
|--------|-------------------|--------|
| Cache dashboard payload (L1/L2) | Supabase API calls -40% | Low |
| Cache taxonomy data in L2 (Redis) | Supabase API calls -20% | Low |
| Trim AI model pool to 2 | AI latency -60% | Low |
| Cache `predict-metadata` results | AI calls -30% (re-uploads) | Low |
| Remove Cloudinary transformations on every view | Cloudinary cost -30–70% | Medium |
| Delete [REMOVED] routes from app.py | app.py -300 lines, less confusion | Low |
| Merge legacy `/api/like`, `/api/bookmark` | Less code, cleaner API | Low |
| Tree-shake CSS bundle | 30–50% smaller CSS | Medium |
| Select only needed DB columns | Supabase payload -40% | Low |
| Push filtering to Supabase (not Python) | Faster, less data transfer | Medium |

---

## 4. What NOT to Change (Preserve These)

1. **PDF.js as canonical viewer** — never swap to Adobe Embed or another library. The anti-piracy model depends on PDF.js's in-browser rendering with no download path.

2. **Anti-piracy headers** — `Content-Disposition: inline`, `X-Download-Options: noopen`, `no-store`, Referer check. These are non-negotiable.

3. **Cloudinary as canonical storage** — Firebase is legacy fallback only. Don't introduce a third storage system.

4. **Supabase schema `abhihub`** — all tables are in this schema. Don't scatter tables across schemas.

5. **The 1-worker gunicorn setup** — for current traffic (85 users, 20 active), 1 worker is fine. Don't add workers until you have evidence of overload (latency spikes, queue depth).

6. **Free-tier OpenRouter models** — they work. Don't pay for API calls until there's a clear revenue justification.

---

## 5. Prioritized Action Plan

### Week 1 — Quick Wins (Low Effort, High Impact)

1. **Cache dashboard payload** — wrap the dashboard data fetch in `cache.get_cached()` with a 3-minute TTL. Measure Supabase call count before/after.
2. **Cache taxonomy in L2** — if Redis is available, promote `all_colleges`, `all_branches`, `all_departments`, `all_subjects` to L2 with 1-hour TTL.
3. **Trim AI models to 2** — edit `AI_MODELS` list in app.py, remove retry chains.
4. **Cache `predict-metadata`** — key by filename hash, 24h TTL.
5. **Delete [REMOVED] routes** — `/prepair/<subject>`, `/UHV`, `/rank`, `/show_rank`, `/verify-file`, `/get-file-url`, `/update-file-metadata`, `/register` alias.

### Week 2 — Medium Effort

6. **Review Cloudinary transformations** — audit which views trigger transformations; switch to direct URLs where possible; pre-generate thumbnails at upload.
7. **Push DB filtering to Supabase** — audit dashboard and search queries; replace Python-side filtering with `.eq()`/`.in_()`/`.limit()`.
8. **Select only needed columns** — replace `select('*')` with explicit column lists in the most common queries.
9. **Merge legacy interaction routes** — decide whether to 301-redirect or delete `/api/like`, `/api/bookmark`, legacy comment routes.

### Month 2 — Structural Improvements

10. **CSS tree-shake** — audit template usage, load page-specific CSS subsets, consider removing Tailwind if unused.
11. **DB index audit** — enable `pg_stat_statements`, add composite indexes for common filter combinations.
12. **PDF.js tuning** — ensure Range request support, disable pre-fetch, preload only page 1.
13. **Evaluate host migration** — if Cloudinary or Supabase costs grow, evaluate Render/Railway/Fly.io as alternatives to Heroku.

---

*This document is a living recommendations list. Re-assess after each change: measure Supabase API calls, Cloudinary transformation count, dashboard render time, and AI call latency before and after.*
