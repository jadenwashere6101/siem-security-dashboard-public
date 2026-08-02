CREATE TABLE IF NOT EXISTS anakin_threads (
    thread_id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT 'siem'
        CHECK (domain = 'siem'),
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE SET NULL,
    primary_entity_type TEXT NOT NULL,
    primary_entity_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'reset', 'closed', 'archived')),
    focus_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    compact_summary TEXT,
    summary_version INTEGER NOT NULL DEFAULT 0 CHECK (summary_version >= 0),
    next_sequence BIGINT NOT NULL DEFAULT 1 CHECK (next_sequence > 0),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    archived_at TIMESTAMPTZ,
    delete_after TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    closed_at TIMESTAMPTZ,
    replaced_by_thread_id TEXT REFERENCES anakin_threads(thread_id) ON DELETE SET NULL,
    CHECK (length(trim(thread_id)) > 0),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(primary_entity_type)) > 0),
    CHECK (length(trim(primary_entity_id)) > 0),
    CHECK (length(trim(scope_key)) > 0),
    CHECK (jsonb_typeof(focus_state) = 'object'),
    CHECK (expires_at >= last_active_at),
    CHECK (delete_after >= expires_at),
    CHECK ((status = 'active' AND closed_at IS NULL) OR status <> 'active'),
    CHECK (replaced_by_thread_id IS NULL OR status = 'reset'),
    UNIQUE (thread_id, owner_username)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_anakin_threads_active_default
    ON anakin_threads (owner_username, domain, scope_key)
    WHERE is_default = TRUE AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_anakin_threads_owner_activity
    ON anakin_threads (owner_username, last_active_at DESC);

CREATE INDEX IF NOT EXISTS idx_anakin_threads_expiry
    ON anakin_threads (status, expires_at)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_anakin_threads_delete_after
    ON anakin_threads (delete_after)
    WHERE status <> 'active';

CREATE TABLE IF NOT EXISTS anakin_turns (
    id BIGSERIAL PRIMARY KEY,
    turn_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    thread_version_after_append BIGINT NOT NULL CHECK (thread_version_after_append > 1),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    workflow TEXT CHECK (workflow IN ('quick_explain', 'deep_investigate', 'decision_support', 'generate_artifact')),
    content TEXT NOT NULL,
    structured_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    assertion_type TEXT NOT NULL
        CHECK (assertion_type IN ('analyst_statement', 'model_inference', 'correction', 'unresolved_question', 'artifact_preview', 'system_event')),
    client_request_id TEXT NOT NULL,
    parent_turn_id BIGINT,
    entity_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle_status TEXT NOT NULL DEFAULT 'recorded'
        CHECK (lifecycle_status IN ('recorded', 'queued', 'running', 'completed', 'failed', 'cancelled', 'superseded')),
    preview_only BOOLEAN NOT NULL DEFAULT FALSE,
    persisted BOOLEAN NOT NULL DEFAULT FALSE,
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CHECK (length(trim(turn_id)) > 0),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(content)) > 0),
    CHECK (length(trim(client_request_id)) > 0),
    CHECK (jsonb_typeof(structured_payload) = 'object'),
    CHECK (jsonb_typeof(entity_snapshot) = 'object'),
    CHECK (
        assertion_type <> 'artifact_preview'
        OR (preview_only = TRUE AND persisted = FALSE AND applied = FALSE AND approval_required = TRUE)
    ),
    UNIQUE (thread_id, sequence),
    UNIQUE (owner_username, thread_id, client_request_id),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username)
        REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (parent_turn_id, thread_id, owner_username)
        REFERENCES anakin_turns(id, thread_id, owner_username)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_anakin_turns_one_active_execution
    ON anakin_turns (thread_id)
    WHERE lifecycle_status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_anakin_turns_owner_thread_sequence
    ON anakin_turns (owner_username, thread_id, sequence);

CREATE OR REPLACE FUNCTION enforce_anakin_turn_immutable_fields()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.turn_id IS DISTINCT FROM OLD.turn_id
       OR NEW.thread_id IS DISTINCT FROM OLD.thread_id
       OR NEW.owner_username IS DISTINCT FROM OLD.owner_username
       OR NEW.sequence IS DISTINCT FROM OLD.sequence
       OR NEW.thread_version_after_append IS DISTINCT FROM OLD.thread_version_after_append
       OR NEW.role IS DISTINCT FROM OLD.role
       OR NEW.workflow IS DISTINCT FROM OLD.workflow
       OR NEW.content IS DISTINCT FROM OLD.content
       OR NEW.structured_payload IS DISTINCT FROM OLD.structured_payload
       OR NEW.assertion_type IS DISTINCT FROM OLD.assertion_type
       OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id
       OR NEW.parent_turn_id IS DISTINCT FROM OLD.parent_turn_id
       OR NEW.entity_snapshot IS DISTINCT FROM OLD.entity_snapshot
       OR NEW.preview_only IS DISTINCT FROM OLD.preview_only
       OR NEW.persisted IS DISTINCT FROM OLD.persisted
       OR NEW.applied IS DISTINCT FROM OLD.applied
       OR NEW.approval_required IS DISTINCT FROM OLD.approval_required
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'anakin turn identity and content are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_anakin_turn_immutable_fields ON anakin_turns;
CREATE TRIGGER trg_anakin_turn_immutable_fields
    BEFORE UPDATE ON anakin_turns
    FOR EACH ROW EXECUTE FUNCTION enforce_anakin_turn_immutable_fields();

