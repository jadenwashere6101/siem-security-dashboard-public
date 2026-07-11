CREATE TABLE IF NOT EXISTS pfsense_ingest_config (
    category TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (category IN (
        'block_events',
        'inbound_sensitive_port_allows',
        'all_allow_events',
        'dns_traffic',
        'icmp_traffic'
    )),
    CHECK (jsonb_typeof(parameters) = 'object')
);

INSERT INTO pfsense_ingest_config (category, enabled, parameters)
VALUES
    ('block_events', TRUE, '{}'::jsonb),
    ('inbound_sensitive_port_allows', TRUE, '{"sensitive_ports":[21,22,23,25,135,445,1433,3306,3389,5432,5900,6379,27017]}'::jsonb),
    ('all_allow_events', FALSE, '{}'::jsonb),
    ('dns_traffic', FALSE, '{}'::jsonb),
    ('icmp_traffic', FALSE, '{}'::jsonb)
ON CONFLICT (category) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_pfsense_ingest_config_updated_at
    ON pfsense_ingest_config (updated_at DESC);
