-- ============================================================================
-- Table: abhihub.ai_practice_questions
-- Purpose: Individual question bank — each question from a generated test is
--          stored as its own row with keywords + sample answer for easy reuse.
-- Linked to: abhihub.ai_practice_tests (test_id)
-- ============================================================================

CREATE TABLE IF NOT EXISTS abhihub.ai_practice_questions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id         UUID NOT NULL,           -- FK → ai_practice_tests.id
    question_no     INT  NOT NULL DEFAULT 1, -- position in paper (1-indexed)
    question_type   TEXT NOT NULL DEFAULT 'mcq',  -- mcq | msq | one_word | short | detail
    question_text   TEXT NOT NULL,
    options         JSONB,                   -- ["A) ...", "B) ...", ...] for mcq/msq
    correct_answer  TEXT,                    -- single correct answer (mcq / one_word / short)
    correct_options JSONB,                   -- ["A) ...", "C) ..."] for msq
    model_answer    TEXT,                    -- full sample/model answer for short/detail
    keywords        JSONB NOT NULL DEFAULT '[]'::jsonb,  -- important terms for grading
    explanation     TEXT,                    -- step-by-step explanation
    marks           INT  NOT NULL DEFAULT 1,
    subject         TEXT,
    doc_id          TEXT,
    creator_user_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_apq_test_id
    ON abhihub.ai_practice_questions (test_id);
CREATE INDEX IF NOT EXISTS idx_apq_type
    ON abhihub.ai_practice_questions (question_type);
CREATE INDEX IF NOT EXISTS idx_apq_subject
    ON abhihub.ai_practice_questions (subject);
CREATE INDEX IF NOT EXISTS idx_apq_doc
    ON abhihub.ai_practice_questions (doc_id);
CREATE INDEX IF NOT EXISTS idx_apq_creator
    ON abhihub.ai_practice_questions (creator_user_id);

-- RLS
ALTER TABLE abhihub.ai_practice_questions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'apq_public_read') THEN
        CREATE POLICY "apq_public_read"
            ON abhihub.ai_practice_questions FOR SELECT
            USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'apq_service_full') THEN
        CREATE POLICY "apq_service_full"
            ON abhihub.ai_practice_questions FOR ALL
            TO service_role USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'apq_auth_insert') THEN
        CREATE POLICY "apq_auth_insert"
            ON abhihub.ai_practice_questions FOR INSERT
            TO authenticated WITH CHECK (TRUE);
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
