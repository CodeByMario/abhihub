-- Migration 036: persistent observability incidents and administrator delivery audit.
CREATE TABLE IF NOT EXISTS abhihub.admin_alert_incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint text NOT NULL,
    name text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    service text NOT NULL DEFAULT 'abhihub',
    environment text NOT NULL DEFAULT 'production',
    route text,
    message text NOT NULL,
    status text NOT NULL DEFAULT 'firing'
        CHECK (status IN ('firing', 'acknowledged', 'resolved')),
    occurrence_count integer NOT NULL DEFAULT 1,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz,
    acknowledged_by uuid,
    resolved_at timestamptz,
    resolution_note text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_incident_firing_fingerprint
    ON abhihub.admin_alert_incidents(fingerprint) WHERE status = 'firing';
CREATE INDEX IF NOT EXISTS idx_alert_incidents_status_seen
    ON abhihub.admin_alert_incidents(status, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS abhihub.admin_alert_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id uuid NOT NULL REFERENCES abhihub.admin_alert_incidents(id) ON DELETE CASCADE,
    admin_id uuid NOT NULL,
    channel text NOT NULL CHECK (channel IN ('in_app', 'push', 'email', 'sms', 'slack')),
    status text NOT NULL CHECK (status IN ('sent', 'failed', 'acknowledged')),
    attempt_number integer NOT NULL DEFAULT 1,
    error_message text,
    sent_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_incident
    ON abhihub.admin_alert_deliveries(incident_id, sent_at DESC);

ALTER TABLE abhihub.admin_alert_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.admin_alert_deliveries ENABLE ROW LEVEL SECURITY;
GRANT ALL ON abhihub.admin_alert_incidents TO service_role;
GRANT ALL ON abhihub.admin_alert_deliveries TO service_role;
