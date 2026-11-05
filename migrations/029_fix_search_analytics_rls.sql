-- Migration 029: Allow anon and authenticated to insert into search_analytics
-- Run via Supabase Dashboard -> SQL Editor

-- 1. Ensure table has RLS enabled
ALTER TABLE IF EXISTS search_analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS abhihub.search_analytics ENABLE ROW LEVEL SECURITY;

-- 2. Drop existing policy if any to avoid duplicates
DROP POLICY IF EXISTS "anon_insert_search_analytics" ON search_analytics;
DROP POLICY IF EXISTS "anon_insert_search_analytics" ON abhihub.search_analytics;
DROP POLICY IF EXISTS "public_insert_search_analytics" ON search_analytics;
DROP POLICY IF EXISTS "public_insert_search_analytics" ON abhihub.search_analytics;

-- 3. Create permissive INSERT policy for anon and authenticated
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'search_analytics' AND schemaname = 'public') THEN
        CREATE POLICY "public_insert_search_analytics"
        ON public.search_analytics
        FOR INSERT
        TO anon, authenticated
        WITH CHECK (true);
    END IF;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'search_analytics' AND schemaname = 'abhihub') THEN
        CREATE POLICY "public_insert_search_analytics"
        ON abhihub.search_analytics
        FOR INSERT
        TO anon, authenticated
        WITH CHECK (true);
    END IF;
END $$;
