-- Admin-controlled ad overrides.
CREATE TABLE IF NOT EXISTS abhihub.ad_overrides (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type text NOT NULL CHECK (scope_type IN ('global', 'page', 'user')),
    scope_key text NOT NULL,
    enabled boolean NOT NULL,
    note text,
    updated_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope_type, scope_key)
);

CREATE INDEX IF NOT EXISTS ad_overrides_lookup_idx
    ON abhihub.ad_overrides (scope_type, scope_key);

ALTER TABLE abhihub.ad_overrides ENABLE ROW LEVEL SECURITY;
