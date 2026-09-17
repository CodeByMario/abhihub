-- Migration: user_crushes
-- Each user can mark at most 2 crushes per calendar year.
-- A "match" occurs when both users have marked each other.

CREATE TABLE IF NOT EXISTS abhihub.user_crushes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_user   UUID NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    to_user     UUID NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    year        SMALLINT NOT NULL DEFAULT EXTRACT(YEAR FROM NOW()),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_user, to_user, year)
);

-- Index for fast lookup of "who did I crush on this year"
CREATE INDEX IF NOT EXISTS idx_crushes_from_year ON abhihub.user_crushes (from_user, year);
-- Index for fast mutual-match check
CREATE INDEX IF NOT EXISTS idx_crushes_to_year   ON abhihub.user_crushes (to_user, year);

-- RLS: users can only read/write their own crush rows
ALTER TABLE abhihub.user_crushes ENABLE ROW LEVEL SECURITY;

CREATE POLICY crushes_select ON abhihub.user_crushes
    FOR SELECT USING (from_user = auth.uid() OR to_user = auth.uid());

CREATE POLICY crushes_insert ON abhihub.user_crushes
    FOR INSERT WITH CHECK (from_user = auth.uid());

CREATE POLICY crushes_delete ON abhihub.user_crushes
    FOR DELETE USING (from_user = auth.uid());
