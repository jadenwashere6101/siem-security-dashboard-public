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

ALTER TABLE soc_briefing_jobs
    ADD COLUMN IF NOT EXISTS trigger_type TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (trigger_type IN ('scheduled', 'manual')),
    ADD COLUMN IF NOT EXISTS requested_by TEXT,
    ADD COLUMN IF NOT EXISTS request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'soc_briefing_jobs_request_metadata_object'
    ) THEN
        ALTER TABLE soc_briefing_jobs
            ADD CONSTRAINT soc_briefing_jobs_request_metadata_object
            CHECK (jsonb_typeof(request_metadata) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_trigger_status
    ON soc_briefing_jobs (trigger_type, status, created_at DESC);
