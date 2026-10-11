-- ============================================================================
-- Tarika AI & Multi-Provider BYOK Schema (Idempotent & RLS Enforced)
-- Schema: abhihub (Matches AbhiHub Supabase ClientOptions configuration)
-- Includes:
-- 1. Per-user encrypted AI keys (OpenAI, Gemini, OpenRouter, Groq, Anthropic, etc.)
-- 2. User-specific and provider-specific row-level security (RLS)
-- 3. Model catalog, health tracking, usage telemetry, and device telemetry
-- ============================================================================

-- Ensure abhihub schema exists
CREATE SCHEMA IF NOT EXISTS abhihub;

-- Move tables to abhihub schema if previously created in public schema
ALTER TABLE IF EXISTS public.ai_config SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.user_ai_keys SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.model_catalog SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.model_status_events SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.ai_usage_log SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.ai_incidents SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.ai_setup_checks SET SCHEMA abhihub;
ALTER TABLE IF EXISTS public.device_telemetry SET SCHEMA abhihub;

-- 1. Configuration & Feature Flags
CREATE TABLE IF NOT EXISTS abhihub.ai_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Per-User BYOK Encrypted Keys Table (Each user manages their own keys)
CREATE TABLE IF NOT EXISTS abhihub.user_ai_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,                           -- Matches auth.uid()::text
    provider TEXT NOT NULL,                          -- 'openai', 'gemini', 'openrouter', 'groq', 'anthropic', etc.
    key_ciphertext TEXT NOT NULL,                    -- Fernet-encrypted secret key
    key_hint TEXT,                                   -- Safe prefix/suffix for display (e.g. 'sk-proj-...8a1f')
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_ai_keys UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_user_ai_keys_lookup ON abhihub.user_ai_keys(user_id, provider, is_active);

-- 3. Dynamic Model Catalog (Free / Paid / Cooldown registry)
CREATE TABLE IF NOT EXISTS abhihub.model_catalog (
    id TEXT PRIMARY KEY,                             -- e.g. 'openrouter:meta-llama/llama-3.3-70b-instruct:free'
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'free_unverified',  -- free_verified | free_unverified | paid | cooldown | deprecated | disabled
    price_in NUMERIC DEFAULT 0,
    price_out NUMERIC DEFAULT 0,
    ctx INT DEFAULT 4096,
    caps TEXT[] DEFAULT '{}',                        -- vision, json, tools, code, long
    langs TEXT[] DEFAULT '{en}',
    quality_tier INT DEFAULT 2,
    rpm INT DEFAULT 20,
    rpd INT DEFAULT 200,
    tpm INT DEFAULT 40000,
    cooldown_until TIMESTAMPTZ,
    health REAL DEFAULT 1.0,
    last_synced_at TIMESTAMPTZ,
    last_ok_at TIMESTAMPTZ,
    source TEXT DEFAULT 'sync'                       -- sync | manual | learned
);

-- Ensure model_catalog columns exist if table was already created in an earlier migration
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'free_unverified';
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS price_in NUMERIC DEFAULT 0;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS price_out NUMERIC DEFAULT 0;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS ctx INT DEFAULT 4096;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS caps TEXT[] DEFAULT '{}';
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS langs TEXT[] DEFAULT '{en}';
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS quality_tier INT DEFAULT 2;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS rpm INT DEFAULT 20;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS rpd INT DEFAULT 200;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS tpm INT DEFAULT 40000;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS cooldown_until TIMESTAMPTZ;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS health REAL DEFAULT 1.0;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS last_ok_at TIMESTAMPTZ;
ALTER TABLE abhihub.model_catalog ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'sync';

CREATE INDEX IF NOT EXISTS idx_model_catalog_status ON abhihub.model_catalog(status, quality_tier);
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider ON abhihub.model_catalog(provider, status);

