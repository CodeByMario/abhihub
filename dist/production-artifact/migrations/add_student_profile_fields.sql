-- Migration: Add Student Profile Fields
-- Description: Add user_role, year_of_joining, profile_completed, and updated_at to students table
-- Date: 2026-02-10

-- Add new columns to students table
ALTER TABLE public.students
ADD COLUMN IF NOT EXISTS user_role TEXT CHECK (user_role IN ('student', 'teacher')),
ADD COLUMN IF NOT EXISTS year_of_joining INTEGER CHECK (year_of_joining >= 1900 AND year_of_joining <= 2100),
ADD COLUMN IF NOT EXISTS profile_completed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_students_user_id ON public.students(user_id);
CREATE INDEX IF NOT EXISTS idx_students_college_branch ON public.students(college_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_students_profile_completed ON public.students(profile_completed);

-- Add trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_students_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_students_timestamp ON public.students;
CREATE TRIGGER update_students_timestamp
    BEFORE UPDATE ON public.students
    FOR EACH ROW
    EXECUTE FUNCTION update_students_updated_at();

-- Optional: Fix typo in column name (uncomment if you want to rename)
-- ALTER TABLE public.students RENAME COLUMN student_moblie_number TO student_mobile_number;

COMMENT ON COLUMN public.students.user_role IS 'User role: student or teacher';
COMMENT ON COLUMN public.students.year_of_joining IS 'Year the user joined the institution';
COMMENT ON COLUMN public.students.profile_completed IS 'Flag indicating if profile setup is complete';
COMMENT ON COLUMN public.students.updated_at IS 'Timestamp of last profile update';
