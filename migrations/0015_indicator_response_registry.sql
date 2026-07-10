-- Indicator response registry foundation (Phase 1).
-- Additive only. Does not alter blocked_ips, alerts, incidents, queue, approvals,
-- playbooks, or soar_response_* operational tables.

CREATE TABLE IF NOT EXISTS indicator_registry (
    id SERIAL PRIMARY KEY,
    indicator_type VARCHAR(32) NOT NULL,
    indicator_value TEXT NOT NULL,
    current_disposition VARCHAR(32) NOT NULL DEFAULT 'observed',
    active_blocked_ip_id INTEGER REFERENCES blocked_ips(id) ON DELETE SET NULL,
    active_incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    monitor_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(indicator_type)) > 0),
    CHECK (length(trim(indicator_value)) > 0),
    CHECK (
        current_disposition IN (
            'observed',
            'monitored',
            'escalated',
            'pending',
            'blocklist_tracked',
            'rejected',
            'failed',
            'expired',
            'removed'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_indicator_registry_type_value
    ON indicator_registry (indicator_type, indicator_value);

CREATE INDEX IF NOT EXISTS idx_indicator_registry_disposition
    ON indicator_registry (current_disposition);

CREATE INDEX IF NOT EXISTS idx_indicator_registry_updated_at
    ON indicator_registry (updated_at DESC);

CREATE TABLE IF NOT EXISTS indicator_response_events (
    id SERIAL PRIMARY KEY,
    registry_id INTEGER NOT NULL REFERENCES indicator_registry(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    requested_action VARCHAR(64) NOT NULL,
    outcome VARCHAR(64) NOT NULL,
    disposition_after VARCHAR(32) NOT NULL,
    enforcement VARCHAR(32) NOT NULL DEFAULT 'none',
    origin_surface VARCHAR(64) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    playbook_step_index INTEGER,
    queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL,
    approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL,
    blocked_ip_id INTEGER REFERENCES blocked_ips(id) ON DELETE SET NULL,
    decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL,
    soar_correlation_id VARCHAR(128),
    response_action_log_id INTEGER REFERENCES response_actions_log(id) ON DELETE SET NULL,
    idempotency_key VARCHAR(128),
    provenance VARCHAR(32) NOT NULL DEFAULT 'recorded',
    expires_at TIMESTAMPTZ,
    safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(event_type)) > 0),
    CHECK (length(trim(requested_action)) > 0),
    CHECK (length(trim(outcome)) > 0),
    CHECK (
        disposition_after IN (
            'observed',
            'monitored',
            'escalated',
            'pending',
            'blocklist_tracked',
            'rejected',
            'failed',
            'expired',
            'removed'
        )
    ),
    CHECK (
        enforcement IN ('none', 'tracking_only', 'simulation', 'real_external')
    ),
    CHECK (
        provenance IN ('recorded', 'inferred', 'unknown')
    ),
    CHECK (playbook_step_index IS NULL OR playbook_step_index >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_indicator_response_events_idempotency
    ON indicator_response_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_indicator_response_events_registry_created
    ON indicator_response_events (registry_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_indicator_response_events_alert_id
    ON indicator_response_events (alert_id);

CREATE INDEX IF NOT EXISTS idx_indicator_response_events_action_outcome
    ON indicator_response_events (requested_action, outcome);
