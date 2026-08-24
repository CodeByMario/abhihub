# AbhiHub — Working On / Roadmap: Dynamic Access & Contribution Economy

Build the scoring/access/ads economy **on top of** what already exists (see `work complete.md`). Reuse `contribution_logs`, `document_views`, `document_votes`, `bookmarks`, `award_contribution_xp()`, and the admin panel. Do not duplicate tables.

---

## Phase 1 — Scoring Engine (`methods/scoring_engine.py`) — 🔄 IN PROGRESS

- [x] **Config table** migration `022_scoring_config.sql` — `abhihub.scoring_config` with seeded defaults (view 0.1, like 2, bookmark 5, publish 5, comment 1, spam penalties), access-level thresholds, ad density map, view-dedupe rules, rate limits. **→ Needs to be run against Supabase (SQL editor).**
- [x] **`methods/scoring_engine.py`** created: `get_config()` (TTL-cached config loader with fallback defaults), `get_points()`, `is_unique_view()` (dedupe on user+doc within window via `document_views`), `process_event()` (self-action skip + view dedupe + awards via existing XP pipeline).
- [x] **`award_contribution_xp()`** (`supabase_helper.py`) extended: `base_xp` now optional; when omitted it resolves from scoring_config; unknown/zero-value actions are skipped instead of defaulting to +10.
- [x] **View hook wired** into `/api/document-view` in `app.py`: after a successful log, calls `process_event('resource_viewed', ...)`; skips scoring self-owned docs; failures never break the view endpoint.
- [x] Wire like/bookmark/comment hooks into `toggle_like` / `toggle_bookmark` / `add_comment` — each now calls `process_event` for the **uploader** (receiving engagement), skipping self-actions; helper `_get_document_uploader()` added.
- [x] Consumption score aggregation + rate-limit enforcement — `_rate_limit_ok()` (per-user sliding hourly limits from `rate_limits` config: views 120/h, likes 60/h, bookmarks 40/h, fail-open) + `recalculate_user_scores()` (rolling 30-day contribution vs unique-doc consumption → `abhihub_score`, `consumption_score`, `ccr`, `access_level` via `get_access_level()` thresholds).
- [ ] **→ Run migration `023_user_scores.sql` in Supabase** — adds `abhihub_score/consumption_score/ccr/access_level` columns to profiles + SQL nightly recalc function (pg_cron optional). Python scheduler job added to `scheduled_tasks.py` as the fallback.
- [ ] Verify end-to-end after running migration 023 (view a doc twice → only first scores; like a doc → uploader +2 in `contribution_logs`).

## Phase 2 — User Score & CCR

- [ ] **AbhiHub Score** = normalized contribution + trust/reputation − consumption pressure. Use **rolling windows** (e.g. 30-day) not lifetime totals; store in new columns on `profiles`: `abhihub_score REAL`, `consumption_score REAL`, `ccr REAL`, `access_level TEXT` (migration `023_user_scores.sql`).
- [ ] Nightly recalculation job (add to `scheduled_tasks.py`) + lazy recompute on login.
- [ ] **CCR = contribution value / consumption value**, classified: >2.0 strong contributor · 1.0–2.0 balanced · 0.5–1.0 consumer-heavy · <0.5 mostly consumer.
- [ ] Resource **quality score** per document from community signal ratio (likes+bookmarks vs views) — feeds back into uploader contribution value; low-engagement uploads earn little.

## Phase 3 — Access Levels

- [ ] Five levels with configurable thresholds: Explorer → Member → Contributor → Power Contributor → Community Leader.
- [ ] Gate expanded features by level: upload limits, search quota, early-access features, profile perks.
- [ ] Never punish basic consumption — Explorers keep full core access, just standard ads/limits.

## Phase 4 — Dynamic Advertising — 🔄 IN PROGRESS

