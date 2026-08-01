CREATE TABLE IF NOT EXISTS ai_workflow_requests (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    workflow TEXT NOT NULL
        CHECK (workflow IN ('deep_investigate', 'decision_support', 'generate_artifact')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'partial', 'degraded', 'failed', 'timed_out', 'cancelled', 'expired')),
    stage TEXT NOT NULL DEFAULT 'queued'
        CHECK (stage IN (
            'queued',
            'running',
            'gathering_context',
            'retrieving_evidence',
            'querying_tools',
            'preparing_evidence',
            'generating_analysis',
            'validating_response',
            'complete',
            'failed'
        )),
    context_type TEXT,
    idempotency_key TEXT NOT NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    classification JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_payload JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 1
        CHECK (max_attempts > 0 AND max_attempts <= 5),
    recovery_count INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_count >= 0),
    priority INTEGER NOT NULL DEFAULT 100,
    lease_owner TEXT,
    lease_acquired_at TIMESTAMPTZ,
    lease_heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(request_id)) > 0),
    CHECK (length(trim(workflow)) > 0),
    CHECK (length(trim(idempotency_key)) > 0),
    CHECK (length(trim(actor_username)) > 0),
    CHECK (length(trim(actor_role)) > 0),
    CHECK (lease_owner IS NULL OR length(trim(lease_owner)) > 0),
    CHECK (jsonb_typeof(request_payload) = 'object'),
    CHECK (jsonb_typeof(classification) = 'object'),
    CHECK (jsonb_typeof(lifecycle) = 'object'),
    CHECK (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_workflow_requests_active_idempotency
    ON ai_workflow_requests (actor_username, idempotency_key)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_claim
    ON ai_workflow_requests (status, not_before, priority, id);

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_actor_created
    ON ai_workflow_requests (actor_username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_workflow_requests_lease_expires
    ON ai_workflow_requests (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;
