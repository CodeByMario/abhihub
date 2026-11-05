-- ==============================================================================
-- PHASE 4: Database Views, Atomic Counter Triggers & RPC Functions (Schema: abhihub)
-- Eliminates N+1 queries from Python and ensures atomic, real-time counter updates.
-- ==============================================================================

SET search_path = abhihub, public;

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. High-Performance Unified Catalog View (`abhihub.v_documents_catalog`)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW abhihub.v_documents_catalog AS
SELECT
    d.id,
    d.title,
    d.document_category,
    d.description,
    d.file_url,
    d.file_type,
    d.file_size_bytes,
    d.status,
    d.created_at,
    d.updated_at,
    d.exam_type,
    d.program,
    d.topics_covered,
    d.difficulty_level,
    -- Monetization
    COALESCE(d.is_paid, false) AS is_paid,
    COALESCE(d.price, 0.00) AS price,
    d.seller_id,
    d.coupon_code,
    d.coupon_discount,
    -- Counters
    COALESCE(d.view_count, 0) AS view_count,
    COALESCE(d.like_count, 0) AS like_count,
    COALESCE(d.bookmark_count, 0) AS bookmark_count,
    -- Academic Hierarchy
    d.college_id,
    c.name AS college_name,
    c.abbreviation AS college_abbr,
    d.department_id,
    dept.name AS department_name,
    dept.abbreviation AS department_abbr,
    d.subject_id,
    s.name AS subject_name,
    s.subject_code,
    COALESCE(s.semester, 1) AS semester,
    -- Uploader profile
    d.uploader_id,
    p.full_name AS uploader_name,
    p.role AS uploader_role,
    p.reputation_score AS uploader_reputation
FROM abhihub.documents d
LEFT JOIN abhihub.colleges c ON d.college_id = c.id
LEFT JOIN abhihub.departments dept ON d.department_id = dept.id
LEFT JOIN abhihub.subjects s ON d.subject_id = s.id
LEFT JOIN abhihub.profiles p ON d.uploader_id = p.id;


-- ------------------------------------------------------------------------------
-- 2. Trigger: Atomic Increment of `view_count` on `abhihub.document_views`
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION abhihub.trg_fn_increment_document_views()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE abhihub.documents
    SET view_count = COALESCE(view_count, 0) + 1
    WHERE id = NEW.document_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_view_added ON abhihub.document_views;
CREATE TRIGGER trg_document_view_added
    AFTER INSERT ON abhihub.document_views
    FOR EACH ROW
    EXECUTE FUNCTION abhihub.trg_fn_increment_document_views();


-- ------------------------------------------------------------------------------
-- 3. Trigger: Synchronize `like_count` on `abhihub.document_votes` changes
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION abhihub.trg_fn_sync_document_likes()
RETURNS TRIGGER AS $$
DECLARE
    target_doc_id UUID;
    total_likes INT;
BEGIN
    target_doc_id := COALESCE(NEW.document_id, OLD.document_id);

    SELECT COUNT(*) INTO total_likes
    FROM abhihub.document_votes
    WHERE document_id = target_doc_id AND vote = 'like';

    UPDATE abhihub.documents
    SET like_count = total_likes
    WHERE id = target_doc_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_vote_sync ON abhihub.document_votes;
CREATE TRIGGER trg_document_vote_sync
    AFTER INSERT OR UPDATE OR DELETE ON abhihub.document_votes
    FOR EACH ROW
    EXECUTE FUNCTION abhihub.trg_fn_sync_document_likes();


-- ------------------------------------------------------------------------------
-- 4. Trigger: Synchronize `bookmark_count` on `abhihub.bookmarks` changes
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION abhihub.trg_fn_sync_document_bookmarks()
RETURNS TRIGGER AS $$
DECLARE
    target_doc_id UUID;
    total_bookmarks INT;
BEGIN
    target_doc_id := COALESCE(NEW.document_id, OLD.document_id);

    SELECT COUNT(*) INTO total_bookmarks
    FROM abhihub.bookmarks
    WHERE document_id = target_doc_id;

    UPDATE abhihub.documents
    SET bookmark_count = total_bookmarks
    WHERE id = target_doc_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_bookmark_sync ON abhihub.bookmarks;
CREATE TRIGGER trg_document_bookmark_sync
    AFTER INSERT OR DELETE ON abhihub.bookmarks
    FOR EACH ROW
    EXECUTE FUNCTION abhihub.trg_fn_sync_document_bookmarks();

COMMIT;