CREATE TABLE IF NOT EXISTS anakin_thread_entities (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    display_alias TEXT,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    salience DOUBLE PRECISION NOT NULL DEFAULT 0.5 CHECK (salience >= 0 AND salience <= 1),
    first_referenced_sequence BIGINT NOT NULL CHECK (first_referenced_sequence > 0),
    last_referenced_sequence BIGINT NOT NULL CHECK (last_referenced_sequence >= first_referenced_sequence),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(entity_type)) > 0),
    CHECK (length(trim(entity_id)) > 0),
    UNIQUE (thread_id, entity_type, entity_id),
    UNIQUE (thread_id, ordinal),
    FOREIGN KEY (thread_id, owner_username)
        REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_anakin_thread_entities_owner_thread
    ON anakin_thread_entities (owner_username, thread_id, salience DESC, ordinal);

CREATE TABLE IF NOT EXISTS anakin_thread_state (
    thread_id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    state_version BIGINT NOT NULL DEFAULT 1 CHECK (state_version > 0),
    conclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    unresolved_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    corrections JSONB NOT NULL DEFAULT '[]'::jsonb,
    compact_summary TEXT,
    rebuild_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    rebuild_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(conclusions) = 'array'),
    CHECK (jsonb_typeof(unresolved_questions) = 'array'),
    CHECK (jsonb_typeof(recommendations) = 'array'),
    CHECK (jsonb_typeof(corrections) = 'array'),
    CHECK (jsonb_typeof(rebuild_metadata) = 'object'),
    FOREIGN KEY (thread_id, owner_username)
        REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anakin_thread_hypotheses (
    id BIGSERIAL PRIMARY KEY,
    hypothesis_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'weakened', 'rejected')),
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('analyst_statement', 'model_inference', 'correction')),
    provenance_turn_id BIGINT,
    superseded_by_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(hypothesis_id)) > 0),
    CHECK (length(trim(hypothesis)) > 0),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username)
        REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (provenance_turn_id, thread_id, owner_username)
        REFERENCES anakin_turns(id, thread_id, owner_username),
    FOREIGN KEY (superseded_by_id, thread_id, owner_username)
        REFERENCES anakin_thread_hypotheses(id, thread_id, owner_username)
);

CREATE INDEX IF NOT EXISTS idx_anakin_hypotheses_owner_thread
    ON anakin_thread_hypotheses (owner_username, thread_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS anakin_thread_evidence (
    id BIGSERIAL PRIMARY KEY,
    evidence_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    hypothesis_id BIGINT,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    snapshot JSONB,
    snapshot_hash TEXT,
    query_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    entity_fingerprint TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    fresh_until TIMESTAMPTZ,
    relationship_type TEXT NOT NULL DEFAULT 'context'
        CHECK (relationship_type IN ('supports', 'refutes', 'context')),
    provenance_type TEXT NOT NULL DEFAULT 'verified_evidence'
        CHECK (provenance_type = 'verified_evidence'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(evidence_id)) > 0),
    CHECK (length(trim(source_type)) > 0),
    CHECK (length(trim(source_ref)) > 0),
    CHECK (snapshot IS NULL OR jsonb_typeof(snapshot) IN ('object', 'array')),
    CHECK (snapshot IS NULL OR octet_length(snapshot::text) <= 32768),
    CHECK (snapshot IS NOT NULL OR length(trim(COALESCE(snapshot_hash, ''))) > 0),
    CHECK (jsonb_typeof(query_parameters) = 'object'),
    CHECK (fresh_until IS NULL OR fresh_until >= observed_at),
    UNIQUE (id, thread_id, owner_username),
    FOREIGN KEY (thread_id, owner_username)
        REFERENCES anakin_threads(thread_id, owner_username) ON DELETE CASCADE,
    FOREIGN KEY (hypothesis_id, thread_id, owner_username)
        REFERENCES anakin_thread_hypotheses(id, thread_id, owner_username)
);

CREATE INDEX IF NOT EXISTS idx_anakin_evidence_owner_thread_freshness
    ON anakin_thread_evidence (owner_username, thread_id, observed_at DESC, fresh_until);

CREATE TABLE IF NOT EXISTS anakin_thread_tombstones (
    thread_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL CHECK (domain = 'siem'),
    deletion_reason TEXT NOT NULL CHECK (deletion_reason IN ('retention_expired')),
    content_deleted BOOLEAN NOT NULL DEFAULT TRUE CHECK (content_deleted = TRUE),
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(thread_id)) > 0)
);

ALTER TABLE ai_workflow_requests
    ADD COLUMN IF NOT EXISTS thread_id TEXT,
    ADD COLUMN IF NOT EXISTS turn_id BIGINT;

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_thread_turn_pair_check
    CHECK ((thread_id IS NULL AND turn_id IS NULL) OR (thread_id IS NOT NULL AND turn_id IS NOT NULL));

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_request_actor_unique
    UNIQUE (request_id, actor_username);

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_thread_owner_fkey
    FOREIGN KEY (thread_id, actor_username)
    REFERENCES anakin_threads(thread_id, owner_username);

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_turn_thread_owner_fkey
    FOREIGN KEY (turn_id, thread_id, actor_username)
    REFERENCES anakin_turns(id, thread_id, owner_username);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_workflow_requests_turn_link
    ON ai_workflow_requests (turn_id)
    WHERE turn_id IS NOT NULL;
