-- ==============================================================================
-- PHASE 6: Admin Database Size RPC Function (Schema: abhihub & public)
-- Enables accurate cloud stats reporting on the Admin Command Center.
-- ==============================================================================

SET search_path = abhihub, public;

CREATE OR REPLACE FUNCTION abhihub.get_db_size()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT pg_database_size(current_database());
$$;

-- Alias in public schema for PostgREST standard discovery
CREATE OR REPLACE FUNCTION public.get_db_size()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT pg_database_size(current_database());
$$;

GRANT EXECUTE ON FUNCTION abhihub.get_db_size() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_db_size() TO anon, authenticated, service_role;

-- ------------------------------------------------------------------------------
-- Grant SELECT permissions on `v_documents_catalog` to eliminate error 42501
-- ------------------------------------------------------------------------------
GRANT SELECT ON abhihub.v_documents_catalog TO anon, authenticated, service_role;

