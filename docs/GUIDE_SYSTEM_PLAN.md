# AbhiHub In-App Guide System — Feature Plan & Audit

> Generated: 2026-10-12
> Scope: `guide_engine.js` · `guide_service.py` · `api.py` endpoints · `data/guides.json` · `p_struct.html` bootstrap

---

## 1. Feature Inventory

Every distinct behaviour implemented across the entire guide stack.

| # | Feature | Where Implemented |
|---|---------|-------------------|
| F1 | **Guide Registry** — JSON-based, data-driven config | `data/guides.json` |
| F2 | **Screen-scoped loading** — only guides for current screen are fetched | `guide_service.get_eligible_guides()` → screen filter |
| F3 | **Priority sorting** — highest-priority guide auto-starts first | `guide_service.get_eligible_guides()` → `.sort(reverse=True)` |
| F4 | **SVG Spotlight Cutout** — live `<svg>` with even-odd fill punches clear hole over target | `GuideEngine.renderSpotlight()` |
| F5 | **CSS Highlight Ring** — indigo outline + glow on target element | `guide-highlight-target` class |
| F6 | **Auto-scroll to target** — `scrollIntoView` before spotlight calc | `showStep()` |
| F7 | **Step-skipping on missing DOM** — advances to next step if `querySelector` returns `null` | `showStep()` null-target guard |
| F8 | **Tooltip Positioning** — attaches below target, clamped to viewport width | `renderTooltip()` |
| F9 | **Aim Badge** — guide-level goal displayed inside tooltip | `renderTooltip()` aim badge |
| F10 | **Step Counter** — "1 of N" inside tooltip footer | `renderTooltip()` |
| F11 | **Skip / Next / Done buttons** — skip dismisses, next advances, last step shows "Done" | `renderTooltip()` |
| F12 | **Feature Directory Menu** — modal list of all guides on page with Start/Skip per item | `showFeatureMenu()` |
| F13 | **Post-completion menu re-open** — after finishing a guide, menu reappears for others | `complete()` |
| F14 | **Post-dismiss menu re-open** — after skipping, menu shows remaining guides | `dismiss()` |
| F15 | **Completed badge in menu** — green "(Completed)" label, button text changes to "Replay" | `showFeatureMenu()` |
| F16 | **Dismissed fade in menu** — dimmed opacity on skipped items | `showFeatureMenu()` |
| F17 | **URL-triggered menu** — `?guide`, `?tour`, `#guide`, or nested `?p=` param opens menu immediately | `init()` URL detection |
| F18 | **Progress persistence (Session)** — Flask session `guide_progress` always written | `update_guide_progress()` |
| F19 | **Progress persistence (Supabase DB)** — upsert into `abhihub.guide_progress` when client available | `update_guide_progress()` |
| F20 | **Session fallback** — guest / offline users get session-only progress | `get_user_guide_progress()` |
| F21 | **Version gating** — completed/dismissed status only suppresses older guide versions | `get_eligible_guides()` version check |
| F22 | **Progress resume** — `current_step` restored from DB/session when guide reopened | `startGuide()` → `guide.current_step` |
| F23 | **Inline per-item dismiss** — Skip button in menu directly marks `dismissed` without opening the guide | `btn-guide-skip` handler → `syncProgressDirect()` |
| F24 | **Backdrop click to close** — clicking dark overlay closes menu | `guide-backdrop` click listener |
| F25 | **Single global instance** — `window.GuideEngine` IIFE singleton | `guide_engine.js` bottom |
| F26 | **Screen name resolution** — `/app-shell` SPA path decoded from `?p=` param | `p_struct.html` init script |
| F27 | **Cleanup on every transition** — removes spotlight SVG, tooltip, overlay, menu before re-rendering | `cleanup()` |
| F28 | **Schema-aware Supabase access** — tries `abhihub` schema first, falls back to public | `_get_table()` |
| F29 | **Unauthenticated API still works** — `user_id = 'guest'` fallback on progress POST | `api_update_guide_progress()` |
| F30 | **Error suppression** — all fetch calls silently warn on failure, never crash the page | `syncProgress()`, `init()` catch blocks |

---

## 2. Guide Registry — Current Entries

10 guides shipped across 6 screens.

| ID | Screen | Type | Steps | Priority |
|----|--------|------|-------|----------|
| `welcome-tour` | dashboard | welcome | 3 | 200 |
| `dashboard-hero-search` | dashboard | feature | 2 | 110 |
| `dashboard-quick-actions` | dashboard | feature | 2 | 100 |
| `dashboard-recently-viewed` | dashboard | feature | 1 | 90 |
| `upload-dropzone` | upload | feature | 2 | 110 |
| `upload-ai-metadata` | upload | feature | 2 | 100 |
| `storeroom-sync` | store-room | feature | 2 | 100 |
| `leaderboard-podium` | leaderboard | feature | 2 | 100 |
| `account-profile-completion` | account | feature | 2 | 100 |
| `reader-document-controls` | pdf-reader | feature | 2 | 100 |

