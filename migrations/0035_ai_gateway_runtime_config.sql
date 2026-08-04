CREATE TABLE IF NOT EXISTS ai_gateway_config (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    gateway_mode TEXT NOT NULL
        CHECK (gateway_mode IN ('disabled', 'local_only', 'ask_before_paid_fallback', 'automatic_fallback')),
    preferred_anthropic_model TEXT NOT NULL DEFAULT '',
    daily_paid_budget_usd NUMERIC(18, 8) NOT NULL DEFAULT 0
        CHECK (daily_paid_budget_usd >= 0),
    anthropic_routing_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        anthropic_routing_enabled = FALSE
        OR (
            length(trim(preferred_anthropic_model)) > 0
            AND daily_paid_budget_usd > 0
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_gateway_config_updated_at
    ON ai_gateway_config (updated_at DESC);
