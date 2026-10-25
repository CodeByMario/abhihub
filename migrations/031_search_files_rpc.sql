-- ============================================================
-- AbhiHub Migration 031: search_files RPC
-- High performance trigram-ranked search function for abhihub.documents
-- ============================================================

SET search_path TO abhihub, public, extensions;

CREATE OR REPLACE FUNCTION abhihub.search_files(
  query_text text DEFAULT NULL,
  target_college_id uuid DEFAULT NULL,
  target_department_id uuid DEFAULT NULL,
  target_semester int DEFAULT NULL,
  target_category text DEFAULT NULL,
  target_subject_id uuid DEFAULT NULL,
  target_year text DEFAULT NULL,
  limit_count int DEFAULT 50
)
RETURNS TABLE (
  id uuid,
  title text,
  file_url text,
  document_category text,
  file_type text,
  view_count int,
  like_count int,
  bookmark_count int,
  created_at timestamptz,
  description text,
  exam_type text,
  college_id uuid,
  department_id uuid,
  subject_id uuid,
  uploader_name text,
  college_name text,
  subject_name text,
  subject_code text,
  semester int,
  rank_score real
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = abhihub, public, extensions
AS $$
DECLARE
  clean_q text := lower(trim(coalesce(query_text, '')));
BEGIN
  RETURN QUERY
  SELECT 
    d.id,
    d.title,
    d.file_url,
    d.document_category,
    d.file_type,
    coalesce(d.view_count, 0) AS view_count,
    coalesce(d.like_count, 0) AS like_count,
    coalesce(d.bookmark_count, 0) AS bookmark_count,
    d.created_at,
    d.description,
    d.exam_type,
    d.college_id,
    d.department_id,
    d.subject_id,
    p.full_name AS uploader_name,
    c.name AS college_name,
    s.name AS subject_name,
    s.subject_code,
    s.semester,
    (
      -- Similarity score using trigrams if query_text is provided
      CASE 
        WHEN clean_q = '' THEN 1.0
        WHEN lower(d.title) = clean_q THEN 100.0
        WHEN lower(s.subject_code) = clean_q THEN 95.0
        WHEN lower(s.abbreviation) = clean_q THEN 90.0
        WHEN d.title ILIKE clean_q || '%' THEN 80.0
        ELSE (
          greatest(
            word_similarity(clean_q, coalesce(d.title, '')),
            word_similarity(clean_q, coalesce(s.name, '')),
            word_similarity(clean_q, coalesce(s.subject_code, ''))
          ) * 50.0
        )
      END
      + coalesce(ln(1 + coalesce(d.view_count, 0) + 5 * coalesce(d.like_count, 0)), 0)
    )::real AS rank_score
  FROM abhihub.documents d
  LEFT JOIN abhihub.profiles p ON p.id = d.uploader_id
  LEFT JOIN abhihub.colleges c ON c.id = d.college_id
  LEFT JOIN abhihub.subjects s ON s.id = d.subject_id
  WHERE d.status = 'approved'
    AND (target_college_id IS NULL OR d.college_id = target_college_id)
    AND (target_department_id IS NULL OR d.department_id = target_department_id)
    AND (target_semester IS NULL OR s.semester = target_semester)
    AND (target_subject_id IS NULL OR d.subject_id = target_subject_id)
    AND (target_category IS NULL OR target_category = 'All types' OR d.document_category ILIKE '%' || target_category || '%')
    AND (target_year IS NULL OR d.title ILIKE '%' || target_year || '%')
    AND (
      clean_q = ''
      OR d.search_text % clean_q
      OR d.title ILIKE '%' || clean_q || '%'
      OR s.subject_code ILIKE '%' || clean_q || '%'
      OR s.abbreviation ILIKE clean_q
    )
  ORDER BY rank_score DESC, d.created_at DESC
  LIMIT limit_count;
END;
$$;

GRANT EXECUTE ON FUNCTION abhihub.search_files TO anon, authenticated, service_role;