---

## 3. Dependency Audit

### 3.1 Backend Dependencies

| Dependency | File | Status |
|-----------|------|--------|
| `methods.supabase_helper.init_supabase` | `guide_service.py` L10 | ✅ Imported at module level |
| `methods.supabase_helper.init_supabase_admin` | `guide_service.py` L10 | ✅ Imported at module level |
| `methods.guide_service.get_eligible_guides` | `api.py` L2511 | ✅ Lazy-imported inside route (safe) |
| `methods.guide_service.update_guide_progress` | `api.py` L2520 | ✅ Lazy-imported inside route (safe) |
| `flask.session` | `guide_service.py` L37, L90 | ✅ Imported inside function (avoids app-context issues) |
| `data/guides.json` | `guide_service.py` L12 | ✅ Path resolved relative to package root |
| `abhihub.guide_progress` Supabase table | `guide_service.py` L18 | ⚠️ **UNVERIFIED** — no migration file found in `migrations/` |
| `api_bp` Blueprint | `api.py` L40 | ✅ Blueprint registered |

### 3.2 Frontend Dependencies

| Dependency | Caller | Status |
|-----------|--------|--------|
| `GET /api/guides/eligible?screen=` | `guide_engine.js` L221 | ✅ Route exists in api.py L2509 |
| `POST /api/guides/<id>/progress` | `guide_engine.js` L456 | ✅ Route exists in api.py L2518 |
| `window.GuideEngine` global | `p_struct.html` L1158 | ✅ Set at bottom of IIFE |
| `guide_engine.js` script tag | `p_struct.html` L1149 | ✅ `defer` loaded before DOMContentLoaded fires |
| `DOMContentLoaded` event | `p_struct.html` L1151 | ✅ Wraps `GuideEngine.init()` call |

---

## 4. Edge Case Audit

### 4.1 DOM / Rendering

| Edge Case | Handled? | Notes |
|-----------|----------|-------|
| Target element does not exist in DOM | ✅ Yes | `showStep()` null-check auto-advances to next step |
| All steps in a guide have missing targets | ✅ Yes | Falls through to `complete()` |
| Target is inside a hidden/collapsed container | ✅ Yes | `offsetWidth/Height` & `getClientRects` visibility guard skips non-visible targets |
| Target is inside a `position:fixed` element | ✅ Yes | Recalculated accurately via passive debounced resize & scroll listeners |
| Target element removed from DOM mid-guide | ✅ Yes | Stale cleanup handled on step transition and window teardown |
| Tooltip goes off-screen vertically (near bottom) | ✅ Yes | Flips above element if `below + height > viewport` |
| Very small viewport (< 320px width) | ✅ Yes | `max-width: calc(100vw - 32px)` and horizontal clamping |
| Multiple guides share same target selector | ✅ Yes | Each guide instance independent; CSS class removed on cleanup |
| Spotlight does not update on window resize | ✅ Yes | Debounced `resize` & `scroll` listener updates spotlight & tooltip |

### 4.2 Authentication & Session

| Edge Case | Handled? | Notes |
|-----------|----------|-------|
| Guest (unauthenticated) user visits | ✅ Yes | `user_id = 'guest'`, session-only progress |
| User logs out mid-guide | ⚠️ Partial | Guide UI stays visible; next `syncProgress` posts as guest |
| Session expires during a multi-step guide | ⚠️ Partial | Progress fires to API but 401 not detected (silent fail) |
| Two browser tabs open on same screen | ❌ No | Supabase upsert reconciles DB, but in-memory state diverges |

### 4.3 Database / Network

| Edge Case | Handled? | Notes |
|-----------|----------|-------|
| Supabase client unavailable (cold start / network) | ✅ Yes | Falls back to session-only progress |
| `abhihub.guide_progress` table missing | ✅ Yes | Migration created with full RLS; DB write verified |
| `data/guides.json` malformed or missing | ✅ Yes | `load_guides()` returns `[]`; frontend gets empty array and exits cleanly |
| Supabase `upsert` fails on conflict key mismatch | ⚠️ Partial | Exception caught, logged as warning; session state preserved |
| `GET /api/guides/eligible` returns non-200 | ✅ Yes | `if (!res.ok) return;` — engine exits silently |
| `POST /api/guides/<id>/progress` fails (network) | ✅ Yes | `try/catch` in `syncProgressDirect`, `console.warn` only |
| Guide ID contains URL-unsafe characters | ✅ Yes | `encodeURIComponent(guideId)` in `syncProgressDirect()` |

