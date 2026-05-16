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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbook_executions_playbook_id
    ON playbook_executions (playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_alert_id
    ON playbook_executions (alert_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_status
    ON playbook_executions (status);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_created_at
    ON playbook_executions (created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_executions_playbook_alert_unique
    ON playbook_executions (playbook_id, alert_id)
    WHERE alert_id IS NOT NULL
      AND status IN ('pending', 'running', 'awaiting_approval');
