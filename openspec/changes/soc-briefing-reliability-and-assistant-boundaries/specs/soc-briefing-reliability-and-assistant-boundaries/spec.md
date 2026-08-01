# Spec: SOC Briefing Reliability And Assistant Boundaries

## ADDED Requirements

### Requirement: SOC briefing step persistence is idempotent

SOC briefing run-step persistence SHALL be safe when a worker retries or resumes the same run.

#### Scenario: Duplicate step index write updates existing step

- **GIVEN** a SOC briefing run already has a step row for `(run_id, step_index)`
- **WHEN** the worker records the same deterministic step again during retry or resume
- **THEN** persistence SHALL update the existing step row instead of inserting a duplicate
- **AND** SHALL NOT raise a uniqueness error.

#### Scenario: Step indexes remain deterministic

- **WHEN** a SOC briefing worker records a run
- **THEN** step indexes SHALL remain monotonic and deterministic for the worker plan
- **AND** repeated processing SHALL NOT create gaps or corrupt prior steps.

### Requirement: SOC briefing recovery is bounded and state-aware

SOC briefing stale-job recovery SHALL distinguish abandoned work from valid timer/lease states.

#### Scenario: Active leased job is not recovered

- **GIVEN** a SOC briefing job is running with a valid lease
- **WHEN** stale recovery runs
- **THEN** the job SHALL remain running and owned by its current lease.

#### Scenario: Expired running job is requeued or terminally failed

- **GIVEN** a SOC briefing job is running with an expired lease
- **WHEN** attempts remain
- **THEN** recovery SHALL requeue the job for bounded retry
- **AND** preserve exact recovery metadata.
- **WHEN** attempts are exhausted
- **THEN** recovery SHALL mark the job failed or timed out with exact error code and message.

#### Scenario: Terminal job is not overwritten

- **GIVEN** a SOC briefing job is completed, partial, degraded, failed, or timed out
- **WHEN** stale recovery runs
- **THEN** recovery SHALL NOT overwrite the terminal state.

### Requirement: SOC briefing worker health is timer-aware

SOC briefing control/status APIs SHALL expose truthful one-shot timer worker health.

#### Scenario: Timer worker waiting is not offline

- **GIVEN** no SOC briefing worker process is currently running
- **AND** the timer model is expected to execute periodically
- **AND** the last execution was recent or no job is due
- **WHEN** status is requested
- **THEN** worker health SHALL be `healthy_waiting` or `recently_successful`
- **AND** SHALL NOT claim the worker is offline solely because there is no continuous heartbeat.

#### Scenario: Stale or inactive timer is explicit

- **WHEN** expected worker execution metadata is stale
- **THEN** status SHALL be `stale`.
- **WHEN** timer/schedule metadata indicates inactive timer behavior
- **THEN** status SHALL be `timer_inactive`.

### Requirement: Manual Run Now lifecycle remains durable and visible

Manual SOC briefing Run Now SHALL queue work safely, expose lifecycle, and surface terminal results.

#### Scenario: Manual-only mode allows Run Now

- **GIVEN** SOC briefing mode is `manual_only`
- **WHEN** an authorized analyst triggers Run Now
- **THEN** a manual job SHALL be queued unless an active manual job already exists
- **AND** long AI work SHALL NOT execute inside the request handler.

#### Scenario: Terminal manual run selects produced briefing

- **GIVEN** a manual SOC briefing job reaches completed, partial, or degraded
- **WHEN** the frontend polls the manual lifecycle
- **THEN** the lifecycle SHALL include the produced briefing identifier when available
- **AND** the frontend SHALL refresh history and select/open that briefing.

### Requirement: Repo Assistant rejects live SIEM-data questions

Repo Assistant SHALL not answer live SIEM operational-data questions from repository context.

#### Scenario: Current alert question returns boundary response

- **WHEN** a user asks the Repo Assistant “What is my most severe alert?”
- **THEN** the backend SHALL return a clear boundary response explaining that live SIEM data is required
- **AND** SHALL guide the user to Dashboard, Alert Details, or SOC Command Center Anakin
- **AND** SHALL NOT invoke repository retrieval or model generation.

#### Scenario: Repository questions still work

- **WHEN** a user asks “Where is the SOAR worker implemented?”
- **THEN** Repo Assistant SHALL answer using repository retrieval and backend-owned citations.
- **WHEN** a user asks “What is my most impressive feature?”
- **THEN** Repo Assistant SHALL answer evaluatively from repository evidence and backend-owned citations.

#### Scenario: Ambiguous live-data questions fail conservatively

- **WHEN** a mixed or ambiguous Repo Assistant question clearly requires current SIEM operational state
- **THEN** the assistant SHALL return the boundary response instead of fabricating live SIEM knowledge.
