-- =====================================================================
-- 009_search_v3_foundation.sql
-- AbhiHub search v3, Step 1: normalization, indexes, aliases, analytics
-- Idempotent: safe to run more than once.
-- Run in Supabase SQL Editor
-- =====================================================================

-- 0. Set search_path so PostgreSQL finds gin_trgm_ops (Supabase stores extensions in 'extensions')
SET search_path TO abhihub, public, extensions;

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

BEGIN;

SET search_path TO abhihub, public, extensions;

-- ---------------------------------------------------------------------
-- 1. Immutable normalizers (required for generated columns and indexes)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION abhihub.norm_code(t text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT lower(regexp_replace(coalesce(t, ''), '[^a-zA-Z0-9]+', '', 'g'))
$$;

CREATE OR REPLACE FUNCTION abhihub.norm_text(t text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT btrim(lower(regexp_replace(coalesce(t, ''), '[^a-zA-Z0-9]+', ' ', 'g')))
$$;

-- ---------------------------------------------------------------------
-- 2. Subjects: normalized columns + indexes
-- ---------------------------------------------------------------------
ALTER TABLE abhihub.subjects
    ADD COLUMN IF NOT EXISTS subject_code_norm text
    GENERATED ALWAYS AS (abhihub.norm_code(subject_code)) STORED;

ALTER TABLE abhihub.subjects
    ADD COLUMN IF NOT EXISTS name_norm text
    GENERATED ALWAYS AS (abhihub.norm_text(name)) STORED;

CREATE INDEX IF NOT EXISTS idx_subjects_code_norm
    ON abhihub.subjects (subject_code_norm text_pattern_ops);

CREATE INDEX IF NOT EXISTS idx_subjects_name_norm_trgm
    ON abhihub.subjects USING gin (name_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_subjects_code_norm_trgm
    ON abhihub.subjects USING gin (subject_code_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_subjects_dept_sem
    ON abhihub.subjects (department_id, semester);

-- ---------------------------------------------------------------------
-- 3. Subject aliases: normalized alias + dedupe + unique index
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS abhihub.subject_aliases (
    id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    subject_id  uuid NOT NULL REFERENCES abhihub.subjects(id) ON DELETE CASCADE,
    alias       text NOT NULL,
    priority    integer DEFAULT 0,
    created_at  timestamptz DEFAULT now()
);

ALTER TABLE abhihub.subject_aliases
    ADD COLUMN IF NOT EXISTS alias_norm text
    GENERATED ALWAYS AS (abhihub.norm_text(alias)) STORED;

DELETE FROM abhihub.subject_aliases a
USING abhihub.subject_aliases b
WHERE a.alias_norm = b.alias_norm
  AND a.subject_id = b.subject_id
  AND a.id::text > b.id::text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_subject_aliases_norm_subject
    ON abhihub.subject_aliases (alias_norm, subject_id);

CREATE INDEX IF NOT EXISTS idx_subject_aliases_norm
    ON abhihub.subject_aliases (alias_norm text_pattern_ops);

-- ---------------------------------------------------------------------
-- 4. College aliases (supports groups: "soa" -> several colleges)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS abhihub.college_aliases (
    id          bigserial PRIMARY KEY,
    college_id  uuid NOT NULL REFERENCES abhihub.colleges(id) ON DELETE CASCADE,
    alias       text NOT NULL,
    alias_norm  text GENERATED ALWAYS AS (abhihub.norm_text(alias)) STORED,
    is_group    boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_college_aliases_norm_college
    ON abhihub.college_aliases (alias_norm, college_id);

-- ---------------------------------------------------------------------
-- 5. Documents: hot-path indexes + title full-text + trigram
-- ---------------------------------------------------------------------
ALTER TABLE abhihub.documents
    ADD COLUMN IF NOT EXISTS title_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_documents_status_subject
    ON abhihub.documents (status, subject_id);

CREATE INDEX IF NOT EXISTS idx_documents_status_college_dept
    ON abhihub.documents (status, college_id, department_id);

CREATE INDEX IF NOT EXISTS idx_documents_title_tsv
    ON abhihub.documents USING gin (title_tsv);

CREATE INDEX IF NOT EXISTS idx_documents_title_trgm
    ON abhihub.documents USING gin (lower(title) gin_trgm_ops);

-- ---------------------------------------------------------------------
-- 6. Search analytics (zero-result log drives alias growth)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS abhihub.search_analytics (
    id             bigserial PRIMARY KEY,
    query_raw      text NOT NULL,
    query_norm     text,
    parsed         jsonb,
    results_count  int  NOT NULL DEFAULT 0,
    relaxed        boolean NOT NULL DEFAULT false,
    latency_ms     int,
    clicked_doc_id uuid,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_analytics_zero
    ON abhihub.search_analytics (created_at DESC) WHERE results_count = 0;

ALTER TABLE abhihub.college_aliases  ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.search_analytics ENABLE ROW LEVEL SECURITY;

GRANT ALL PRIVILEGES ON TABLE abhihub.subject_aliases TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.college_aliases TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.search_analytics TO anon, authenticated, service_role;

-- ---------------------------------------------------------------------
-- 7. Seed subject aliases
-- ---------------------------------------------------------------------
WITH seed(alias, name_regex, priority) AS (VALUES
    ('os',        '^operating systems?$',                          1),
    ('operating system', '^operating systems?$',                   2),
    ('dbms',      'database management',                           1),
    ('db',        'database management',                           3),
    ('daa',       'design (and|&) analysis of algorithms?',        1),
    ('algo',      'design (and|&) analysis of algorithms?',        2),
    ('algorithms','design (and|&) analysis of algorithms?',        3),
    ('toc',       'theory of computation|formal languages?',       1),
    ('flat',      'theory of computation|formal languages?',       1),
    ('automata',  'theory of computation|formal languages?',       2),
    ('coa',       'computer organi[sz]ation',                      1),
    ('cao',       'computer organi[sz]ation',                      1),
    ('cn',        'computer networks?',                            1),
    ('nw',        'computer networks?',                            2),
    ('networks',  'computer networks?',                            2),
    ('wt',        'web tech|internet (and|&) web',                 1),
    ('webtech',   'web tech|internet (and|&) web',                 1),
    ('oop',       'object.oriented',                               1),
    ('oops',      'object.oriented',                               1),
    ('java',      'object.oriented.*java|java',                    2),
    ('dld',       'digital (logic|electronics)',                   1),
    ('de',        'digital (logic|electronics)',                   2),
    ('ai',        'artificial intelligence',                       1),
    ('ml',        'machine learning',                              1),
    ('cd',        'compiler design',                               1),
    ('se',        'software engineering',                          1),
    ('ds',        'data structures?',                              1),
    ('dsa',       'data structures?',                              1),
    ('mp',        'microprocessors?',                              1),
    ('up',        'microprocessors?',                              2),
    ('mc',        'microcontrollers?',                             2),
    ('m1',        '^(engineering )?mathematics[- ]?(i|1)$',        1),
    ('m2',        '^(engineering )?mathematics[- ]?(ii|2)$',       1),
    ('m3',        '^(engineering )?mathematics[- ]?(iii|3)$',      1),
    ('maths 1',   '^(engineering )?mathematics[- ]?(i|1)$',        2),
    ('maths 2',   '^(engineering )?mathematics[- ]?(ii|2)$',       2),
    ('maths 3',   '^(engineering )?mathematics[- ]?(iii|3)$',      2),
    ('maths',     '^(engineering )?mathematics',                   3),
    ('chem',      '^(engineering )?chemistry',                     1),
    ('physics',   '^(engineering )?physics',                       2),
    ('stats',     'statistics|probability',                        1),
    ('calc',      'calculus',                                      1)
)
INSERT INTO abhihub.subject_aliases (subject_id, alias, priority)
SELECT s.id, seed.alias, seed.priority
FROM seed
JOIN abhihub.subjects s ON s.name_norm ~* seed.name_regex
ON CONFLICT (alias_norm, subject_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- 8. Seed college aliases
-- ---------------------------------------------------------------------
WITH seed(alias, name_regex, is_group) AS (VALUES
    ('iter',  'iter|institute of technical education', false),
    ('soa',   'iter|institute of technical education|soa|siksha', true),
    ('kiit',  'kiit|kalinga institute',               false),
    ('vssut', 'vssut|veer surendra',                  false),
    ('outr',  'outr|odisha university of technology', false),
    ('cet',   'college of engineering',               false)
)
INSERT INTO abhihub.college_aliases (college_id, alias, is_group)
SELECT c.id, seed.alias, seed.is_group
FROM seed
JOIN abhihub.colleges c ON lower(c.name) ~* seed.name_regex
ON CONFLICT (alias_norm, college_id) DO NOTHING;

COMMIT;
