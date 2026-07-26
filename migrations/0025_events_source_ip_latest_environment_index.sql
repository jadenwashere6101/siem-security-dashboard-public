CREATE INDEX IF NOT EXISTS idx_events_source_ip_created_at_latest
ON events (source_ip, created_at DESC, id DESC) INCLUDE (environment);
