-- Add quota tracking fields to profiles table
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS paper_quota_remaining INTEGER DEFAULT 19,
ADD COLUMN IF NOT EXISTS last_quota_reset TEXT DEFAULT '2026-05';
