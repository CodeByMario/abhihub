-- Migration 025: Add NaCl key pair columns to profiles for E2E chat encryption
-- Run once in Supabase SQL editor

-- Add public_key and private_key columns to profiles table
ALTER TABLE abhihub.profiles 
    ADD COLUMN IF NOT EXISTS public_key TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS private_key TEXT DEFAULT NULL;

-- Index for key lookup
CREATE INDEX IF NOT EXISTS idx_profiles_public_key ON abhihub.profiles(public_key) WHERE public_key IS NOT NULL;

-- Note: private_key should NEVER be exposed via the anon client.
-- RLS policy ensures only the owner can read their own private_key.
-- For maximum security, prefer client-side key generation with only
-- the public key stored server-side (private key stays on device).
