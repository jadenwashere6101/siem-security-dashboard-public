CREATE TABLE IF NOT EXISTS soar_dead_letters (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(64) NOT NULL
        CHECK (source_type IN (
            'playbook_execution',
            'notification_delivery',
            'response_action',
            'approval'
        )),
    source_id INTEGER NOT NULL,
    execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    playbook_id VARCHAR(64) REFERENCES playbook_definitions(id) ON DELETE SET NULL,
    step_index INTEGER,
    action_name VARCHAR(128),
    failure_class VARCHAR(64) NOT NULL DEFAULT 'unknown',
    error_message TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'retrying', 'retried', 'dismissed')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    first_failed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_failed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed_at TIMESTAMPTZ,
    dismissed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    dismiss_reason TEXT,
    retry_requested_at TIMESTAMPTZ,
    retry_requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(source_type)) > 0),
    CHECK (length(trim(failure_class)) > 0),
    CHECK (length(trim(error_message)) > 0),
    CHECK (retry_count >= 0),
    CHECK (step_index IS NULL OR step_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_status_created_at
    ON soar_dead_letters (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_source_type_source_id
    ON soar_dead_letters (source_type, source_id);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_incident_id
    ON soar_dead_letters (incident_id);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_alert_id
    ON soar_dead_letters (alert_id);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_execution_id
    ON soar_dead_letters (execution_id);

CREATE INDEX IF NOT EXISTS idx_soar_dead_letters_failure_class
    ON soar_dead_letters (failure_class);

CREATE UNIQUE INDEX IF NOT EXISTS idx_soar_dead_letters_active_source_unique
    ON soar_dead_letters (source_type, source_id)
    WHERE status IN ('open', 'retrying');
