-- ============================================================
-- AbhiHub Migration 008: Final (pre-deployment)
-- Summary of all changes:
--   - pending_subject_requests (T2) + duplicate index + approved_subject_id
--   - college_departments mapping table (T3)
--   - profiles: welcome_seen, last_donation_popup_at (T4, replaces popup tables)
--   - subjects.semester + CHECK(1-8) (T4a)
--   - user_events restricted to 3 types (T7)
--   - FK verified: profiles.id = auth.users.id
-- ============================================================

-- ── TASK 2: Missing Subject Workflow ─────────────────────────────────
CREATE TABLE IF NOT EXISTS abhihub.pending_subject_requests (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
  college_id uuid REFERENCES abhihub.colleges(id),
  department_id uuid REFERENCES abhihub.departments(id),
  subject_name text NOT NULL,
  subject_code text,
  semester integer CHECK (semester BETWEEN 1 AND 8),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at timestamptz DEFAULT now(),
  reviewed_by uuid REFERENCES abhihub.profiles(id),
  reviewed_at timestamptz,
  -- Audit trail: set when admin approves and creates the subject row
  approved_subject_id uuid REFERENCES abhihub.subjects(id) ON DELETE SET NULL
);

-- Duplicate protection: same dept + same name cannot have two 'pending' rows
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_subject_unique
  ON abhihub.pending_subject_requests (department_id, lower(subject_name))
  WHERE status = 'pending';

-- ── TASK 3: College-Department Mapping ───────────────────────────────
CREATE TABLE IF NOT EXISTS abhihub.college_departments (
  college_id uuid NOT NULL REFERENCES abhihub.colleges(id) ON DELETE CASCADE,
  department_id uuid NOT NULL REFERENCES abhihub.departments(id) ON DELETE CASCADE,
  PRIMARY KEY (college_id, department_id)
);

-- Narrow migration: only populate from existing profile and document data
INSERT INTO abhihub.college_departments (college_id, department_id)
SELECT DISTINCT p.college_id, p.department_id
FROM abhihub.profiles p
WHERE p.college_id IS NOT NULL AND p.department_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO abhihub.college_departments (college_id, department_id)
SELECT DISTINCT d.college_id, d.department_id
FROM abhihub.documents d
WHERE d.college_id IS NOT NULL AND d.department_id IS NOT NULL
ON CONFLICT DO NOTHING;


CREATE INDEX IF NOT EXISTS idx_college_departments_dept
  ON abhihub.college_departments(department_id);

-- ── TASK 4: Onboarding via profiles columns (no extra table needed) ──
-- welcome_seen + last_donation_popup_at added directly to profiles.
-- This is sufficient for ~290 users and avoids unnecessary joins.

-- Alternative lightweight approach: popup timestamps on profiles
-- (replaces popup_definitions + user_popup_history tables)
ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS welcome_seen boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS last_donation_popup_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_feature_popup_at timestamptz;

-- ── TASK 4a: Upload flow — add semester to subjects ───────────────────
-- Semester 1-8 (integer). NULL = subject spans all semesters.
ALTER TABLE abhihub.subjects
  ADD COLUMN IF NOT EXISTS semester integer CHECK (semester BETWEEN 1 AND 8);

-- ── TASK 7: Analytics (3 event types only) ───────────────────────────
CREATE TABLE IF NOT EXISTS abhihub.user_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid REFERENCES abhihub.profiles(id) ON DELETE SET NULL,
  event_type text NOT NULL CHECK (event_type IN ('UPLOAD', 'DOWNLOAD', 'SUBJECT_REQUEST')),
  metadata jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_events_type ON abhihub.user_events(event_type);
CREATE INDEX IF NOT EXISTS idx_user_events_user ON abhihub.user_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_created ON abhihub.user_events(created_at DESC);

-- ── GRANTS FOR API ROLES ─────────────────────────────────────────────
GRANT ALL PRIVILEGES ON TABLE abhihub.pending_subject_requests TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.college_departments TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.user_events TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.colleges TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.departments TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.subjects TO anon, authenticated, service_role;


