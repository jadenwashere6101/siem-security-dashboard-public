-- Additive lease metadata for playbook execution worker ownership (slice 1).
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

CREATE INDEX IF NOT EXISTS idx_playbook_executions_status_lease_expires_at
    ON playbook_executions (status, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_playbook_executions_lease_owner
    ON playbook_executions (lease_owner)
    WHERE lease_owner IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_playbook_executions_status_created_at
    ON playbook_executions (status, created_at, id);
