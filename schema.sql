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
    CHECK (incident_id IS NOT NULL OR queue_id IS NOT NULL),
    CHECK (
        (status = 'pending' AND decided_at IS NULL)
        OR (status IN ('approved', 'denied', 'expired') AND decided_at IS NOT NULL)
    ),
    CHECK (
        (status = 'approved' AND approved_by IS NOT NULL)
        OR status IN ('pending', 'denied', 'expired')
    )
);

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
