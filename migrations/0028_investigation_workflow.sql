CREATE TABLE IF NOT EXISTS analyst_workspaces (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'My Investigation Workspace',
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(name)) > 0),
    UNIQUE (owner_username, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_analyst_workspaces_default_owner
    ON analyst_workspaces (owner_username)
    WHERE is_default = TRUE;

CREATE INDEX IF NOT EXISTS idx_analyst_workspaces_owner_updated
    ON analyst_workspaces (owner_username, updated_at DESC);

CREATE TABLE IF NOT EXISTS investigations (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'waiting', 'resolved', 'closed')),
    summary TEXT,
    linked_alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    linked_incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    linked_source_ip INET,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    saved_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (jsonb_typeof(saved_state) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_investigations_owner_updated
    ON investigations (owner_username, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigations_alert
    ON investigations (linked_alert_id)
    WHERE linked_alert_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_investigations_incident
    ON investigations (linked_incident_id)
    WHERE linked_incident_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS workspace_items (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    owner_username TEXT NOT NULL,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('alert', 'incident', 'recon_activity', 'source_ip', 'investigation', 'evidence')),
    referenced_object_type TEXT NOT NULL,
    referenced_object_id TEXT NOT NULL,
    label TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    item_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(referenced_object_type)) > 0),
    CHECK (length(trim(referenced_object_id)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (workspace_id, item_type, referenced_object_type, referenced_object_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_items_owner_order
    ON workspace_items (owner_username, item_order, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_items_workspace_order
    ON workspace_items (workspace_id, item_order, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_notes (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(body)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_notes_owner_created
    ON investigation_notes (owner_username, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_hypotheses (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'supported', 'rejected', 'unknown')),
    body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_hypotheses_owner_created
    ON investigation_hypotheses (owner_username, created_at DESC);

CREATE TABLE IF NOT EXISTS investigation_tasks (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'done')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_investigation_tasks_owner_status
    ON investigation_tasks (owner_username, status, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_references (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    workspace_id INTEGER REFERENCES analyst_workspaces(id) ON DELETE CASCADE,
    investigation_id INTEGER REFERENCES investigations(id) ON DELETE CASCADE,
    parent_type TEXT NOT NULL DEFAULT 'workspace'
        CHECK (parent_type IN ('workspace', 'investigation')),
    referenced_object_type TEXT NOT NULL,
    referenced_object_id TEXT NOT NULL,
    label TEXT NOT NULL,
    source TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (workspace_id IS NOT NULL OR investigation_id IS NOT NULL),
    CHECK (length(trim(owner_username)) > 0),
    CHECK (length(trim(referenced_object_type)) > 0),
    CHECK (length(trim(referenced_object_id)) > 0),
    CHECK (length(trim(label)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_evidence_references_owner_created
    ON evidence_references (owner_username, created_at DESC);
