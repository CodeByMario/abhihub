-- ============================================================
-- AbhiHub Migration 017: Add program column to documents
-- ============================================================
-- Tracks the academic program for each document:
-- b.tech, m.tech, mba, bsc, msc, phd, diplomas, etc.
-- Default backfill: 'b.tech' for all existing documents.

ALTER TABLE abhihub.documents
  ADD COLUMN IF NOT EXISTS program text;

-- Backfill existing rows with 'b.tech' (engineering default)
UPDATE abhihub.documents
SET program = 'b.tech'
WHERE program IS NULL;

-- Index for filtering by program
CREATE INDEX IF NOT EXISTS idx_documents_program ON abhihub.documents(program);
