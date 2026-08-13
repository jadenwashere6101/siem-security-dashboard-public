## ADDED Requirements

### Requirement: Immutable V1 Mapping Catalog
The system SHALL expose exactly the 12 approved NIST SP 800-171 Rev. 3 mappings with official IDs and names, static mapping strength, evidence categories, source dependencies, limitations, collector version, and a deterministic catalog hash.

#### Scenario: Mapping strength is not assessment status
- **WHEN** a mapping is read or evaluated
- **THEN** `strong_siem_evidence` or `partial_siem_evidence` SHALL remain distinct from the evidence status and SHALL NOT represent requirement satisfaction.

#### Scenario: Canonical source authority
- **WHEN** mappings identify telemetry dependencies
- **THEN** they SHALL use canonical inventory IDs including `azure_insights`, `opentelemetry`, and `nginx`, and SHALL NOT persist `azure`, `otlp`, or `web_log` as mapping authority.

### Requirement: Declared Assessment Boundaries
The system SHALL persist named assessment boundaries with selected canonical sources/types, optional environments, a bounded default window, active state, actor metadata, and an explicit declaration that scope is user-provided rather than automatically discovered CUI scope.

#### Scenario: Authorized boundary mutation
- **WHEN** a super-admin creates or updates a valid boundary
- **THEN** the normalized boundary SHALL be persisted and a safe audit event SHALL be recorded.

#### Scenario: Unauthorized boundary mutation
- **WHEN** a viewer or analyst attempts to mutate a boundary
- **THEN** the request SHALL be denied without changing the boundary.

### Requirement: Reproducible Assessment Runs
The system SHALL execute all 12 mappings over a required bounded time window and persist framework version, catalog hash, collector version, boundary, actor, timestamps, source-health snapshot, terminal run state, and summary counts.

#### Scenario: Successful bounded run
- **WHEN** a super-admin starts a run for an active boundary and valid window
- **THEN** the system SHALL collect deterministic evidence, persist 12 requirement results and bounded references, and complete the run without AI or provider traffic.

#### Scenario: Unbounded run rejected
- **WHEN** the requested window is missing, inverted, or exceeds the maximum
- **THEN** the system SHALL reject the run before querying evidence.

### Requirement: Separate Evidence Status and Confidence
The system SHALL calculate evidence status independently from collection confidence using only deterministic collector output.

#### Scenario: Complete healthy evidence
- **WHEN** every required evidence category is present, relevant collectors completed, and source confidence is Healthy
- **THEN** evidence status SHALL be `evidence_available` and confidence SHALL be `healthy` without implying requirement satisfaction.

#### Scenario: Incomplete or unhealthy collection
- **WHEN** evidence categories are incomplete or confidence is Degraded or Unknown
- **THEN** evidence status SHALL be `partial_evidence`.

#### Scenario: Healthy empty collection
- **WHEN** the mapping is SIEM-assessable, collectors completed, health is Healthy, the window is meaningful, and qualifying evidence count is zero
- **THEN** evidence status MAY be `no_evidence_found`.

#### Scenario: Unhealthy empty collection
- **WHEN** qualifying evidence count is zero but health is Degraded or Unknown
- **THEN** evidence status SHALL NOT be `no_evidence_found`.

#### Scenario: Non-SIEM evidence
- **WHEN** an evaluated requirement explicitly requires evidence outside SIEM visibility
- **THEN** status SHALL be `not_assessable_by_siem` with a rationale.

### Requirement: Bounded Requirement Collectors
The system SHALL implement a bounded deterministic collector for each approved mapping using only the evidence categories and current SIEM records defined by the catalog.

#### Scenario: All approved mappings collected
- **WHEN** a run executes
- **THEN** collectors SHALL evaluate 03.03.01 through 03.03.07, 03.06.01, 03.06.02, 03.14.06, 03.13.01, and 03.01.08 and SHALL NOT add unapproved mappings.

#### Scenario: Truncation disclosed
- **WHEN** qualifying evidence exceeds a category reference limit
- **THEN** the collector SHALL preserve the total count and record the omitted/truncated count.

### Requirement: Evidence Provenance
The system SHALL persist references to canonical records rather than unrestricted raw copies and SHALL preserve occurrence, ingestion, outcome, and verification semantics where available.

#### Scenario: Reference-only evidence
- **WHEN** evidence is persisted
- **THEN** it SHALL include requirement/category, canonical source/type, source health, entity type and ID, timestamps, window, safe query metadata or hash, operational classification, truncation, versions, and a short redacted summary without unrestricted raw payloads or secrets.

#### Scenario: Missing occurrence timestamp
- **WHEN** an event lacks `event_timestamp`
- **THEN** ingestion time SHALL remain separately labeled and the collector SHALL disclose that occurrence time was unavailable rather than silently substituting it.

### Requirement: SOAR and Synthetic Evidence Integrity
The system SHALL preserve existing SOAR execution distinctions and SHALL prevent synthetic, demo, or test evidence from silently establishing production operational evidence.

#### Scenario: Real external execution
- **WHEN** SOAR evidence has real execution mode, succeeded state, and `external_executed=true`
- **THEN** it MAY be classified as a real external action.

#### Scenario: Non-execution states
- **WHEN** evidence is simulated, tracking-only, selected, queued, awaiting approval, running, skipped, blocked, failed, or approval-only
- **THEN** it SHALL retain that classification and SHALL NOT be represented as real external execution.

#### Scenario: Synthetic-only evidence
- **WHEN** all qualifying records are explicitly synthetic, demo, test, simulated, documentation-range, or confirmed fixture evidence
- **THEN** they SHALL be excluded from operational evidence counts or separately classified and SHALL NOT produce operational `evidence_available`.

### Requirement: RBAC-Protected Evidence API
The system SHALL provide minimal APIs to list/read boundaries, create/update boundaries, start runs, read run summaries/results/references, and export bounded results.

#### Scenario: Read access
- **WHEN** an analyst or super-admin requests assessment evidence
- **THEN** the system SHALL return only authorized bounded records.

#### Scenario: Run mutation access
- **WHEN** a non-super-admin attempts to start a run
- **THEN** the request SHALL be denied and no run SHALL be created.

### Requirement: Non-Misleading Export
The system SHALL provide deterministic JSON and CSV exports containing framework, boundary, run, requirement, mapping strength, evidence status, confidence, limitation, and provenance.

#### Scenario: Export omits compliance conclusions
- **WHEN** a run is exported
- **THEN** the export SHALL contain no overall compliance percentage, pass/fail control label, certification status, or claim of NIST or CMMC compliance.

#### Scenario: Export is audited
- **WHEN** an authorized user exports a run
- **THEN** a safe audit event SHALL record run ID and format without raw evidence payloads or secrets.

### Requirement: Requirement-Specific Limitations
Each v1 mapping SHALL retain its approved limitation text so the evidence cannot be expanded into unsupported conclusions.

#### Scenario: Configuration and organizational claims remain excluded
- **WHEN** evidence is available for timestamps, incident handling, boundary traffic, authentication failures, or audit activity
- **THEN** the result SHALL continue to disclose unavailable policy, CUI-scope, clock-synchronization, topology, MFA, lockout, retention-policy, external-reporting, staffing, preparation, eradication, recovery, and complete-source-coverage evidence as applicable.
