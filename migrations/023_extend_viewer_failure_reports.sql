-- Migration 023: Extend viewer_failure_reports with file metadata columns
-- Run once in Supabase SQL editor

-- Add columns that may not exist (safe if already present)
ALTER TABLE abhihub.viewer_failure_reports 
    ADD COLUMN IF NOT EXISTS reporter_id UUID DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS file_name TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS file_url TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS file_type TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS issue_type TEXT DEFAULT NULL;

-- Update doc_id to be nullable-friendly and ensure indexes
CREATE INDEX IF NOT EXISTS idx_vfr_reporter ON abhihub.viewer_failure_reports(reporter_email);
CREATE INDEX IF NOT EXISTS idx_vfr_type ON abhihub.viewer_failure_reports(issue_type);

-- Ensure anon role can insert reports (for users reporting broken files)
-- Note: this assumes RLS policies exist; if not, this provides minimal access
GRANT INSERT(file_name, file_url, file_type, issue_type, viewer_type, error_msg, page_url, reporter_email, reporter_id, doc_id) 
    ON abhihub.viewer_failure_reports TO anon;

-- Ensure authenticated users can insert reports
GRANT INSERT(file_name, file_url, file_type, issue_type, viewer_type, error_msg, page_url, reporter_email, reporter_id, doc_id) 
    ON abhihub.viewer_failure_reports TO authenticated;
