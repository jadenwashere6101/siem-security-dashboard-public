-- Schema snapshot version: 0034

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

CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    connector_name TEXT PRIMARY KEY,
    last_processed_at TIMESTAMPTZ,
    last_poll_status TEXT,
    last_poll_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_updated_at
ON ingestion_checkpoints (updated_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_events_source_ip_created_at_latest
ON events (source_ip, created_at DESC, id DESC) INCLUDE (environment);

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

CREATE TABLE IF NOT EXISTS incident_notes (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS idx_incident_notes_incident_id ON incident_notes (incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_notes_created_at ON incident_notes (created_at);
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

CREATE TABLE IF NOT EXISTS ai_action_idempotency (
    id SERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_digest TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_resource_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome TEXT NOT NULL,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(target_resource_keys) = 'array'),
    CHECK (jsonb_typeof(result_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_ai_action_idempotency_action_type
    ON ai_action_idempotency (action_type);

CREATE TABLE IF NOT EXISTS soc_briefing_controls (
    id INTEGER PRIMARY KEY DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'manual_only'
        CHECK (mode IN ('manual_only', 'scheduled_autonomous')),
    schedules_paused BOOLEAN NOT NULL DEFAULT TRUE,
    pause_reason TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (id = 1)
);

INSERT INTO soc_briefing_controls (id, mode, schedules_paused, pause_reason)
VALUES (1, 'manual_only', TRUE, 'manual-first default')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS soc_briefing_schedules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    schedule_kind TEXT NOT NULL DEFAULT 'cadence'
        CHECK (schedule_kind IN ('cadence')),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    cadence_minutes INTEGER NOT NULL DEFAULT 1440
        CHECK (cadence_minutes > 0 AND cadence_minutes <= 10080),
    time_of_day TIME,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked')),
    failure_code TEXT,
    failure_message TEXT,
    catch_up_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    max_catch_up_windows INTEGER NOT NULL DEFAULT 3
        CHECK (max_catch_up_windows >= 0 AND max_catch_up_windows <= 24),
    max_lookback_hours INTEGER NOT NULL DEFAULT 24
        CHECK (max_lookback_hours > 0 AND max_lookback_hours <= 168),
    coalesce_missed_windows BOOLEAN NOT NULL DEFAULT TRUE,
    next_due_at TIMESTAMPTZ,
    last_successful_window_end TIMESTAMPTZ,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(name)) > 0),
    CHECK (length(trim(timezone)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_schedules_due
    ON soc_briefing_schedules (enabled, next_due_at);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_schedules_status
    ON soc_briefing_schedules (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_schedule_windows (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'queued', 'running', 'success', 'partial', 'failed', 'blocked', 'skipped')),
    skip_reason TEXT,
    coalesced BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_end > window_start),
    UNIQUE (schedule_id, window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_windows_schedule_status_end
    ON soc_briefing_schedule_windows (schedule_id, status, window_end);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_windows_created
    ON soc_briefing_schedule_windows (created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_jobs (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL UNIQUE REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    priority INTEGER NOT NULL DEFAULT 100,
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0 AND max_attempts <= 10),
    recovery_count INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_count >= 0),
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    service_actor TEXT NOT NULL DEFAULT 'scheduled_soc_briefing_worker',
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_code TEXT,
    failure_message TEXT,
    trigger_type TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (trigger_type IN ('scheduled', 'manual')),
    requested_by TEXT,
    request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(request_metadata) = 'object'),
    CHECK (lease_owner IS NULL OR length(trim(lease_owner)) > 0),
    CHECK (length(trim(service_actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_claim
    ON soc_briefing_jobs (status, not_before, priority, id);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_lease_expires
    ON soc_briefing_jobs (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_schedule_status
    ON soc_briefing_jobs (schedule_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_trigger_status
    ON soc_briefing_jobs (trigger_type, status, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_runs (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES soc_briefing_jobs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    run_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    service_actor TEXT NOT NULL DEFAULT 'scheduled_soc_briefing_worker',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    runtime_ms INTEGER
        CHECK (runtime_ms IS NULL OR runtime_ms >= 0),
    ai_gateway_status TEXT,
    provider_status TEXT,
    budget_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(budget_policy) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (length(trim(service_actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_runs_status_started
    ON soc_briefing_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_runs_schedule_started
    ON soc_briefing_runs (schedule_id, started_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_run_steps (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL
        CHECK (step_index >= 0),
    step_type TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    tool_name TEXT,
    sanitized_input JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_summary TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0
        CHECK (latency_ms >= 0),
    error_code TEXT,
    error_message TEXT,
    read_only BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, step_index),
    CHECK (length(trim(step_type)) > 0),
    CHECK (jsonb_typeof(sanitized_input) = 'object'),
    CHECK (jsonb_typeof(evidence_refs) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_run_steps_run_index
    ON soc_briefing_run_steps (run_id, step_index);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_run_steps_status
    ON soc_briefing_run_steps (status, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefings (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL UNIQUE REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'success', 'partial', 'failed', 'blocked', 'skipped')),
    lifecycle_status TEXT NOT NULL DEFAULT 'created'
        CHECK (lifecycle_status IN ('created', 'content_pending', 'content_ready', 'blocked', 'failed', 'skipped')),
    briefing_type TEXT NOT NULL DEFAULT 'scheduled_soc_briefing',
    generated_at TIMESTAMPTZ,
    content_status TEXT NOT NULL DEFAULT 'not_generated'
        CHECK (content_status IN ('not_generated', 'pending', 'ready', 'blocked', 'failed', 'skipped')),
    summary TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(sections) = 'object'),
    CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CHECK (length(trim(briefing_type)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefings_schedule_generated
    ON soc_briefings (schedule_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefings_status_created
    ON soc_briefings (status, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_delivery_attempts (
    id SERIAL PRIMARY KEY,
    briefing_id INTEGER NOT NULL REFERENCES soc_briefings(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL DEFAULT 'slack'
        CHECK (channel IN ('slack')),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'sent', 'failed', 'blocked', 'skipped', 'retry_scheduled', 'duplicate_suppressed')),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0 AND max_attempts <= 10),
    next_retry_at TIMESTAMPTZ,
    last_attempted_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    provider TEXT NOT NULL DEFAULT 'slack',
    provider_mode TEXT NOT NULL DEFAULT 'simulation'
        CHECK (provider_mode IN ('simulation', 'real')),
    summary_fingerprint TEXT NOT NULL,
    failure_code TEXT,
    failure_message TEXT,
    delivery_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(summary_fingerprint)) > 0),
    CHECK (jsonb_typeof(delivery_metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_briefing_created
    ON soc_briefing_delivery_attempts (briefing_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_status_retry
    ON soc_briefing_delivery_attempts (status, next_retry_at)
    WHERE status IN ('retry_scheduled', 'pending');

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_schedule_created
    ON soc_briefing_delivery_attempts (schedule_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_channel_status
    ON soc_briefing_delivery_attempts (channel, status, created_at DESC);

CREATE TABLE IF NOT EXISTS analyst_workspaces (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'My Investigation Workspace',
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(name)) > 0),
    UNIQUE (owner_username, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_analyst_workspaces_default_owner
    ON analyst_workspaces (owner_username)
    WHERE is_default = TRUE;

CREATE INDEX IF NOT EXISTS idx_analyst_workspaces_owner_updated
    ON analyst_workspaces (owner_username, updated_at DESC);

CREATE TABLE IF NOT EXISTS investigations (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'new', 'investigating', 'waiting', 'awaiting_evidence', 'ready_for_review', 'resolved', 'closed')),
    summary TEXT,
    linked_alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    linked_incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    linked_source_ip INET,
    disposition TEXT NOT NULL DEFAULT 'undetermined'
        CHECK (disposition IN ('true_positive', 'false_positive', 'benign_expected', 'needs_monitoring', 'escalated', 'undetermined')),
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    conclusion TEXT,
    closed_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    saved_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (jsonb_typeof(saved_state) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_investigations_owner_updated
    ON investigations (owner_username, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigations_owner_last_activity
    ON investigations (owner_username, last_activity_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigations_alert
    ON investigations (linked_alert_id)
    WHERE linked_alert_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_investigations_incident
    ON investigations (linked_incident_id)
    WHERE linked_incident_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS workspace_items (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    owner_username TEXT NOT NULL,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('alert', 'incident', 'recon_activity', 'source_ip', 'investigation', 'evidence')),
    referenced_object_type TEXT NOT NULL,
    referenced_object_id TEXT NOT NULL,
    label TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    item_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(referenced_object_type)) > 0),
    CHECK (length(trim(referenced_object_id)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (workspace_id, item_type, referenced_object_type, referenced_object_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_items_owner_order
    ON workspace_items (owner_username, item_order, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_items_workspace_order
    ON workspace_items (workspace_id, item_order, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_notes (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(body)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_notes_owner_created
    ON investigation_notes (owner_username, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_hypotheses (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'supported', 'rejected', 'unknown')),
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_hypotheses_owner_created
    ON investigation_hypotheses (owner_username, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_tasks (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'done')),
    hypothesis_id INTEGER REFERENCES investigation_hypotheses(id) ON DELETE SET NULL,
    evidence_reference_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_tasks_owner_status
    ON investigation_tasks (owner_username, status, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_references (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    parent_type TEXT NOT NULL DEFAULT 'workspace'
        CHECK (parent_type IN ('workspace', 'investigation')),
    referenced_object_type TEXT NOT NULL,
    referenced_object_id TEXT NOT NULL,
    label TEXT NOT NULL,
    source TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    rationale TEXT,
    relationship_type TEXT NOT NULL DEFAULT 'context'
        CHECK (relationship_type IN ('supports', 'refutes', 'context')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(referenced_object_type)) > 0),
    CHECK (length(trim(referenced_object_id)) > 0),
    CHECK (length(trim(label)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_evidence_references_owner_created
    ON evidence_references (owner_username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_references_investigation_created
    ON evidence_references (investigation_id, created_at DESC)
    WHERE investigation_id IS NOT NULL;

ALTER TABLE investigation_tasks
    ADD CONSTRAINT investigation_tasks_evidence_reference_id_fkey
    FOREIGN KEY (evidence_reference_id) REFERENCES evidence_references(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS investigation_hypothesis_evidence (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    hypothesis_id INTEGER NOT NULL REFERENCES investigation_hypotheses(id) ON DELETE CASCADE,
    evidence_reference_id INTEGER NOT NULL REFERENCES evidence_references(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT 'context'
        CHECK (relationship_type IN ('supports', 'refutes', 'context')),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    UNIQUE (hypothesis_id, evidence_reference_id)
);

CREATE INDEX IF NOT EXISTS idx_investigation_hypothesis_evidence_owner
    ON investigation_hypothesis_evidence (owner_username, investigation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_workflow_requests (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    workflow TEXT NOT NULL
        CHECK (workflow IN ('deep_investigate', 'decision_support', 'generate_artifact', 'repo_assistant')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'partial', 'degraded', 'failed', 'timed_out', 'cancelled', 'expired')),
    stage TEXT NOT NULL DEFAULT 'queued'
        CHECK (stage IN (
            'queued',
            'running',
            'gathering_context',
            'retrieving_evidence',
            'querying_tools',
            'preparing_evidence',
            'generating_analysis',
            'validating_response',
            'retrieving_repository_evidence',
            'preparing_repository_context',
            'generating_answer',
            'validating_citations',
            'complete',
            'failed'
        )),
    context_type TEXT,
    idempotency_key TEXT NOT NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    classification JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_payload JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 1
        CHECK (max_attempts > 0 AND max_attempts <= 5),
    recovery_count INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_count >= 0),
    priority INTEGER NOT NULL DEFAULT 100,
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(request_id)) > 0),
    CHECK (length(trim(workflow)) > 0),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(actor_username)) > 0),
    CHECK (length(trim(actor_role)) > 0),
    CHECK (lease_owner IS NULL OR length(trim(lease_owner)) > 0),
    CHECK (jsonb_typeof(request_payload) = 'object'),
    CHECK (jsonb_typeof(classification) = 'object'),
    CHECK (jsonb_typeof(lifecycle) = 'object'),
    CHECK (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_workflow_requests_active_idempotency
    ON ai_workflow_requests (actor_username, idempotency_key)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_claim
    ON ai_workflow_requests (status, not_before, priority, id);

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_actor_created
    ON ai_workflow_requests (actor_username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_lease_expires
    ON ai_workflow_requests (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS anakin_threads (
    thread_id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT 'siem' CHECK (domain = 'siem'),
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE SET NULL,
    primary_entity_type TEXT NOT NULL,
    primary_entity_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'reset', 'closed', 'archived')),
    focus_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    compact_summary TEXT,
    summary_version INTEGER NOT NULL DEFAULT 0 CHECK (summary_version >= 0),
    next_sequence BIGINT NOT NULL DEFAULT 1 CHECK (next_sequence > 0),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    archived_at TIMESTAMPTZ,
    delete_after TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    closed_at TIMESTAMPTZ,
    replaced_by_thread_id TEXT REFERENCES anakin_threads(thread_id) ON DELETE SET NULL,
    CHECK (length(trim(thread_id)) > 0),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(primary_entity_type)) > 0),
    CHECK (length(trim(primary_entity_id)) > 0),
    CHECK (length(trim(scope_key)) > 0),
    CHECK (jsonb_typeof(focus_state) = 'object'),
    CHECK (expires_at >= last_active_at),
    CHECK (delete_after >= expires_at),
    CHECK ((status = 'active' AND closed_at IS NULL) OR status <> 'active'),
    CHECK (replaced_by_thread_id IS NULL OR status = 'reset'),
    UNIQUE (thread_id, owner_username)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_anakin_threads_active_default ON anakin_threads (owner_username, domain, scope_key) WHERE is_default = TRUE AND status = 'active';
CREATE INDEX IF NOT EXISTS idx_anakin_threads_owner_activity ON anakin_threads (owner_username, last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_anakin_threads_expiry ON anakin_threads (status, expires_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_anakin_threads_delete_after ON anakin_threads (delete_after) WHERE status <> 'active';

CREATE TABLE IF NOT EXISTS anakin_turns (
    id BIGSERIAL PRIMARY KEY,
    turn_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    thread_version_after_append BIGINT NOT NULL CHECK (thread_version_after_append > 1),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    workflow TEXT CHECK (workflow IN ('quick_explain', 'deep_investigate', 'decision_support', 'generate_artifact')),
    content TEXT NOT NULL,
    structured_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    assertion_type TEXT NOT NULL CHECK (assertion_type IN ('analyst_statement', 'model_inference', 'correction', 'unresolved_question', 'artifact_preview', 'system_event')),
    client_request_id TEXT NOT NULL,
    parent_turn_id BIGINT,
    entity_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle_status TEXT NOT NULL DEFAULT 'recorded' CHECK (lifecycle_status IN ('recorded', 'queued', 'running', 'completed', 'failed', 'cancelled', 'superseded')),
    preview_only BOOLEAN NOT NULL DEFAULT FALSE,
    persisted BOOLEAN NOT NULL DEFAULT FALSE,
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CHECK (length(trim(turn_id)) > 0),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(content)) > 0),
    CHECK (length(trim(client_request_id)) > 0),
    CHECK (jsonb_typeof(structured_payload) = 'object'),
    CHECK (jsonb_typeof(entity_snapshot) = 'object'),
    CHECK (assertion_type <> 'artifact_preview' OR (preview_only = TRUE AND persisted = FALSE AND applied = FALSE AND approval_required = TRUE)),
    UNIQUE (thread_id, sequence),
    UNIQUE (owner_username, thread_id, client_request_id),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username) REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (parent_turn_id, thread_id, owner_username) REFERENCES anakin_turns(id, thread_id, owner_username)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_anakin_turns_one_active_execution ON anakin_turns (thread_id) WHERE lifecycle_status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_anakin_turns_owner_thread_sequence ON anakin_turns (owner_username, thread_id, sequence);

CREATE OR REPLACE FUNCTION enforce_anakin_turn_immutable_fields()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.turn_id IS DISTINCT FROM OLD.turn_id OR NEW.thread_id IS DISTINCT FROM OLD.thread_id
       OR NEW.owner_username IS DISTINCT FROM OLD.owner_username OR NEW.sequence IS DISTINCT FROM OLD.sequence
       OR NEW.thread_version_after_append IS DISTINCT FROM OLD.thread_version_after_append
       OR NEW.role IS DISTINCT FROM OLD.role OR NEW.workflow IS DISTINCT FROM OLD.workflow
       OR NEW.content IS DISTINCT FROM OLD.content OR NEW.structured_payload IS DISTINCT FROM OLD.structured_payload
       OR NEW.assertion_type IS DISTINCT FROM OLD.assertion_type OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id
       OR NEW.parent_turn_id IS DISTINCT FROM OLD.parent_turn_id OR NEW.entity_snapshot IS DISTINCT FROM OLD.entity_snapshot
       OR NEW.preview_only IS DISTINCT FROM OLD.preview_only OR NEW.persisted IS DISTINCT FROM OLD.persisted
       OR NEW.applied IS DISTINCT FROM OLD.applied OR NEW.approval_required IS DISTINCT FROM OLD.approval_required
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN RAISE EXCEPTION 'anakin turn identity and content are immutable'; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_anakin_turn_immutable_fields ON anakin_turns;
CREATE TRIGGER trg_anakin_turn_immutable_fields BEFORE UPDATE ON anakin_turns FOR EACH ROW EXECUTE FUNCTION enforce_anakin_turn_immutable_fields();

CREATE TABLE IF NOT EXISTS anakin_thread_entities (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    display_alias TEXT,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    salience DOUBLE PRECISION NOT NULL DEFAULT 0.5 CHECK (salience >= 0 AND salience <= 1),
    first_referenced_sequence BIGINT NOT NULL CHECK (first_referenced_sequence > 0),
    last_referenced_sequence BIGINT NOT NULL CHECK (last_referenced_sequence >= first_referenced_sequence),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(entity_type)) > 0),
    CHECK (length(trim(entity_id)) > 0),
    UNIQUE (thread_id, entity_type, entity_id),
    UNIQUE (thread_id, ordinal),
    FOREIGN KEY (thread_id, owner_username) REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_anakin_thread_entities_owner_thread ON anakin_thread_entities (owner_username, thread_id, salience DESC, ordinal);

CREATE TABLE IF NOT EXISTS anakin_thread_state (
    thread_id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    state_version BIGINT NOT NULL DEFAULT 1 CHECK (state_version > 0),
    conclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    unresolved_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    corrections JSONB NOT NULL DEFAULT '[]'::jsonb,
    compact_summary TEXT,
    rebuild_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    rebuild_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(conclusions) = 'array'), CHECK (jsonb_typeof(unresolved_questions) = 'array'),
    CHECK (jsonb_typeof(recommendations) = 'array'), CHECK (jsonb_typeof(corrections) = 'array'),
    CHECK (jsonb_typeof(rebuild_metadata) = 'object'),
    FOREIGN KEY (thread_id, owner_username) REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anakin_thread_hypotheses (
    id BIGSERIAL PRIMARY KEY,
    hypothesis_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'weakened', 'rejected')),
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('analyst_statement', 'model_inference', 'correction')),
    provenance_turn_id BIGINT,
    superseded_by_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(hypothesis_id)) > 0), CHECK (length(trim(hypothesis)) > 0),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username) REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (provenance_turn_id, thread_id, owner_username) REFERENCES anakin_turns(id, thread_id, owner_username),
    FOREIGN KEY (superseded_by_id, thread_id, owner_username) REFERENCES anakin_thread_hypotheses(id, thread_id, owner_username)
);
CREATE INDEX IF NOT EXISTS idx_anakin_hypotheses_owner_thread ON anakin_thread_hypotheses (owner_username, thread_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS anakin_thread_evidence (
    id BIGSERIAL PRIMARY KEY,
    evidence_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    hypothesis_id BIGINT,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    snapshot JSONB,
    snapshot_hash TEXT,
    query_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    entity_fingerprint TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    fresh_until TIMESTAMPTZ,
    relationship_type TEXT NOT NULL DEFAULT 'context' CHECK (relationship_type IN ('supports', 'refutes', 'context')),
    provenance_type TEXT NOT NULL DEFAULT 'verified_evidence' CHECK (provenance_type = 'verified_evidence'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(evidence_id)) > 0), CHECK (length(trim(source_type)) > 0), CHECK (length(trim(source_ref)) > 0),
    CHECK (snapshot IS NULL OR jsonb_typeof(snapshot) IN ('object', 'array')),
    CHECK (snapshot IS NULL OR octet_length(snapshot::text) <= 32768),
    CHECK (snapshot IS NOT NULL OR length(trim(COALESCE(snapshot_hash, ''))) > 0),
    CHECK (jsonb_typeof(query_parameters) = 'object'), CHECK (fresh_until IS NULL OR fresh_until >= observed_at),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username) REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (hypothesis_id, thread_id, owner_username) REFERENCES anakin_thread_hypotheses(id, thread_id, owner_username)
);
CREATE INDEX IF NOT EXISTS idx_anakin_evidence_owner_thread_freshness ON anakin_thread_evidence (owner_username, thread_id, observed_at DESC, fresh_until);

CREATE TABLE IF NOT EXISTS anakin_thread_tombstones (
    thread_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL CHECK (domain = 'siem'),
    deletion_reason TEXT NOT NULL CHECK (deletion_reason IN ('retention_expired')),
    content_deleted BOOLEAN NOT NULL DEFAULT TRUE CHECK (content_deleted = TRUE),
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(thread_id)) > 0)
);

ALTER TABLE ai_workflow_requests ADD COLUMN IF NOT EXISTS thread_id TEXT, ADD COLUMN IF NOT EXISTS turn_id BIGINT;
ALTER TABLE ai_workflow_requests ADD CONSTRAINT ai_workflow_requests_thread_turn_pair_check CHECK ((thread_id IS NULL AND turn_id IS NULL) OR (thread_id IS NOT NULL AND turn_id IS NOT NULL));
ALTER TABLE ai_workflow_requests ADD CONSTRAINT ai_workflow_requests_request_actor_unique UNIQUE (request_id, actor_username);
ALTER TABLE ai_workflow_requests ADD CONSTRAINT ai_workflow_requests_thread_owner_fkey FOREIGN KEY (thread_id, actor_username) REFERENCES anakin_threads(thread_id, owner_username);
ALTER TABLE ai_workflow_requests ADD CONSTRAINT ai_workflow_requests_turn_thread_owner_fkey FOREIGN KEY (turn_id, thread_id, actor_username) REFERENCES anakin_turns(id, thread_id, owner_username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_workflow_requests_turn_link ON ai_workflow_requests (turn_id) WHERE turn_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ai_paid_usage_days (
    usage_day DATE PRIMARY KEY,
    daily_cap_usd NUMERIC(18, 8) NOT NULL CHECK (daily_cap_usd > 0),
    reserved_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
    settled_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (settled_usd >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (reserved_usd + settled_usd <= daily_cap_usd)
);

CREATE TABLE IF NOT EXISTS ai_paid_request_attempts (
    attempt_id TEXT PRIMARY KEY,
    usage_day DATE NOT NULL REFERENCES ai_paid_usage_days(usage_day),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    profile TEXT NOT NULL,
    correlation_id TEXT,
    attempt_kind TEXT NOT NULL CHECK (attempt_kind IN ('initial', 'repair')),
    status TEXT NOT NULL,
    reserved_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    settled_cost_usd NUMERIC(18, 8) CHECK (settled_cost_usd >= 0),
    estimated_cost_usd NUMERIC(18, 8) NOT NULL CHECK (estimated_cost_usd >= 0),
    actual_billed_cost_usd NUMERIC(18, 8),
    input_tokens BIGINT NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens BIGINT NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens BIGINT NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    token_usage_source TEXT NOT NULL CHECK (token_usage_source IN ('estimated', 'provider_reported')),
    cost_source TEXT NOT NULL CHECK (cost_source IN ('estimated', 'provider_reported')),
    provider_latency_ms BIGINT CHECK (provider_latency_ms >= 0),
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (length(trim(attempt_id)) > 0),
    CHECK (length(trim(provider)) > 0),
    CHECK (length(trim(model)) > 0),
    CHECK (length(trim(profile)) > 0),
    CHECK (correlation_id IS NULL OR length(trim(correlation_id)) > 0),
    CHECK (actual_billed_cost_usd IS NULL OR actual_billed_cost_usd >= 0)
);

CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_usage_day
    ON ai_paid_request_attempts (usage_day, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_correlation
    ON ai_paid_request_attempts (correlation_id, attempt_kind) WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_provider_profile
    ON ai_paid_request_attempts (provider, profile, created_at DESC);
