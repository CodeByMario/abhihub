-- ============================================================================
-- Fix: Move or Create Creator Wallet Tables in abhihub schema
-- ============================================================================

-- If previously created in public schema, move them to abhihub schema:
ALTER TABLE IF EXISTS public.creator_wallets SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.wallet_ledger SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.creator_payout_requests SET SCHEMA abhihub;

-- Create tables in abhihub schema if they do not exist
CREATE TABLE IF NOT EXISTS abhihub.creator_wallets (
    user_id TEXT PRIMARY KEY,
    pending_balance NUMERIC(10, 2) DEFAULT 0.00,
    withdrawable_balance NUMERIC(10, 2) DEFAULT 0.00,
    total_withdrawn NUMERIC(10, 2) DEFAULT 0.00,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS abhihub.wallet_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('credit', 'debit', 'payout')),
    status TEXT NOT NULL DEFAULT 'locked' CHECK (status IN ('locked', 'available', 'paid', 'cancelled')),
    doc_id TEXT,
    order_id TEXT,
    unlock_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wallet_ledger_creator_status ON abhihub.wallet_ledger(creator_id, status);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_unlock ON abhihub.wallet_ledger(status, unlock_at);

CREATE TABLE IF NOT EXISTS abhihub.creator_payout_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payout_method TEXT NOT NULL CHECK (payout_method IN ('upi', 'bank')),
    payout_details JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'rejected')),
    admin_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payout_requests_creator ON abhihub.creator_payout_requests(creator_id, status);

-- Enable RLS and permissions
ALTER TABLE abhihub.creator_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.wallet_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.creator_payout_requests ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service_role creator_wallets') THEN
        CREATE POLICY "Allow service_role creator_wallets" ON abhihub.creator_wallets FOR ALL TO service_role USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service_role wallet_ledger') THEN
        CREATE POLICY "Allow service_role wallet_ledger" ON abhihub.wallet_ledger FOR ALL TO service_role USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service_role creator_payout_requests') THEN
        CREATE POLICY "Allow service_role creator_payout_requests" ON abhihub.creator_payout_requests FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
