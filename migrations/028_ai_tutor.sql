-- ============================================================
-- AbhiHub Migration 028: AI Tutor — BYOK / Platform Key
-- ============================================================
-- NOTE (schema namespace): add_quota_fields.sql used `public.profiles`
-- instead of `abhihub.profiles`. This is a latent bug in that migration —
-- it may have silently targeted the wrong schema. All DDL below uses the
-- explicit `abhihub.` prefix which matches the live client config
-- (ClientOptions(schema="abhihub") in supabase_helper.py L111).
-- ============================================================

-- ── profiles: AI tier columns ────────────────────────────────────────────────

ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS ai_plan     TEXT NOT NULL DEFAULT 'free'
    CHECK (ai_plan IN ('free', 'byok')),
  ADD COLUMN IF NOT EXISTS ai_key_enc  TEXT,          -- Fernet-encrypted BYOK key; NULL = no key set
  ADD COLUMN IF NOT EXISTS ai_provider TEXT NOT NULL DEFAULT 'openrouter'
    CHECK (ai_provider IN ('openrouter'));             -- Constrained to one value until a second adapter is built

-- ── tutor_sessions ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS abhihub.tutor_sessions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
  doc_id         UUID NOT NULL REFERENCES abhihub.documents(id) ON DELETE CASCADE,
  summary        TEXT,                                -- rolling compacted context from older turns
  topic_map      JSONB NOT NULL DEFAULT '{}',         -- {topic: {doc_id, confidence, last_seen_at}}
  mode           TEXT NOT NULL DEFAULT 'scaffold'
    CHECK (mode IN ('scaffold', 'direct')),
  turn_count     INTEGER NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, doc_id)                            -- one active session per user+document
);

CREATE INDEX IF NOT EXISTS idx_tutor_sessions_user_id ON abhihub.tutor_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_tutor_sessions_doc_id  ON abhihub.tutor_sessions(doc_id);

-- ── ai_usage_log ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS abhihub.ai_usage_log (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID REFERENCES abhihub.profiles(id) ON DELETE SET NULL,
  session_id    UUID REFERENCES abhihub.tutor_sessions(id) ON DELETE SET NULL,
  provider      TEXT NOT NULL,                        -- e.g. 'openrouter'
  model         TEXT NOT NULL,                        -- e.g. 'google/gemma-4-31b-it:free'
  tokens_in     INTEGER NOT NULL DEFAULT 0,
  tokens_out    INTEGER NOT NULL DEFAULT 0,
  cost_usd      NUMERIC(10, 8) NOT NULL DEFAULT 0,   -- 8 decimal places; free models cost 0.00000000
  duration_ms   INTEGER,
  mode          TEXT CHECK (mode IN ('scaffold', 'direct', 'compaction')),
  override_used BOOLEAN NOT NULL DEFAULT FALSE,       -- TRUE when student switches to direct mode
  error_type    TEXT,                                 -- NULL on success; else error class name
  safety_flag   TEXT,                                 -- NULL = clean; populated for borderline check_input results (passed through, not blocked)
  finish_reason TEXT,                                 -- 'stop' | 'length' | 'error'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_user_id    ON abhihub.ai_usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_created_at ON abhihub.ai_usage_log(created_at DESC);
-- Partial index for daily cost aggregation query (the hot path for ceiling checks)
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_user_day
  ON abhihub.ai_usage_log(user_id, created_at)
  WHERE error_type IS NULL;

-- ── Grants ───────────────────────────────────────────────────────────────────

GRANT ALL PRIVILEGES ON TABLE abhihub.tutor_sessions TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.ai_usage_log   TO anon, authenticated, service_role;
