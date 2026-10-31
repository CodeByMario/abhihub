-- Migration: Add 'new_upload' to notification_type enum
-- Run via Supabase Dashboard SQL Editor if you want native 'new_upload' type in DB.
-- Note: Python code already includes auto-fallback to 'system' so notifications work even without this.

ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'new_upload';
