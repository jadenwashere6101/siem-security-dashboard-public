-- Additive: allow distinct approval_expired reason_code on canonical outcome tables.
-- Does not rewrite historical approval_denied rows.

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'soar_response_decisions'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%approval_denied%'
      AND pg_get_constraintdef(con.oid) LIKE '%reason_code%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%approval_expired%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE soar_response_decisions DROP CONSTRAINT %I',
            constraint_name
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        WHERE con.conrelid = 'soar_response_decisions'::regclass
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%approval_expired%'
          AND pg_get_constraintdef(con.oid) LIKE '%reason_code%'
    ) THEN
        ALTER TABLE soar_response_decisions
        ADD CONSTRAINT soar_response_decisions_reason_code_check
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
        );
    END IF;
END $$;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'soar_response_outcome_events'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%approval_denied%'
      AND pg_get_constraintdef(con.oid) LIKE '%reason_code%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%approval_expired%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE soar_response_outcome_events DROP CONSTRAINT %I',
            constraint_name
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        WHERE con.conrelid = 'soar_response_outcome_events'::regclass
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%approval_expired%'
          AND pg_get_constraintdef(con.oid) LIKE '%reason_code%'
    ) THEN
        ALTER TABLE soar_response_outcome_events
        ADD CONSTRAINT soar_response_outcome_events_reason_code_check
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
        );
    END IF;
END $$;
