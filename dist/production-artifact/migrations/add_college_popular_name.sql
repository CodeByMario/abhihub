-- Migration: Add popular_name and aliases to colleges table
-- Run this in Supabase SQL Editor (Schema: abhihub)

ALTER TABLE abhihub.colleges
  ADD COLUMN IF NOT EXISTS popular_name TEXT,
  ADD COLUMN IF NOT EXISTS aliases TEXT[]; -- array of alternate slugs/nicknames

-- ─── Raisoni Group (GHRCE campuses) ─────────────────────────────────────────
-- All GHRCE branches get popular_name='Raisoni' so /college/raisoni
-- renders a brand page listing ALL of them.
-- Then each campus links to its own page: /college/ghrcen, /college/ghrcem, etc.

-- GHRCEN = G H Raisoni College of Engineering, Nagpur
UPDATE abhihub.colleges
SET popular_name = 'Raisoni', aliases = ARRAY['raisoni', 'ghrce', 'gh raisoni']
WHERE abbreviation ILIKE 'GHRCEN';

-- GHRCEM = G H Raisoni College of Engineering & Management, Pune (example)
UPDATE abhihub.colleges
SET popular_name = 'Raisoni', aliases = ARRAY['raisoni', 'ghrce']
WHERE abbreviation ILIKE 'GHRCEM';

-- Add more GHRCE campuses below as needed:
-- UPDATE abhihub.colleges SET popular_name = 'Raisoni' WHERE abbreviation ILIKE 'GHRCEMNG';

-- ─── Add more brand groups below ─────────────────────────────────────────────
-- UPDATE abhihub.colleges SET popular_name = 'YCCE', aliases = ARRAY['ycce'] WHERE abbreviation ILIKE 'YCCE';

