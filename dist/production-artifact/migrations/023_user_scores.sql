-- ============================================================
-- AbhiHub Migration 023: User Scores (Dynamic Access Economy)
-- Rolling scores + access level on profiles.
-- ============================================================

ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS abhihub_score REAL DEFAULT 0,
ADD COLUMN IF NOT EXISTS consumption_score REAL DEFAULT 0,
ADD COLUMN IF NOT EXISTS ccr REAL DEFAULT 0,
ADD COLUMN IF NOT EXISTS access_level TEXT DEFAULT 'explorer';

CREATE INDEX IF NOT EXISTS idx_profiles_access_level ON abhihub.profiles(access_level);
CREATE INDEX IF NOT EXISTS idx_profiles_abhihub_score ON abhihub.profiles(abhihub_score DESC);

-- Nightly recalculation: rolling 30-day contribution value vs consumption
-- pressure, CCR classification, and access-level assignment from scoring_config.
CREATE OR REPLACE FUNCTION abhihub.recalc_user_scores()
RETURNS void AS $$
DECLARE
  cfg JSONB;
  lvl JSONB;
  win_days INT;
BEGIN
  SELECT COALESCE(value, '30')::INT INTO win_days FROM abhihub.scoring_config WHERE key = 'rolling_window_days';
  SELECT value INTO lvl FROM abhihub.scoring_config WHERE key = 'access_levels';

  CREATE TEMP TABLE tmp_scores ON COMMIT DROP AS
  WITH contrib AS (
    -- Positive engagement received/created in the window
    SELECT user_id,
           SUM(xp_awarded) FILTER (WHERE xp_awarded > 0) AS contribution_value,
           SUM(xp_awarded) FILTER (WHERE xp_awarded < 0) AS penalties
    FROM abhihub.contribution_logs
    WHERE created_at >= NOW() - make_interval(days => COALESCE(win_days, 30))
    GROUP BY user_id
  ),
  consum AS (
    -- Consumption pressure: unique views per doc count as consumption units
    SELECT dv.user_id,
           COUNT(DISTINCT dv.document_id)::REAL AS consumption_value
    FROM abhihub.document_views dv
    WHERE dv.accessed_at >= NOW() - make_interval(days => COALESCE(win_days, 30))
    GROUP BY dv.user_id
  )
  SELECT p.id AS user_id,
         GREATEST(COALESCE(c.contribution_value,0) + COALESCE(p.reputation_score,0)*0.1
                  + COALESCE(c.penalties,0), 0) AS abhihub_score_raw,
         COALESCE(cs.consumption_value, 0) AS consumption_value,
         COALESCE(c.contribution_value,0)
           / GREATEST(COALESCE(cs.consumption_value,0), 1.0) AS ccr
  FROM abhihub.profiles p
  LEFT JOIN contrib c ON c.user_id = p.id
  LEFT JOIN consum cs ON cs.user_id = p.id;

  UPDATE abhihub.profiles p SET
    abhihub_score = t.abhihub_score_raw,
    consumption_score = t.consumption_value,
    ccr = t.ccr,
    access_level = CASE
      WHEN t.abhihub_score_raw >= COALESCE((lvl->>'community_leader')::REAL, 1500) THEN 'community_leader'
      WHEN t.abhihub_score_raw >= COALESCE((lvl->>'power_contributor')::REAL, 600) THEN 'power_contributor'
      WHEN t.abhihub_score_raw >= COALESCE((lvl->>'contributor')::REAL, 200) THEN 'contributor'
      WHEN t.abhihub_score_raw >= COALESCE((lvl->>'member')::REAL, 50) THEN 'member'
      ELSE 'explorer' END,
    updated_at = NOW()
  FROM tmp_scores t
  WHERE t.user_id = p.id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Nightly scheduling: handled by scheduled_tasks.py (APScheduler) in the app,
-- so no pg_cron dependency. To use pg_cron instead, uncomment after enabling
-- the extension: SELECT cron.schedule('abhihub-recalc-scores', '30 2 * * *',
--   'SELECT abhihub.recalc_user_scores();');
