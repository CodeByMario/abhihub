-- MemoryWall (know_me) feature tables
-- Schema: abhihub
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS abhihub.memory_wall (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          TEXT NOT NULL,
  slug             TEXT UNIQUE NOT NULL,
  title            TEXT,
  photo_url        TEXT,
  college          TEXT,
  branch           TEXT,
  graduation_year  INTEGER,
  status           TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed')),
  response_count   INTEGER DEFAULT 0,
  view_count       INTEGER DEFAULT 0,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS abhihub.memory_response (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wall_id         UUID NOT NULL REFERENCES abhihub.memory_wall(id) ON DELETE CASCADE,
  friend_name     TEXT NOT NULL,
  word_1          TEXT NOT NULL,
  word_2          TEXT NOT NULL,
  word_3          TEXT NOT NULL,
  memory_message  TEXT,
  emoji           TEXT,
  anonymous       BOOLEAN DEFAULT false,
  ip_hash         TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS abhihub.signature (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id  UUID NOT NULL REFERENCES abhihub.memory_response(id) ON DELETE CASCADE,
  signature_url TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_memory_wall_user_id   ON abhihub.memory_wall(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_wall_slug       ON abhihub.memory_wall(slug);
CREATE INDEX IF NOT EXISTS idx_memory_response_wall   ON abhihub.memory_response(wall_id);
CREATE INDEX IF NOT EXISTS idx_memory_response_iphash ON abhihub.memory_response(ip_hash, created_at);

-- Disable Row Level Security (managed entirely by Flask backend)
ALTER TABLE abhihub.memory_wall DISABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.memory_response DISABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.signature DISABLE ROW LEVEL SECURITY;

-- Grant schema usage to API roles
GRANT USAGE ON SCHEMA abhihub TO anon, authenticated, service_role;

-- Grant all privileges on tables to API roles
GRANT ALL PRIVILEGES ON TABLE abhihub.memory_wall TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.memory_response TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.signature TO anon, authenticated, service_role;

