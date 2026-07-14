CREATE TABLE IF NOT EXISTS soar_worker_heartbeats (
    worker_name VARCHAR(64) PRIMARY KEY,
    worker_instance_id VARCHAR(128) NOT NULL,
    build_version VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(worker_name)) > 0),
    CHECK (length(trim(worker_instance_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_soar_worker_heartbeats_last_heartbeat_at
    ON soar_worker_heartbeats (last_heartbeat_at DESC);

CREATE INDEX IF NOT EXISTS idx_soar_worker_heartbeats_updated_at
    ON soar_worker_heartbeats (updated_at DESC);
