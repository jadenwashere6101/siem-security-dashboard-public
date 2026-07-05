## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement Phase 8 from parent roadmap `openspec/changes/clarify-soar-response-outcomes` — Alert Details, response log UI, manual action wording, and SOAR Queue UI canonical outcome display.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for Phase 8 only

#### Scenario: Phase 7 dependency
- **WHEN** this child change is implemented
- **THEN** all components SHALL be imported from Phase 7 shared files (`add-response-outcome-frontend-components`) and SHALL NOT re-implement `outcomeLabel`, `outcomeColor`, `ResponseOutcomeBadge`, or `ResponseOutcomeSummary` inline

#### Scenario: No backend or schema changes
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify backend routes, add migrations, change canonical outcome writers, or alter real execution policy

#### Scenario: No Phase 9 screens
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify SOC Command Center, Source-IP Context, Attack Map, Blocklist Manager, Approvals Panel, Playbooks Panel, or SOAR Metrics

### Requirement: Alert Expanded Row Outcome Badge
The expanded alert row SHALL display a canonical outcome badge.

#### Scenario: Non-null outcome
- **WHEN** an alert has a non-null `response_outcome`
- **THEN** the expanded row SHALL render a `ResponseOutcomeBadge` with the correct canonical label

#### Scenario: Null outcome
- **WHEN** an alert has `response_outcome = null`
- **THEN** the badge SHALL render the no-history state without crashing

#### Scenario: Legacy columns preserved
- **WHEN** the badge is added
- **THEN** all existing alert row columns SHALL remain present and unchanged

### Requirement: Alert Detail Panel Outcome Summary
The alert detail panel SHALL display a canonical outcome summary.

#### Scenario: Non-null outcome
- **WHEN** an alert has a non-null `response_outcome`
- **THEN** the detail panel SHALL render `ResponseOutcomeSummary` with selected action, decision source, execution actor, execution booleans, outcome summary, reason code, and related ids

#### Scenario: Null outcome
- **WHEN** an alert has `response_outcome = null`
- **THEN** the summary SHALL render a non-empty no-history message

#### Scenario: Legacy fields preserved
- **WHEN** the summary is added
- **THEN** legacy `response_action` and `response_status` SHALL remain displayed during Phase 8 and SHALL NOT be removed

### Requirement: Response Log Display Canonical Labels
Response log entries SHALL use canonical outcome labels.

#### Scenario: Log entry with outcome
- **WHEN** a response log entry has associated canonical outcome data
- **THEN** the status label SHALL use `outcomeLabel` and SHALL NOT use standalone `"Executed"`

#### Scenario: Log entry without outcome
- **WHEN** a response log entry has no canonical outcome
- **THEN** the existing legacy display SHALL be preserved without modification

### Requirement: Manual Action Feedback Accuracy
Manual `block_ip` feedback SHALL accurately describe tracking-only behavior.

#### Scenario: Tracking-only block_ip success
- **WHEN** a manual `block_ip` action succeeds and `response_outcome.execution_mode = "tracking_only"`
- **THEN** the feedback message SHALL state that a SIEM blocklist entry was created with no external enforcement
- **AND** it SHALL NOT use standalone `"Executed"` or imply firewall, provider, external, or local enforcement

### Requirement: SOAR Queue List Row Canonical Badge
Queue list rows SHALL display a canonical outcome badge.

#### Scenario: Queue item with outcome
- **WHEN** a queue item has a non-null `response_outcome`
- **THEN** the list row SHALL render `ResponseOutcomeBadge` with the correct label

#### Scenario: Queue item without outcome
- **WHEN** a queue item has `response_outcome = null`
- **THEN** the badge SHALL render the no-history state without crashing

#### Scenario: Queue columns preserved
- **WHEN** the badge is added
- **THEN** existing queue list columns (action, source IP, status, retry count, timestamps) SHALL remain unchanged

### Requirement: SOAR Queue Detail Canonical Summary
The queue detail panel SHALL display SOAR correlation id and canonical outcome summary.

#### Scenario: Queue detail with outcome
- **WHEN** a queue item has a non-null `response_outcome`
- **THEN** the detail panel SHALL display the SOAR correlation id and `ResponseOutcomeSummary` with `showRelated = true`

#### Scenario: Queue detail fields preserved
- **WHEN** the canonical fields are added
- **THEN** existing queue detail fields (action, status, retry count, last error, related approval, response log, playbook execution) SHALL remain unchanged

### Requirement: Batch Simulation Feedback Language
SOAR queue batch simulation run feedback SHALL use canonical simulation language.

#### Scenario: Batch simulation complete
- **WHEN** a batch simulation run completes
- **THEN** the feedback SHALL use `"Simulated"` or equivalent canonical phrasing
- **AND** it SHALL NOT use standalone `"Executed"`

### Requirement: Test Coverage
All updated surfaces SHALL have frontend test coverage.

#### Scenario: Alert tests
- **WHEN** tests run
- **THEN** there SHALL be tests covering alert expanded row badge (non-null, null), alert detail summary (non-null fields, null no-history state), response log label (with and without outcome), and manual action feedback (tracking-only copy, no enforcement implication)

#### Scenario: Queue tests
- **WHEN** tests run
- **THEN** there SHALL be tests covering queue list row badge (non-null, null), queue detail panel (SOAR correlation id, summary), and batch simulation feedback language

#### Scenario: Zero test failures
- **WHEN** the frontend test suite runs after implementation
- **THEN** all new Phase 8 tests SHALL pass with zero failures
