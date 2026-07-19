CREATE TABLE IF NOT EXISTS incident_notes (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_notes_incident_id
    ON incident_notes (incident_id);

CREATE INDEX IF NOT EXISTS idx_incident_notes_created_at
    ON incident_notes (created_at);

CREATE TABLE IF NOT EXISTS ai_action_idempotency (
    id SERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_digest TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_resource_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome TEXT NOT NULL,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(target_resource_keys) = 'array'),
    CHECK (jsonb_typeof(result_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_ai_action_idempotency_action_type
    ON ai_action_idempotency (action_type);
