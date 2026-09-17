-- ============================================================================
-- Fix for file_access_history table - Complete RLS Setup
-- ============================================================================

-- STEP 1: Drop existing table if in wrong schema and recreate in abhihub schema
DROP TABLE IF EXISTS public.file_access_history;

-- STEP 2: Create the table in abhihub schema with proper constraints
CREATE TABLE IF NOT EXISTS abhihub.file_access_history (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
  user_email text NOT NULL,
  file_name text NOT NULL,
  file_type text,
  file_path text,
  file_url text,
  accessed_at timestamp with time zone DEFAULT NOW(),
  CONSTRAINT file_access_history_pkey PRIMARY KEY (id),
  CONSTRAINT file_access_history_user_email_check CHECK (user_email != '')
);

-- STEP 3: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_file_access_user_id 
  ON abhihub.file_access_history(user_id) 
  WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_file_access_user_email 
  ON abhihub.file_access_history(user_email);

CREATE INDEX IF NOT EXISTS idx_file_access_accessed_at 
  ON abhihub.file_access_history(accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_access_user_time 
  ON abhihub.file_access_history(user_id, accessed_at DESC) 
  WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_file_access_email_time 
  ON abhihub.file_access_history(user_email, accessed_at DESC);

-- STEP 4: Enable Row Level Security
ALTER TABLE abhihub.file_access_history ENABLE ROW LEVEL SECURITY;

-- STEP 5: Drop existing policies if any
DROP POLICY IF EXISTS "Users can read own file access history" ON abhihub.file_access_history;
DROP POLICY IF EXISTS "Users can insert own file access history" ON abhihub.file_access_history;
DROP POLICY IF EXISTS "Admins can read all file access history" ON abhihub.file_access_history;
DROP POLICY IF EXISTS "Admins can insert file access history" ON abhihub.file_access_history;
DROP POLICY IF EXISTS "Allow insert for authenticated users" ON abhihub.file_access_history;
DROP POLICY IF EXISTS "Allow select for own records" ON abhihub.file_access_history;

-- STEP 6: Create RLS Policies

-- Policy 1: Users can READ their own file access history (by user_id)
CREATE POLICY "Users can read own file access history"
  ON abhihub.file_access_history
  FOR SELECT
  USING (auth.uid() = user_id);

-- Policy 2: Users can INSERT their own file access records
CREATE POLICY "Users can insert own file access history"
  ON abhihub.file_access_history
  FOR INSERT
  WITH CHECK (auth.uid() = user_id OR auth.uid() IS NOT NULL);

-- Policy 3: Admins/Moderators can READ all file access history
CREATE POLICY "Admins can read all file access history"
  ON abhihub.file_access_history
  FOR SELECT
  USING (abhihub.is_admin_or_mod(auth.uid()));

-- Policy 4: Allow unauthenticated or system inserts (for logging from backend)
CREATE POLICY "Allow backend file access logging"
  ON abhihub.file_access_history
  FOR INSERT
  WITH CHECK (true);

-- STEP 7: Grant permissions to service role (for backend operations)
GRANT ALL PRIVILEGES ON TABLE abhihub.file_access_history TO authenticated;
GRANT ALL PRIVILEGES ON TABLE abhihub.file_access_history TO service_role;
GRANT USAGE ON SCHEMA abhihub TO authenticated;
GRANT USAGE ON SCHEMA abhihub TO service_role;

-- STEP 8: Add trigger to update user_email if user_id changes
CREATE OR REPLACE FUNCTION abhihub.sync_file_access_email()
RETURNS TRIGGER AS $$
BEGIN
  -- Auto-populate user_email from profiles table when user_id is set
  IF NEW.user_id IS NOT NULL AND (NEW.user_email IS NULL OR NEW.user_email = '') THEN
    SELECT email INTO NEW.user_email 
    FROM abhihub.profiles 
    WHERE id = NEW.user_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop existing trigger if any
DROP TRIGGER IF EXISTS sync_file_access_email_trigger ON abhihub.file_access_history;

-- Create trigger
CREATE TRIGGER sync_file_access_email_trigger
  BEFORE INSERT OR UPDATE ON abhihub.file_access_history
  FOR EACH ROW
  EXECUTE FUNCTION abhihub.sync_file_access_email();

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Check table exists and has data
SELECT 
  schemaname, 
  tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE tablename = 'file_access_history';

-- Check RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE tablename = 'file_access_history';

-- Check policies exist
SELECT 
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  qual,
  with_check
FROM pg_policies 
WHERE tablename = 'file_access_history';

-- Check indexes
SELECT 
  schemaname,
  tablename,
  indexname,
  indexdef
FROM pg_indexes 
WHERE tablename = 'file_access_history'
ORDER BY indexname;

-- ============================================================================
-- Test Data Insertion (if needed)
-- ============================================================================

-- Test insert (replace with actual user_id and email)
-- INSERT INTO abhihub.file_access_history (user_id, user_email, file_name, file_type, file_url, accessed_at)
-- VALUES (
--   (SELECT id FROM abhihub.profiles LIMIT 1),
--   (SELECT email FROM abhihub.profiles LIMIT 1),
--   'test_document.pdf',
--   'pdf',
--   'https://example.com/test.pdf',
--   NOW()
-- );

-- View all records (admin only)
-- SELECT id, user_id, user_email, file_name, file_type, accessed_at 
-- FROM abhihub.file_access_history 
-- ORDER BY accessed_at DESC 
-- LIMIT 10;
