-- Migration 032: Unified credit ledger + KYC details
-- Run in Supabase SQL editor

-- ── Table 1: user_credit_ledger ──────────────────────────────────────────────
-- Replaces scattered paper_quota_remaining direct writes.
-- All view credit mutations (earn / spend / grant) flow through this table.

CREATE TABLE IF NOT EXISTS user_credit_ledger (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    delta       int  NOT NULL,           -- positive = earn, negative = spend
    balance     int  NOT NULL,           -- running balance snapshot after this row
    reason      text NOT NULL,           -- 'upload_reward' | 'referral' | 'pack_purchase'
                                         -- | 'view_spend' | 'admin_grant' | 'tea_support'
    source      text DEFAULT 'system',   -- 'system' | 'razorpay' | 'webhook' | 'admin'
    ref_id      text,                    -- order_id / doc_id / payout_id
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ucl_user_id    ON user_credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_ucl_created_at ON user_credit_ledger(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ucl_reason     ON user_credit_ledger(reason);

-- RLS: users can only read their own rows; writes are service-role only
ALTER TABLE user_credit_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY ucl_select_own ON user_credit_ledger
    FOR SELECT USING (auth.uid() = user_id);

-- ── Table 2: user_kyc_details ────────────────────────────────────────────────
-- Stores PAN, UPI/bank details for payout eligibility.
-- PAN stored raw (server-side); masked to ABCDE****F in API responses.
-- Account number masked to ****1234 in API responses.

CREATE TABLE IF NOT EXISTS user_kyc_details (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              uuid UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    -- Identity
    full_name            text NOT NULL,
    pan_number           text NOT NULL,
    pan_verified         boolean NOT NULL DEFAULT false,

    -- UPI
    upi_id               text,
    upi_verified         boolean NOT NULL DEFAULT false,

    -- Bank
    account_number       text,               -- DO NOT return raw; mask in all API responses
    ifsc_code            text,
    bank_name            text,
    account_holder_name  text,

    -- Preferred method
    preferred_method     text NOT NULL DEFAULT 'upi' CHECK (preferred_method IN ('upi', 'bank')),

    -- Verification status
    is_verified          boolean NOT NULL DEFAULT false,
    verified_at          timestamptz,
    verified_by          uuid REFERENCES profiles(id),
    rejection_reason     text,           -- set by admin on rejection

    submitted_at         timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kyc_user_id     ON user_kyc_details(user_id);
CREATE INDEX IF NOT EXISTS idx_kyc_is_verified ON user_kyc_details(is_verified);

ALTER TABLE user_kyc_details ENABLE ROW LEVEL SECURITY;

CREATE POLICY kyc_select_own ON user_kyc_details
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY kyc_insert_own ON user_kyc_details
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY kyc_update_own ON user_kyc_details
    FOR UPDATE USING (auth.uid() = user_id);
