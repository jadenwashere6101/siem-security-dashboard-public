ALTER TABLE source_ingestion_health_state
    ADD COLUMN IF NOT EXISTS total_events BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_events_initialized BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE source_ingestion_health_state
    DROP CONSTRAINT IF EXISTS source_ingestion_health_state_source_check;

ALTER TABLE source_ingestion_health_state
    ADD CONSTRAINT source_ingestion_health_state_source_check
    CHECK (
        source IN (
            'honeypot', 'bank_app', 'pfsense', 'nginx',
            'azure_insights', 'opentelemetry'
        )
    );

ALTER TABLE source_ingestion_health_state
    DROP CONSTRAINT IF EXISTS source_ingestion_health_state_total_events_check;

ALTER TABLE source_ingestion_health_state
    ADD CONSTRAINT source_ingestion_health_state_total_events_check
    CHECK (total_events >= 0);
