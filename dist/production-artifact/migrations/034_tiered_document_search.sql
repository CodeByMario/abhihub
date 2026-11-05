-- =====================================================================
-- AbhiHub Migration 034: Tiered Document Search & Suggestions
-- Target: Supabase / Postgres 15+ (Schema: abhihub)
-- Tiered ranking: Exact Code -> Title Exact -> Title Prefix -> Code Prefix
--                -> Full-Text AND -> Fuzzy Typo-Tolerant -> Full-Text OR
-- =====================================================================

SET search_path TO abhihub, public, extensions;

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. Search columns
ALTER TABLE abhihub.documents
  ADD COLUMN IF NOT EXISTS search_code  text,
  ADD COLUMN IF NOT EXISTS search_title text,
  ADD COLUMN IF NOT EXISTS search_year  int,
  ADD COLUMN IF NOT EXISTS search_vec   tsvector;

-- 2. Trigger function to populate search fields on insert/update
CREATE OR REPLACE FUNCTION abhihub.documents_search_refresh()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = abhihub, public, extensions
AS $$
DECLARE
  j        jsonb;
  v_code   text;
  v_year   int;
  v_topics text;
  v_title  text;
BEGIN
  BEGIN
    j := nullif(new.description::text, '')::jsonb;
  EXCEPTION WHEN others THEN
    j := null;
  END;
  IF j IS NULL OR jsonb_typeof(j) <> 'object' THEN
    j := '{}'::jsonb;
  END IF;

  -- Subject code extraction
  v_code := upper(coalesce(
    nullif(btrim(j->>'subject_code'), ''),
    (regexp_match(coalesce(j->>'subject', ''), '\(([A-Za-z]{2,8}[0-9]{3})\)'))[1],
    (regexp_match(coalesce(new.provider_public_id, ''), '([A-Za-z]{2,8}[0-9]{3})_[A-Za-z0-9]+$'))[1]
  ));

  -- Year extraction
  v_year := CASE
    WHEN (j->>'year') ~ '^(19|20)[0-9]{2}$' THEN (j->>'year')::int
    ELSE ((regexp_match(coalesce(new.provider_public_id, ''), '((?:19|20)[0-9]{2})'))[1])::int
  END;

  v_topics := regexp_replace(coalesce(new.topics_covered::text, ''), '[{}"]', ' ', 'g');

  -- Normalise title: drop noise prefixes and " - Unit Test"
  v_title := lower(coalesce(new.title, ''));
  v_title := regexp_replace(v_title, '\s*-\s*unit test\s*$', '');
  v_title := regexp_replace(v_title, '^(ct|cr|tt|oe|lt|es|is)\s+', '');
  v_title := btrim(regexp_replace(regexp_replace(v_title, '[^a-z0-9]+', ' ', 'g'), '\s+', ' ', 'g'));

  new.search_code  := v_code;
  new.search_title := v_title;
  new.search_year  := v_year;
  new.search_vec   :=
      setweight(to_tsvector('simple', v_title), 'A')
   || setweight(to_tsvector('simple', lower(coalesce(v_code, ''))), 'A')
   || setweight(to_tsvector('simple', lower(concat_ws(' ', new.exam_type, new.program,
                                                      new.document_category, v_year::text))), 'B')
   || setweight(to_tsvector('simple', lower(v_topics)), 'C');
  RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS trg_documents_search_refresh ON abhihub.documents;
CREATE TRIGGER trg_documents_search_refresh
  BEFORE INSERT OR UPDATE OF title, description, provider_public_id, exam_type,
                             program, document_category, topics_covered
  ON abhihub.documents
  FOR EACH ROW EXECUTE FUNCTION abhihub.documents_search_refresh();

-- Backfill existing rows
UPDATE abhihub.documents SET title = title WHERE search_vec IS NULL;

