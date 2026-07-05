## ADDED Requirements

### Requirement: Child Change Scope
This change SHALL implement Phase 7 from parent roadmap `openspec/changes/clarify-soar-response-outcomes` — shared frontend utilities and components for canonical response outcome display.

#### Scenario: Parent roadmap remains master
- **WHEN** this child change is implemented
- **THEN** the parent roadmap SHALL remain the master roadmap/spec and this child change SHALL be treated as the active implementation spec for Phase 7 shared frontend component work only

#### Scenario: No screen-level changes
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT modify any existing screen components (Alert Details, SOAR Queue, SOC Command Center, Approvals Panel, Playbooks Panel, Source-IP Context, Blocklist Manager, Attack Map, or SOAR Metrics dashboard)
- **AND** it SHALL NOT modify backend routes, migrations, or runtime behavior

#### Scenario: No backend changes
- **WHEN** this child change is implemented
- **THEN** it SHALL NOT add migrations, modify API routes, change canonical outcome writers, or alter real execution policy

### Requirement: Canonical Label Utility
The shared label utility SHALL map canonical outcome fields to the exact UI label strings defined in parent Decision 7.

#### Scenario: Null outcome input
- **WHEN** `outcomeLabel(null)` is called
- **THEN** it SHALL return `"Observed only"`

#### Scenario: Real executed outcome
- **WHEN** `execution_mode = "real"` and `external_executed = true`
- **THEN** `outcomeLabel` SHALL return `"Real executed"`

#### Scenario: Tracking-only outcome
- **WHEN** `execution_mode = "tracking_only"` or `tracking_recorded = true`
- **THEN** `outcomeLabel` SHALL return `"Tracking only"`

#### Scenario: Simulated outcome
- **WHEN** `execution_mode = "simulation"` or `simulated = true`
- **THEN** `outcomeLabel` SHALL return `"Simulated"`

#### Scenario: Awaiting approval
- **WHEN** `execution_state = "awaiting_approval"`
- **THEN** `outcomeLabel` SHALL return `"Awaiting approval"`

#### Scenario: Blocked by approval
- **WHEN** `execution_state = "blocked"`
- **THEN** `outcomeLabel` SHALL return `"Blocked by approval"`

#### Scenario: Skipped
- **WHEN** `execution_state = "skipped"`
- **THEN** `outcomeLabel` SHALL return `"Skipped"`

#### Scenario: Failed
- **WHEN** `execution_state = "failed"`
- **THEN** `outcomeLabel` SHALL return `"Failed"`

#### Scenario: No standalone executed copy
- **WHEN** any utility or component produces a display string
- **THEN** that string SHALL NOT contain standalone `"executed"` without a qualifying mode prefix

### Requirement: ResponseOutcomeBadge Component
The `ResponseOutcomeBadge` component SHALL display the canonical outcome label and color without crashing on any valid input.

#### Scenario: Null outcome
- **WHEN** `ResponseOutcomeBadge` receives `outcome = null`
- **THEN** it SHALL render without crashing and SHALL display a non-empty label

#### Scenario: Non-null outcome
- **WHEN** `ResponseOutcomeBadge` receives a non-null `outcome`
- **THEN** it SHALL render the label from `outcomeLabel(outcome)` and apply color from `outcomeColor(outcome)`

#### Scenario: Accessible label
- **WHEN** `ResponseOutcomeBadge` renders any outcome
- **THEN** the rendered element SHALL include a non-empty `aria-label` attribute

### Requirement: ResponseOutcomeSummary Component
The `ResponseOutcomeSummary` component SHALL render canonical outcome details or a clear no-history state.

#### Scenario: Non-null outcome
- **WHEN** `ResponseOutcomeSummary` receives a non-null `outcome`
- **THEN** it SHALL render selected action, decision source, execution actor (when present), execution booleans as human-readable clauses, outcome summary text, and reason code explanation when present

#### Scenario: Null outcome
- **WHEN** `ResponseOutcomeSummary` receives `outcome = null`
- **THEN** it SHALL render a non-empty no-history message (e.g., `"No response outcome recorded."`) and SHALL NOT render a blank or empty element

#### Scenario: Related ids section
- **WHEN** `ResponseOutcomeSummary` receives `showRelated = true` and a non-null outcome
- **THEN** it SHALL render the related ids section including alert id, queue id, playbook execution id, approval request id, and notification delivery id

#### Scenario: No legacy field derivation
- **WHEN** `ResponseOutcomeSummary` renders any outcome
- **THEN** it SHALL NOT derive canonical state from legacy fields (`response_action`, `response_status`, `executed`)

### Requirement: Test Coverage
All tests SHALL pass for canonical utilities and components.

#### Scenario: Full enum coverage
- **WHEN** tests run
- **THEN** `outcomeLabel` and `outcomeColor` SHALL have coverage for all four `execution_mode` values, all nine `execution_state` values, all three execution boolean flags, null input, and every canonical `reason_code` value

#### Scenario: Component rendering tests
- **WHEN** tests run
- **THEN** `ResponseOutcomeBadge` and `ResponseOutcomeSummary` SHALL each have rendering tests covering null input, non-null input, accessibility assertions, and no standalone `executed` copy

#### Scenario: Zero test failures
- **WHEN** the frontend test suite runs after implementation
- **THEN** all new tests SHALL pass with zero failures
