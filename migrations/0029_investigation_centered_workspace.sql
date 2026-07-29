ALTER TABLE investigations
    ADD COLUMN IF NOT EXISTS disposition TEXT NOT NULL DEFAULT 'undetermined'
        CHECK (disposition IN ('true_positive', 'false_positive', 'benign_expected', 'needs_monitoring', 'escalated', 'undetermined')),
    ADD COLUMN IF NOT EXISTS confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    ADD COLUMN IF NOT EXISTS conclusion TEXT,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE evidence_references
    ADD COLUMN IF NOT EXISTS rationale TEXT,
    ADD COLUMN IF NOT EXISTS relationship_type TEXT NOT NULL DEFAULT 'context'
        CHECK (relationship_type IN ('supports', 'refutes', 'context'));

ALTER TABLE investigation_tasks
    ADD COLUMN IF NOT EXISTS hypothesis_id INTEGER REFERENCES investigation_hypotheses(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS evidence_reference_id INTEGER REFERENCES evidence_references(id) ON DELETE SET NULL;

ALTER TABLE investigation_hypotheses
    ADD COLUMN IF NOT EXISTS confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high'));

CREATE TABLE IF NOT EXISTS investigation_hypothesis_evidence (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    hypothesis_id INTEGER NOT NULL REFERENCES investigation_hypotheses(id) ON DELETE CASCADE,
    evidence_reference_id INTEGER NOT NULL REFERENCES evidence_references(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT 'context'
        CHECK (relationship_type IN ('supports', 'refutes', 'context')),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (length(trim(owner_username)) > 0),
    UNIQUE (hypothesis_id, evidence_reference_id)
);

CREATE INDEX IF NOT EXISTS idx_investigation_hypothesis_evidence_owner
    ON investigation_hypothesis_evidence (owner_username, investigation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigations_owner_last_activity
    ON investigations (owner_username, last_activity_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_references_investigation_created
    ON evidence_references (investigation_id, created_at DESC)
    WHERE investigation_id IS NOT NULL;
