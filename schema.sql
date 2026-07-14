-- Schema snapshot version: 0021

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_ip INET NOT NULL,
    source TEXT NOT NULL DEFAULT 'bank_app',
    source_type TEXT NOT NULL DEFAULT 'custom',
    event_timestamp TIMESTAMPTZ,
    message TEXT NOT NULL,
    app_name TEXT NOT NULL DEFAULT 'unknown_app',
    environment TEXT NOT NULL DEFAULT 'dev',
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_ip INET NOT NULL,
    source TEXT,
    source_type TEXT,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    country TEXT,
    city TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    reputation_score INTEGER,
    reputation_label TEXT,
    reputation_source TEXT,
    reputation_summary TEXT,
    response_action TEXT,
    response_status TEXT,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS response_actions_log (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    source_ip INET,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- response_actions_queue holds pending actions for future async execution.
-- response_actions_log (above) remains the audit trail of what was executed;
-- this table tracks what is intended to be executed. A queue row may reference
-- a log row once execution completes, but the log schema is not modified here.
CREATE TABLE IF NOT EXISTS response_actions_queue (
    id SERIAL PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    source_ip INET,
    action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'awaiting_approval', 'success', 'failed', 'skipped')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'response_actions_queue_status_check'
          AND conrelid = 'response_actions_queue'::regclass
    ) THEN
        ALTER TABLE response_actions_queue
        DROP CONSTRAINT response_actions_queue_status_check;
    END IF;

    ALTER TABLE response_actions_queue
    ADD CONSTRAINT response_actions_queue_status_check
    CHECK (status IN ('pending', 'running', 'awaiting_approval', 'success', 'failed', 'skipped'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('super_admin', 'analyst', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_username TEXT,
    actor_role TEXT,
    target_username TEXT,
    target_alert_id INTEGER,
    http_method TEXT,
    request_path TEXT,
    source_ip INET,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_notes (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS detection_config (
    rule_id TEXT PRIMARY KEY,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pfsense_ingest_config (
    category TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (category IN ('block_events', 'inbound_sensitive_port_allows', 'all_allow_events', 'dns_traffic', 'icmp_traffic')),
    CHECK (jsonb_typeof(parameters) = 'object')
);

INSERT INTO pfsense_ingest_config (category, enabled, parameters)
VALUES
    ('block_events', TRUE, '{}'::jsonb),
    ('inbound_sensitive_port_allows', TRUE, '{"sensitive_ports":[21,22,23,25,135,445,1433,3306,3389,5432,5900,6379,27017]}'::jsonb),
    ('all_allow_events', FALSE, '{}'::jsonb),
    ('dns_traffic', FALSE, '{}'::jsonb),
    ('icmp_traffic', FALSE, '{}'::jsonb)
ON CONFLICT (category) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_pfsense_ingest_config_updated_at
ON pfsense_ingest_config (updated_at DESC);

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
    critical_cross_source_destination TEXT NOT NULL
        DEFAULT 'Critical / Cross-Source Security destination'
        CHECK (btrim(critical_cross_source_destination) <> ''),
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
    critical_cross_source_destination,
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
    'Critical / Cross-Source Security destination',
    NULL
)
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_notification_policy_updated_at
ON notification_policy (updated_at DESC);

CREATE TABLE IF NOT EXISTS blocked_ips (
    id SERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    source_alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_events_source_ip ON events (source_ip);
CREATE INDEX IF NOT EXISTS idx_events_source ON events (source);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events (created_at);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);

CREATE INDEX IF NOT EXISTS idx_alerts_source_ip ON alerts (source_ip);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts (created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts (alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);

CREATE INDEX IF NOT EXISTS idx_response_actions_log_alert_id
ON response_actions_log (alert_id);

CREATE INDEX IF NOT EXISTS idx_response_actions_log_executed_at
ON response_actions_log (executed_at);

CREATE INDEX IF NOT EXISTS idx_response_actions_queue_status
ON response_actions_queue (status);

CREATE INDEX IF NOT EXISTS idx_response_actions_queue_alert_id
ON response_actions_queue (alert_id);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_username ON audit_log (actor_username);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_target_username ON audit_log (target_username);
CREATE INDEX IF NOT EXISTS idx_audit_log_target_alert_id ON audit_log (target_alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_notes_alert_id ON alert_notes (alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_notes_created_at ON alert_notes (created_at);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_ip_address ON blocked_ips (ip_address);
CREATE INDEX IF NOT EXISTS idx_blocked_ips_status ON blocked_ips (status);

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'P2'
        CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    source_ip INET,
    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (incident_id, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_source_ip ON incidents (source_ip);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents (severity);
CREATE INDEX IF NOT EXISTS idx_incident_alerts_alert_id ON incident_alerts (alert_id);
CREATE INDEX IF NOT EXISTS idx_incident_alerts_incident_id ON incident_alerts (incident_id);

CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE RESTRICT,
    queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE RESTRICT,
    playbook_execution_id INTEGER,
    playbook_step_index INTEGER,
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    action TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'high'
        CHECK (risk_level IN ('medium', 'high', 'critical')),
    request_reason TEXT,
    decision_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (
        incident_id IS NOT NULL
        OR queue_id IS NOT NULL
        OR playbook_execution_id IS NOT NULL
    ),
    CHECK (
        (status = 'pending' AND decided_at IS NULL)
        OR (status IN ('approved', 'denied', 'expired') AND decided_at IS NOT NULL)
    ),
    CHECK (
        (status = 'approved' AND approved_by IS NOT NULL)
        OR status IN ('pending', 'denied', 'expired')
    )
);

ALTER TABLE approval_requests
    ADD COLUMN IF NOT EXISTS playbook_execution_id INTEGER;

ALTER TABLE approval_requests
    ADD COLUMN IF NOT EXISTS playbook_step_index INTEGER;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'approval_requests'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%incident_id IS NOT NULL%'
      AND pg_get_constraintdef(con.oid) LIKE '%queue_id IS NOT NULL%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%playbook_execution_id IS NOT NULL%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE approval_requests DROP CONSTRAINT %I', constraint_name);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        WHERE con.conrelid = 'approval_requests'::regclass
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%playbook_execution_id IS NOT NULL%'
          AND pg_get_constraintdef(con.oid) LIKE '%incident_id IS NOT NULL%'
          AND pg_get_constraintdef(con.oid) LIKE '%queue_id IS NOT NULL%'
    ) THEN
        ALTER TABLE approval_requests
        ADD CONSTRAINT approval_requests_target_check
        CHECK (
            incident_id IS NOT NULL
            OR queue_id IS NOT NULL
            OR playbook_execution_id IS NOT NULL
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS approval_request_events (
    id SERIAL PRIMARY KEY,
    approval_request_id INTEGER NOT NULL
        REFERENCES approval_requests(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('created', 'approved', 'denied', 'expired')),
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_status
ON approval_requests (status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_incident_id
ON approval_requests (incident_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_queue_id
ON approval_requests (queue_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_queue_action
ON approval_requests (queue_id, action, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_approval_requests_expires_at
ON approval_requests (expires_at);

CREATE INDEX IF NOT EXISTS idx_approval_requests_pending_expiry
ON approval_requests (expires_at)
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_approval_request_events_request_id
ON approval_request_events (approval_request_id);

CREATE INDEX IF NOT EXISTS idx_approval_request_events_created_at
ON approval_request_events (created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_requests_queue_action_active
ON approval_requests (queue_id, action)
WHERE queue_id IS NOT NULL
  AND status IN ('pending', 'approved');

-- Playbook definitions and executions (SOAR playbook foundation).
-- Step execution and ingest wiring are intentionally out of scope for this schema slice.
CREATE TABLE IF NOT EXISTS playbook_definitions (
    id VARCHAR(64) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    trigger_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbook_definitions_enabled
    ON playbook_definitions (enabled);

CREATE TABLE IF NOT EXISTS playbook_schedules (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(64) NOT NULL REFERENCES playbook_definitions(id) ON DELETE CASCADE,
    schedule_expression TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    last_scheduled_execution_id INTEGER,
    missed_run_policy VARCHAR(30) NOT NULL DEFAULT 'skip',
    max_catchup_runs INTEGER NOT NULL DEFAULT 0,
    max_concurrent_runs INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (missed_run_policy IN ('skip', 'record_only', 'run_once')),
    CHECK (max_catchup_runs >= 0),
    CHECK (max_concurrent_runs >= 1)
);

CREATE INDEX IF NOT EXISTS idx_playbook_schedules_playbook_id
    ON playbook_schedules (playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbook_schedules_enabled
    ON playbook_schedules (enabled);
CREATE INDEX IF NOT EXISTS idx_playbook_schedules_next_run_at
    ON playbook_schedules (next_run_at);

CREATE TABLE IF NOT EXISTS playbook_executions (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(64) NOT NULL REFERENCES playbook_definitions(id),
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_completed_step INTEGER,
    steps_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_attempted_at TIMESTAMPTZ,
    failure_reason TEXT,
    stale_after INTEGER,
    timeout_seconds INTEGER,
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    recovery_count INTEGER NOT NULL DEFAULT 0,
    parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL,
    chain_depth INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS stale_after INTEGER;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS timeout_seconds INTEGER;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS lease_owner TEXT;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS lease_acquired_at TIMESTAMPTZ;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS lease_heartbeat_at TIMESTAMPTZ;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS recovery_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL;
ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS chain_depth INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_playbook_executions_playbook_id
    ON playbook_executions (playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_alert_id
    ON playbook_executions (alert_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_status
    ON playbook_executions (status);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_created_at
    ON playbook_executions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_status_lease_expires_at
    ON playbook_executions (status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_lease_owner
    ON playbook_executions (lease_owner)
    WHERE lease_owner IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_playbook_executions_status_created_at
    ON playbook_executions (status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_parent_execution_id
    ON playbook_executions (parent_execution_id);

CREATE TABLE IF NOT EXISTS soar_worker_heartbeats (
    worker_name VARCHAR(64) PRIMARY KEY,
    worker_instance_id VARCHAR(128) NOT NULL,
    build_version VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(worker_name)) > 0),
    CHECK (length(trim(worker_instance_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soar_worker_heartbeats_last_heartbeat_at
    ON soar_worker_heartbeats (last_heartbeat_at DESC);

CREATE INDEX IF NOT EXISTS idx_soar_worker_heartbeats_updated_at
    ON soar_worker_heartbeats (updated_at DESC);

DROP INDEX IF EXISTS idx_playbook_executions_playbook_alert_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_executions_playbook_alert_unique
    ON playbook_executions (playbook_id, alert_id)
    WHERE alert_id IS NOT NULL
      AND status IN ('pending', 'running', 'awaiting_approval');

DO $$
BEGIN
    ALTER TABLE approval_requests
    ADD CONSTRAINT approval_requests_playbook_execution_id_fkey
    FOREIGN KEY (playbook_execution_id)
    REFERENCES playbook_executions(id)
    ON DELETE RESTRICT;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_approval_requests_playbook_execution_id
    ON approval_requests (playbook_execution_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_requests_playbook_step_active
    ON approval_requests (playbook_execution_id, playbook_step_index)
    WHERE playbook_execution_id IS NOT NULL
      AND status IN ('pending', 'approved');

-- Immutable notification delivery attempt ledger (simulation and future real Slack/Teams).
-- Append-only at application layer: no UPDATE helpers; do not store secrets or raw payloads.
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
            'approval_expired',
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
            'real',
            'internal',
            'read_only'
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
            'approval_expired',
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
    CHECK (
        execution_mode <> 'internal'
        OR (
            simulated = FALSE
            AND external_executed = FALSE
            AND tracking_recorded = FALSE
        )
    ),
    CHECK (
        execution_mode <> 'read_only'
        OR (
            simulated = FALSE
            AND external_executed = FALSE
            AND tracking_recorded = FALSE
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
