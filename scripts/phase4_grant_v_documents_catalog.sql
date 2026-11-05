-- ==============================================================================
-- FIX: Grant Select Permissions on View `v_documents_catalog` (Code: 42501)
-- Allows PostgREST API roles to read the unified catalog view.
-- ==============================================================================

SET search_path = abhihub, public;

-- Grant select permission to all Supabase API roles
GRANT SELECT ON abhihub.v_documents_catalog TO anon, authenticated, service_role;

-- Optional: ensure public schema alias has permission if exposed
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_views 
        WHERE schemaname = 'public' AND viewname = 'v_documents_catalog'
    ) THEN
        GRANT SELECT ON public.v_documents_catalog TO anon, authenticated, service_role;
    END IF;
END $$;
