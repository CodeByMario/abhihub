-- Migration: Add notification tracking columns to file_records table
-- Purpose: Track which uploads have been notified to prevent duplicate notifications
-- Date: 2026-02-10

-- Add columns for tracking notification status
ALTER TABLE file_records 
ADD COLUMN IF NOT EXISTS upload_notified BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS notified_at TIMESTAMP WITH TIME ZONE;

-- Create index on upload_notified for faster queries
CREATE INDEX IF NOT EXISTS idx_file_records_upload_notified 
ON file_records(upload_notified, uploaded_at) 
WHERE upload_notified = FALSE;

-- Add comment to columns
COMMENT ON COLUMN file_records.upload_notified IS 'Whether user has been notified about successful upload';
COMMENT ON COLUMN file_records.notified_at IS 'Timestamp when notification was sent';
