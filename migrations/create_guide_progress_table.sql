-- ============================================================================
-- Migration: Create guide_progress in abhihub schema
-- Run this in your Supabase SQL Editor
-- Matches the session dict schema used by methods/guide_service.py
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.guide_progress (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,
    guide_id    TEXT        NOT NULL,
    version     INT         NOT NULL DEFAULT 1,
    status      TEXT        NOT NULL DEFAULT 'not_started',
                            -- not_started | in_progress | completed | dismissed
    current_step INT        NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_guide_progress_user_guide UNIQUE (user_id, guide_id)
);

CREATE INDEX IF NOT EXISTS idx_guide_progress_user_id  ON abhihub.guide_progress (user_id);
CREATE INDEX IF NOT EXISTS idx_guide_progress_guide_id ON abhihub.guide_progress (guide_id);

ALTER TABLE abhihub.guide_progress ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    -- service_role: full access (used by init_supabase_admin)
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'guide_progress'
          AND policyname = 'Allow service_role guide_progress'
    ) THEN
        CREATE POLICY "Allow service_role guide_progress"
            ON abhihub.guide_progress
            FOR ALL
            TO service_role
            USING (true);
    END IF;

    -- authenticated: users can read/write their own rows only
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'guide_progress'
          AND policyname = 'Allow authenticated own guide_progress'
    ) THEN
        CREATE POLICY "Allow authenticated own guide_progress"
            ON abhihub.guide_progress
            FOR ALL
            TO authenticated
            USING (user_id = auth.uid()::TEXT)
            WITH CHECK (user_id = auth.uid()::TEXT);
    END IF;

    -- anon: SELECT only (fallback when init_supabase_admin unavailable)
    -- Writes for guest sessions are always done via service_role client
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'abhihub'
          AND tablename  = 'guide_progress'
          AND policyname = 'Allow anon select guide_progress'
    ) THEN
        CREATE POLICY "Allow anon select guide_progress"
            ON abhihub.guide_progress
            FOR SELECT
            TO anon
            USING (true);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
