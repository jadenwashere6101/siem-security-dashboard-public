CREATE TABLE IF NOT EXISTS soar_response_decisions (
    id SERIAL PRIMARY KEY,
    soar_correlation_id VARCHAR(128) NOT NULL,
    parent_soar_correlation_id VARCHAR(128),
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    source_ip INET,
    selected_action TEXT NOT NULL,
    decision_source VARCHAR(64) NOT NULL,
    reason_code VARCHAR(128),
    outcome_summary TEXT NOT NULL,
    playbook_id VARCHAR(64) REFERENCES playbook_definitions(id) ON DELETE SET NULL,
    playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    playbook_step_index INTEGER,
    queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL,
    approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(soar_correlation_id)) > 0),
    CHECK (length(trim(selected_action)) > 0),
    CHECK (
        decision_source IN (
            'detection_default',
            'correlation',
            'playbook',
            'manual',
            'migration'
        )
    ),
    CHECK (
        reason_code IS NULL
        OR reason_code IN (
            'approval_required',
            'approval_denied',
            'simulation_mode',
            'tracking_only',
            'adapter_unavailable',
            'provider_error',
            'policy_blocked',
            'duplicate_suppressed',
            'unsupported_action'
        )
    ),
    CHECK (playbook_step_index IS NULL OR playbook_step_index >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_soar_response_decisions_soar_correlation_id
    ON soar_response_decisions (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_decisions_alert_id
    ON soar_response_decisions (alert_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_decisions_incident_id
    ON soar_response_decisions (incident_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_decisions_source_ip
    ON soar_response_decisions (source_ip);

CREATE INDEX IF NOT EXISTS idx_soar_response_decisions_created_at
    ON soar_response_decisions (created_at DESC);

CREATE TABLE IF NOT EXISTS soar_response_outcome_events (
    id SERIAL PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES soar_response_decisions(id) ON DELETE CASCADE,
    soar_correlation_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    source_ip INET,
    execution_mode VARCHAR(32) NOT NULL,
    execution_state VARCHAR(32) NOT NULL,
    external_executed BOOLEAN NOT NULL DEFAULT FALSE,
    tracking_recorded BOOLEAN NOT NULL DEFAULT FALSE,
    simulated BOOLEAN NOT NULL DEFAULT FALSE,
    execution_actor VARCHAR(64) NOT NULL,
    reason_code VARCHAR(128),
    outcome_summary TEXT NOT NULL,
    queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL,
    playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    playbook_step_index INTEGER,
    approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL,
    notification_delivery_attempt_id INTEGER REFERENCES notification_delivery_attempts(id) ON DELETE SET NULL,
    response_action_log_id INTEGER REFERENCES response_actions_log(id) ON DELETE SET NULL,
    provider VARCHAR(64),
    adapter_name VARCHAR(64),
    external_reference TEXT,
    idempotency_key VARCHAR(160),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(soar_correlation_id)) > 0),
    CHECK (length(trim(event_type)) > 0),
    CHECK (length(trim(outcome_summary)) > 0),
    CHECK (
        execution_mode IN (
            'observed',
            'simulation',
            'tracking_only',
            'real'
        )
    ),
    CHECK (
        execution_state IN (
            'observed',
            'selected',
            'queued',
            'awaiting_approval',
            'running',
            'skipped',
            'blocked',
            'succeeded',
            'failed'
        )
    ),
    CHECK (
        execution_actor IN (
            'queue_worker',
            'playbook_worker',
            'adapter',
            'approval_service',
            'manual',
            'system'
        )
    ),
    CHECK (
        reason_code IS NULL
        OR reason_code IN (
            'approval_required',
            'approval_denied',
            'simulation_mode',
            'tracking_only',
            'adapter_unavailable',
            'provider_error',
            'policy_blocked',
            'duplicate_suppressed',
            'unsupported_action'
        )
    ),
    CHECK (
        external_executed = FALSE
        OR (
            execution_mode = 'real'
            AND execution_state = 'succeeded'
        )
    ),
    CHECK (
        tracking_recorded = FALSE
        OR (
            execution_mode = 'tracking_only'
            AND execution_state = 'succeeded'
        )
    ),
    CHECK (
        simulated = FALSE
        OR execution_mode = 'simulation'
    ),
    CHECK (
        execution_mode <> 'observed'
        OR (
            external_executed = FALSE
            AND tracking_recorded = FALSE
            AND simulated = FALSE
        )
    ),
    CHECK (
        execution_mode <> 'real'
        OR (
            simulated = FALSE
            AND tracking_recorded = FALSE
        )
    ),
    CHECK (
        execution_mode <> 'tracking_only'
        OR (
            simulated = FALSE
            AND external_executed = FALSE
        )
    ),
    CHECK (playbook_step_index IS NULL OR playbook_step_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_decision_id
    ON soar_response_outcome_events (decision_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_alert_id
    ON soar_response_outcome_events (alert_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_incident_id
    ON soar_response_outcome_events (incident_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_source_ip
    ON soar_response_outcome_events (source_ip);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_soar_correlation_id
    ON soar_response_outcome_events (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_created_at
    ON soar_response_outcome_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_decision_latest
    ON soar_response_outcome_events (decision_id, created_at DESC, id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_mode_state_created
    ON soar_response_outcome_events (execution_mode, execution_state, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_queue_id
    ON soar_response_outcome_events (queue_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_playbook_execution_step
    ON soar_response_outcome_events (playbook_execution_id, playbook_step_index);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_approval_request_id
    ON soar_response_outcome_events (approval_request_id);

CREATE INDEX IF NOT EXISTS idx_soar_response_outcome_events_notification_delivery_id
    ON soar_response_outcome_events (notification_delivery_attempt_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_soar_response_outcome_events_idempotency_key
    ON soar_response_outcome_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE response_actions_queue
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL;

ALTER TABLE response_actions_queue
    ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128);

ALTER TABLE response_actions_log
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL;

ALTER TABLE response_actions_log
    ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128);

ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL;

ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128);

ALTER TABLE approval_requests
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL;

ALTER TABLE approval_requests
    ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128);

ALTER TABLE notification_delivery_attempts
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL;

ALTER TABLE notification_delivery_attempts
    ADD COLUMN IF NOT EXISTS soar_correlation_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_response_actions_queue_decision_id
    ON response_actions_queue (decision_id);

CREATE INDEX IF NOT EXISTS idx_response_actions_queue_soar_correlation_id
    ON response_actions_queue (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_response_actions_log_decision_id
    ON response_actions_log (decision_id);

CREATE INDEX IF NOT EXISTS idx_response_actions_log_soar_correlation_id
    ON response_actions_log (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_playbook_executions_decision_id
    ON playbook_executions (decision_id);

CREATE INDEX IF NOT EXISTS idx_playbook_executions_soar_correlation_id
    ON playbook_executions (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_decision_id
    ON approval_requests (decision_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_soar_correlation_id
    ON approval_requests (soar_correlation_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_decision_id
    ON notification_delivery_attempts (decision_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_soar_correlation_id
    ON notification_delivery_attempts (soar_correlation_id);
