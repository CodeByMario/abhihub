-- ============================================================================
-- Table: abhihub.ai_practice_tests
-- Purpose: Records AI-generated tests/quizzes and makes them globally accessible.
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.ai_practice_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_user_id TEXT,
    creator_email TEXT,
    doc_id TEXT,
    title TEXT NOT NULL,
    subject TEXT,
    difficulty TEXT DEFAULT 'medium',
    total_questions INT NOT NULL DEFAULT 0,
    total_marks INT NOT NULL DEFAULT 0,
    questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_used TEXT,
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fast lookup indexes
CREATE INDEX IF NOT EXISTS idx_ai_practice_tests_public 
    ON abhihub.ai_practice_tests (is_public, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_practice_tests_creator 
    ON abhihub.ai_practice_tests (creator_user_id);
CREATE INDEX IF NOT EXISTS idx_ai_practice_tests_doc 
    ON abhihub.ai_practice_tests (doc_id);

-- Enable Row Level Security (RLS)
ALTER TABLE abhihub.ai_practice_tests ENABLE ROW LEVEL SECURITY;

-- Allow all users (anon & authenticated) to view public tests
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow all users to view public tests') THEN
        CREATE POLICY "Allow all users to view public tests" 
            ON abhihub.ai_practice_tests 
            FOR SELECT 
            USING (is_public = TRUE OR auth.uid()::text = creator_user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow service role full access to tests') THEN
        CREATE POLICY "Allow service role full access to tests" 
            ON abhihub.ai_practice_tests 
            FOR ALL 
            TO service_role 
            USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow authenticated users to insert tests') THEN
        CREATE POLICY "Allow authenticated users to insert tests" 
            ON abhihub.ai_practice_tests 
            FOR INSERT 
            TO authenticated 
            WITH CHECK (TRUE);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
