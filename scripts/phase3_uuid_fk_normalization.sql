-- ==============================================================================
-- PHASE 3: Referential Integrity & UUID Normalization (Schema: abhihub)
-- Fixes: Drops dependent RLS policies before type altering to prevent error 0A000,
-- safely cleans invalid strings, alters to UUID, adds FKs, and recreates policies.
-- ==============================================================================

SET search_path = abhihub, public;

BEGIN;

-- ==============================================================================
-- 1. `abhihub.user_ai_keys` (Handles dependent policy users_manage_own_ai_keys)
-- ==============================================================================
-- Step A: Drop dependent policy
DROP POLICY IF EXISTS "users_manage_own_ai_keys" ON abhihub.user_ai_keys;

-- Step B: Purge invalid / orphaned rows
DELETE FROM abhihub.user_ai_keys
WHERE user_id IS NULL
   OR user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   OR NOT EXISTS (SELECT 1 FROM abhihub.profiles p WHERE p.id = user_id::uuid);

-- Step C: Alter column to UUID
ALTER TABLE abhihub.user_ai_keys
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;

-- Step D: Add Foreign Key
ALTER TABLE abhihub.user_ai_keys
    DROP CONSTRAINT IF EXISTS fk_user_ai_keys_user;
ALTER TABLE abhihub.user_ai_keys
    ADD CONSTRAINT fk_user_ai_keys_user
    FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id) ON DELETE CASCADE;

-- Step E: Recreate policy with clean native UUID equality
CREATE POLICY "users_manage_own_ai_keys" ON abhihub.user_ai_keys
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ==============================================================================
-- 2. `abhihub.tarika_agent_state` (Handles dependent policy Allow user own tarika_agent_state)
-- ==============================================================================
-- Step A: Drop dependent policy
DROP POLICY IF EXISTS "Allow user own tarika_agent_state" ON abhihub.tarika_agent_state;

-- Step B: Purge invalid / orphaned rows
DELETE FROM abhihub.tarika_agent_state
WHERE user_id IS NULL
   OR user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   OR NOT EXISTS (SELECT 1 FROM abhihub.profiles p WHERE p.id = user_id::uuid);

-- Step C: Alter column to UUID
ALTER TABLE abhihub.tarika_agent_state
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;

-- Step D: Add Foreign Key
ALTER TABLE abhihub.tarika_agent_state
    DROP CONSTRAINT IF EXISTS fk_tarika_agent_state_user;
ALTER TABLE abhihub.tarika_agent_state
    ADD CONSTRAINT fk_tarika_agent_state_user
    FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id) ON DELETE CASCADE;

-- Step E: Recreate policy with clean native UUID equality
CREATE POLICY "Allow user own tarika_agent_state" ON abhihub.tarika_agent_state
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ==============================================================================
-- 3. `abhihub.credit_transactions`
-- ==============================================================================
UPDATE abhihub.credit_transactions
SET user_id = NULL
WHERE user_id IS NOT NULL 
  AND (
    user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    OR NOT EXISTS (SELECT 1 FROM abhihub.profiles p WHERE p.id = user_id::uuid)
  );

ALTER TABLE abhihub.credit_transactions
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;

ALTER TABLE abhihub.credit_transactions
    DROP CONSTRAINT IF EXISTS fk_credit_transactions_user;
ALTER TABLE abhihub.credit_transactions
    ADD CONSTRAINT fk_credit_transactions_user
    FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id) ON DELETE SET NULL;


-- ==============================================================================
-- 4. `abhihub.creator_wallets` & `abhihub.wallet_ledger`
-- ==============================================================================
-- creator_wallets
DELETE FROM abhihub.creator_wallets
WHERE user_id IS NULL
   OR user_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   OR NOT EXISTS (SELECT 1 FROM abhihub.profiles p WHERE p.id = user_id::uuid);

ALTER TABLE abhihub.creator_wallets
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;

ALTER TABLE abhihub.creator_wallets
    DROP CONSTRAINT IF EXISTS fk_creator_wallets_user;
ALTER TABLE abhihub.creator_wallets
    ADD CONSTRAINT fk_creator_wallets_user
    FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id) ON DELETE CASCADE;

-- wallet_ledger creator_id
DELETE FROM abhihub.wallet_ledger
WHERE creator_id IS NULL
   OR creator_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
   OR NOT EXISTS (SELECT 1 FROM abhihub.profiles p WHERE p.id = creator_id::uuid);

ALTER TABLE abhihub.wallet_ledger
    ALTER COLUMN creator_id TYPE UUID USING creator_id::uuid;

ALTER TABLE abhihub.wallet_ledger
    DROP CONSTRAINT IF EXISTS fk_wallet_ledger_creator;
ALTER TABLE abhihub.wallet_ledger
    ADD CONSTRAINT fk_wallet_ledger_creator
    FOREIGN KEY (creator_id) REFERENCES abhihub.profiles(id) ON DELETE CASCADE;

-- wallet_ledger doc_id
UPDATE abhihub.wallet_ledger
SET doc_id = NULL
WHERE doc_id IS NOT NULL 
  AND (
    doc_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    OR NOT EXISTS (SELECT 1 FROM abhihub.documents d WHERE d.id = doc_id::uuid)
  );

ALTER TABLE abhihub.wallet_ledger
    ALTER COLUMN doc_id TYPE UUID USING doc_id::uuid;

ALTER TABLE abhihub.wallet_ledger
    DROP CONSTRAINT IF EXISTS fk_wallet_ledger_doc;
ALTER TABLE abhihub.wallet_ledger
    ADD CONSTRAINT fk_wallet_ledger_doc
    FOREIGN KEY (doc_id) REFERENCES abhihub.documents(id) ON DELETE SET NULL;


-- ==============================================================================
-- 5. `abhihub.viewer_failure_reports`
-- ==============================================================================
-- Drop NOT NULL constraint so reports for generic/corrupted uploads can store NULL doc_id
ALTER TABLE abhihub.viewer_failure_reports
    ALTER COLUMN doc_id DROP NOT NULL;

UPDATE abhihub.viewer_failure_reports
SET doc_id = NULL
WHERE doc_id IS NOT NULL 
  AND (
    doc_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    OR NOT EXISTS (SELECT 1 FROM abhihub.documents d WHERE d.id = doc_id::uuid)
  );

ALTER TABLE abhihub.viewer_failure_reports
    ALTER COLUMN doc_id TYPE UUID USING doc_id::uuid;

ALTER TABLE abhihub.viewer_failure_reports
    DROP CONSTRAINT IF EXISTS fk_viewer_failure_doc;
ALTER TABLE abhihub.viewer_failure_reports
    ADD CONSTRAINT fk_viewer_failure_doc
    FOREIGN KEY (doc_id) REFERENCES abhihub.documents(id) ON DELETE SET NULL;

COMMIT;
