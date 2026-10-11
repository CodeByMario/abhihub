-- ==============================================================================
-- Migration: Enforce Unique Views & Exclude Owner Self-Views for Payouts
-- Schema: abhihub
-- ==============================================================================

SET search_path = abhihub, public;

BEGIN;

-- 1. Deduplicate historical view records (keep the earliest view per document & user)
DELETE FROM abhihub.document_views
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY document_id, user_id 
                   ORDER BY accessed_at ASC, id ASC
               ) AS rnum
        FROM abhihub.document_views
        WHERE user_id IS NOT NULL
    ) duplicates
    WHERE duplicates.rnum > 1
);

-- 2. Create a Unique Index on (document_id, user_id) in document_views
-- Ensures a user can only ever have 1 view record per document.
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_views_unique_user 
ON abhihub.document_views(document_id, user_id) 
WHERE user_id IS NOT NULL;

-- 3. Trigger function: Atomic Increment of view_count ONLY on valid non-owner unique views
CREATE OR REPLACE FUNCTION abhihub.trg_fn_increment_document_views()
RETURNS TRIGGER AS $$
DECLARE
    target_uploader_id UUID;
BEGIN
    -- Retrieve document creator
    SELECT uploader_id INTO target_uploader_id 
    FROM abhihub.documents 
    WHERE id = NEW.document_id;

    -- Disallow creator self-view from incrementing view_count / payouts
    IF NEW.user_id IS NOT NULL AND NEW.user_id = target_uploader_id THEN
        RETURN NEW;
    END IF;

    -- Increment view counter atomically
    UPDATE abhihub.documents
    SET view_count = COALESCE(view_count, 0) + 1
    WHERE id = NEW.document_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4. Re-bind trigger on document_views
DROP TRIGGER IF EXISTS trg_document_view_added ON abhihub.document_views;
CREATE TRIGGER trg_document_view_added
    AFTER INSERT ON abhihub.document_views
    FOR EACH ROW
    EXECUTE FUNCTION abhihub.trg_fn_increment_document_views();

-- 5. Fast RPC Function for unique non-owner view count per creator
CREATE OR REPLACE FUNCTION abhihub.get_creator_unique_views(p_creator_id TEXT)
RETURNS BIGINT AS $$
DECLARE
    total_unique BIGINT;
BEGIN
    SELECT COUNT(DISTINCT (dv.document_id, COALESCE(dv.user_id::text, dv.ip_address)))
    INTO total_unique
    FROM abhihub.document_views dv
    JOIN abhihub.documents d ON d.id = dv.document_id
    WHERE d.uploader_id::text = p_creator_id
      AND (dv.user_id IS NULL OR dv.user_id::text != p_creator_id);

    RETURN COALESCE(total_unique, 0);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Expose in public schema for PostgREST RPC
CREATE OR REPLACE FUNCTION public.get_creator_unique_views(p_creator_id TEXT)
RETURNS BIGINT AS $$
BEGIN
    RETURN abhihub.get_creator_unique_views(p_creator_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION public.get_creator_unique_views(TEXT) TO anon, authenticated, service_role;

COMMIT;

NOTIFY pgrst, 'reload schema';
