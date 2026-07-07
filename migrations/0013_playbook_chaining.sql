ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL;

ALTER TABLE playbook_executions
    ADD COLUMN IF NOT EXISTS chain_depth INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_playbook_executions_parent_execution_id
    ON playbook_executions (parent_execution_id);