-- 3. Dedicated indexes
CREATE INDEX IF NOT EXISTS documents_search_vec_gin    ON abhihub.documents USING gin (search_vec);
CREATE INDEX IF NOT EXISTS documents_search_title_trgm ON abhihub.documents USING gin (search_title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS documents_search_title_pfx  ON abhihub.documents (search_title text_pattern_ops);
CREATE INDEX IF NOT EXISTS documents_search_code_pfx   ON abhihub.documents (search_code text_pattern_ops);
CREATE INDEX IF NOT EXISTS documents_search_code_trgm  ON abhihub.documents USING gin (search_code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS documents_filter_idx        ON abhihub.documents (status, college_id, department_id);
CREATE INDEX IF NOT EXISTS documents_search_year_idx   ON abhihub.documents (search_year);

-- 4. Tiered search function
CREATE OR REPLACE FUNCTION abhihub.search_documents(
  p_query      text,
  p_limit      int    DEFAULT 20,
  p_offset     int    DEFAULT 0,
  p_college    uuid   DEFAULT NULL,
  p_department uuid   DEFAULT NULL,
  p_subject    uuid   DEFAULT NULL,
  p_program    text   DEFAULT NULL,
  p_category   text   DEFAULT NULL,
  p_exam_type  text   DEFAULT NULL,
  p_year       int    DEFAULT NULL,
  p_status     text[] DEFAULT ARRAY['approved']
)
RETURNS TABLE (
  id                uuid,
  title             text,
  description       text,
  file_url          text,
  file_type         text,
  document_category text,
  exam_type         text,
  program           text,
  subject_id        uuid,
  college_id        uuid,
  department_id     uuid,
  status            text,
  view_count        int,
  like_count        int,
  created_at        timestamptz,
  search_code       text,
  search_year       int,
  score             real,
  match_type        text
)
LANGUAGE plpgsql
STABLE
SET search_path = abhihub, public, extensions
AS $$
#variable_conflict use_column
DECLARE
  q        text;
  q_norm   text;
  v_txt    text;
  v_code   text;
  v_year   int;
  v_and    text;
  v_or     text;
  v_tsq    tsquery;
  v_tsq_or tsquery;
  v_lim    int;
BEGIN
  q := lower(btrim(coalesce(p_query, '')));
  IF length(q) < 2 THEN
    RETURN;
  END IF;
  v_lim := least(greatest(coalesce(p_limit, 20), 1), 100);

  PERFORM set_config('pg_trgm.similarity_threshold', '0.4', true);
  PERFORM set_config('pg_trgm.word_similarity_threshold', '0.4', true);

  -- Query understanding
  v_code := upper((regexp_match(q, '\m([a-z]{2,8}[0-9]{3})\M'))[1]);
  v_year := ((regexp_match(q, '\m((?:19|20)[0-9]{2})\M'))[1])::int;
  q_norm := btrim(regexp_replace(q, '[^a-z0-9]+', ' ', 'g'));

  v_txt := regexp_replace(q, '\m[a-z]{2,8}[0-9]{3}\M', ' ', 'g');
  v_txt := regexp_replace(v_txt, '\m(?:19|20)[0-9]{2}\M', ' ', 'g');
  v_txt := regexp_replace(v_txt, '[^a-z0-9]+', ' ', 'g');
  v_txt := regexp_replace(v_txt, '\m(and|of|the|to|for|in|a|an|with)\M', ' ', 'g');
  v_txt := btrim(regexp_replace(v_txt, '\s+', ' ', 'g'));

  IF v_txt <> '' THEN
    SELECT string_agg(w || ':*', ' & '), string_agg(w || ':*', ' | ')
      INTO v_and, v_or
      FROM unnest(string_to_array(v_txt, ' ')) AS w
     WHERE w <> '';
    v_tsq    := to_tsquery('simple', v_and);
    v_tsq_or := to_tsquery('simple', v_or);
  END IF;

  IF v_code IS NULL AND v_tsq IS NULL AND v_year IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH strong AS (
    -- 1. Code exact / prefix
    SELECT d.id, (CASE WHEN d.search_code = v_code THEN 100.0 ELSE 85.0 END)::float8 AS sc,
           (CASE WHEN d.search_code = v_code THEN 'code_exact' ELSE 'code_prefix' END)::text AS mt
      FROM abhihub.documents d
     WHERE v_code IS NOT NULL
       AND d.search_code LIKE v_code || '%'
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 2. Title exact
    SELECT d.id, 98.0::float8, 'title_exact'::text
      FROM abhihub.documents d
     WHERE q_norm <> '' AND d.search_title = q_norm
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 3. Title prefix
    SELECT d.id, 90.0::float8, 'title_prefix'::text
      FROM abhihub.documents d
     WHERE length(q_norm) >= 3 AND d.search_title LIKE q_norm || '%'
       AND d.search_title <> q_norm
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 4. Full-text AND match
    SELECT d.id, (50.0 + 30.0 * ts_rank_cd(d.search_vec, v_tsq, 32))::float8, 'fulltext'::text
      FROM abhihub.documents d
     WHERE v_tsq IS NOT NULL AND d.search_vec @@ v_tsq
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 5. Year-only query
    SELECT d.id, 40.0::float8, 'year'::text
      FROM abhihub.documents d
     WHERE v_tsq IS NULL AND v_code IS NULL AND v_year IS NOT NULL
       AND d.search_year = v_year
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
  ),
  weak AS (
    -- 6. Typo-tolerant title
    SELECT d.id, (35.0 + 30.0 * word_similarity(v_txt, d.search_title))::float8 AS sc, 'fuzzy_title'::text AS mt
      FROM abhihub.documents d
     WHERE (SELECT count(*) FROM strong) < v_lim
       AND length(v_txt) >= 3 AND v_txt <% d.search_title
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 7. Typo-tolerant code
    SELECT d.id, (35.0 + 30.0 * similarity(d.search_code, v_code))::float8, 'fuzzy_code'::text
      FROM abhihub.documents d
     WHERE (SELECT count(*) FROM strong) < v_lim
       AND v_code IS NOT NULL AND d.search_code % v_code
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
    UNION ALL
    -- 8. Fallback OR match
    SELECT d.id, (20.0 + 15.0 * ts_rank_cd(d.search_vec, v_tsq_or, 32))::float8, 'fulltext_any'::text
      FROM abhihub.documents d
     WHERE (SELECT count(*) FROM strong) < v_lim
       AND v_tsq_or IS NOT NULL AND d.search_vec @@ v_tsq_or
       AND (p_status IS NULL OR d.status::text = ANY(p_status))
       AND (p_college IS NULL OR d.college_id = p_college)
       AND (p_department IS NULL OR d.department_id = p_department)
       AND (p_subject IS NULL OR d.subject_id = p_subject)
       AND (p_program IS NULL OR lower(d.program::text) = lower(p_program))
       AND (p_category IS NULL OR lower(d.document_category::text) = lower(p_category))
       AND (p_exam_type IS NULL OR lower(d.exam_type::text) = lower(p_exam_type))
       AND (p_year IS NULL OR d.search_year = p_year)
  ),
  hits AS (
    SELECT h.id, max(h.sc) AS sc, (array_agg(h.mt ORDER BY h.sc DESC))[1] AS mt
      FROM (SELECT * FROM strong UNION ALL SELECT * FROM weak) h
     GROUP BY h.id
  )
  SELECT d.id, d.title, d.description::text, d.file_url, d.file_type::text,
         d.document_category::text, d.exam_type::text, d.program::text,
         d.subject_id, d.college_id, d.department_id, d.status::text,
         coalesce(d.view_count, 0)::int, coalesce(d.like_count, 0)::int, d.created_at,
         d.search_code, d.search_year,
         (h.sc + CASE WHEN v_year IS NOT NULL AND d.search_year = v_year THEN 5 ELSE 0 END)::real,
         h.mt
    FROM hits h
    JOIN abhihub.documents d ON d.id = h.id
   ORDER BY 18 DESC, d.search_year DESC NULLS LAST, coalesce(d.view_count, 0) DESC, d.created_at DESC, d.id
   LIMIT v_lim
  OFFSET greatest(coalesce(p_offset, 0), 0);
END;
$$;

-- 5. Autocomplete suggestions function
CREATE OR REPLACE FUNCTION abhihub.suggest_documents(
  p_query  text,
  p_limit  int    DEFAULT 8,
  p_status text[] DEFAULT ARRAY['approved']
)
RETURNS TABLE (suggestion text, doc_count bigint)
LANGUAGE sql
STABLE
SET search_path = abhihub, public, extensions
AS $$
  SELECT initcap(d.search_title) AS suggestion, count(*) AS doc_count
    FROM abhihub.documents d
   WHERE length(btrim(coalesce(p_query, ''))) >= 2
     AND d.search_title LIKE
         btrim(regexp_replace(lower(p_query), '[^a-z0-9]+', ' ', 'g')) || '%'
     AND (p_status IS NULL OR d.status::text = ANY(p_status))
   GROUP BY d.search_title
   ORDER BY count(*) DESC, d.search_title
   LIMIT least(greatest(coalesce(p_limit, 8), 1), 20);
$$;

-- 6. Permissions
GRANT EXECUTE ON FUNCTION abhihub.search_documents(text,int,int,uuid,uuid,uuid,text,text,text,int,text[])
  TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION abhihub.suggest_documents(text,int,text[])
  TO anon, authenticated, service_role;
