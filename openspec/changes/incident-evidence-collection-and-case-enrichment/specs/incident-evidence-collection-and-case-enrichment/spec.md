## ADDED Requirements

### Requirement: One-Time Immutable Evidence Snapshot at Incident Creation
The incident store SHALL capture a single, immutable evidence snapshot synchronously, in the same transaction as incident creation, and SHALL NOT recapture, update, or refresh it afterward under any circumstance.

#### Scenario: New incident always receives an evidence snapshot
- **WHEN** `maybe_create_or_link_incident` takes the "no open incident exists" branch and creates a new incident row
- **THEN** that same transaction SHALL populate `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` on the new row before commit.

#### Scenario: Linking to an existing incident does not capture or recapture evidence
- **WHEN** `maybe_create_or_link_incident` takes the "existing open incident" branch and only links the triggering alert
- **THEN** the existing incident's `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` SHALL remain exactly as they were, unmodified.

#### Scenario: No mutator other than creation ever writes evidence columns
- **WHEN** `update_incident_status` or `link_alert_to_incident` runs against any incident
- **THEN** neither function SHALL read, write, or otherwise reference `evidence_snapshot`, `evidence_captured_at`, or `evidence_schema_version`.

### Requirement: Evidence Reuses Existing Enrichment Without Re-Deriving It
The evidence snapshot SHALL be assembled entirely from data and functions that already exist in the codebase at the time of this spec, and SHALL NOT invoke any new external call or duplicate enrichment logic.

#### Scenario: Reputation fields are copied, not re-queried
- **WHEN** the evidence snapshot is assembled for a triggering alert
- **THEN** its reputation fields SHALL be copied directly from that alert's existing `reputation_score`, `reputation_label`, `reputation_source`, and `reputation_summary` columns, and no new call to an AbuseIPDB or behavioral-reputation lookup SHALL be made as part of evidence capture.

#### Scenario: MITRE mapping is derived using the existing pure function
- **WHEN** the evidence snapshot is assembled
- **THEN** its MITRE fields SHALL be produced by the existing alert-type-to-technique mapping function, using the same mapping table already used for alert serialization elsewhere, and then frozen into the snapshot rather than re-derived on every future read.

#### Scenario: Correlation context uses the existing whitelist
- **WHEN** the triggering alert's type is a correlation alert type
- **THEN** the snapshot SHALL include only the already-established whitelisted subset of the alert's context data, and SHALL NOT copy the raw, unfiltered context value.

#### Scenario: Correlation context is omitted for non-correlation alerts
- **WHEN** the triggering alert's type is not a correlation alert type
- **THEN** the snapshot SHALL omit the correlation-context section entirely rather than including it with null or empty placeholder values.

### Requirement: Evidence Scope Excludes Not-Yet-Existing Investigation Data
The evidence snapshot SHALL NOT attempt to capture playbook execution history, response outcomes, or analyst notes at incident-creation time; that data SHALL continue to be served by existing live queries.

#### Scenario: Execution history is not snapshotted
- **WHEN** an incident is created
- **THEN** no playbook execution or step data SHALL be copied into `evidence_snapshot`, and playbook execution history SHALL remain retrievable only through the existing live incident-timeline query.

#### Scenario: Response outcomes are not snapshotted
- **WHEN** an incident is created
- **THEN** no response-decision or outcome-event data SHALL be copied into `evidence_snapshot`, and response outcomes SHALL remain retrievable only through the existing live outcome-query functions.

#### Scenario: Analyst notes are not snapshotted
- **WHEN** an incident is created
- **THEN** no analyst-note data SHALL be copied into `evidence_snapshot`, and notes SHALL remain retrievable only through the existing live notes query.

### Requirement: Evidence Data Model Is a Schema Extension, Not a New Table
This capability SHALL be implemented as an extension of the existing `incidents` table (`evidence_snapshot` JSONB, `evidence_captured_at` timestamp, `evidence_schema_version` integer), not as a new dedicated evidence table.

#### Scenario: Pre-existing incidents remain valid without backfill
- **WHEN** an incident created before this capability existed is read after this capability ships
- **THEN** its `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` SHALL be `null`/absent, and no backfill migration SHALL be required or attempted for it to remain valid.

#### Scenario: Schema version is recorded with every snapshot
- **WHEN** a new evidence snapshot is captured
- **THEN** `evidence_schema_version` SHALL be set to the version of the snapshot shape used at capture time, so a future shape change does not require rewriting historical rows.

### Requirement: Evidence Redaction Reuses the Existing Redaction Convention
The evidence snapshot SHALL be passed through the same redaction rules already used for SOAR outcome metadata before being persisted, rather than a newly invented redaction policy.

#### Scenario: Denylisted keys are stripped from evidence
- **WHEN** the assembled evidence dict contains a key matching the existing outcome-metadata denylist (e.g., a webhook-URL-shaped key)
- **THEN** that key SHALL be removed from the snapshot before it is persisted.

#### Scenario: Embedded URLs in free text are scrubbed
- **WHEN** a string field being copied into the snapshot (e.g., an alert message or reputation summary) contains an embedded URL
- **THEN** that URL SHALL be redacted using the same scrubbing logic already applied to SOAR outcome metadata.

### Requirement: Evidence Read Access Uses Existing Incident RBAC
Evidence fields SHALL be exposed only through the existing incident-detail read path and SHALL be governed by the same role check already applied to all other incident data, with no new permission tier introduced.

#### Scenario: Evidence is visible to existing authorized incident readers
- **WHEN** an analyst or super admin who can already read `GET /incidents/:id` requests an incident that has an evidence snapshot
- **THEN** the response SHALL include `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` without requiring any additional permission grant.

### Requirement: Engine-Only Change Boundary
This change SHALL define incident evidence and enrichment requirements only. It SHALL NOT modify application source code as part of this spec-writing step, and SHALL NOT create or alter any incident row.

#### Scenario: No functional files touched by spec authoring
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/incident-evidence-collection-and-case-enrichment/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No incident rows created or altered
- **WHEN** this change's artifacts are created
- **THEN** no `incidents` row SHALL be created or modified, and no existing engine or store behavior SHALL be changed — implementation remains a separate, later pass.
