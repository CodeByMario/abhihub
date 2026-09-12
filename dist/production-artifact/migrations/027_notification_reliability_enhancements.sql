-- Migration: 027_notification_reliability_enhancements.sql
-- Description: Adds lifecycle columns to push_subscriptions and notification preferences to profiles

-- 1. Enhance push_subscriptions with lifecycle and device metadata
ALTER TABLE IF EXISTS abhihub.push_subscriptions
  ADD COLUMN IF NOT EXISTS platform text DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS browser text,
  ADD COLUMN IF NOT EXISTS permission_state text DEFAULT 'granted',
  ADD COLUMN IF NOT EXISTS enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS last_success_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_failure_at timestamptz,
  ADD COLUMN IF NOT EXISTS failure_code text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS revoked_at timestamptz;

-- Index for active subscriptions by user
CREATE INDEX IF NOT EXISTS idx_push_subs_user_enabled 
  ON abhihub.push_subscriptions (user_id, enabled) 
  WHERE enabled = true;

-- 2. Add notification preferences to profiles
ALTER TABLE IF EXISTS abhihub.profiles
  ADD COLUMN IF NOT EXISTS notif_push_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_email_enabled boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS notif_uploads_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_chat_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_crush_enabled boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS notif_quiet_hours_enabled boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS notif_quiet_hours_start text DEFAULT '22:00',
  ADD COLUMN IF NOT EXISTS notif_quiet_hours_end text DEFAULT '07:00';
