-- ============================================================================
-- Table: abhihub.tarika_agent_state
-- Purpose: Partitioned memory store for Tarika goal tracking & autonomous loop
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.tarika_agent_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    goal TEXT NOT NULL,
    completed_summary TEXT DEFAULT '',
    remaining JSONB DEFAULT '[]'::jsonb,
    next_action TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in_progress', -- 'in_progress', 'completed', 'paused'
    step_count INT NOT NULL DEFAULT 0,
    max_steps INT NOT NULL DEFAULT 5,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tarika_agent_user ON abhihub.tarika_agent_state(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tarika_agent_convo ON abhihub.tarika_agent_state(conversation_id);

ALTER TABLE abhihub.tarika_agent_state ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service role tarika_agent_state') THEN
        CREATE POLICY "Allow service role tarika_agent_state" 
            ON abhihub.tarika_agent_state FOR ALL TO service_role USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow user own tarika_agent_state') THEN
        CREATE POLICY "Allow user own tarika_agent_state" 
            ON abhihub.tarika_agent_state FOR ALL TO authenticated 
            USING (auth.uid()::text = user_id)
            WITH CHECK (auth.uid()::text = user_id);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
