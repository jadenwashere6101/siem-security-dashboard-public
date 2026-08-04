CREATE TABLE IF NOT EXISTS ai_paid_usage_days (
    usage_day DATE PRIMARY KEY,
    daily_cap_usd NUMERIC(18, 8) NOT NULL CHECK (daily_cap_usd > 0),
    reserved_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
    settled_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (settled_usd >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (reserved_usd + settled_usd <= daily_cap_usd)
);

CREATE TABLE IF NOT EXISTS ai_paid_request_attempts (
    attempt_id TEXT PRIMARY KEY,
    usage_day DATE NOT NULL REFERENCES ai_paid_usage_days(usage_day),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    profile TEXT NOT NULL,
    correlation_id TEXT,
    attempt_kind TEXT NOT NULL CHECK (attempt_kind IN ('initial', 'repair')),
    status TEXT NOT NULL,
    reserved_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    settled_cost_usd NUMERIC(18, 8) CHECK (settled_cost_usd >= 0),
    estimated_cost_usd NUMERIC(18, 8) NOT NULL CHECK (estimated_cost_usd >= 0),
    actual_billed_cost_usd NUMERIC(18, 8),
    input_tokens BIGINT NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens BIGINT NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens BIGINT NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    token_usage_source TEXT NOT NULL CHECK (token_usage_source IN ('estimated', 'provider_reported')),
    cost_source TEXT NOT NULL CHECK (cost_source IN ('estimated', 'provider_reported')),
    provider_latency_ms BIGINT CHECK (provider_latency_ms >= 0),
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (length(trim(attempt_id)) > 0),
    CHECK (length(trim(provider)) > 0),
    CHECK (length(trim(model)) > 0),
    CHECK (length(trim(profile)) > 0),
    CHECK (correlation_id IS NULL OR length(trim(correlation_id)) > 0),
    CHECK (actual_billed_cost_usd IS NULL OR actual_billed_cost_usd >= 0)
);

CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_usage_day
    ON ai_paid_request_attempts (usage_day, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_correlation
    ON ai_paid_request_attempts (correlation_id, attempt_kind)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_paid_request_attempts_provider_profile
    ON ai_paid_request_attempts (provider, profile, created_at DESC);
