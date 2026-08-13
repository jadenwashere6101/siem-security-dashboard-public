CREATE TABLE IF NOT EXISTS nist_assessment_boundaries (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    selected_sources TEXT[] NOT NULL,
    selected_source_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    environments TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    default_window_hours INTEGER NOT NULL DEFAULT 24
        CHECK (default_window_hours BETWEEN 1 AND 168),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    scope_declaration TEXT NOT NULL DEFAULT
        'Assessment scope is declared by an authorized user and is not an automatically discovered CUI boundary.',
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(name)) > 0),
    CHECK (cardinality(selected_sources) > 0),
    CHECK (length(trim(created_by)) > 0),
    CHECK (length(trim(updated_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_nist_assessment_boundaries_active_updated
    ON nist_assessment_boundaries (is_active, updated_at DESC);

CREATE TABLE IF NOT EXISTS nist_assessment_runs (
    id BIGSERIAL PRIMARY KEY,
    boundary_id BIGINT NOT NULL
        REFERENCES nist_assessment_boundaries(id) ON DELETE RESTRICT,
    framework_id TEXT NOT NULL,
    framework_version TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    catalog_hash CHAR(64) NOT NULL,
    collector_version TEXT NOT NULL,
    requested_window_start TIMESTAMPTZ NOT NULL,
    requested_window_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'completed_with_partial_evidence', 'error')),
    source_health_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_username TEXT NOT NULL,
    summary_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (requested_window_start < requested_window_end),
    CHECK (length(trim(actor_username)) > 0),
    CHECK (jsonb_typeof(source_health_snapshot) = 'object'),
    CHECK (jsonb_typeof(summary_counts) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_nist_assessment_runs_boundary_created
    ON nist_assessment_runs (boundary_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_nist_assessment_runs_status_created
    ON nist_assessment_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS nist_requirement_results (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES nist_assessment_runs(id) ON DELETE CASCADE,
    requirement_id TEXT NOT NULL,
    requirement_name TEXT NOT NULL,
    mapping_strength TEXT NOT NULL
        CHECK (mapping_strength IN ('strong_siem_evidence', 'partial_siem_evidence')),
    evidence_status TEXT NOT NULL
        CHECK (
            evidence_status IN (
                'evidence_available',
                'partial_evidence',
                'no_evidence_found',
                'not_assessable_by_siem'
            )
        ),
    collection_confidence TEXT NOT NULL
        CHECK (collection_confidence IN ('healthy', 'degraded', 'unknown')),
    reason_code TEXT NOT NULL,
    limitation TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    omitted_count INTEGER NOT NULL DEFAULT 0 CHECK (omitted_count >= 0),
    evaluated_at TIMESTAMPTZ NOT NULL,
    catalog_version TEXT NOT NULL,
    catalog_hash CHAR(64) NOT NULL,
    collector_version TEXT NOT NULL,
    UNIQUE (run_id, requirement_id)
);

CREATE INDEX IF NOT EXISTS idx_nist_requirement_results_run_requirement
    ON nist_requirement_results (run_id, requirement_id);

CREATE INDEX IF NOT EXISTS idx_nist_requirement_results_status_confidence
    ON nist_requirement_results (evidence_status, collection_confidence);

CREATE TABLE IF NOT EXISTS nist_evidence_references (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES nist_assessment_runs(id) ON DELETE CASCADE,
    requirement_result_id BIGINT NOT NULL
        REFERENCES nist_requirement_results(id) ON DELETE CASCADE,
    requirement_id TEXT NOT NULL,
    evidence_category TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    canonical_source TEXT,
    source_type TEXT,
    source_health_state TEXT NOT NULL
        CHECK (source_health_state IN ('healthy', 'degraded', 'unknown')),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    occurrence_timestamp TIMESTAMPTZ,
    ingestion_timestamp TIMESTAMPTZ,
    collection_timestamp TIMESTAMPTZ NOT NULL,
    query_window_start TIMESTAMPTZ NOT NULL,
    query_window_end TIMESTAMPTZ NOT NULL,
    query_hash CHAR(64) NOT NULL,
    operational_classification TEXT NOT NULL
        CHECK (
            operational_classification IN (
                'real',
                'synthetic',
                'simulated',
                'tracking_only',
                'approval_only',
                'internal_workflow',
                'unknown',
                'observed',
                'selected',
                'queued',
                'awaiting_approval',
                'running',
                'skipped',
                'blocked',
                'succeeded',
                'failed'
            )
        ),
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    omitted_count INTEGER NOT NULL DEFAULT 0 CHECK (omitted_count >= 0),
    catalog_version TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    reference_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (query_window_start < query_window_end),
    CHECK (length(trim(requirement_id)) > 0),
    CHECK (length(trim(evidence_category)) > 0),
    CHECK (length(trim(evidence_type)) > 0),
    CHECK (length(trim(entity_type)) > 0),
    CHECK (length(trim(entity_id)) > 0),
    CHECK (length(trim(evidence_summary)) > 0),
    CHECK (jsonb_typeof(reference_metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_nist_evidence_references_result_created
    ON nist_evidence_references (requirement_result_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_nist_evidence_references_run_requirement
    ON nist_evidence_references (run_id, requirement_id, evidence_category, id);

CREATE INDEX IF NOT EXISTS idx_events_source_event_timestamp
    ON events (source, event_timestamp DESC, id DESC)
    WHERE event_timestamp IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_events_source_created_at_nist
    ON events (source, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_source_created_at_nist
    ON alerts (source, created_at DESC, id DESC);
