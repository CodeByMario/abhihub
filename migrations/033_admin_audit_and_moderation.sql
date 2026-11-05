-- Migration 033: Admin Audit Logs, User Moderation Flags, and Site Settings
-- Target Schema: abhihub
-- Safe, idempotent execution for Supabase PostgreSQL

CREATE SCHEMA IF NOT EXISTS abhihub;

-- ── 1. Admin Audit Logs (Append-Only) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS abhihub.admin_audit_logs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp   timestamptz NOT NULL DEFAULT now(),
    admin_id    uuid,
    admin_email text NOT NULL,
    action      text NOT NULL,
    target_type text NOT NULL,
    target_id   text,
    old_value   text,
    new_value   text,
    reason      text,
    ip_address  text DEFAULT '0.0.0.0',
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON abhihub.admin_audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action    ON abhihub.admin_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_admin_id  ON abhihub.admin_audit_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_target    ON abhihub.admin_audit_logs(target_type, target_id);

ALTER TABLE abhihub.admin_audit_logs ENABLE ROW LEVEL SECURITY;

-- Add superadmin to enum if enum exists
DO $$
BEGIN
    ALTER TYPE abhihub.user_role ADD VALUE IF NOT EXISTS 'superadmin';
EXCEPTION
    WHEN undefined_object THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'abhihub' AND tablename = 'admin_audit_logs' AND policyname = 'audit_logs_read_admins'
    ) THEN
        CREATE POLICY audit_logs_read_admins ON abhihub.admin_audit_logs
            FOR SELECT USING (
                EXISTS (
                    SELECT 1 FROM abhihub.profiles 
                    WHERE abhihub.profiles.id = auth.uid() 
                    AND abhihub.profiles.role::text IN ('admin', 'superadmin')
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'abhihub' AND tablename = 'admin_audit_logs' AND policyname = 'audit_logs_service_role'
    ) THEN
        CREATE POLICY audit_logs_service_role ON abhihub.admin_audit_logs 
            FOR ALL TO service_role USING (true);
    END IF;
END $$;


-- ── 2. User Moderation Flags on abhihub.profiles table ──────────────────────
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS is_blocked      boolean DEFAULT false;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS blocked_reason  text;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS blocked_until   timestamptz;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS is_banned       boolean DEFAULT false;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS banned_reason   text;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS banned_at       timestamptz;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS banned_by       uuid;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS account_status  text DEFAULT 'active';
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS is_deleted      boolean DEFAULT false;
ALTER TABLE abhihub.profiles ADD COLUMN IF NOT EXISTS deleted_at      timestamptz;

CREATE INDEX IF NOT EXISTS idx_profiles_moderation_status 
ON abhihub.profiles(is_blocked, is_banned, account_status, is_deleted);


-- ── 3. Admin Site Settings Table ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS abhihub.admin_site_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_by  uuid,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Seed default site settings if not present
INSERT INTO abhihub.admin_site_settings (key, value) VALUES
    ('maintenance_mode', 'false'::jsonb),
    ('registration_enabled', 'true'::jsonb),
    ('uploads_enabled', 'true'::jsonb),
    ('payouts_enabled', 'true'::jsonb),
    ('ad_monetization_enabled', 'true'::jsonb),
    ('site_announcement', '""'::jsonb),
    ('min_withdrawal_inr', '100'::jsonb)
ON CONFLICT (key) DO NOTHING;

ALTER TABLE abhihub.admin_site_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'abhihub' AND tablename = 'admin_site_settings' AND policyname = 'site_settings_public_read'
    ) THEN
        CREATE POLICY site_settings_public_read ON abhihub.admin_site_settings FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'abhihub' AND tablename = 'admin_site_settings' AND policyname = 'site_settings_service_role'
    ) THEN
        CREATE POLICY site_settings_service_role ON abhihub.admin_site_settings FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- Grants
GRANT USAGE ON SCHEMA abhihub TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA abhihub TO service_role;
GRANT SELECT ON abhihub.admin_site_settings TO anon, authenticated;
