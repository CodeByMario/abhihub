-- Migration: College waitlist table
-- Run in Supabase SQL Editor (Schema: abhihub)

CREATE TABLE IF NOT EXISTS abhihub.college_waitlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  college_id UUID NOT NULL REFERENCES abhihub.colleges(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(college_id, email)  -- one signup per email per college
);

-- Index for fast count queries per college
CREATE INDEX IF NOT EXISTS idx_college_waitlist_college_id ON abhihub.college_waitlist(college_id);

-- Enable Row Level Security
ALTER TABLE abhihub.college_waitlist ENABLE ROW LEVEL SECURITY;

-- Anyone can insert (join waitlist)
CREATE POLICY "Allow public inserts" ON abhihub.college_waitlist
  FOR INSERT WITH CHECK (true);

-- Only service role can read (for admin/analytics)
CREATE POLICY "Service role reads all" ON abhihub.college_waitlist
  FOR SELECT USING (true);
