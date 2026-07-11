## ADDED Requirements

### Requirement: Metrics source contract mapping
Every SOAR Metrics section SHALL have a documented and tested UI-to-source mapping and SHALL represent source failures distinctly from zero values.

#### Scenario: Metrics section succeeds
- **WHEN** a metrics endpoint returns a valid snapshot
- **THEN** the UI SHALL render values attributable to its documented source table/service and record the refresh state

#### Scenario: Metrics section fails
- **WHEN** one metrics source is unavailable or unauthorized
- **THEN** that section SHALL show an error/unknown state while independently successful sections remain visible and SHALL NOT substitute zero

### Requirement: Authorized read-only production outcome tracing
VM verification SHALL trace representative outcome chains without invoking action endpoints or mutating state.

#### Scenario: Representative record trace
- **WHEN** VM AI has explicit read-only authorization, a clean tree, and the approved deployed SHA
- **THEN** it SHALL capture sanitized alert, outcome, queue, execution, delivery, approval, and integration-mode evidence that exists for the selected record and classify missing links as not recorded

#### Scenario: Label reconciliation
- **WHEN** a user-facing label is compared with its canonical production chain
- **THEN** verification SHALL confirm the label or report a contradiction without remediating data

### Requirement: Authorized read-only metrics reconciliation
VM verification SHALL compare SOAR Metrics API values with bounded source-table counts using a recorded snapshot boundary.

#### Scenario: Metrics reconcile
- **WHEN** source queries and API responses are sampled at the agreed boundary
- **THEN** VM AI SHALL report per-section matching counts or explain bounded concurrent-ingest differences with sanitized evidence

#### Scenario: Unsafe verification state
- **WHEN** the VM is dirty, SHA is unapproved, a query would expose secrets, or a tool may mutate data
- **THEN** VM AI SHALL stop without querying further or taking corrective action

### Requirement: Verification prohibits external effects
The production verification phase SHALL be read-only.

#### Scenario: Action temptation during verification
- **WHEN** tracing reveals pending, failed, skipped, or dead-letter work
- **THEN** VM AI SHALL NOT send notifications, run simulations, approve work, retry queues/dead letters, enable integrations, or mutate records