- [x] `get_ad_decision(user_id)` in scoring engine — reads `access_level` from profiles, maps via `ad_density` config → `{show_ads, density}`; anonymous/anonymous-error fallback = show, high (AdSense-safe: frequency reduction only).
- [x] `inject_ad_decision` context processor in `app.py` — every template now has `ad_decision`, `ad_density`, and `show_secondary_ads` (True only for high/medium density).
- [x] Ad slots gated: `p_index.html` + `p_view.html` + `p_pdf_reader.html` (banner), `p_store_room.html` + `_search_partial.html` (in-feed). Contributors/power/leader users stop seeing secondary slots.
- [ ] `templates/ads/sticky_mobile.html` — not currently included by any page; wire when a page adopts it.
- [ ] Verify with a test user at each access level.

## Phase 5 — Anti-Abuse — 🔄 IN PROGRESS

- [x] No self-credit: skip scoring when actor == uploader (likes/bookmarks/views/comments on own docs).
- [x] Rate limits per user on view/like/bookmark scoring (Phase 1 `_rate_limit_ok`).
- [x] Duplicate-resource detection at upload: publish XP withheld when the file's `file_hash` (migration `012`) already exists in `documents`; check failure fails-open so hashing gaps don't block legit uploads.
- [x] Trust score component: `get_trust_score(user_id)` in scoring engine — `0.4×age_factor (90-day ramp) + 0.3×is_verified + 0.3×history_factor` (−0.2 per spam penalty in contribution_logs); errors → neutral 0.5.
- [x] Spam-penalty events wired into admin reject flow — `/api/admin/reject-document` awards `content_removed` with `spam_penalty_min` (−10 from config) to the uploader before rank recalc; penalty failures never block rejection.
- [x] Trust score weighting applied in `recalculate_user_scores()` — score = `contribution × (0.5 + 0.5 × trust) − 0.05 × consumption`; new/unverified/penalized accounts earn a fraction of full credit, trusted contributors keep 100%.

## Phase 3 — Access Levels — 🔄 IN PROGRESS

- [x] Five levels with configurable thresholds (`access_levels` config, `get_access_level()`).
- [x] `FEATURE_GATES` in scoring engine — per-level daily limits (uploads 3/5/15/40/100, searches 50→5000) + `early_access` flag for contributor+.
- [x] `get_feature_gate()` + `check_upload_quota()` — upload quota enforced server-side in `/upload` POST (HTTP 429 with upgrade nudge); fails open on errors.
- [x] `GET /api/my-access` — client endpoint returning level, limits, and remaining uploads today.
- [x] Search-quota enforcement — `search_v2_endpoint` counts `search_performed` events per 24h; over-quota returns 429 with `quota_exceeded: true` and an upgrade nudge. Fails open.
- [x] `search_performed` event logging wired into `search_analytics_endpoint` (fires alongside search_analytics insert; zero-point consumption event, tracked for quotas + CCR).
- [x] UI: level badge + progress-to-next-level bar on profile hero (`p_profile.html`) via `/api/my-access`; shows "Max level 🎉" at top.

## Phase 6 — Admin Dashboard — ✅ DONE

- [x] `/admin/economy` page (`templates/admin_economy.html`, admin-gated like `/admin/analytics`):
  - level distribution pills, top contributors, most consumer-heavy (lowest CCR), recent scored events table
  - live editor for every `scoring_config` key (JSON textarea + Save) — busts the engine cache instantly
  - manual per-user access-level override form
- [x] API: `GET/POST /api/admin/economy/config`, `GET /api/admin/economy/overview`, `POST /api/admin/economy/user/<id>` — all behind `@auth_required @admin_required`.
- [x] Linked from `/admin/controle` nav as a "💰 Economy" tab button.
- [ ] Flagged-abuse accounts list in dashboard (needs spam-penalty events above).

---

### Suggested order of execution
1. Migration `022` (scoring_config) + Phase 1 event hooks — smallest change, biggest unlock.
2. Phases 2–3 (scores, levels) behind a feature flag.
3. Phase 4 ads once real score data exists; Phase 5 anti-abuse hardening alongside; Phase 6 last.
