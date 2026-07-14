CREATE TABLE IF NOT EXISTS notification_policy (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    slack_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_severity TEXT NOT NULL DEFAULT 'high'
        CHECK (minimum_severity IN ('low', 'medium', 'high', 'critical')),
    notify_on_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    notify_on_incidents BOOLEAN NOT NULL DEFAULT TRUE,
    slack_format TEXT NOT NULL DEFAULT 'compact'
        CHECK (slack_format IN ('compact', 'detailed')),
    pfsense_destination TEXT NOT NULL DEFAULT 'pfSense destination'
        CHECK (btrim(pfsense_destination) <> ''),
    honeypot_destination TEXT NOT NULL DEFAULT 'Honeypot destination'
        CHECK (btrim(honeypot_destination) <> ''),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

INSERT INTO notification_policy (
    id,
    slack_enabled,
    minimum_severity,
    notify_on_alerts,
    notify_on_incidents,
    slack_format,
    pfsense_destination,
    honeypot_destination,
    updated_by
)
VALUES (
    1,
    FALSE,
    'high',
    TRUE,
    TRUE,
    'compact',
    'pfSense destination',
    'Honeypot destination',
    NULL
)
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_notification_policy_updated_at
    ON notification_policy (updated_at DESC);
