## ADDED Requirements

### Requirement: One canonical action vocabulary
All action producers, validators, queues, playbook definitions, executors, API serializers, and UI labels SHALL use one canonical action registry that identifies the owning execution path and supported modes.

#### Scenario: Supported action is produced
- **WHEN** any component emits an action
- **THEN** the action SHALL be validated against the same registry used by its owning executor before durable work is enqueued

### Requirement: Deterministic notification actions
The ambiguous bare action `notify` SHALL NOT enter execution unless a deterministic provider and canonical notification action can be resolved before enqueueing.

#### Scenario: Bare notify lacks provider
- **WHEN** a producer submits `notify` without enough information to select Slack, Email, Webhook, or Teams
- **THEN** validation SHALL reject it with an actionable error before queue or dead-letter creation

#### Scenario: Historical notify has deterministic provider
- **WHEN** an explicitly approved compatibility rule can safely map a historical `notify` payload to one provider action
- **THEN** the migration SHALL record the original action, mapped action, reason, and idempotency evidence

### Requirement: Read-only enrichment routing
`enrich_context` SHALL be owned by the playbook read-only executor and SHALL NOT be enqueued to or dispatched by the legacy response-action worker.

#### Scenario: Playbook contains enrichment
- **WHEN** a valid playbook reaches `enrich_context`
- **THEN** the playbook executor SHALL perform the read-only enrichment and record its truthful outcome without producing an unsupported-action dead letter

#### Scenario: Legacy producer attempts enrichment enqueue
- **WHEN** a legacy response-action producer attempts to enqueue `enrich_context`
- **THEN** it SHALL be rejected or rerouted before durable queue creation with diagnostic provenance

### Requirement: Unsupported-action observability
Rejected actions SHALL be measurable at validation boundaries, and production SHALL expose whether new `unsupported_action` dead letters continue after deployment.

#### Scenario: Post-deployment verification runs
- **WHEN** the VM AI completes deployment and backlog triage
- **THEN** it SHALL verify no new `notify` or `enrich_context` unsupported-action cohort is growing and SHALL report any remaining producer path to the Mac AI

### Requirement: Historical dead-letter safety handoff
The Mac implementation SHALL provide the VM AI with classification and retry criteria for historical unsupported-action dead letters.

#### Scenario: Existing unsupported-action backlog is reviewed
- **WHEN** the VM AI reviews open `notify` and `enrich_context` dead letters plus the retrying record
- **THEN** only still-relevant, idempotent work corrected by the deployed routing fix SHALL receive a canary retry and all obsolete, ambiguous, unsafe, or duplicate-prone work SHALL be dismissed or escalated with preserved evidence
