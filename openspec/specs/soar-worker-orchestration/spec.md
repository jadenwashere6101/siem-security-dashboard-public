## Requirements

### Requirement: Daemon worker process
The system SHALL define a dedicated SOAR worker daemon process for continuous playbook execution polling and processing.

#### Scenario: Worker starts in simulation-safe mode
- **WHEN** the SOAR worker daemon starts with default configuration
- **THEN** it SHALL preserve simulation-safe execution behavior and SHALL NOT enable real Slack, Teams, firewall, or other external adapter actions.

#### Scenario: Worker handles shutdown
- **WHEN** the worker receives a shutdown signal
- **THEN** it SHALL stop claiming new work, perform bounded cleanup for owned work, and exit without creating duplicate executions.

### Requirement: Safe polling and backpressure
The system SHALL poll eligible execution work using configurable cadence, batch limits, idle backoff, and starvation prevention.

#### Scenario: No work is available
- **WHEN** the worker polling loop finds no eligible work
- **THEN** it SHALL sleep or back off rather than tight-looping against the database.

#### Scenario: Large queue is available
- **WHEN** more eligible executions exist than the configured batch limit
- **THEN** the worker SHALL claim only within the limit and preserve visibility into remaining queue depth.

### Requirement: Lease-owned execution
The system SHALL require successful lease acquisition before any worker processes a playbook execution.

#### Scenario: Lease claim succeeds
- **WHEN** a worker atomically claims an eligible execution
- **THEN** the execution SHALL record ownership for that worker and only that worker may complete, fail, renew, or dead-letter the attempt.

#### Scenario: Lease claim loses contention
- **WHEN** two workers attempt to claim the same execution
- **THEN** only one worker SHALL receive ownership and the other worker SHALL NOT execute that item.

### Requirement: Duplicate execution prevention
The system SHALL prevent duplicate processing across restarts, lease contention, retry flows, and multi-worker deployments.

#### Scenario: Completed execution is encountered
- **WHEN** a worker polls an execution that has already completed
- **THEN** the worker SHALL NOT process it again.

#### Scenario: Retry execute creates replacement work
- **WHEN** a dead-letter retry-execute action is approved
- **THEN** the system SHALL create a new pending execution and SHALL NOT mutate the dead-lettered execution into active processing.

### Requirement: Stale lease recovery loop
The system SHALL recover stale leased executions through a bounded recovery loop that respects active worker heartbeats.

#### Scenario: Lease is stale
- **WHEN** an execution lease has expired beyond the configured stale threshold
- **THEN** the recovery loop SHALL make the execution eligible for safe retry or dead-letter handling according to retry policy.

#### Scenario: Lease is active
- **WHEN** a worker has renewed a lease within the configured heartbeat window
- **THEN** the recovery loop SHALL NOT reclaim that execution.

### Requirement: Dead-letter and retry coordination
The system SHALL coordinate worker failures, retry exhaustion, and dead-letter creation without losing failure history.

#### Scenario: Retry limit is exhausted
- **WHEN** an execution repeatedly fails past the configured retry limit
- **THEN** the system SHALL record a dead letter with failure class, source type, retry count, and enough context for SOAR Operations review.

#### Scenario: Dead-letter retry is requested
- **WHEN** an analyst or super admin requests retry for a dead letter
- **THEN** the worker SHALL treat the resulting work according to normal lease and idempotency rules.

### Requirement: Worker operational visibility
The system SHALL expose read-only operational visibility for worker health, queue depth, stale execution counts, recovery counts, and failure rates.

#### Scenario: Analyst views worker health
- **WHEN** an authorized analyst or super admin opens SOAR metrics or operations visibility
- **THEN** the system SHALL provide current worker and queue health without exposing mutation controls to viewers.

#### Scenario: Worker heartbeat is missing
- **WHEN** worker heartbeat data is unavailable or stale
- **THEN** the system SHALL surface that state as unknown or unhealthy without crashing dashboard views.

### Requirement: Deployment safety
The system SHALL define deployment practices for daemonized execution that preserve current runtime safety constraints.

#### Scenario: systemd deployment is prepared
- **WHEN** deployment artifacts are introduced in a later implementation slice
- **THEN** they SHALL include environment requirements, logging expectations, restart policy, and graceful shutdown semantics.

#### Scenario: Real integrations remain disabled
- **WHEN** the daemonized worker is deployed
- **THEN** it SHALL NOT enable autonomous real firewall actions or real Slack/Teams notifications by default.

### Requirement: Concurrency and load validation
The system SHALL include verification coverage for concurrent workers, queue pressure, stale recovery, and failure injection before production-style rollout.

#### Scenario: Multiple workers process the same queue
- **WHEN** two or more workers run against the same execution queue
- **THEN** tests SHALL prove each execution is completed, failed, retried, or dead-lettered at most once per owned attempt.

#### Scenario: Failure injection is run
- **WHEN** tests simulate worker crash, DB disconnect, mid-step lease expiry, or poison execution behavior
- **THEN** the system SHALL recover safely without duplicate execution or unbounded retry loops.
