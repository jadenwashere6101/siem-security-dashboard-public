## ADDED Requirements

### Requirement: Manual playbook execution
The system SHALL allow an authenticated analyst or super-admin to manually create a normal pending playbook execution for an enabled playbook against exactly one existing alert or incident.

#### Scenario: Analyst manually launches a playbook for an alert
- **WHEN** an authenticated analyst requests manual execution of an enabled playbook with a valid `alert_id`
- **THEN** the system creates a `playbook_executions` row with `status` set to `pending`
- **AND** the row is processable by the existing playbook worker.

#### Scenario: Analyst manually launches a playbook for an incident
- **WHEN** an authenticated analyst requests manual execution of an enabled playbook with a valid `incident_id`
- **THEN** the system creates a `playbook_executions` row with `status` set to `pending`
- **AND** the row is processable by the existing playbook worker.

#### Scenario: Invalid target shape is rejected
- **WHEN** a manual execution request provides neither `alert_id` nor `incident_id`, or provides both
- **THEN** the system returns a validation error and creates no execution.

#### Scenario: Disabled playbook is rejected
- **WHEN** a manual execution request references a disabled or missing playbook
- **THEN** the system rejects the request and creates no execution.

### Requirement: Manual executions reuse the existing orchestration pipeline
Manual executions SHALL use existing playbook execution rows, canonical response outcome linkage, worker leasing, step execution, approval handling, and terminal statuses.

#### Scenario: Existing worker claims manual execution
- **WHEN** a manual execution has been created with `status` set to `pending`
- **THEN** the existing playbook worker can claim and process it without a separate manual execution engine.

#### Scenario: Approval gates still apply
- **WHEN** a manually launched playbook reaches a `require_approval` step
- **THEN** the execution pauses through the existing approval flow before later steps run.

#### Scenario: Manual launch itself is not approval gated
- **WHEN** a user with launch permission starts an investigation-only playbook manually
- **THEN** the launch does not require a separate approval unless the playbook definition contains an approval step.

### Requirement: Manual execution traceability
The system SHALL distinguish manual executions from automatic executions in audit logs and canonical response outcome metadata.

#### Scenario: Audit event records manual launch
- **WHEN** a manual execution is created successfully
- **THEN** an audit event records the actor username, actor role, playbook ID, execution ID, target type, target ID, and trigger type `manual`.

#### Scenario: Execution metadata identifies trigger type
- **WHEN** execution outcome metadata is inspected for a manually launched execution
- **THEN** it identifies the execution as manually triggered and includes safe actor and target metadata.

### Requirement: Manual launch permission enforcement
The system SHALL restrict manual playbook launch to authenticated analyst and super-admin users.

#### Scenario: Unauthenticated launch is rejected
- **WHEN** an unauthenticated user requests manual playbook execution
- **THEN** the system rejects the request.

#### Scenario: Viewer launch is rejected
- **WHEN** an authenticated viewer requests manual playbook execution
- **THEN** the system rejects the request.

### Requirement: Manual launch UI surfaces
The frontend SHALL expose manual playbook launch only from UI contexts that identify a concrete existing alert or incident target.

#### Scenario: Alert surface can launch for an alert
- **WHEN** an authorized user views an alert action surface
- **THEN** the UI can offer manual playbook launch with that alert as the target.

#### Scenario: Incident surface can launch for an incident
- **WHEN** an authorized user views an incident detail or timeline surface
- **THEN** the UI can offer manual playbook launch with that incident as the target.

#### Scenario: Threat hunt does not launch from raw event alone
- **WHEN** an authorized user expands a raw threat-hunt event
- **THEN** the UI does not launch directly against the raw event unless the user selects an existing alert or incident target.

#### Scenario: SOC Command Center launch uses concrete targets
- **WHEN** an authorized user launches from SOC Command Center context
- **THEN** the launch is tied to an existing alert or incident, not to an aggregate-only metric.

### Requirement: Reusable read-only enrichment step
The playbook engine SHALL support a reusable read-only enrichment action that gathers bounded existing local context for the execution target and records the result in the execution step log.

#### Scenario: Enrichment step succeeds for alert target
- **WHEN** a playbook execution with an alert target runs the enrichment step
- **THEN** the step output includes bounded existing alert, MITRE, correlation, reputation, source-IP, related alert, incident, and playbook execution context where available.

#### Scenario: Enrichment step succeeds for incident target
- **WHEN** a playbook execution with an incident target runs the enrichment step
- **THEN** the step output includes bounded existing incident context and linked alert/source-IP context where available.

#### Scenario: Enrichment is read-only
- **WHEN** the enrichment step runs
- **THEN** it does not mutate alerts, incidents, playbook executions, approvals, blocklists, response queues, reputation fields, or external systems.

#### Scenario: Enrichment uses no new external sources
- **WHEN** the enrichment step gathers reputation or location context
- **THEN** it uses existing stored reputation snapshots, existing behavioral reputation logic, and existing stored geolocation fields, and does not call AbuseIPDB, geolocation APIs, or any new external service.

### Requirement: Enrichment output contract
The enrichment step output SHALL be bounded, JSON-serializable, sanitized, and suitable for downstream playbook steps to consume through future or existing parameter binding.

#### Scenario: Output is bounded
- **WHEN** many related alerts, incidents, or executions exist
- **THEN** the enrichment step returns only capped recent collections or aggregate counts.

#### Scenario: Downstream context is stable
- **WHEN** later playbook steps inspect enrichment output
- **THEN** they receive a deterministic object containing only fields gathered from existing local records and helpers.

### Requirement: No duplicate orchestration architecture
The system SHALL NOT introduce a duplicate execution engine, scheduler, workflow builder, branching redesign, chaining redesign, or new dependency to support manual launch or enrichment.

#### Scenario: Manual and automatic executions share execution semantics
- **WHEN** manual and automatic executions are compared
- **THEN** both use the same execution statuses, worker processing, approval behavior, and detail APIs, with only trigger metadata distinguishing their origin.
