-- Migration 018: Viewer failure reports
-- Run once in Supabase SQL editor

CREATE TABLE IF NOT EXISTS abhihub.viewer_failure_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id      TEXT NOT NULL,
    viewer_type TEXT NOT NULL DEFAULT 'unknown',  -- 'pdf' | 'image' | 'unknown'
    error_msg   TEXT,
    page_url    TEXT,
    reporter_email TEXT DEFAULT 'anonymous',
    status      TEXT NOT NULL DEFAULT 'open',     -- 'open' | 'resolved'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vfr_status ON abhihub.viewer_failure_reports(status);
CREATE INDEX IF NOT EXISTS idx_vfr_doc_id ON abhihub.viewer_failure_reports(doc_id);
CREATE INDEX IF NOT EXISTS idx_vfr_created ON abhihub.viewer_failure_reports(created_at DESC);
