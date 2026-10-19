# AbhiHub In-App Guide System — Implementation Status & Audit

> Updated: 2026-10-18  
> Scope: `guide_engine.js` · `guide_service.py` · `api.py` endpoints · `data/guides.json` · `p_struct.html` bootstrap · `migrations/create_guide_progress_table.sql`

---

## 1. Executive Implementation Status

| Domain | Status | Implemented | Remaining |
|--------|--------|-------------|-----------|
| **Guide Engine (`guide_engine.js`)** | 🟢 Complete | SVG spotlight, tooltip positioning, auto-scroll with frame settling, Escape/Tab focus trap, passive resize/scroll listener, reduced motion, ARIA roles | None |
| **State & Multi-Tab Sync** | 🟢 Complete | `BroadcastChannel('abhihub_guide_sync')`, instant multi-tab sync, auto-cleanup on 401/403 or logout | None |
| **Modal Collision Safety** | 🟢 Complete | Proactive check for `.popup-overlay`, `.file-info-modal-overlay.show`, `.modal.show`, auto-start delay | None |
| **Backend Service (`guide_service.py`)** | 🟢 Complete | Screening & filtering, session + Supabase persistence, stable sort, version gating, upsert fallback | None |
| **API Endpoints (`routes/api.py`)** | 🟢 Complete | `GET /api/guides/eligible` & `POST /api/guides/<id>/progress` | None |
| **Route & Screen Aliasing** | 🟢 Complete | Canonical normalization (`SCREEN_ALIASES`) for `/rank`, `/settings`, `/profile`, `/view`, etc. | None |
| **Target Selectors (`data/guides.json`)** | 🟢 Complete | 10 guides across 6 screens updated with multi-template fallbacks | None |
| **Database Migration (`migrations/`)** | 🟢 Complete | `create_guide_progress_table.sql` applied & verified live in Supabase | None |

---

## 2. Feature Inventory (F1 – F35)

| # | Feature | Status | Implementation Details |
|---|---------|--------|------------------------|
| F1 | **Guide Registry** | ✅ Implemented | `data/guides.json` with 10 guides across 6 screens |
| F2 | **Screen-scoped loading** | ✅ Implemented | `guide_service.get_eligible_guides()` screen filtering |
| F3 | **Priority sorting** | ✅ Implemented | Stable Python sort by `(-priority, guide_id)` |
| F4 | **SVG Spotlight Cutout** | ✅ Implemented | Live SVG path with `evenodd` fill punching crystal-clear hole |
| F5 | **CSS Highlight Ring** | ✅ Implemented | Glow + indigo outline via `.guide-highlight-target` |
| F6 | **Auto-scroll to target** | ✅ Implemented | `scrollIntoView` with smooth scroll settling RAF detection |
| F7 | **Step-skipping on missing DOM** | ✅ Implemented | Skips nonexistent or invisible elements cleanly |
| F8 | **Tooltip Positioning** | ✅ Implemented | Viewport clamped, auto-flips above target if below bounds |
| F9 | **Aim Badge** | ✅ Implemented | Guide-level goal displayed inside tooltip header |
| F10 | **Step Counter** | ✅ Implemented | "X of Y" counter in tooltip footer |
| F11 | **Skip / Next / Done buttons** | ✅ Implemented | Interactive navigation and completion triggers |
| F12 | **Feature Directory Menu** | ✅ Implemented | Interactive modal listing all screen guides with Start/Skip |
| F13 | **Post-completion menu re-open** | ✅ Implemented | Reopens menu offering remaining guides upon completion |
| F14 | **Post-dismiss menu re-open** | ✅ Implemented | Reopens directory upon skip if remaining guides exist |
| F15 | **Completed badge in menu** | ✅ Implemented | Green "(Completed)" label with button changing to "Replay" |
| F16 | **Dismissed fade in menu** | ✅ Implemented | Dimmed 35% opacity on skipped guides |
| F17 | **URL-triggered menu** | ✅ Implemented | `?guide`, `?tour`, `#guide`, and nested `?p=` parameter support |
| F18 | **Progress persistence (Session)** | ✅ Implemented | Flask session `session['guide_progress']` cache |
| F19 | **Progress persistence (Supabase DB)** | ✅ Implemented | Upsert into `abhihub.guide_progress` table with RLS |
| F20 | **Session fallback** | ✅ Implemented | Guest & unauthenticated users persist via session |
| F21 | **Version gating** | ✅ Implemented | Suppresses guides only when user completed version `>=` guide version |
| F22 | **Progress resume** | ✅ Implemented | Resumes from `current_step` stored in DB/session |
| F23 | **Inline per-item dismiss** | ✅ Implemented | Skip button in directory syncs dismiss without opening tour |
| F24 | **Backdrop click to close** | ✅ Implemented | Clicking dark overlay dismisses menu |
| F25 | **Single global instance** | ✅ Implemented | `window.GuideEngine` IIFE singleton |
| F26 | **Screen name resolution** | ✅ Implemented | Decodes `/app-shell` SPA query parameters |
| F27 | **Cleanup on transition** | ✅ Implemented | Centralized `cleanup()` removes spotlight, tooltips, and handlers |
| F28 | **Schema-aware Supabase access** | ✅ Implemented | Prioritizes `abhihub` schema, falls back to `public` |
| F29 | **Unauthenticated API tolerance** | ✅ Implemented | Safe `guest` fallback on progress updates |
| F30 | **Error suppression** | ✅ Implemented | Network failures warn in console without breaking UI |
| F31 | **Multi-tab synchronization** | ✅ Implemented | `BroadcastChannel('abhihub_guide_sync')` synchronizes progress |
| F32 | **Active modal collision guard** | ✅ Implemented | Defers guide start when modals/popups are already open |
| F33 | **Session invalidation cleanup** | ✅ Implemented | 401/403 status & `auth:logout` events tear down overlays |
| F34 | **Screen alias resolution** | ✅ Implemented | `SCREEN_ALIASES` maps `/rank`, `/settings`, `/profile`, `/view` |
| F35 | **Universal selector fallback** | ✅ Implemented | Multi-target selectors support legacy and redesigned views |

