-- ============================================================
-- AbhiHub Migration 013: Gamification & Dopamine Loop
-- ============================================================

-- Track every contribution action to build timelines and award XP
CREATE TABLE IF NOT EXISTS abhihub.contribution_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL, -- e.g., 'upload_document', 'receive_like', 'receive_download'
    entity_id UUID,                   -- ID of the document/subject related to this action
    entity_type VARCHAR(50),          -- 'document', 'subject', etc.
    xp_awarded INTEGER DEFAULT 0,
    description TEXT,                 -- e.g., 'Uploaded TNM Notes'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contribution_logs_user_id ON abhihub.contribution_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_contribution_logs_created_at ON abhihub.contribution_logs(created_at);

-- Store badges unlocked by the user
CREATE TABLE IF NOT EXISTS abhihub.user_achievements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    badge_name VARCHAR(100) NOT NULL, -- e.g., 'Semester Hero', 'Note Master'
    badge_icon VARCHAR(50),           -- e.g., '🏆', '📚'
    unlocked_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, badge_name)       -- Prevent earning the exact same badge twice
);

CREATE INDEX IF NOT EXISTS idx_user_achievements_user_id ON abhihub.user_achievements(user_id);

-- Optional: Track total students helped directly on the profile
ALTER TABLE abhihub.profiles
ADD COLUMN IF NOT EXISTS students_helped INTEGER DEFAULT 0;
