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
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
