CREATE TABLE IF NOT EXISTS schema_migrations (
    id            SERIAL PRIMARY KEY,
    version       INTEGER NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by    TEXT,
    checksum      TEXT
);
