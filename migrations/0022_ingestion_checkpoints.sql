CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    connector_name TEXT PRIMARY KEY,
    last_processed_at TIMESTAMPTZ,
    last_poll_status TEXT,
    last_poll_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_updated_at
ON ingestion_checkpoints (updated_at DESC);
