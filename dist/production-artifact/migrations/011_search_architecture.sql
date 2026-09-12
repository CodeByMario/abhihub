-- ============================================================
-- AbhiHub Migration 011: Long-Term Search Architecture
-- ============================================================

-- 1. Subject Aliases Table (for acronyms, common misspellings, abbreviations)
CREATE TABLE IF NOT EXISTS abhihub.subject_aliases (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  subject_id uuid NOT NULL REFERENCES abhihub.subjects(id) ON DELETE CASCADE,
  alias text NOT NULL,
  priority integer DEFAULT 0,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_subject_aliases_subject_id ON abhihub.subject_aliases(subject_id);

-- 2. Search Documents (Decoupled exact/fuzzy Search Index)
CREATE TABLE IF NOT EXISTS abhihub.search_documents (
  file_id uuid PRIMARY KEY, -- Using file_id as the primary key since it is 1:1 with a document
  source text NOT NULL DEFAULT 'uploads',
  subject_id uuid REFERENCES abhihub.subjects(id) ON DELETE CASCADE,
  college_id uuid REFERENCES abhihub.colleges(id) ON DELETE SET NULL,
  department_id uuid REFERENCES abhihub.departments(id) ON DELETE SET NULL,
  semester integer CHECK (semester BETWEEN 1 AND 8),
  
  normalized_title text,
  search_vector jsonb, -- e.g., {"tnm": 100, "transform": 90, "laplace": 30}
  
  token_version integer DEFAULT 1,
  last_indexed timestamptz DEFAULT now(),
  status text DEFAULT 'ready' CHECK (status IN ('pending', 'indexing', 'ready', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_search_docs_college ON abhihub.search_documents(college_id);
CREATE INDEX IF NOT EXISTS idx_search_docs_subject ON abhihub.search_documents(subject_id);
CREATE INDEX IF NOT EXISTS idx_search_docs_status ON abhihub.search_documents(status);

-- 3. Search Manifest (Versioning and Background Pipeline Tracking)
CREATE TABLE IF NOT EXISTS abhihub.search_manifest (
  file_id uuid PRIMARY KEY REFERENCES abhihub.search_documents(file_id) ON DELETE CASCADE,
  pipeline_version integer DEFAULT 1,
  tokenizer_version integer DEFAULT 1,
  ocr_version integer DEFAULT 1,
  embedding_version integer DEFAULT 1,
  alias_version integer DEFAULT 1,
  indexed_at timestamptz DEFAULT now(),
  status text DEFAULT 'completed'
);

-- 4. Search Analytics (Self-Improving AI Feedback Loop)
CREATE TABLE IF NOT EXISTS abhihub.search_analytics (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  query text NOT NULL,
  results_count integer DEFAULT 0,
  clicked_file_id uuid, -- Can be null if they didn't click anything
  response_time_ms integer,
  user_id uuid REFERENCES abhihub.profiles(id) ON DELETE SET NULL,
  created_at timestamptz DEFAULT now()
);

-- Grants
GRANT ALL PRIVILEGES ON TABLE abhihub.subject_aliases TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.search_documents TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.search_manifest TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.search_analytics TO anon, authenticated, service_role;
