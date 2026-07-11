-- Additive: allow canonical internal and read_only execution modes.
-- Vocabulary already defines these modes; writers must persist them truthfully.
-- Does not rewrite historical simulation-labeled rows.

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'soar_response_outcome_events'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%execution_mode%'
      AND pg_get_constraintdef(con.oid) LIKE '%tracking_only%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%internal%'
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
          AND pg_get_constraintdef(con.oid) LIKE '%execution_mode%'
          AND pg_get_constraintdef(con.oid) LIKE '%internal%'
          AND pg_get_constraintdef(con.oid) LIKE '%read_only%'
    ) THEN
        ALTER TABLE soar_response_outcome_events
        ADD CONSTRAINT soar_response_outcome_events_execution_mode_check
        CHECK (
            execution_mode IN (
                'observed',
                'simulation',
                'tracking_only',
                'real',
                'internal',
                'read_only'
            )
        );
    END IF;
END $$;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Ensure internal/read_only cannot claim external or tracking effects.
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'soar_response_outcome_events'::regclass
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%execution_mode <> ''internal''%'
    LIMIT 1;

    IF constraint_name IS NULL THEN
        ALTER TABLE soar_response_outcome_events
        ADD CONSTRAINT soar_response_outcome_events_internal_mode_booleans_check
        CHECK (
            execution_mode <> 'internal'
            OR (
                simulated = FALSE
                AND external_executed = FALSE
                AND tracking_recorded = FALSE
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
      AND pg_get_constraintdef(con.oid) LIKE '%execution_mode <> ''read_only''%'
    LIMIT 1;

    IF constraint_name IS NULL THEN
        ALTER TABLE soar_response_outcome_events
        ADD CONSTRAINT soar_response_outcome_events_read_only_mode_booleans_check
        CHECK (
            execution_mode <> 'read_only'
            OR (
                simulated = FALSE
                AND external_executed = FALSE
                AND tracking_recorded = FALSE
            )
        );
    END IF;
END $$;
