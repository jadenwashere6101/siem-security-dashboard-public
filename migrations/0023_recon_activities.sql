CREATE TABLE IF NOT EXISTS recon_activities (
    id SERIAL PRIMARY KEY,
    activity_type TEXT NOT NULL
        CHECK (activity_type = 'distributed_internet_reconnaissance'),
    source TEXT NOT NULL DEFAULT 'pfsense',
    source_type TEXT NOT NULL DEFAULT 'firewall',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'monitoring', 'resolved')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high')),
    coordination_status TEXT NOT NULL DEFAULT 'not_established'
        CHECK (coordination_status IN ('not_established', 'possible', 'supported')),
    protected_range_key TEXT NOT NULL,
    service_signature JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    assessment_text TEXT NOT NULL,
    membership_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    related_incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    opened_notification_sent_at TIMESTAMPTZ,
    last_notified_fingerprint TEXT,
    last_notified_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(service_signature) = 'array'),
    CHECK (jsonb_typeof(membership_evidence) = 'object'),
    CHECK (jsonb_typeof(summary) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_recon_activities_activity_status
    ON recon_activities (activity_type, status, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_recon_activities_range_status
    ON recon_activities (protected_range_key, status, last_seen DESC);

CREATE TABLE IF NOT EXISTS recon_activity_alerts (
    recon_activity_id INTEGER NOT NULL REFERENCES recon_activities(id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL UNIQUE REFERENCES alerts(id) ON DELETE CASCADE,
    member_role TEXT NOT NULL DEFAULT 'primary'
        CHECK (member_role IN ('primary', 'supporting')),
    source_ip INET,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    membership_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (recon_activity_id, alert_id),
    CHECK (jsonb_typeof(membership_evidence) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_recon_activity_alerts_activity
    ON recon_activity_alerts (recon_activity_id, linked_at DESC);

CREATE INDEX IF NOT EXISTS idx_recon_activity_alerts_source
    ON recon_activity_alerts (source_ip, linked_at DESC);

ALTER TABLE notification_delivery_attempts
    ADD COLUMN IF NOT EXISTS recon_activity_id INTEGER REFERENCES recon_activities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_notification_delivery_recon_activity_id
    ON notification_delivery_attempts (recon_activity_id);
