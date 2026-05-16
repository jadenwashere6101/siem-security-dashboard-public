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
