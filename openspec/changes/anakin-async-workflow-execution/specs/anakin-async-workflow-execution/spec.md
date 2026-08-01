# Spec: Anakin Async Workflow Execution

## ADDED Requirements

### Requirement: Durable async workflow requests

Deep Investigate, Decision Support, and Generate Artifact SHALL be executable through durable queued workflow requests rather than long-running Gunicorn request handlers.

#### Scenario: Queue request returns quickly

- **GIVEN** an authenticated analyst submits `deep_investigate`, `decision_support`, or `generate_artifact` to `POST /ai/workflows/requests`
- **WHEN** the request envelope is valid
- **THEN** the backend SHALL persist a workflow request
- **AND** return a request identifier and `queued` lifecycle without executing Ollama inference inside the request.

#### Scenario: Unsupported async workflows are rejected

- **WHEN** the async request API receives `quick_explain`, `soc_briefing`, `repo_assistant`, preview, confirm, or mutation fields
- **THEN** it SHALL reject the request without creating executable work.

#### Scenario: Duplicate idempotency returns active request

- **GIVEN** a non-terminal async workflow request already exists for the same actor and idempotency key
- **WHEN** an equivalent queue request is submitted
- **THEN** the backend SHALL return the existing active request
- **AND** SHALL NOT create duplicate long-running execution.

#### Scenario: Auto-routed long workflow is queued

- **GIVEN** an authenticated analyst submits `workflow="auto"` to `POST /ai/workflows/requests`
- **WHEN** backend classification chooses `deep_investigate`, `decision_support`, or `generate_artifact`
- **THEN** the backend SHALL create a durable async workflow request
- **AND** return `202` with request identifier and auditable classification metadata.

#### Scenario: Auto-routed Quick Explain returns immediately

- **GIVEN** an authenticated analyst submits `workflow="auto"` to `POST /ai/workflows/requests`
- **WHEN** backend classification chooses `quick_explain`
- **THEN** the backend SHALL return a valid immediate Quick Explain envelope
- **AND** SHALL NOT create a durable async workflow request.

#### Scenario: Low-confidence auto classification does not enqueue

- **WHEN** auto classification returns a chooser-required state
- **THEN** the backend SHALL return the chooser immediately
- **AND** SHALL NOT create a durable async workflow request
- **AND** SHALL NOT silently invoke SOC Briefing, Repo Assistant, preview, confirm, or mutation paths.

### Requirement: Polling lifecycle contract

The async request status API SHALL expose truthful lifecycle state, stage, metadata, result, timestamps, and failure details.

#### Scenario: Polling reaches terminal result

- **GIVEN** a queued async workflow request
- **WHEN** a worker completes it
- **THEN** `GET /ai/workflows/requests/<id>` SHALL return `completed`, `partial`, `degraded`, `failed`, or `timed_out`
- **AND** include the canonical workflow response envelope when one exists.

#### Scenario: Lifecycle stages are truthful

- **WHEN** an async workflow request is queued, claimed, executing tools, generating analysis, validating, or completed
- **THEN** lifecycle stages SHALL use backend-owned states such as `queued`, `running`, `gathering_context`, `retrieving_evidence`, `querying_tools`, `preparing_evidence`, `generating_analysis`, `validating_response`, and `complete`
- **AND** SHALL NOT fabricate model thinking.

### Requirement: Worker claim, retry, and stale recovery

The worker SHALL claim async workflow jobs safely, bound retries, and recover stale running jobs.

#### Scenario: Worker claims one request safely

- **WHEN** multiple queued requests exist
- **THEN** the worker SHALL claim work with a lease or equivalent concurrency control
- **AND** only the lease owner SHALL complete or fail the request.

#### Scenario: Stale running request is recovered

- **GIVEN** a running request lease expires
- **WHEN** stale recovery runs
- **THEN** the request SHALL be requeued if attempts remain
- **OR** marked failed/timed_out when retry bounds are exhausted.

### Requirement: Workflow safety is preserved

Async execution SHALL preserve all existing workflow safety contracts.

#### Scenario: Decision Support stays recommendation-only

- **WHEN** Decision Support executes asynchronously
- **THEN** it SHALL remain read-only
- **AND** SHALL NOT generate artifacts, preview actions, confirm actions, apply actions, persist drafts, or mutate state.

#### Scenario: Generate Artifact remains review-only

- **WHEN** Generate Artifact executes asynchronously
- **THEN** it SHALL preserve strict schema validation and one bounded repair attempt
- **AND** SHALL return preview/non-persistent draft output with no automatic persistence or apply path.

#### Scenario: Deep Investigate keeps bounded read tools

- **WHEN** Deep Investigate executes asynchronously
- **THEN** it SHALL use approved bounded read tools only
- **AND** preserve partial/degraded evidence behavior.

### Requirement: Frontend async polling UX

The consolidated frontend SHALL queue long-running workflows, poll status, and render terminal canonical results.

#### Scenario: Long workflow control uses queue API

- **WHEN** an analyst clicks Deep Investigate, Decision Support, or Generate Artifact
- **THEN** the frontend SHALL call `POST /ai/workflows/requests`
- **AND** poll `GET /ai/workflows/requests/<id>` until terminal
- **AND** render the same canonical result UI on success.

#### Scenario: Active request is recoverable

- **WHEN** the component remounts or page refreshes while a matching request is active
- **THEN** the frontend SHALL safely recover and continue polling the existing request when the context key still matches.

#### Scenario: Freeform auto uses queue-capable route

- **WHEN** the analyst submits a natural-language Ask Anakin request with `workflow="auto"`
- **THEN** the frontend SHALL call `POST /ai/workflows/requests`
- **AND** SHALL handle immediate Quick Explain, chooser-required, and queued async responses.

#### Scenario: Specific errors are visible

- **WHEN** worker unavailable, provider unavailable, provider timeout, workflow timeout, context/prompt limit, validation failure, authorization failure, or network/proxy failure occurs
- **THEN** the frontend SHALL show a specific error rather than only `AI response unavailable`.
