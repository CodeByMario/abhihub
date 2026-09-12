-- Migration 016: add referral credit/score columns (referral loop fix)
-- Apply in Supabase SQL editor (project: abhihub schema). Safe to re-run.
-- After applying, run: python tests/test_referral_flow.py  (expect PASS)

ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS referral_credits INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS referral_count  INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN abhihub.profiles.referral_credits IS 'Total view-credits earned from invites';
COMMENT ON COLUMN abhihub.profiles.referral_count  IS 'Number of users who joined via this user''s code';
