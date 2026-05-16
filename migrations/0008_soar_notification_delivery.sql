CREATE TABLE IF NOT EXISTS notification_delivery_attempts (
    id SERIAL PRIMARY KEY,
    correlation_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    mode VARCHAR(20) NOT NULL
        CHECK (mode IN ('simulation', 'real')),
    status VARCHAR(32) NOT NULL
        CHECK (status IN ('pending', 'success', 'failed', 'timeout', 'blocked')),
    playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    playbook_step_index INTEGER,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    adapter_name VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    failure_code VARCHAR(64),
    failure_message TEXT,
    timeout_seconds INTEGER,
    circuit_breaker_state VARCHAR(32)
        CHECK (
            circuit_breaker_state IS NULL
            OR circuit_breaker_state IN ('closed', 'open', 'half_open', 'unknown', 'invalid')
        ),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (length(trim(correlation_id)) > 0),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(provider)) > 0),
    CHECK (length(trim(adapter_name)) > 0),
    CHECK (length(trim(action)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_provider_mode_status_created
    ON notification_delivery_attempts (provider, mode, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_playbook_step
    ON notification_delivery_attempts (playbook_execution_id, playbook_step_index);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_incident_id
    ON notification_delivery_attempts (incident_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_approval_request_id
    ON notification_delivery_attempts (approval_request_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_correlation_id
    ON notification_delivery_attempts (correlation_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_idempotency_key
    ON notification_delivery_attempts (idempotency_key);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_alert_id
    ON notification_delivery_attempts (alert_id);
