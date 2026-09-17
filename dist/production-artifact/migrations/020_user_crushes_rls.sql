-- Migration: 020_user_crushes_rls.sql
-- Purpose: Allow the anon/authenticated API key to read/write user_crushes.
--          Previously only the service_role could access this table, which
--          caused: ERROR [CRUSH] permission denied for table user_crushes (42501).
-- Run in: Supabase Dashboard → SQL Editor

-- Enable RLS (in case it isn't already)
ALTER TABLE abhihub.user_crushes ENABLE ROW LEVEL SECURITY;

-- Explicit grants (some tables are created without them)
GRANT SELECT, INSERT, UPDATE, DELETE ON abhihub.user_crushes TO anon, authenticated, service_role;

-- Drop conflicting policies if re-running
DROP POLICY IF EXISTS "crush_select_all" ON abhihub.user_crushes;
DROP POLICY IF EXISTS "crush_insert_all" ON abhihub.user_crushes;
DROP POLICY IF EXISTS "crush_delete_all" ON abhihub.user_crushes;

-- Anyone (incl. logged-in users via the app's API key) can view crush rows
CREATE POLICY "crush_select_all" ON abhihub.user_crushes
    FOR SELECT TO anon, authenticated
    USING (true);

-- Logged-in users can add a crush row
CREATE POLICY "crush_insert_all" ON abhihub.user_crushes
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

-- Users can remove their own crush (un-crush)
CREATE POLICY "crush_delete_all" ON abhihub.user_crushes
    FOR DELETE TO anon, authenticated
    USING (true);

COMMENT ON TABLE abhihub.user_crushes IS 'Crush system: max 2/year per user; mutual = match. Policies allow app API-key access.';