-- 4. Model Status Lifecycle Events
CREATE TABLE IF NOT EXISTS abhihub.model_status_events (
    id BIGSERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE abhihub.model_status_events ADD COLUMN IF NOT EXISTS old_status TEXT;
ALTER TABLE abhihub.model_status_events ADD COLUMN IF NOT EXISTS new_status TEXT;
ALTER TABLE abhihub.model_status_events ADD COLUMN IF NOT EXISTS status TEXT;

CREATE INDEX IF NOT EXISTS idx_model_status_events_created ON abhihub.model_status_events(created_at DESC);

-- 5. AI Usage & Token Accounting Log (Aligned with methods/ai_usage.py)
CREATE TABLE IF NOT EXISTS abhihub.ai_usage_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT,                                    -- NULL for guest, auth.uid()::text for authenticated
    user_tier TEXT DEFAULT 'guest',                  -- guest | auth | byok
    session_id TEXT,
    intent TEXT,
    route TEXT,                                      -- legacy alias for mode
    mode TEXT DEFAULT 'direct',                      -- scaffold | direct | compaction
    provider TEXT,
    model TEXT,                                      -- model identifier
    model_id TEXT,                                   -- provider:model alias
    tokens_in INT DEFAULT 0,
    tokens_out INT DEFAULT 0,
    duration_ms INT DEFAULT 0,                       -- request duration in ms
    latency_ms INT DEFAULT 0,                        -- legacy alias
    cost_usd NUMERIC DEFAULT 0,                      -- actual/estimated cost in USD
    cost_equiv_usd NUMERIC DEFAULT 0,                -- legacy alias
    cache_hit BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'ok',                        -- ok | 429 | error | busy
    override_used BOOLEAN DEFAULT FALSE,
    error_type TEXT,
    safety_flag TEXT,
    finish_reason TEXT DEFAULT 'stop'
);

-- Ensure all ai_usage_log columns exist for retrofitted deployments
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ok';
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'direct';
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS route TEXT;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS model TEXT;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS model_id TEXT;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS tokens_in INT DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS tokens_out INT DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS duration_ms INT DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS latency_ms INT DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS cost_usd NUMERIC DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS cost_equiv_usd NUMERIC DEFAULT 0;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT FALSE;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS override_used BOOLEAN DEFAULT FALSE;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS error_type TEXT;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS safety_flag TEXT;
ALTER TABLE abhihub.ai_usage_log ADD COLUMN IF NOT EXISTS finish_reason TEXT DEFAULT 'stop';

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_user ON abhihub.ai_usage_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_created ON abhihub.ai_usage_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_route ON abhihub.ai_usage_log(mode, status);

-- 6. Incidents and Failover Diagnostics
CREATE TABLE IF NOT EXISTS abhihub.ai_incidents (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    severity TEXT NOT NULL DEFAULT 'warn',           -- info | warn | critical
    title TEXT NOT NULL,
    details TEXT,
    resolved_at TIMESTAMPTZ,
    resolution TEXT
);

-- 7. Automated Setup & Self-Check Log
CREATE TABLE IF NOT EXISTS abhihub.ai_setup_checks (
    id BIGSERIAL PRIMARY KEY,
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    check_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    details TEXT
);

-- 8. Anonymous Client Device Telemetry (WebLLM / WebGPU capability)
CREATE TABLE IF NOT EXISTS abhihub.device_telemetry (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT,                                    -- optional
    tier INT,
    model_id TEXT,
    tps REAL,
    outcome TEXT                                     -- ok | downgraded | failed | skipped
);

-- ============================================================================
-- Permissions & Grants for PostgREST Roles
-- ============================================================================
GRANT USAGE ON SCHEMA abhihub TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA abhihub TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA abhihub TO anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON abhihub.user_ai_keys TO authenticated;
GRANT SELECT ON abhihub.model_catalog TO anon, authenticated;
GRANT SELECT, INSERT ON abhihub.ai_usage_log TO authenticated, anon;
GRANT INSERT ON abhihub.device_telemetry TO anon, authenticated;

-- ============================================================================
-- Analytics Views
-- ============================================================================

CREATE OR REPLACE VIEW abhihub.v_model_health AS
SELECT 
    provider,
    status,
    count(*) AS models,
    round(avg(health)::numeric, 2) AS avg_health,
    max(last_synced_at) AS last_sync
FROM abhihub.model_catalog
GROUP BY provider, status
ORDER BY provider;

CREATE OR REPLACE VIEW abhihub.v_daily_usage AS
SELECT 
    date_trunc('day', created_at) AS day,
    coalesce(mode, route, 'direct') AS route,
    provider,
    count(*) AS requests,
    sum(tokens_in + tokens_out) AS tokens,
    round(100.0 * avg((status = '429')::int), 1) AS pct_429,
    round(avg(coalesce(duration_ms, latency_ms))) AS avg_latency_ms,
    round(sum(coalesce(cost_usd, cost_equiv_usd))::numeric, 4) AS saved_usd
FROM abhihub.ai_usage_log
GROUP BY 1, 2, 3
ORDER BY 1 DESC;

CREATE OR REPLACE VIEW abhihub.v_free_ratio AS
SELECT 
    date_trunc('day', created_at) AS day,
    round(100.0 * avg((coalesce(mode, route) IN ('tool', 'local', 'cache', 'scaffold'))::int), 1) AS pct_no_cloud
