-- ============================================================================
-- Migration: Create app_feedback in abhihub schema
-- Run this in your Supabase SQL Editor
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.app_feedback (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NULL,
    name        TEXT        NOT NULL DEFAULT 'Student',
    rating      INT         NOT NULL DEFAULT 5 CHECK (rating >= 1 AND rating <= 5),
    college     TEXT        NULL,
    branch      TEXT        NULL,
    message     TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'approved',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_feedback_created_at ON abhihub.app_feedback (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_feedback_user_id    ON abhihub.app_feedback (user_id);

ALTER TABLE abhihub.app_feedback ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    -- service_role: full access
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'app_feedback'
          AND policyname = 'Allow service_role app_feedback'
    ) THEN
        CREATE POLICY "Allow service_role app_feedback"
            ON abhihub.app_feedback
            FOR ALL
            TO service_role
            USING (true);
    END IF;

    -- public/anon/authenticated: allow read (SELECT) for approved feedbacks
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'app_feedback'
          AND policyname = 'Allow public select app_feedback'
    ) THEN
        CREATE POLICY "Allow public select app_feedback"
            ON abhihub.app_feedback
            FOR SELECT
            TO anon, authenticated
            USING (status = 'approved');
    END IF;

    -- authenticated and anon: allow insert
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'app_feedback'
          AND policyname = 'Allow insert app_feedback'
    ) THEN
        CREATE POLICY "Allow insert app_feedback"
            ON abhihub.app_feedback
            FOR INSERT
            TO anon, authenticated
            WITH CHECK (true);
    END IF;
END $$;
