-- Additive: allow canonical internal and read_only execution modes.
-- Vocabulary already defines these modes; writers must persist them truthfully.
-- Does not rewrite historical simulation-labeled rows.
--
-- Root-cause note: PostgreSQL auto-names the CREATE TABLE CHECK from migration
-- 0012 as soar_response_outcome_events_execution_mode_check. A naive DROP that
-- matched any definition containing both execution_mode and tracking_only
-- incorrectly selected the tracking_only boolean-guard constraint, left the
-- membership check in place, then failed on ADD with "already exists".

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Drop the existing membership CHECK whether it is the known auto-name
    -- or an alternate name, but never drop boolean/evidence guards
    -- (those use "execution_mode <> ..." shapes).
    SELECT con.conname
    INTO constraint_name
    FROM pg_constraint con
    WHERE con.conrelid = 'soar_response_outcome_events'::regclass
      AND con.contype = 'c'
      AND (
          con.conname = 'soar_response_outcome_events_execution_mode_check'
          OR (
              pg_get_constraintdef(con.oid) LIKE '%execution_mode%'
              AND pg_get_constraintdef(con.oid) LIKE '%observed%'
              AND pg_get_constraintdef(con.oid) LIKE '%simulation%'
              AND pg_get_constraintdef(con.oid) LIKE '%tracking_only%'
              AND pg_get_constraintdef(con.oid) LIKE '%real%'
              AND pg_get_constraintdef(con.oid) NOT LIKE '%execution_mode <>%'
          )
      )
      AND pg_get_constraintdef(con.oid) NOT LIKE '%internal%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%read_only%'
    ORDER BY CASE
        WHEN con.conname = 'soar_response_outcome_events_execution_mode_check' THEN 0
        ELSE 1
    END
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
          AND con.conname = 'soar_response_outcome_events_execution_mode_check'
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
BEGIN
    -- Ensure internal cannot claim external/tracking/simulation effects.
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        WHERE con.conrelid = 'soar_response_outcome_events'::regclass
          AND con.contype = 'c'
          AND con.conname = 'soar_response_outcome_events_internal_mode_booleans_check'
    ) THEN
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
BEGIN
    -- Ensure read_only cannot claim external/tracking/simulation effects.
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        WHERE con.conrelid = 'soar_response_outcome_events'::regclass
          AND con.contype = 'c'
          AND con.conname = 'soar_response_outcome_events_read_only_mode_booleans_check'
    ) THEN
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
