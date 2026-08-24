-- ============================================================
-- AbhiHub Migration 022: Scoring Config (Dynamic Access Economy)
-- All point values / thresholds admin-editable, no code changes.
-- ============================================================

CREATE TABLE IF NOT EXISTS abhihub.scoring_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed defaults (points per plan: view=0.1, like=2, bookmark=5, publish=5)
INSERT INTO abhihub.scoring_config (key, value, description) VALUES
('points', '{"view": 0.1, "like": 2, "bookmark": 5, "publish": 5, "comment": 1, "spam_penalty_min": -10, "spam_penalty_max": -25}', 'Contribution point values per action'),
('access_levels', '{"explorer": 0, "member": 50, "contributor": 200, "power_contributor": 600, "community_leader": 1500}', 'Minimum rolling AbhiHub Score per level'),
('ad_density', '{"explorer": "high", "member": "medium", "contributor": "low", "power_contributor": "very_low", "community_leader": "minimal"}', 'Ad density per access level'),
('view_dedupe', '{"window_days": 1, "max_per_doc_per_day": 1, "diminishing_returns_threshold": 500}', 'Unique-view rules: dedupe window and diminishing returns'),
('rate_limits', '{"views_per_hour": 120, "likes_per_hour": 60, "bookmarks_per_hour": 40}', 'Anti-abuse rate limits per user'),
('rolling_window_days', '30', 'Rolling window for score calculation'),
ON CONFLICT (key) DO NOTHING;

ALTER TABLE abhihub.scoring_config ENABLE ROW LEVEL SECURITY;

-- Server-side reads use the anon key; writes happen via SQL editor or
-- service key. Grant anon read + write (writes only ever come from the
-- admin economy dashboard, which is auth/admin-gated at the app layer).
DROP POLICY IF EXISTS "scoring_config_read_all" ON abhihub.scoring_config;
CREATE POLICY "scoring_config_all_anon" ON abhihub.scoring_config
    FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_scoring_config_key ON abhihub.scoring_config(key);