---

## 3. Guide Registry Entries

| ID | Screen | Trigger Alias | Type | Steps | Priority |
|----|--------|---------------|------|-------|----------|
| `welcome-tour` | `dashboard` | `/`, `/dashboard`, `/home`, `/index` | welcome | 3 | 200 |
| `dashboard-hero-search` | `dashboard` | `/`, `/dashboard` | feature | 2 | 110 |
| `dashboard-quick-actions` | `dashboard` | `/`, `/dashboard` | feature | 2 | 100 |
| `dashboard-recently-viewed` | `dashboard` | `/`, `/dashboard` | feature | 1 | 90 |
| `upload-dropzone` | `upload` | `/upload` | feature | 2 | 110 |
| `upload-ai-metadata` | `upload` | `/upload` | feature | 2 | 100 |
| `storeroom-sync` | `store-room` | `/store-room`, `/storeroom` | feature | 2 | 100 |
| `leaderboard-podium` | `leaderboard` | `/leaderboard`, `/rank`, `/ranking` | feature | 2 | 100 |
| `account-profile-completion` | `account` | `/account`, `/profile`, `/settings` | feature | 2 | 100 |
| `reader-document-controls` | `pdf-reader` | `/pdf-reader`, `/dashboard/view`, `/local-viewer` | feature | 2 | 100 |

---

## 4. Edge Case Audit

### 4.1 DOM & Rendering
- **Target element missing in DOM**: ✅ Handled — `showStep()` null-guard advances to next step or completes.
- **Target in hidden/collapsed container**: ✅ Handled — `offsetWidth/Height` & `getClientRects` guard skips non-visible targets.
- **Target in fixed-position container**: ✅ Handled — debounced `scroll` and `resize` listeners recalculate coordinates.
- **Tooltip near bottom edge**: ✅ Handled — automatically flips above element if vertical bounds exceed viewport.
- **Small viewports (< 320px)**: ✅ Handled — constrained via `max-width: calc(100vw - 32px)` and horizontal clamping.
- **Motion sensitivity**: ✅ Handled — `@media (prefers-reduced-motion: reduce)` disables transition animations.

### 4.2 Authentication & Multi-Window
- **Guest users**: ✅ Handled — session-only storage with `user_id = 'guest'`.
- **User logout during tour**: ✅ Handled — `user:logout` and `auth:logout` listeners call `cleanup()`.
- **Session expiration**: ✅ Handled — 401/403 status in `syncProgressDirect()` cleans up UI and stops sync.
- **Concurrent browser tabs**: ✅ Handled — `BroadcastChannel('abhihub_guide_sync')` propagates step/status and closes stale overlays.

### 4.3 Database & Resilience
- **Supabase unavailable**: ✅ Handled — session fallback preserves all progress seamlessly.
- **Upsert key/schema mismatch**: ✅ Handled — explicit fallback to `SELECT` + `UPDATE` or `INSERT`.
- **Data format errors**: ✅ Handled — graceful empty array fallback in `load_guides()`.
- **Malformed URLs / Special Characters**: ✅ Handled — `encodeURIComponent(guideId)` in all endpoints.

### 4.4 Guide Logic & Accessibility
- **Zero-step guide**: ✅ Handled — early return guard cleanly calls `complete()`.
- **Version rollbacks**: ✅ Handled — `version >= ver` guard ensures completed guides are not re-triggered.
- **Replayability**: ✅ Handled — user can replay any completed guide from the directory menu.
- **Keyboard navigation**: ✅ Handled — `Escape` closes overlays; `Tab` / `Shift+Tab` focus trapped inside dialogs.
- **Screen readers**: ✅ Handled — `role="dialog"`, `role="region"`, `aria-modal="true"`, `aria-labelledby`, and `aria-label`.
- **Existing modal collision**: ✅ Handled — active dialog guard pauses tour auto-start until modals are dismissed.

---

## 5. What is Implemented vs Remaining

### ✅ What is Implemented (Code Complete)
1. **Frontend Architecture**: All 619+ lines of `static/js/guide_engine.js` with full lifecycle management, cross-tab sync, accessibility, and modal protection.
2. **Backend Engine**: Full Python service `methods/guide_service.py` with screen aliasing, session caching, and Supabase upsert fallback.
3. **API Routing**: `/api/guides/eligible` and `/api/guides/<guide_id>/progress` in `routes/api.py`.
4. **Target Multi-Matching**: Updated selectors in `data/guides.json` supporting both legacy and v2 pages.
5. **Client Bootstrapping**: `initAppGuide()` in `templates/p_struct.html` with client-side screen alias resolution.
6. **SQL Migration Script**: Created `migrations/create_guide_progress_table.sql` with table definitions, unique indexes, and RLS policies for `service_role`, `authenticated`, and `anon`.

### 🟡 Operational & Testing Verification
1. **Execute Supabase SQL Migration**: ✅ **COMPLETED** — Table `abhihub.guide_progress` applied and verified live via Supabase client.
2. **Interactive Walkthrough**: Ready to test anytime via `http://localhost:5000/dashboard?guide` or by clicking any guide in the in-app directory.
