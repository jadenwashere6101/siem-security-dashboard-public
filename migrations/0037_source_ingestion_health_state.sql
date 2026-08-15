CREATE TABLE IF NOT EXISTS source_ingestion_health_state (
    source TEXT PRIMARY KEY,
    latest_event_at TIMESTAMPTZ,
    latest_qualifying_real_ingestion_at TIMESTAMPTZ,
    historical_backfill_complete BOOLEAN NOT NULL DEFAULT FALSE,
    backfill_high_water_event_id BIGINT,
    backfill_last_processed_event_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        source IN ('honeypot', 'bank_app', 'pfsense', 'nginx', 'opentelemetry')
    ),
    CHECK (backfill_high_water_event_id IS NULL OR backfill_high_water_event_id >= 0),
    CHECK (backfill_last_processed_event_id >= 0),
    CHECK (
        backfill_high_water_event_id IS NULL
        OR backfill_last_processed_event_id <= backfill_high_water_event_id
    ),
    CHECK (
        NOT historical_backfill_complete
        OR (
            backfill_high_water_event_id IS NOT NULL
            AND backfill_last_processed_event_id = backfill_high_water_event_id
        )
    )
);
