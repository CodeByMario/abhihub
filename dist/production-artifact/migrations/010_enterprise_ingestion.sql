-- ============================================================
-- AbhiHub Migration 010: Enterprise Ingestion Workflow
-- Creates the storage_assets index and enforces DB-level unique 
-- constraints for physical file mapping.
-- ============================================================

-- 1. Create storage_assets table
CREATE TABLE IF NOT EXISTS abhihub.storage_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider TEXT NOT NULL,
    provider_public_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT,
    public_url TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'LABELED', 'ERROR', 'DELETED')),
    locked_by UUID REFERENCES auth.users(id),
    locked_until TIMESTAMP WITH TIME ZONE,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(provider, provider_public_id)
);

-- 2. Add Unique Constraint to documents table
-- Ensures no duplicate labels can ever exist for the same physical file.
ALTER TABLE abhihub.documents 
ADD CONSTRAINT unique_storage_asset UNIQUE (storage_provider, provider_public_id);

-- 3. Create Audit Logs table
CREATE TABLE IF NOT EXISTS abhihub.label_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id),
    document_id UUID REFERENCES abhihub.documents(id),
    action TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Create Indexes for fast Queue fetching
CREATE INDEX IF NOT EXISTS idx_storage_assets_status ON abhihub.storage_assets(status);
CREATE INDEX IF NOT EXISTS idx_storage_assets_provider_id ON abhihub.storage_assets(provider, provider_public_id);

-- 5. Grant Permissions (Required for PostgREST API)
GRANT ALL ON abhihub.storage_assets TO anon, authenticated, service_role;
GRANT ALL ON abhihub.label_audit_logs TO anon, authenticated, service_role;

-- 6. Row Level Security (RLS) Policies
ALTER TABLE abhihub.storage_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.label_audit_logs ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to manage storage assets (Ingestion queue)
CREATE POLICY "Allow all for authenticated on storage_assets" 
ON abhihub.storage_assets FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Allow authenticated users to insert and read audit logs
CREATE POLICY "Allow all for authenticated on label_audit_logs" 
ON abhihub.label_audit_logs FOR ALL TO authenticated USING (true) WITH CHECK (true);
