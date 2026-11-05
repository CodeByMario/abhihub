-- Keep college_departments aligned with profile and document relationships.
-- Applying this migration is idempotent and repairs existing orphaned mappings.

SET search_path TO abhihub, public;

CREATE OR REPLACE FUNCTION abhihub.ensure_college_department_mapping()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = abhihub, public
AS $$
BEGIN
  IF NEW.college_id IS NOT NULL AND NEW.department_id IS NOT NULL THEN
    INSERT INTO abhihub.college_departments (college_id, department_id)
    VALUES (NEW.college_id, NEW.department_id)
    ON CONFLICT (college_id, department_id) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_sync_college_department ON abhihub.profiles;
CREATE TRIGGER profiles_sync_college_department
AFTER INSERT OR UPDATE OF college_id, department_id ON abhihub.profiles
FOR EACH ROW
EXECUTE FUNCTION abhihub.ensure_college_department_mapping();

DROP TRIGGER IF EXISTS documents_sync_college_department ON abhihub.documents;
CREATE TRIGGER documents_sync_college_department
AFTER INSERT OR UPDATE OF college_id, department_id ON abhihub.documents
FOR EACH ROW
EXECUTE FUNCTION abhihub.ensure_college_department_mapping();

INSERT INTO abhihub.college_departments (college_id, department_id)
SELECT DISTINCT college_id, department_id
FROM abhihub.profiles
WHERE college_id IS NOT NULL AND department_id IS NOT NULL
ON CONFLICT (college_id, department_id) DO NOTHING;

INSERT INTO abhihub.college_departments (college_id, department_id)
SELECT DISTINCT college_id, department_id
FROM abhihub.documents
WHERE college_id IS NOT NULL AND department_id IS NOT NULL
ON CONFLICT (college_id, department_id) DO NOTHING;
