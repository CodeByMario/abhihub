-- ============================================================================
-- Migration: Create credit_transactions in abhihub schema
-- Run this in your Supabase SQL Editor if you wish to query payments directly in Supabase
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    order_id TEXT UNIQUE NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    utr TEXT,
    status TEXT NOT NULL DEFAULT 'initiated',
    client_ip TEXT,
    user_agent TEXT,
    admin_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_transactions_order_id ON abhihub.credit_transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON abhihub.credit_transactions(user_id);

ALTER TABLE abhihub.credit_transactions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service_role credit_transactions') THEN
        CREATE POLICY "Allow service_role credit_transactions" ON abhihub.credit_transactions FOR ALL TO service_role USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow anon select credit_transactions') THEN
        CREATE POLICY "Allow anon select credit_transactions" ON abhihub.credit_transactions FOR SELECT TO anon USING (true);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
