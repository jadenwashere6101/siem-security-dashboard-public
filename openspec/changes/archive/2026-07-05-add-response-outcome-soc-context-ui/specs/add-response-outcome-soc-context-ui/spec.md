## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement Phase 9 from parent roadmap `openspec/changes/clarify-soar-response-outcomes` — SOC Command Center, Source-IP Context, Attack Map popup integration, Blocklist Manager, Approvals Panel, Playbooks Panel, and SOAR Metrics dashboard canonical outcome display.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for Phase 9 only

#### Scenario: Phase 7 and 8 dependency
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify Phase 8 surfaces (Alert Details, response log, SOAR Queue)
- **AND** all components SHALL be imported from Phase 7 shared files without re-implementation

#### Scenario: No backend or schema changes
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify backend routes, add migrations, change canonical outcome writers, or alter real execution policy

### Requirement: SOC Command Center Canonical Counts
SOC Command Center operational cards SHALL display canonical outcome mode/state counts.

#### Scenario: Canonical mode counts
- **WHEN** the SOC Command Center renders SOAR action counts
- **THEN** it SHALL display canonical counts grouped by `execution_mode` (observed/simulation/tracking_only/real) from metrics endpoint data

#### Scenario: No standalone executed
- **WHEN** SOC Command Center renders any SOAR outcome label
- **THEN** the label SHALL NOT use standalone `"Executed"`

#### Scenario: Existing content preserved
- **WHEN** canonical counts are added
- **THEN** existing SOC Command Center card content SHALL remain present

### Requirement: Source-IP Context Canonical Outcomes
The Source-IP Context component SHALL display recent canonical outcomes for the selected IP.

#### Scenario: Non-null outcome
- **WHEN** the Source-IP Context API returns a non-null `response_outcome`
- **THEN** the component SHALL render `ResponseOutcomeBadge` and `ResponseOutcomeSummary`

#### Scenario: Null outcome
- **WHEN** the Source-IP Context API returns no canonical outcomes
- **THEN** the component SHALL render the no-history state without crashing

#### Scenario: Multiple recent outcomes
- **WHEN** the Source-IP Context API returns multiple recent outcomes
- **THEN** the component SHALL render each with canonical label and summary

### Requirement: Attack Map Popup
The Attack Map popup behavior SHALL be determined by inspection and documented.

#### Scenario: Response status displayed in popup
- **WHEN** inspection confirms the Attack Map popup currently displays response status fields
- **THEN** the status label SHALL be updated to use `outcomeLabel` and `ResponseOutcomeBadge`

#### Scenario: No response status in popup
- **WHEN** inspection confirms the Attack Map popup does NOT display response status fields
- **THEN** no modification SHALL be made and the finding SHALL be documented

#### Scenario: No new backend route
- **WHEN** the Attack Map popup is updated
- **THEN** a new backend route SHALL NOT be created regardless of outcome

### Requirement: Blocklist Manager Tracking-Only Clarity
The Blocklist Manager SHALL clearly mark tracking-only entries and avoid implying enforcement.

#### Scenario: Tracking-only entry with provenance
- **WHEN** a blocklist entry has canonical tracking-only outcome provenance
- **THEN** the entry SHALL display `ResponseOutcomeBadge` with `"Tracking only"` label

#### Scenario: Enforcement language removed
- **WHEN** a tracking-only entry is displayed
- **THEN** any wording implying firewall, external, or local enforcement SHALL be removed or updated

#### Scenario: Entry without outcome
- **WHEN** a blocklist entry has no canonical outcome
- **THEN** no badge SHALL be added and the existing display SHALL be preserved

### Requirement: Approvals Panel Canonical Language
The Approvals Panel SHALL use canonical awaiting/blocked/real-executed-after-approval language.

#### Scenario: Awaiting approval
- **WHEN** an approval has `execution_state = "awaiting_approval"` in `response_outcome`
- **THEN** the panel SHALL display `"Awaiting approval"` label

#### Scenario: Blocked by approval
- **WHEN** an approval has `execution_state = "blocked"` in `response_outcome`
- **THEN** the panel SHALL display `"Blocked by approval"` label

#### Scenario: Real executed after approval
- **WHEN** an approval has `execution_mode = "real"` and `external_executed = true` in `response_outcome`
- **THEN** the panel SHALL display `"Real executed"` label

#### Scenario: Legacy fields preserved
- **WHEN** canonical labels are added
- **THEN** existing approval fields (status, risk_level, decided_by, events) SHALL remain present

### Requirement: Playbooks Panel Canonical Labels
The Playbooks Panel execution timeline SHALL use canonical step outcome labels.

#### Scenario: Execution with outcome
- **WHEN** a playbook execution has a non-null `response_outcome`
- **THEN** the execution list SHALL display `ResponseOutcomeBadge` and the detail timeline SHALL show `ResponseOutcomeSummary`

#### Scenario: Step outcome labels
- **WHEN** the execution timeline shows step outcomes
- **THEN** step labels SHALL use canonical execution state labels from outcome data

#### Scenario: Legacy fields preserved
- **WHEN** canonical labels are added
- **THEN** existing execution fields (status, playbook id, step count, error, timestamps) SHALL remain present

### Requirement: SOAR Metrics Dashboard Canonical Breakdowns
The SOAR Metrics dashboard SHALL display canonical outcome breakdown counts.

#### Scenario: Mode breakdown
- **WHEN** the metrics dashboard renders
- **THEN** it SHALL display canonical outcome counts grouped by `execution_mode` (observed/simulation/tracking_only/real)

#### Scenario: State breakdown
- **WHEN** the metrics dashboard renders
- **THEN** it SHALL display canonical outcome counts grouped by `execution_state`

#### Scenario: Boolean breakdowns
- **WHEN** the metrics dashboard renders
- **THEN** it SHALL display `external_executed`, `tracking_recorded`, and `simulated` true/false counts

#### Scenario: Existing metrics preserved
- **WHEN** canonical breakdowns are added
- **THEN** all existing metrics display content SHALL remain present and unchanged

### Requirement: Test Coverage
All updated surfaces SHALL have frontend test coverage.

#### Scenario: SOC Command Center tests
- **WHEN** tests run
- **THEN** there SHALL be tests for canonical count rendering and no standalone `"Executed"` labels

#### Scenario: Source-IP Context tests
- **WHEN** tests run
- **THEN** there SHALL be tests for non-null badge/summary, null no-history state, and multiple outcomes list

#### Scenario: Blocklist, Approvals, Playbooks, Metrics tests
- **WHEN** tests run
- **THEN** there SHALL be tests for each updated surface covering canonical label correctness and legacy field preservation

#### Scenario: Zero test failures
- **WHEN** the frontend test suite runs after implementation
- **THEN** all new Phase 9 tests SHALL pass with zero failures
