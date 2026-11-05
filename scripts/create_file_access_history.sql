-- Create file_access_history in abhihub schema
CREATE TABLE IF NOT EXISTS abhihub.file_access_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    user_email TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT,
    file_path TEXT,
    file_url TEXT,
    status TEXT DEFAULT 'success',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_file_access_history_user ON abhihub.file_access_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_file_access_history_email ON abhihub.file_access_history(user_email);

-- Enable RLS
ALTER TABLE abhihub.file_access_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow authenticated read own access" ON abhihub.file_access_history
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Allow service role full access" ON abhihub.file_access_history
    FOR ALL TO service_role USING (true);

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
