"""
Migration: Add missing notification_type enum values.
Run: psql $DATABASE_URL -f this_file.sql
Or via Supabase dashboard SQL editor.
"""
-- These types are used by the app but missing from the enum:
--   chat_message  → used by _create_chat_notification (app.py:6821)
--   quota_deduction → used by view tracking (app.py:594)

ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'chat_message';
ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'quota_deduction';
