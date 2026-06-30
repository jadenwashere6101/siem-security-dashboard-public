## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement Phases 10 and 11 from parent roadmap `openspec/changes/clarify-soar-response-outcomes` — retention/archive/reporting verification and end-to-end traceability tests.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for Phases 10 and 11 work only

#### Scenario: No phase implementations changed
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify canonical outcome writers, API route implementations, UI components, migrations, or runtime behavior from Phases 1–9

#### Scenario: Depends on all prior phases
- **WHEN** this child change is implemented
- **THEN** all Phases 1–9 SHALL be implemented and passing before end-to-end tests are run

### Requirement: Retention Window and Archive Criteria Defined
A default retention window and archive criteria SHALL be documented before production deployment.

#### Scenario: Retention window documented
- **WHEN** this child change is complete
- **THEN** there SHALL be a documented default retention window for canonical decisions and outcome events

#### Scenario: Archive criteria documented
- **WHEN** this child change is complete
- **THEN** there SHALL be documented criteria specifying which events are eligible for archival and what minimum fields must be preserved

#### Scenario: Audit evidence preserved
- **WHEN** archival occurs
- **THEN** events with `external_executed = true` SHALL be treated as audit records and SHALL NOT be deleted without preserving a summary record

#### Scenario: Primary analyst question answerable from archive
- **WHEN** a canonical decision/event is archived
- **THEN** the archive SHALL preserve at minimum: decision id, SOAR correlation id, selected action, decision source, final execution mode/state, execution booleans, outcome summary, and enough related ids to answer "What happened, what response was selected, what playbook ran, and was anything actually executed?"

### Requirement: Reporting Query
A reporting query or helper SHALL answer the primary analyst question from canonical tables.

#### Scenario: Query by alert id
- **WHEN** the reporting query receives an `alert_id`
- **THEN** it SHALL return selected action, decision source, execution mode/state, execution booleans, outcome summary, playbook execution id, approval request id, and SOAR correlation id for that alert

#### Scenario: Query by incident id
- **WHEN** the reporting query receives an `incident_id`
- **THEN** it SHALL return the same canonical outcome fields for all decisions related to that incident

#### Scenario: Query works for backfill rows
- **WHEN** the reporting query processes a row with `decision_source = "migration"`
- **THEN** it SHALL return the same canonical fields as for live rows

### Requirement: Performance Verification
Latest-outcome queries SHALL perform acceptably at representative event volume.

#### Scenario: Single-decision lookup performance
- **WHEN** `get_latest_outcome_for_decision` is executed with representative volume (≥50,000 events)
- **THEN** it SHALL complete in acceptable time (< 50 ms)

#### Scenario: Bulk alert lookup performance
- **WHEN** `get_latest_outcomes_for_alerts_bulk` is executed with a 100-item batch at representative volume
- **THEN** it SHALL complete in acceptable time

#### Scenario: Bulk approval lookup performance
- **WHEN** `get_latest_outcomes_for_approvals_bulk` is executed with a 50-item batch at representative volume
- **THEN** it SHALL complete in acceptable time

### Requirement: Metrics Retention Documentation
Metrics endpoints SHALL either include archived summaries or document their live retention window.

#### Scenario: Metrics include archived summaries
- **WHEN** a metrics endpoint aggregates canonical outcome counts
- **THEN** it SHALL either include archived event summaries in the count OR document that the count covers only the live retention window

### Requirement: End-to-End Lifecycle Tests
Each major SOAR lifecycle path SHALL have an end-to-end test.

#### Scenario: Observed-only lifecycle
- **WHEN** an alert has no decision or outcome event
- **THEN** the alert API SHALL return `response_outcome: null`
- **AND** the end-to-end test SHALL assert this

#### Scenario: Simulated queue lifecycle
- **WHEN** a detection-selected simulated queue action completes
- **THEN** the API SHALL return `execution_mode = "simulation"`, `simulated = true`, `external_executed = false`
- **AND** the end-to-end test SHALL assert all three fields

#### Scenario: Manual tracking-only lifecycle
- **WHEN** a manual tracking-only blocklist action completes
- **THEN** the API SHALL return `execution_mode = "tracking_only"`, `tracking_recorded = true`, `external_executed = false`
- **AND** the end-to-end test SHALL assert all three fields

#### Scenario: Playbook simulation lifecycle
- **WHEN** a playbook simulation step sequence completes
- **THEN** the API SHALL return step events attached to the execution-level decision
- **AND** the end-to-end test SHALL assert step events have `decision_id` matching the execution-level decision

#### Scenario: Approval awaiting and denied/expired lifecycle
- **WHEN** a playbook awaiting approval is blocked by denial or expiration
- **THEN** the API SHALL return `execution_state = "blocked"` and `reason_code = "approval_denied"`
- **AND** the end-to-end test SHALL assert both fields

#### Scenario: Notification simulated and real lifecycles
- **WHEN** notification outcomes are returned
- **THEN** simulated deliveries SHALL have `external_executed = false`
- **AND** real success deliveries SHALL have `external_executed = true`
- **AND** fail-closed deliveries SHALL have `external_executed = false` and `execution_state = "failed"`

### Requirement: Regression Tests
Canonical boundaries SHALL be enforced by automated regression tests.

#### Scenario: Simulated never shown as real
- **WHEN** any `simulated = true` event exists
- **THEN** no API response for that event SHALL return `external_executed = true`
- **AND** the regression test SHALL be deterministic and SHALL NOT pass if this invariant is violated

#### Scenario: Tracking-only never shown as enforcement
- **WHEN** any `tracking_recorded = true` event exists
- **THEN** no API response for that event SHALL return `external_executed = true` or the canonical label `"Real executed"`
- **AND** the regression test SHALL be deterministic and SHALL NOT pass if this invariant is violated

#### Scenario: Zero test failures
- **WHEN** all end-to-end and regression tests run
- **THEN** all 12 tests SHALL pass with zero failures
