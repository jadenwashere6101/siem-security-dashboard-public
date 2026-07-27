CREATE TABLE IF NOT EXISTS soc_briefing_delivery_attempts (
    id SERIAL PRIMARY KEY,
    briefing_id INTEGER NOT NULL REFERENCES soc_briefings(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL DEFAULT 'slack'
        CHECK (channel IN ('slack')),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'sent', 'failed', 'blocked', 'skipped', 'retry_scheduled', 'duplicate_suppressed')),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0 AND max_attempts <= 10),
    next_retry_at TIMESTAMPTZ,
    last_attempted_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    provider TEXT NOT NULL DEFAULT 'slack',
    provider_mode TEXT NOT NULL DEFAULT 'simulation'
        CHECK (provider_mode IN ('simulation', 'real')),
    summary_fingerprint TEXT NOT NULL,
    failure_code TEXT,
    failure_message TEXT,
    delivery_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(summary_fingerprint)) > 0),
    CHECK (jsonb_typeof(delivery_metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_briefing_created
    ON soc_briefing_delivery_attempts (briefing_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_status_retry
    ON soc_briefing_delivery_attempts (status, next_retry_at)
    WHERE status IN ('retry_scheduled', 'pending');

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_schedule_created
    ON soc_briefing_delivery_attempts (schedule_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_delivery_channel_status
    ON soc_briefing_delivery_attempts (channel, status, created_at DESC);
