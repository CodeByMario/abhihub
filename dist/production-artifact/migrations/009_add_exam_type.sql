-- ============================================================
-- AbhiHub Migration 009: Add exam_type column
-- Resolves the data loss issue where exam_type/unit was stuffed
-- into the description JSON.
-- ============================================================

-- 1. Add exam_type column to documents table
ALTER TABLE abhihub.documents
  ADD COLUMN IF NOT EXISTS exam_type text;

-- 2. Backfill existing data from the JSON description field
-- The description looks like: {"subject": "...", "year": "2023", "subject_code": "...", "exam_type": "CAE1"}
-- Or similar. We extract it using JSON operations.
-- Note: Requires description to be cast to jsonb if it's currently text.
UPDATE abhihub.documents
SET exam_type = (description::jsonb)->>'exam_type'
WHERE description IS NOT NULL 
  AND description LIKE '{%'
  AND exam_type IS NULL;

-- 3. Add an index to speed up filtering by exam_type
CREATE INDEX IF NOT EXISTS idx_documents_exam_type ON abhihub.documents(exam_type);
