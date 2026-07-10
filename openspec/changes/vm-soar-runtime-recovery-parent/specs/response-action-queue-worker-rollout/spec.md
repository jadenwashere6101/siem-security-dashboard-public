## MODIFIED Requirements

### Requirement: Simulation-Safe Backlog Drain
The system SHALL provide a controlled backlog drain workflow that uses the existing response-action runner in simulation mode and terminally accounts for every reviewed eligible row.

#### Scenario: Preflight counts are recorded
- **WHEN** an operator prepares to drain backlog
- **THEN** the system SHALL provide queue counts by status and action plus record-level evidence for anomalously old pending work before any mutation occurs

#### Scenario: Bounded simulation batch runs
- **WHEN** the drain is invoked
- **THEN** it SHALL use `SOAR_EXECUTION_MODE=simulation`, a bounded batch size, and idempotency checks

#### Scenario: Backlog transitions are verified
- **WHEN** a drain batch completes
- **THEN** the operator SHALL compare before/after counts and inspect transitions for success, awaiting approval, skipped, failed, and remaining pending states

#### Scenario: Poison or obsolete work is encountered
- **WHEN** an eligible row cannot be safely processed or is no longer relevant
- **THEN** it SHALL receive an explicit safe terminal disposition or documented escalation and SHALL NOT be deleted or falsely recorded as successful
