-- ============================================================
-- AbhiHub Migration 015: Referral / Invite System
-- ============================================================
-- Drives zero-budget growth: every user gets a shareable referral
-- code; inviting an active peer credits both sides (via app logic).

-- Unique, human-readable referral code per user (e.g. ABHI-XK4F9Q)
ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS referral_code VARCHAR(24) UNIQUE;

-- Who invited this user (FK to the inviter's profile id)
ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS referred_by UUID REFERENCES abhihub.profiles(id) ON DELETE SET NULL;

-- Referral credit balance (spendable on view quota / perks)
ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS referral_credits INTEGER NOT NULL DEFAULT 0;

-- Track referral conversion state on the referrer side
ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS referral_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_profiles_referral_code
  ON abhihub.profiles(referral_code);

CREATE INDEX IF NOT EXISTS idx_profiles_referred_by
  ON abhihub.profiles(referred_by);

-- Backfill: assign a referral code to any existing profile missing one.
-- Uses the first 6 chars of a uuid v4 + a fixed prefix for brandability.
UPDATE abhihub.profiles
SET referral_code = 'ABHI-' || UPPER(LEFT(REPLACE(id::text, '-', ''), 6))
WHERE referral_code IS NULL;
