-- Migration 016: add referral credit/score columns (referral loop fix)
-- Context: migration 015 added referral_code + referred_by, but the credit
-- columns were missed in the live DB, so register_referral() /api/referral/my-code
-- errored on referral_credits / referral_count. This completes the schema.
-- Safe to re-run: IF NOT EXISTS guards.

ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS referral_credits INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS referral_count  INTEGER NOT NULL DEFAULT 0;

-- Backfill: users who already referred someone (referred_by set on others)
-- keep count 0 — counts are incremented live by register_referral.
-- No backfill needed for credits (they only accrue on a completed referral).

COMMENT ON COLUMN abhihub.profiles.referral_credits IS 'Total view-credits earned from invites';
COMMENT ON COLUMN abhihub.profiles.referral_count  IS 'Number of users who joined via this user''s code';
