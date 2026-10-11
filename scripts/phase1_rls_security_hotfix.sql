-- ==============================================================================
-- PHASE 1: RLS Security Policy Lockdown (Schema: abhihub)
-- Safe, zero-downtime, no table/data modifications.
-- Closes critical anonymous data leakage and arbitrary write access.
-- ==============================================================================

SET search_path = abhihub, public;

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. Secure `abhihub.user_crushes` (Drop leaky open-access policies)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "crush_select_all" ON abhihub.user_crushes;
DROP POLICY IF EXISTS "crush_insert_all" ON abhihub.user_crushes;
DROP POLICY IF EXISTS "crush_delete_all" ON abhihub.user_crushes;

-- Ensure owner-only policies exist and are enforced
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'user_crushes' AND policyname = 'crushes_select'
    ) THEN
        CREATE POLICY "crushes_select" ON abhihub.user_crushes
            FOR SELECT TO authenticated
            USING ((from_user = auth.uid()) OR (to_user = auth.uid()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'user_crushes' AND policyname = 'crushes_insert'
    ) THEN
        CREATE POLICY "crushes_insert" ON abhihub.user_crushes
            FOR INSERT TO authenticated
            WITH CHECK (from_user = auth.uid());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'user_crushes' AND policyname = 'crushes_delete'
    ) THEN
        CREATE POLICY "crushes_delete" ON abhihub.user_crushes
            FOR DELETE TO authenticated
            USING (from_user = auth.uid());
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 2. Secure `abhihub.scoring_config` (Prevent anonymous modifications)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "scoring_config_all_anon" ON abhihub.scoring_config;

-- Public/authenticated can READ scoring config
CREATE POLICY "scoring_config_read" ON abhihub.scoring_config
    FOR SELECT TO anon, authenticated
    USING (true);

-- Only service role can modify scoring config
CREATE POLICY "scoring_config_service_manage" ON abhihub.scoring_config
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);


-- ------------------------------------------------------------------------------
-- 3. Clean up duplicate policies on `abhihub.viewer_failure_reports`
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "allow_select_reports" ON abhihub.viewer_failure_reports;
DROP POLICY IF EXISTS "allow_insert_reports" ON abhihub.viewer_failure_reports;


-- ------------------------------------------------------------------------------
-- 4. Secure `abhihub.ai_usage_log` (Prevent unauthorized deletion / modification)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "ai_usage_log_allow_all" ON abhihub.ai_usage_log;

COMMIT;
