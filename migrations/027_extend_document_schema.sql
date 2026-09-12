-- Migration 027: Extend document schema for AdSense SEO compliance
-- Adds optional metadata fields to abhihub.documents table for crawlable text content

ALTER TABLE abhihub.documents 
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS topics_covered TEXT[],
ADD COLUMN IF NOT EXISTS difficulty_level VARCHAR(50),
ADD COLUMN IF NOT EXISTS uploader_note TEXT;

COMMENT ON COLUMN abhihub.documents.description IS 'Curated summary or descriptive overview of the document content';
COMMENT ON COLUMN abhihub.documents.topics_covered IS 'List of key syllabus topics/chapters covered in this resource';
COMMENT ON COLUMN abhihub.documents.difficulty_level IS 'Subjective difficulty rating: Easy, Medium, Hard, Advanced';
COMMENT ON COLUMN abhihub.documents.uploader_note IS 'Optional note, advice, or context provided by the student uploader';
