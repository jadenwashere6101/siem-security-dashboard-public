## ADDED Requirements

### Requirement: Cohesive NIST evidence workspace
The system SHALL provide Analyst+ users one NIST workspace powered only by persisted boundaries, runs, requirement results, and evidence references, and SHALL permanently state that evidence availability does not determine requirement satisfaction or compliance.

#### Scenario: Workspace loads persisted state
- **WHEN** an authorized user opens the NIST workspace
- **THEN** the system SHALL load boundaries and bounded persisted run metadata without starting an assessment, invoking AI or collectors, querying events, or recalculating source health

#### Scenario: AI is unavailable
- **WHEN** the explanation provider or worker is unavailable
- **THEN** the workspace SHALL continue to display deterministic results, provenance, and exports and SHALL label only the optional explanation as unavailable

### Requirement: Role-appropriate NIST controls
The system SHALL permit Analyst+ users to view catalog, boundaries, runs, results, evidence, exports, and explanations while restricting boundary mutations and assessment execution to super-admins.

#### Scenario: Analyst reviews evidence
- **WHEN** an analyst opens a persisted result
- **THEN** the system SHALL allow evidence review, export, and explanation without showing boundary-edit or run-assessment controls

#### Scenario: Viewer is denied
- **WHEN** a viewer requests any protected NIST workspace API
- **THEN** the system SHALL return the existing fail-closed RBAC denial and audit behavior

### Requirement: Non-compliance status presentation
The workspace SHALL present mapping strength, evidence status, and collection confidence as three separate concepts using the specified labels and SHALL NOT present a compliance, satisfaction, pass/fail, certification, CMMC, maturity, or percentage conclusion.

#### Scenario: Result status is rendered
- **WHEN** a requirement result is displayed
- **THEN** its mapping, evidence, and confidence values SHALL appear as separately labelled, accessible, non-success-styled fields with deterministic reason and limitation

### Requirement: Bounded persisted run history
The system SHALL provide a keyset-bounded Analyst+ run-history API for a specified boundary using persisted run metadata only.

#### Scenario: Latest runs are listed
- **WHEN** an authorized user requests boundary run history with a valid limit and optional complete cursor
- **THEN** the system SHALL return at most the bounded limit in descending `(created_at, id)` order and a next cursor only when more persisted rows exist

#### Scenario: Boundary or cursor is invalid
- **WHEN** the boundary does not exist or only part of the keyset cursor is supplied
- **THEN** the system SHALL return 404 or 400 respectively without invoking collectors

### Requirement: Evidence ownership is fail closed
The system SHALL verify that a requested requirement result belongs to the specified run before returning evidence.

#### Scenario: Requirement mismatch
- **WHEN** a run exists but the requested requirement has no result in that run
- **THEN** the evidence API SHALL return 404 and SHALL NOT substitute or return another result's evidence

### Requirement: ID-only explanation submission
The system SHALL accept explanation submissions containing exactly four immutable NIST identifiers and a UUID client request ID, validate their authoritative relationship, and enqueue an owner-bound asynchronous workflow.

#### Scenario: Valid submission is queued
- **WHEN** an Analyst+ user submits matching boundary, run, result, and requirement identifiers
- **THEN** the system SHALL create or return the idempotent `nist_evidence_explanation` workflow request without invoking a model in the HTTP request

#### Scenario: Binding is invalid
- **WHEN** any submitted identifier is absent or does not belong to the preceding entity
- **THEN** the system SHALL return 404, audit the rejection, and SHALL NOT enqueue work or call a provider

#### Scenario: Client supplies authority fields
- **WHEN** a submission contains evidence, status, confidence, mapping, workflow, tools, prompt context, instructions, or conversation memory
- **THEN** the system SHALL reject the request as invalid

### Requirement: Isolated deterministic explanation context
The explanation worker SHALL independently repeat four-ID validation and build a server-owned context only from the persisted run, result, and at most 25 evidence references plus one look-ahead row.

#### Scenario: Worker constructs context
- **WHEN** a queued explanation is claimed
- **THEN** the worker SHALL preserve total, supplied, omitted, and truncation metadata and SHALL NOT invoke planner, Deep Investigate, session memory, tools, entity resolution, events, source health, or NIST collectors

#### Scenario: Queued binding no longer validates
- **WHEN** worker-side four-ID validation fails
- **THEN** the request SHALL fail closed, audit the rejection, and SHALL NOT call the model

### Requirement: Local bounded explanation synthesis
The explanation worker SHALL use the existing local-only `fast_triage` profile and SHALL request only the bounded explanation schema.

#### Scenario: Provider is invoked
- **WHEN** valid persisted context is available
- **THEN** the worker SHALL call Ollama through the existing gateway with profile `fast_triage`, no tools, no planning, no paid fallback, and no new model profile

### Requirement: Strict grounded-output validation
The system SHALL accept only a small explanation object containing `summary`, `why_it_matters`, `limitations`, `additional_evidence_needed`, and `citation_ids`, and SHALL keep deterministic result fields outside model ownership.

#### Scenario: Grounded output succeeds
- **WHEN** model output matches the schema, cites only supplied reference IDs, introduces no identities, preserves deterministic limitations, and contains no prohibited authority claim
- **THEN** the system SHALL persist the validated explanation separately from the server-owned deterministic result block

#### Scenario: Output is malformed or contradictory
- **WHEN** output is malformed, has an unknown field, introduces an identifier, overclaims compliance or satisfaction, contradicts deterministic state, hides degraded/unknown confidence, claims completeness after truncation, or misrepresents non-real evidence
- **THEN** the system SHALL discard all model prose, persist `explanation_unavailable`, and perform no repair loop

### Requirement: Safe lifecycle and audit metadata
The system SHALL reuse existing workflow claim, lease, polling, retention, ownership, gateway metadata, and worker lifecycle behavior while auditing explanation transitions with safe metadata only.

#### Scenario: Explanation completes or fails
- **WHEN** a request completes, is rejected, becomes unavailable, or fails
- **THEN** the system SHALL audit identifiers, workflow request ID, outcome, and bounded provider/reference metadata without prompts, model prose, raw evidence, raw payloads, or secrets

#### Scenario: Stale UI response arrives
- **WHEN** polling completes after the user changes boundary, run, result, or requirement selection
- **THEN** the frontend SHALL discard the explanation response and keep the currently selected deterministic result visible

### Requirement: Safe evidence drill-down
The workspace SHALL paginate safe persisted provenance and SHALL link only validated alert, incident, approval-request, and playbook-execution identifiers through existing navigation contracts.

#### Scenario: Evidence is inspected
- **WHEN** an authorized user opens requirement evidence
- **THEN** the UI SHALL display bounded categories, sources, entity identity, timestamps, query window/hash, source health, operational classification, omissions, versions, and summary without raw payload or arbitrary metadata

#### Scenario: Unsupported entity is displayed
- **WHEN** an evidence reference has any other entity type or invalid identifier
- **THEN** the UI SHALL render read-only provenance text without inventing a destination
