# repo-assistant-async-execution

## ADDED Requirements

### Requirement: Repo Assistant Queued Requests

Repo Assistant SHALL queue normal repository questions instead of holding nginx open for model generation.

#### Scenario: Repository question queues
- **WHEN** an authorized user asks a factual, architectural, or evaluative repository question
- **THEN** `POST /ai/repo/requests` SHALL return a durable request ID quickly
- **AND** the model answer SHALL be generated outside the Gunicorn request.

#### Scenario: Live SIEM boundary remains immediate
- **WHEN** the question clearly asks for live SIEM operational data
- **THEN** the route SHALL return `scope_boundary` immediately
- **AND** SHALL NOT queue a job or retrieve repository evidence.

### Requirement: Repo Assistant Durable Store Constraints

The durable workflow request store SHALL accept Repo Assistant jobs and truthful repository lifecycle stages.

#### Scenario: Store accepts repo assistant workflow
- **WHEN** a normal repository question is queued
- **THEN** the durable request row SHALL be accepted with workflow `repo_assistant`
- **AND** repository stages SHALL pass schema validation without changing existing async workflow semantics.

### Requirement: Repo Assistant Polling Lifecycle

Repo Assistant SHALL expose truthful polling states.

#### Scenario: Polling returns terminal result
- **WHEN** `GET /ai/repo/requests/<id>` reaches a terminal state
- **THEN** it SHALL include answer, question type, citations, retrieval metadata, provider metadata, timestamps, and error details when applicable.

#### Scenario: Repo-specific stages are exposed
- **WHEN** a repo request is running
- **THEN** stages SHALL include repository evidence retrieval, context preparation, answer generation, citation validation, and completion
- **AND** SHALL NOT fabricate model thinking.

### Requirement: Repo Boundaries And Authorization Remain

Queued Repo Assistant execution SHALL preserve existing boundaries.

#### Scenario: RBAC is unchanged
- **WHEN** a non-super-admin user accesses repo request routes
- **THEN** access SHALL be denied.

#### Scenario: Citations remain backend-owned
- **WHEN** a repo answer completes
- **THEN** citations SHALL be selected and validated by the backend
- **AND** unauthorized repo content SHALL NOT be exposed.

### Requirement: Frontend Polls Repo Requests

The Repo Assistant UI SHALL queue, poll, and render repo request results.

#### Scenario: UI handles queued result
- **WHEN** a normal repo question is submitted
- **THEN** the UI SHALL show truthful progress and render the terminal answer.

#### Scenario: UI handles immediate boundary
- **WHEN** a live SIEM-data question is submitted
- **THEN** the UI SHALL render boundary guidance without polling.
