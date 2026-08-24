# AbhiHub — Work Complete

Core principle of the plan: **users consume for free; meaningful contribution earns higher access and fewer ads.** No file downloads — everything is consumed on-platform.

---

## ✅ 1. Gamification Foundation (LIVE)

Existing systems already shipped on the Memory-wall branch:

- **`abhihub.contribution_logs`** table (migration `013_gamification.sql`) — logs every contribution action with XP awarded, entity type/id, description.
- **`abhihub.user_achievements`** — badge system with unique `(user_id, badge_name)` constraint.
- **`profiles.reputation_score` + `rank_title`** — persisted per-user score.
- **`abhihub.leaderboard_view`** (migration `014_leaderboard.sql`) — aggregates reputation + XP totals.
- **`award_contribution_xp()`** in `methods/supabase_helper.py:1968` — writes log entry, increments `reputation_score`, returns new rank. Already wired into upload flow (`upload_document` → +25 XP at `supabase_helper.py:746`).
- **`get_contribution_timeline()`** — recent contributions per user.

## ✅ 2. Activity Event Sources (LIVE)

The raw events the scoring engine will consume are all being captured today:

| Event | Where it's logged |
|---|---|
| Resource view | `/api/document-view` → `DocumentView.log_view()` (`data/interactions.py`) into `abhihub.document_views` (with user_id, IP, device_type, time_spent_seconds) |
| Like | `/api/interactions/like` → `toggle_like()` (`supabase_helper.py:1016`) via `document_votes` |
| Bookmark | `/api/interactions/bookmark` → `toggle_bookmark()` (`supabase_helper.py:1044`) via `bookmarks` |
| Upload/publish | Upload flow → `award_contribution_xp(..., 'upload_document', ..., base_xp=25)` |
| Comments | `/api/interactions/comments/<doc_id>` → `document_comments` |
| Pageviews / sessions / time-on-page | `methods/analytics_tracker.py` → `document_views` |
| Referrals | migrations `015/016_referral_system` |

## ✅ 3. Admin Surface (PARTIAL — exists)

- Admin routes under `/admin/controle`, `/api/admin/stats`, `/api/admin/users`, pending-document approval queue.
- Admin analytics dashboard (`templates/admin_analytics.html`, `methods/analytics_reporter*.py`).
- Ad slots already templated: `templates/ads/banner.html`, `in_feed.html`, `sticky_mobile.html`.

## ✅ 4. Housekeeping

- Migration numbering is at `021_enable_rls_all.sql`; RLS enabled across schema; viewer-failure reports and crushes tables shipped (018–020).
- Supabase auth keys migrated to `SUPABASE_PUBLIC_API_KEY` / `SUPABASE_SECRET_API_KEY`.
