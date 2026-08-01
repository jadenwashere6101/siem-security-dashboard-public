## ADDED Requirements

### Requirement: Manual Run Now exposes durable job identity
Run Now SHALL return and display the manual briefing job that was created or already active.

#### Scenario: One click creates exactly one manual job
- **WHEN** an analyst clicks Run Anakin Briefing Now with no active manual job
- **THEN** the backend SHALL create one durable manual job
- **AND** return its job id and lifecycle status.

#### Scenario: Repeat click returns already-running
- **WHEN** an analyst clicks Run Anakin Briefing Now while a manual job is pending or running
- **THEN** the backend SHALL NOT create a duplicate active manual job
- **AND** return the existing job id with an already-running lifecycle indicator.

### Requirement: Manual lifecycle status is pollable
The system SHALL expose pollable durable manual job/run/briefing state until terminal outcome.

#### Scenario: UI progresses through lifecycle
- **WHEN** a tracked manual job moves through queued, running, completed, partial/degraded, failed, blocked, or timed-out durable states
- **THEN** the UI SHALL display the current lifecycle state
- **AND** stop polling only when the lifecycle is terminal.

#### Scenario: Completed briefing opens from history
- **WHEN** a manual job completes and a briefing is persisted
- **THEN** the UI SHALL refresh briefing history
- **AND** select/open the new briefing.

#### Scenario: Page refresh recovers active tracking
- **WHEN** the SOC Briefings panel loads while a manual job is pending or running
- **THEN** the UI SHALL recover and poll the active manual job from durable state.

### Requirement: Worker and blocked states are visible
The manual lifecycle UI SHALL show worker heartbeat and specific blocked/failure reasons.

#### Scenario: Worker unavailable is explicit
- **WHEN** a manual job is queued but no fresh briefing worker heartbeat is available
- **THEN** the UI SHALL show the job as queued
- **AND** indicate worker unavailable, stale, or offline without executing the job in Gunicorn.

#### Scenario: Blocked reasons are specific
- **WHEN** durable job/run/provider state indicates AI provider unavailable, local model unavailable, already running, runtime/budget failure, timeout, or another blocked/failure reason
- **THEN** the UI SHALL display that reason clearly.

### Requirement: Manual runs remain independent of schedules
Manual Run Now SHALL remain available while schedules are paused and in either briefing mode.

#### Scenario: Paused schedules do not block manual run
- **WHEN** schedules are paused
- **AND** an analyst clicks Run Anakin Briefing Now
- **THEN** the backend SHALL allow the manual job unless another manual job is already active.

### Requirement: Existing worker architecture and safety boundaries remain
Manual run lifecycle tracking SHALL NOT move long AI execution into Gunicorn or introduce production mutation.

#### Scenario: Worker owns execution
- **WHEN** a manual job is created
- **THEN** the API request SHALL only enqueue/report durable state
- **AND** the PostgreSQL-backed worker SHALL remain responsible for claiming and executing the job.

#### Scenario: No paid fallback or production action
- **WHEN** manual lifecycle APIs and UI run
- **THEN** they SHALL NOT enable paid fallback
- **AND** SHALL NOT execute production actions, create fake briefings, or mutate production outside existing durable queue/run/briefing records.