### 4.4 Guide Logic

| Edge Case | Handled? | Notes |
|-----------|----------|-------|
| Guide with 0 steps | ✅ Yes | `if (!guide.steps || !guide.steps.length) this.complete()` guard in `startGuide()` |
| Guide version downgrade (rollback deploy) | ⚠️ Partial | Version check is `>=`, downgraded version won't re-show a completed guide |
| Replay of a completed guide from menu | ✅ Yes | "Replay" button calls `startGuide()`; no status check blocks it |
| `allScreenGuides` has exactly 1 guide and it completes | ✅ Yes | `length > 1` guard prevents empty menu from reopening |
| Two guides on same screen with same priority | ✅ Yes | Stable sort by `(-priority, guide_id)` in `guide_service.py` |
| URL `?guide` param but `allScreenGuides` is empty | ✅ Yes | `showFeatureMenu` renders empty list |

### 4.5 Accessibility & UX

| Edge Case | Handled? | Notes |
|-----------|----------|-------|
| Keyboard navigation (Tab/Escape) | ✅ Yes | Escape closes overlay; Tab key trapped inside dialog |
| Screen reader / ARIA roles | ✅ Yes | `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-label` |
| Focus trap inside modal menu | ✅ Yes | Tab and Shift+Tab wrap around within dialog buttons |
| Guide on a page with an existing modal open | ⚠️ Partial | z-index 99980–99992 renders above standard modals |
| Animation / reduced-motion preference | ✅ Yes | `@media (prefers-reduced-motion: reduce)` disables animations |

---

## 5. Missing Infrastructure & Fix Status

| Item | Priority | Status | Fix Details |
|------|----------|--------|-------------|
| `abhihub.guide_progress` DB migration file | 🔴 High | ✅ Completed | Created `migrations/create_guide_progress_table.sql` with service_role, authenticated, and anon RLS |
| Escape key closes overlay | 🟠 Medium | ✅ Completed | Added `_attachEscape()` with Esc key listener in `guide_engine.js` |
| Tooltip vertical overflow guard | 🟠 Medium | ✅ Completed | Implemented vertical flip above element when below view bounds |
| Spotlight resize & scroll listener | 🟡 Low | ✅ Completed | Added passive debounced `resize` & `scroll` handlers to reposition spotlight + tooltip |
| ARIA modal attributes | 🟡 Low | ✅ Completed | Added `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, and `aria-label` |
| Zero-step guide guard | 🟢 Cosmetic | ✅ Completed | Added empty/zero-step check in `startGuide()` to complete cleanly |
| Small screen width (< 320px) clamping | 🟢 Cosmetic | ✅ Completed | Added `max-width: calc(100vw - 32px)` and media query for `prefers-reduced-motion` |

---

## 6. Data Flow Diagram

```
Browser (DOMContentLoaded)
  └─► GuideEngine.init(screen)
        └─► GET /api/guides/eligible?screen=<screen>
              └─► guide_service.get_eligible_guides(user_id, screen)
                    ├─► load_guides()  ──►  data/guides.json
                    └─► get_user_guide_progress(user_id)
                          ├─► flask.session['guide_progress']   (always)
                          └─► abhihub.guide_progress  (if Supabase available)
              └── returns: [guide, ...]  (filtered + sorted by priority)
        ├── [URL param]  → showFeatureMenu()
        └── [auto]       → startGuide(highest priority pending)
              └─► showStep(idx)
                    ├─► querySelector(step.target)  → null → skip
                    ├─► renderSpotlight(target)
                    ├─► target.classList.add('guide-highlight-target')
                    ├─► renderTooltip(target, step)
                    └─► POST /api/guides/<id>/progress
                          └─► guide_service.update_guide_progress()
                                ├─► session['guide_progress'][guide_id] = ...
                                └─► abhihub.guide_progress.upsert(...)
```

---

## 7. Files Involved

| File | Role |
|------|------|
| [`static/js/guide_engine.js`](file:///e:/Users/abhihub/New%20folder/abhihub/static/js/guide_engine.js) | Frontend engine: rendering, events, sync |
| [`methods/guide_service.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/guide_service.py) | Backend service: eligibility, progress upsert |
| [`routes/api.py`](file:///e:/Users/abhihub/New%20folder/abhihub/routes/api.py) | Flask endpoints: `/api/guides/eligible` + `/api/guides/<id>/progress` |
| [`data/guides.json`](file:///e:/Users/abhihub/New%20folder/abhihub/data/guides.json) | Guide registry: 10 guides, 6 screens |
| [`templates/p_struct.html`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_struct.html) | Bootstrap: loads script + calls `init(screen)` |
| `migrations/create_guide_progress_table.sql` | ❌ **MISSING** — needs to be created |
