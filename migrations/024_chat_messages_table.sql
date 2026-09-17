-- Migration 024: Encrypted chat messages table in Supabase
-- Run once in Supabase SQL editor

-- Create the encrypted_chat_messages table for Supabase-backed chat
-- Messages are encrypted client-side OR server-side before storage
-- Only sender and receiver can decrypt (server stores ciphertext only)
CREATE TABLE IF NOT EXISTS abhihub.chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_id   UUID NOT NULL,
    recipient_id UUID NOT NULL,
    ciphertext  TEXT NOT NULL,          -- Encrypted message content
    nonce       TEXT,                   -- Encryption nonce (for AEAD)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT NOT NULL DEFAULT 'sent',  -- sent | delivered | read
    delivered_at TIMESTAMPTZ,
    read_at     TIMESTAMPTZ
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_chat_sender ON abhihub.chat_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_chat_recipient ON abhihub.chat_messages(recipient_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON abhihub.chat_messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_conversation ON abhihub.chat_messages(sender_id, recipient_id, created_at);

-- RLS policies
-- Only sender and recipient can read/write their conversation
ALTER TABLE abhihub.chat_messages ENABLE ROW LEVEL SECURITY;

-- Policy: authenticated users can insert their own messages
CREATE POLICY "chat_insert_own" ON abhihub.chat_messages
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = sender_id);

-- Policy: users can read messages they sent or received
CREATE POLICY "chat_select_conversation" ON abhihub.chat_messages
    FOR SELECT TO authenticated
    USING (
        auth.uid() = sender_id OR auth.uid() = recipient_id
    );

-- Policy: users can update status of messages they received
CREATE POLICY "chat_update_status" ON abhihub.chat_messages
    FOR UPDATE TO authenticated
    USING (auth.uid() = recipient_id);

-- Grant necessary privileges
GRANT SELECT, INSERT, UPDATE ON abhihub.chat_messages TO anon, authenticated, service_role;
GRANT USAGE ON SEQUENCE abhihub.chat_messages_id_seq TO anon, authenticated, service_role;
