-- Migration 037: administrator-controlled incident silences.
CREATE TABLE IF NOT EXISTS abhihub.admin_alert_silences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id uuid NOT NULL REFERENCES abhihub.admin_alert_incidents(id) ON DELETE CASCADE,
    created_by uuid NOT NULL,
    reason text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alert_silences_active
    ON abhihub.admin_alert_silences(incident_id, expires_at);
ALTER TABLE abhihub.admin_alert_silences ENABLE ROW LEVEL SECURITY;
GRANT ALL ON abhihub.admin_alert_silences TO service_role;