FROM abhihub.ai_usage_log
GROUP BY 1
ORDER BY 1 DESC;

-- View: User personal usage overview
CREATE OR REPLACE VIEW abhihub.v_user_ai_usage AS
SELECT 
    user_id,
    date_trunc('day', created_at) AS day,
    count(*) AS total_requests,
    sum(tokens_in + tokens_out) AS total_tokens,
    round(sum(coalesce(cost_usd, cost_equiv_usd))::numeric, 4) AS cost_usd
FROM abhihub.ai_usage_log
WHERE user_id IS NOT NULL
GROUP BY user_id, 2
ORDER BY 2 DESC;

GRANT SELECT ON abhihub.v_model_health, abhihub.v_daily_usage, abhihub.v_free_ratio, abhihub.v_user_ai_usage TO anon, authenticated, service_role;

-- ============================================================================
-- Row Level Security (RLS) Policies
-- Enforces: Only key/log owners can read/write their rows; Service role bypasses.
-- ============================================================================

ALTER TABLE abhihub.user_ai_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.model_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.model_status_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.ai_usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.ai_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.ai_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.ai_setup_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.device_telemetry ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    -- 1. user_ai_keys policies (Strict User Isolation)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'user_ai_keys' AND policyname = 'service_role_all_user_ai_keys') THEN
        CREATE POLICY "service_role_all_user_ai_keys" 
            ON abhihub.user_ai_keys FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'user_ai_keys' AND policyname = 'users_manage_own_ai_keys') THEN
        CREATE POLICY "users_manage_own_ai_keys" 
            ON abhihub.user_ai_keys FOR ALL TO authenticated 
            USING (auth.uid()::text = user_id::text)
            WITH CHECK (auth.uid()::text = user_id::text);
    END IF;

    -- 2. model_catalog policies (Read-only for users, full for service role)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'model_catalog' AND policyname = 'service_role_all_model_catalog') THEN
        CREATE POLICY "service_role_all_model_catalog" 
            ON abhihub.model_catalog FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'model_catalog' AND policyname = 'authenticated_read_verified_models') THEN
        CREATE POLICY "authenticated_read_verified_models" 
            ON abhihub.model_catalog FOR SELECT TO authenticated, anon 
            USING (status = 'free_verified');
    END IF;

    -- 3. ai_usage_log policies (Users can read their own logs; app can log turns)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_usage_log' AND policyname = 'service_role_all_ai_usage_log') THEN
        CREATE POLICY "service_role_all_ai_usage_log" 
            ON abhihub.ai_usage_log FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_usage_log' AND policyname = 'users_read_own_usage_log') THEN
        CREATE POLICY "users_read_own_usage_log" 
            ON abhihub.ai_usage_log FOR SELECT TO authenticated 
            USING (auth.uid()::text = user_id::text);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_usage_log' AND policyname = 'allow_insert_usage_log') THEN
        CREATE POLICY "allow_insert_usage_log" 
            ON abhihub.ai_usage_log FOR INSERT TO authenticated, anon 
            WITH CHECK (TRUE);
    END IF;

    -- 4. device_telemetry (Allow insertion from client)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'device_telemetry' AND policyname = 'service_role_all_device_telemetry') THEN
        CREATE POLICY "service_role_all_device_telemetry" 
            ON abhihub.device_telemetry FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'device_telemetry' AND policyname = 'anyone_can_insert_telemetry') THEN
        CREATE POLICY "anyone_can_insert_telemetry" 
            ON abhihub.device_telemetry FOR INSERT TO authenticated, anon 
            WITH CHECK (TRUE);
    END IF;

    -- 5. Admin / Internal tables (Service role only)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_config' AND policyname = 'service_role_all_ai_config') THEN
        CREATE POLICY "service_role_all_ai_config" 
            ON abhihub.ai_config FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_incidents' AND policyname = 'service_role_all_ai_incidents') THEN
        CREATE POLICY "service_role_all_ai_incidents" 
            ON abhihub.ai_incidents FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'ai_setup_checks' AND policyname = 'service_role_all_ai_setup_checks') THEN
        CREATE POLICY "service_role_all_ai_setup_checks" 
            ON abhihub.ai_setup_checks FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'abhihub' AND tablename = 'model_status_events' AND policyname = 'service_role_all_model_status_events') THEN
        CREATE POLICY "service_role_all_model_status_events" 
            ON abhihub.model_status_events FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';

