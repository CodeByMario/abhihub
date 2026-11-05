-- ============================================================
-- AbhiHub Migration 030: Search Redesign Phase 1
-- Compatible with Supabase SQL Editor and live abhihub tables
-- ============================================================

-- 0. Set search path so PostgreSQL finds gin_trgm_ops in extensions or public
SET search_path TO abhihub, public, extensions;

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS unaccent;

SET search_path TO abhihub, public, extensions;

-- 1. Subject enhancements
ALTER TABLE IF EXISTS abhihub.subjects ADD COLUMN IF NOT EXISTS abbreviation text;
ALTER TABLE IF EXISTS abhihub.subjects ADD COLUMN IF NOT EXISTS aliases text[] DEFAULT '{}';

-- 2. College enhancements
ALTER TABLE IF EXISTS abhihub.colleges ADD COLUMN IF NOT EXISTS short_name text;

-- If short_name is empty, backfill from existing abbreviation
UPDATE abhihub.colleges
SET short_name = abbreviation
WHERE short_name IS NULL AND abbreviation IS NOT NULL;

-- 3. Document search_text column, trigger & GIN trigram index
ALTER TABLE IF EXISTS abhihub.documents ADD COLUMN IF NOT EXISTS search_text text;

-- Function to auto-generate search_text on insert/update
CREATE OR REPLACE FUNCTION abhihub.generate_document_search_text()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_text := lower(
    coalesce(NEW.title, '') || ' ' ||
    coalesce(NEW.description, '') || ' ' ||
    coalesce(NEW.document_category, '') || ' ' ||
    coalesce(NEW.exam_type, '')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_search_text ON abhihub.documents;
CREATE TRIGGER trg_documents_search_text
BEFORE INSERT OR UPDATE OF title, description, document_category, exam_type
ON abhihub.documents
FOR EACH ROW
EXECUTE FUNCTION abhihub.generate_document_search_text();

-- Backfill existing documents
UPDATE abhihub.documents
SET search_text = lower(
  coalesce(title, '') || ' ' ||
  coalesce(description, '') || ' ' ||
  coalesce(document_category, '') || ' ' ||
  coalesce(exam_type, '')
)
WHERE search_text IS NULL;

-- GIN Trigram index on documents
CREATE INDEX IF NOT EXISTS idx_documents_search_trgm 
ON abhihub.documents USING gin (search_text gin_trgm_ops);

-- 4. Search Vocabulary table (search_vocab)
CREATE TABLE IF NOT EXISTS abhihub.search_vocab (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL, -- 'subject_code', 'subject_name', 'abbreviation', 'alias', 'college', 'branch', 'author', 'type'
  term text NOT NULL, -- normalised lowercase text
  label text NOT NULL, -- display label (e.g. 'UITL201 - Object Oriented Programming')
  ref_id uuid, -- referenced entity ID (subject, college, etc.)
  college_id uuid REFERENCES abhihub.colleges(id) ON DELETE CASCADE,
  weight integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  CONSTRAINT uq_search_vocab_kind_term_ref UNIQUE (kind, term, ref_id)
);

-- Indexes for search_vocab
CREATE INDEX IF NOT EXISTS idx_search_vocab_trgm ON abhihub.search_vocab USING gin (term gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_vocab_kind ON abhihub.search_vocab (kind);
CREATE INDEX IF NOT EXISTS idx_search_vocab_college ON abhihub.search_vocab (college_id);

-- Permissions for API & client roles
GRANT ALL PRIVILEGES ON TABLE abhihub.search_vocab TO anon, authenticated, service_role;
