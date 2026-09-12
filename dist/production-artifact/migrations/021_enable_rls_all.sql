-- ============================================================
-- Migration: 021_enable_rls_all.sql
-- Purpose: Enable RLS on ALL existing tables in the abhihub schema
--          and add sensible default policies.
--
-- Access model:
--   - READ (SELECT): public (anon + authenticated) on all tables
--   - WRITE: two tiers:
--       * APP-WRITE TABLES (anon allowed): documents, profiles,
--         document_views, user_crushes, user_sessions,
--         security_audit_logs, file_records — the Flask backend uses
--         the anon API key server-side, so these need anon grants.
--       * ALL OTHER TABLES: authenticated users only.
--
-- Run: Supabase Dashboard → SQL Editor → paste → Run
-- ============================================================

-- Tables where the Flask backend writes via the anon key
DO $$
DECLARE
  app_write_tables text[] := ARRAY[
    'documents',
    'profiles',
    'document_views',
    'user_crushes',
    'user_sessions',
    'security_audit_logs',
    'file_records'
  ];
  t text;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'abhihub'
  LOOP
    -- 1. Enable RLS
    EXECUTE format('ALTER TABLE abhihub.%I ENABLE ROW LEVEL SECURITY', t);

    -- 2. Public read on every table
    EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_select', t);
    EXECUTE format(
      'CREATE POLICY %I ON abhihub.%I FOR SELECT TO anon, authenticated USING (true)',
      t || '_rls_select', t);

    -- 3. Write access tier
    IF t = ANY (app_write_tables) THEN
      -- App-write tables: anon + authenticated can insert/update/delete
      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_insert', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR INSERT TO anon, authenticated WITH CHECK (true)',
        t || '_rls_insert', t);

      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_update', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true)',
        t || '_rls_update', t);

      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_delete', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR DELETE TO anon, authenticated USING (true)',
        t || '_rls_delete', t);

      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON abhihub.%I TO anon, authenticated, service_role', t);
      RAISE NOTICE 'RLS enabled (public read + anon write) on abhihub.%', t;
    ELSE
      -- Everything else: authenticated-only writes
      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_insert', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR INSERT TO authenticated WITH CHECK (true)',
        t || '_rls_insert', t);

      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_update', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR UPDATE TO authenticated USING (true) WITH CHECK (true)',
        t || '_rls_update', t);

      EXECUTE format('DROP POLICY IF EXISTS %I ON abhihub.%I', t || '_rls_delete', t);
      EXECUTE format(
        'CREATE POLICY %I ON abhihub.%I FOR DELETE TO authenticated USING (true)',
        t || '_rls_delete', t);

      EXECUTE format(
        'GRANT SELECT ON abhihub.%I TO anon', t);
      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON abhihub.%I TO authenticated, service_role', t);
      RAISE NOTICE 'RLS enabled (public read + authed write) on abhihub.%', t;
    END IF;
  END LOOP;
END $$;

-- ============================================================
-- Verify: list all abhihub tables with their RLS status
-- ============================================================
SELECT schemaname, tablename, rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'abhihub'
ORDER BY tablename;

-- Verify: count policies per table
SELECT tablename, COUNT(policyname) AS policy_count
FROM pg_policies
WHERE schemaname = 'abhihub'
GROUP BY tablename
ORDER BY tablename;
