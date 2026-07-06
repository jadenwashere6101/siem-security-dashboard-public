# response-action-queue-worker-rollout Specification

## Purpose
TBD - created by archiving change add-response-action-queue-worker-rollout. Update Purpose after archive.
## Requirements
### Requirement: Response Action Queue Worker Separation
The system SHALL treat `response_actions_queue` processing as a separate worker
path from playbook execution processing.

#### Scenario: Playbook worker does not drain response-action queue
- **WHEN** only the playbook worker daemon is running
- **THEN** pending rows in `response_actions_queue` SHALL NOT be considered
  drained by that service

#### Scenario: Response-action runner drains response-action queue
- **WHEN** the response-action queue runner is invoked
- **THEN** it SHALL process eligible `response_actions_queue` rows through
  `engines.soar_action_worker.process_batch`

### Requirement: Simulation-Safe Backlog Drain
The system SHALL provide a controlled one-time backlog drain workflow that uses
the existing response-action runner in simulation mode.

#### Scenario: Preflight counts are recorded
- **WHEN** an operator prepares to drain backlog
- **THEN** the system SHALL provide queue counts by status and action before any
  mutation occurs

#### Scenario: Bounded simulation batch runs
- **WHEN** the one-time drain is invoked
- **THEN** it SHALL use `SOAR_EXECUTION_MODE=simulation` and a bounded batch size

#### Scenario: Backlog transitions are verified
- **WHEN** a drain batch completes
- **THEN** the operator SHALL be able to compare before/after counts and inspect
  transitions for success, awaiting approval, skipped, failed, and remaining
  pending states

### Requirement: Approval Gate Preservation
The response-action worker SHALL preserve high-risk action approval behavior.

#### Scenario: Block IP requires approval
- **WHEN** the response-action worker processes a pending `block_ip` queue row
- **THEN** the row SHALL move to approval flow or a safe skipped state instead of
  real firewall enforcement

#### Scenario: Approved block IP remains simulation-safe by default
- **WHEN** a `block_ip` action is approved while the worker is configured for
  simulation mode
- **THEN** the worker SHALL NOT perform real firewall enforcement

### Requirement: Automated Worker Scheduling
The system SHALL provide durable operator-managed scheduling for the
response-action queue runner.

#### Scenario: Timer invokes bounded batches
- **WHEN** the response-action worker timer is enabled
- **THEN** each invocation SHALL process only a configured bounded batch and then
  exit

#### Scenario: Timer is disabled
- **WHEN** the response-action worker timer is disabled or stopped
- **THEN** no new scheduled response-action batches SHALL be invoked

#### Scenario: Service uses VM environment safely
- **WHEN** the response-action worker service starts on the VM
- **THEN** it SHALL load database and runner configuration from the approved VM
  environment without printing secrets

### Requirement: Real Execution Boundary
The rollout SHALL NOT enable autonomous real firewall enforcement.

#### Scenario: Default service mode
- **WHEN** deployment artifacts are installed
- **THEN** they SHALL default to `SOAR_EXECUTION_MODE=simulation`

#### Scenario: Real mode rejected by scope
- **WHEN** an implementation attempts to enable real firewall execution as part
  of this change
- **THEN** that implementation SHALL be out of scope and require a separate
  approved OpenSpec

### Requirement: Operational Visibility and Rollback
The rollout SHALL include verification and rollback documentation for operators.

#### Scenario: Queue depth is visible
- **WHEN** an operator checks worker status
- **THEN** they SHALL be able to see queue counts by status before and after a
  worker run

#### Scenario: Rollback preserves data
- **WHEN** rollback is required
- **THEN** operators SHALL stop or disable the service/timer and SHALL NOT delete
  queue rows, approval rows, response logs, or canonical outcome events as part
  of rollback

#### Scenario: Deployment is safe to pause
- **WHEN** any rollout step completes
- **THEN** the system SHALL be safe to pause before the next step without
  requiring data reconstruction

