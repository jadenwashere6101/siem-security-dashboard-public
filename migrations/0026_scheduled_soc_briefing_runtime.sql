CREATE TABLE IF NOT EXISTS soc_briefing_schedules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    schedule_kind TEXT NOT NULL DEFAULT 'cadence'
        CHECK (schedule_kind IN ('cadence')),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    cadence_minutes INTEGER NOT NULL DEFAULT 1440
        CHECK (cadence_minutes > 0 AND cadence_minutes <= 10080),
    time_of_day TIME,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked')),
    failure_code TEXT,
    failure_message TEXT,
    catch_up_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    max_catch_up_windows INTEGER NOT NULL DEFAULT 3
        CHECK (max_catch_up_windows >= 0 AND max_catch_up_windows <= 24),
    max_lookback_hours INTEGER NOT NULL DEFAULT 24
        CHECK (max_lookback_hours > 0 AND max_lookback_hours <= 168),
    coalesce_missed_windows BOOLEAN NOT NULL DEFAULT TRUE,
    next_due_at TIMESTAMPTZ,
    last_successful_window_end TIMESTAMPTZ,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(name)) > 0),
    CHECK (length(trim(timezone)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_schedules_due
    ON soc_briefing_schedules (enabled, next_due_at);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_schedules_status
    ON soc_briefing_schedules (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_schedule_windows (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'queued', 'running', 'success', 'partial', 'failed', 'blocked', 'skipped')),
    skip_reason TEXT,
    coalesced BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_end > window_start),
    UNIQUE (schedule_id, window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_windows_schedule_status_end
    ON soc_briefing_schedule_windows (schedule_id, status, window_end);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_windows_created
    ON soc_briefing_schedule_windows (created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_jobs (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL UNIQUE REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    priority INTEGER NOT NULL DEFAULT 100,
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0 AND max_attempts <= 10),
    recovery_count INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_count >= 0),
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    service_actor TEXT NOT NULL DEFAULT 'scheduled_soc_briefing_worker',
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_code TEXT,
    failure_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (lease_owner IS NULL OR length(trim(lease_owner)) > 0),
    CHECK (length(trim(service_actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_claim
    ON soc_briefing_jobs (status, not_before, priority, id);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_lease_expires
    ON soc_briefing_jobs (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_soc_briefing_jobs_schedule_status
    ON soc_briefing_jobs (schedule_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_runs (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES soc_briefing_jobs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    run_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    service_actor TEXT NOT NULL DEFAULT 'scheduled_soc_briefing_worker',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    runtime_ms INTEGER
        CHECK (runtime_ms IS NULL OR runtime_ms >= 0),
    ai_gateway_status TEXT,
    provider_status TEXT,
    budget_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(budget_policy) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (length(trim(service_actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_runs_status_started
    ON soc_briefing_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_runs_schedule_started
    ON soc_briefing_runs (schedule_id, started_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefing_run_steps (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL
        CHECK (step_index >= 0),
    step_type TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('running', 'success', 'partial', 'failed', 'blocked', 'skipped', 'interrupted')),
    tool_name TEXT,
    sanitized_input JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_summary TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0
        CHECK (latency_ms >= 0),
    error_code TEXT,
    error_message TEXT,
    read_only BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, step_index),
    CHECK (length(trim(step_type)) > 0),
    CHECK (jsonb_typeof(sanitized_input) = 'object'),
    CHECK (jsonb_typeof(evidence_refs) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_run_steps_run_index
    ON soc_briefing_run_steps (run_id, step_index);

CREATE INDEX IF NOT EXISTS idx_soc_briefing_run_steps_status
    ON soc_briefing_run_steps (status, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_briefings (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL UNIQUE REFERENCES soc_briefing_runs(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES soc_briefing_schedules(id) ON DELETE CASCADE,
    window_id INTEGER NOT NULL REFERENCES soc_briefing_schedule_windows(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'success', 'partial', 'failed', 'blocked', 'skipped')),
    lifecycle_status TEXT NOT NULL DEFAULT 'created'
        CHECK (lifecycle_status IN ('created', 'content_pending', 'content_ready', 'blocked', 'failed', 'skipped')),
    briefing_type TEXT NOT NULL DEFAULT 'scheduled_soc_briefing',
    generated_at TIMESTAMPTZ,
    content_status TEXT NOT NULL DEFAULT 'not_generated'
        CHECK (content_status IN ('not_generated', 'pending', 'ready', 'blocked', 'failed', 'skipped')),
    summary TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(sections) = 'object'),
    CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CHECK (length(trim(briefing_type)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soc_briefings_schedule_generated
    ON soc_briefings (schedule_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_soc_briefings_status_created
    ON soc_briefings (status, created_at DESC);
