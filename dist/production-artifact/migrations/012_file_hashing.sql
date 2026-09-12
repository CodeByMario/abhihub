-- ============================================================
-- AbhiHub Migration 012: File Hashing for Duplicate Detection
-- ============================================================

-- Add file_hash column to documents table
ALTER TABLE abhihub.documents
ADD COLUMN IF NOT EXISTS file_hash text;

-- Create an index to quickly look up duplicate hashes
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON abhihub.documents(file_hash);
