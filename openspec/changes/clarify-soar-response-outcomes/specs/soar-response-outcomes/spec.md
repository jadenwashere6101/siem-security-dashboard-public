## ADDED Requirements

### Requirement: Canonical Response Outcome Model
The system SHALL define one canonical response outcome model for SOAR decisions and execution results across alerts, manual actions, queue actions, playbook steps, approvals, notification deliveries, response logs, incidents, source-IP context, SOC Command Center, Attack Map context, and blocklist views.

#### Scenario: Observed-only alert
- **WHEN** an alert exists and no response action has been selected, queued, simulated, tracked, or really executed
- **THEN** the canonical outcome SHALL use `execution_mode=observed`, `execution_state=observed`, `executed=false`, and an outcome summary that says detection occurred but no response was selected.

#### Scenario: Simulated response
- **WHEN** a queue action, playbook step, or adapter result completes in simulation mode
- **THEN** the canonical outcome SHALL use `execution_mode=simulation`, SHALL use an appropriate terminal or active `execution_state`, SHALL set `executed=false`, and SHALL NOT imply provider delivery, firewall enforcement, or local enforcement occurred.

#### Scenario: Tracking-only response
- **WHEN** the SIEM records internal state only, such as a blocklist tracking record without firewall enforcement
- **THEN** the canonical outcome SHALL use `execution_mode=tracking_only`, SHALL set `executed=true` only after the internal tracking state is durably recorded, and SHALL include an outcome summary that states no external enforcement occurred.

#### Scenario: Real external execution
- **WHEN** an external provider action or approved local enforcement action actually happens and returns explicit success evidence
- **THEN** the canonical outcome SHALL use `execution_mode=real`, `execution_state=succeeded`, `executed=true`, and SHALL include the provider or enforcement surface in safe metadata.

#### Scenario: Failed response
- **WHEN** a selected response fails before or during simulation, tracking-only recording, or real execution
- **THEN** the canonical outcome SHALL use `execution_state=failed`, SHALL preserve the effective `execution_mode`, SHALL set `executed=false` unless a tracking-only or real side effect is known to have occurred, and SHALL include a sanitized reason.

#### Scenario: Blocked by approval
- **WHEN** an approval denial or approval expiration prevents a selected response from continuing
- **THEN** the canonical outcome SHALL use `execution_state=blocked`, SHALL set `executed=false`, and SHALL link the relevant approval request where available.

#### Scenario: Awaiting approval
- **WHEN** a selected response is paused pending human approval
- **THEN** the canonical outcome SHALL use `execution_state=awaiting_approval`, SHALL set `executed=false`, and SHALL identify the approval request, playbook step, or queue row that is awaiting approval.

#### Scenario: Skipped response
- **WHEN** a response is skipped because of validation, protected target policy, duplicate prevention, unsupported action, terminal status, abandonment, or operator choice
- **THEN** the canonical outcome SHALL use `execution_state=skipped`, SHALL set `executed=false`, and SHALL include a reason code and analyst-readable summary.

### Requirement: Execution Mode Semantics
The system SHALL use exactly four canonical execution modes: `observed`, `simulation`, `tracking_only`, and `real`.

#### Scenario: Observed mode
- **WHEN** the mode is `observed`
- **THEN** the system SHALL treat the record as detection or visibility only, with no response selected or executed.

#### Scenario: Simulation mode
- **WHEN** the mode is `simulation`
- **THEN** the system SHALL treat the record as a non-real response path and SHALL require `executed=false`.

#### Scenario: Tracking-only mode
- **WHEN** the mode is `tracking_only`
- **THEN** the system SHALL treat the record as an internal SIEM state change and SHALL NOT describe it as firewall, provider, or external enforcement.

#### Scenario: Real mode
- **WHEN** the mode is `real`
- **THEN** the system SHALL require evidence that an external provider action or approved local enforcement action actually occurred before setting `executed=true`.

### Requirement: Execution State Semantics
The system SHALL use canonical execution states: `observed`, `selected`, `queued`, `awaiting_approval`, `running`, `skipped`, `blocked`, `succeeded`, and `failed`.

#### Scenario: Response selected but not queued
- **WHEN** a response action is chosen by detection, correlation, playbook, or manual operator but no worker has started it
- **THEN** the canonical outcome SHALL use `execution_state=selected` or `queued` according to whether a durable queue/execution row exists.

#### Scenario: Worker processing response
- **WHEN** a queue worker or playbook worker has claimed work
- **THEN** the canonical outcome SHALL use `execution_state=running` until the work reaches a terminal canonical state.

#### Scenario: Response reaches terminal state
- **WHEN** a response finishes, fails, is blocked, or is skipped
- **THEN** the canonical outcome SHALL use one of `succeeded`, `failed`, `blocked`, or `skipped` and SHALL include a timestamp for the terminal transition where available.

### Requirement: Executed Boolean Semantics
The system SHALL define `executed` as a boolean that answers whether anything actually happened beyond observation or simulation.

#### Scenario: Simulated result cannot be executed
- **WHEN** a response outcome has `execution_mode=simulation`
- **THEN** the system SHALL set `executed=false` even when the simulation completed successfully.

#### Scenario: Observed result cannot be executed
- **WHEN** a response outcome has `execution_mode=observed`
- **THEN** the system SHALL set `executed=false`.

#### Scenario: Tracking-only success is executed internally
- **WHEN** a tracking-only internal SIEM state change is durably recorded
- **THEN** the system SHALL set `executed=true` and SHALL label the mode as `tracking_only` in every API/UI surface.

#### Scenario: Real success is executed externally
- **WHEN** a real external provider action or approved local enforcement action is confirmed successful
- **THEN** the system SHALL set `executed=true` and SHALL label the mode as `real`.

#### Scenario: Ambiguous or failed real attempt
- **WHEN** a real-capable adapter times out, is blocked, fails closed, or cannot confirm success
- **THEN** the system SHALL set `executed=false` unless positive evidence proves the action occurred.

### Requirement: Decision Record Semantics
The system SHALL record response decision facts separately from execution outcome facts.

#### Scenario: Detection default decision
- **WHEN** detection or correlation selects a default response action for an alert
- **THEN** the system SHALL record the selected action, `decision_source=detection_default` or `decision_source=correlation`, the alert id, source IP, selected timestamp, and outcome summary.

#### Scenario: Manual decision
- **WHEN** an analyst or super admin manually selects a response action
- **THEN** the system SHALL record `decision_source=manual`, the actor user id, selected action, alert id, source IP, and a separate correlation id or child correlation id.

#### Scenario: Playbook decision
- **WHEN** a playbook step selects or represents a response action
- **THEN** the system SHALL record `decision_source=playbook`, the playbook id, playbook execution id, step index, selected action, and related alert or incident ids where available.

#### Scenario: Approval decision
- **WHEN** an approval is approved, denied, or expired
- **THEN** the system SHALL record an outcome linked to the approval request and SHALL represent denied or expired approval as blocked response work, not as successful execution.

#### Scenario: Adapter decision/result
- **WHEN** an adapter returns a result for a notification or response step
- **THEN** the system SHALL record `decision_source=adapter`, adapter/provider identity, effective execution mode, execution state, executed boolean, and safe metadata.

### Requirement: Correlation ID Strategy
The system SHALL use a safe `correlation_id` to link related records across alert, queue, playbook, approval, adapter, response log, incident, source-IP context, and UI views.

#### Scenario: New alert response lifecycle
- **WHEN** a response is first selected for an alert
- **THEN** the system SHALL create or assign one safe SOAR correlation id and propagate it to subsequent queue, playbook, approval, delivery, log, and outcome records.

#### Scenario: Child lifecycle event
- **WHEN** a playbook step, adapter delivery, approval decision, or manual follow-up represents a child event under an existing lifecycle
- **THEN** the system SHALL preserve the parent correlation id or explicitly record a child correlation id linked to the parent.

#### Scenario: Legacy backfill
- **WHEN** historical records do not have a correlation id
- **THEN** the backfill SHALL assign deterministic legacy correlation ids that do not contain secrets and that are stable across repeated migration validation.

#### Scenario: Correlation id safety
- **WHEN** a correlation id is stored, returned, logged, or shown in the UI
- **THEN** it SHALL NOT contain webhooks, tokens, passwords, provider payloads, raw source payloads, or unsafe user input.

### Requirement: Database Schema Changes
The system SHALL add an additive canonical response outcome data model while preserving existing tables and records.

#### Scenario: Outcome ledger table
- **WHEN** schema migration for this change is applied
- **THEN** it SHALL create an additive canonical outcome table, such as `soar_response_outcomes`, with fields for correlation id, related entity ids, source IP, selected action, decision source, execution mode, execution state, executed boolean, outcome summary, reason code, provider/adapter metadata, safe JSON metadata, and timestamps.

#### Scenario: Existing table linkage
- **WHEN** schema migration for this change is applied
- **THEN** it SHOULD add nullable linkage fields such as `correlation_id` and `outcome_id` to existing SOAR tables where they improve traceability without breaking old records.

#### Scenario: Schema constraints
- **WHEN** the outcome schema stores canonical enums
- **THEN** it SHALL constrain execution modes, execution states, and decision sources to approved values.

#### Scenario: Secret-free metadata
- **WHEN** the outcome schema stores JSON metadata
- **THEN** metadata SHALL be safe and sanitized and SHALL NOT store secrets, webhooks, raw provider payloads, raw headers, raw responses, raw passwords, or raw unsafe exception strings.

#### Scenario: Query support
- **WHEN** the outcome schema is added
- **THEN** it SHALL include indexes or query paths for correlation id, alert id, source IP, incident id, queue id, playbook execution/step, approval request, notification delivery, execution mode/state, and recent outcomes.

### Requirement: Backend Outcome Writer
The system SHALL centralize canonical outcome creation, validation, serialization, and compatibility inference in backend helper modules.

#### Scenario: Writer validates enums
- **WHEN** backend code writes a canonical outcome
- **THEN** the writer SHALL validate execution mode, execution state, decision source, executed boolean compatibility, correlation id safety, and metadata safety before persistence.

#### Scenario: Writer preserves old behavior
- **WHEN** existing detection, queue, playbook, approval, notification, or manual action flows write canonical outcomes
- **THEN** they SHALL preserve existing side effects and SHALL NOT change detection thresholds, approval policy, SOAR queue semantics, or playbook matching semantics.

#### Scenario: Compatibility resolver
- **WHEN** an API reads an older record without canonical outcome rows
- **THEN** the backend SHALL return a conservative inferred canonical outcome with `decision_source=migration` or equivalent compatibility metadata.

### Requirement: Backend API Response Contracts
The system SHALL expose canonical response outcome payloads from SOAR-related APIs while preserving existing legacy fields during rollout.

#### Scenario: Alert detail API
- **WHEN** an authorized user reads an alert detail or alert list item
- **THEN** the API SHALL include canonical response outcome data or an inferred observed-only outcome.

#### Scenario: SOAR Queue API
- **WHEN** an authorized super admin reads SOAR queue status, list, or detail
- **THEN** the API SHALL include canonical execution mode/state, selected action, executed boolean, decision source, outcome summary, correlation id, and linked approval/playbook/log ids where available.

#### Scenario: Playbook API
- **WHEN** an authorized user reads playbook executions or a playbook execution detail
- **THEN** the API SHALL include canonical outcome summaries for the execution and for each step where available.

#### Scenario: Approval API
- **WHEN** an authorized user reads approval list or detail
- **THEN** the API SHALL include linked canonical outcomes and SHALL represent denied or expired approvals as blocked, not executed.

#### Scenario: Notification delivery API
- **WHEN** an authorized user reads notification delivery attempts
- **THEN** the API SHALL expose canonical execution mode/state and executed boolean derived from delivery status, mode, and adapter result metadata.

#### Scenario: Incident API
- **WHEN** an authorized user reads incidents or incident timeline
- **THEN** the API SHALL include related canonical outcomes in timeline or detail context without mutating incident state.

#### Scenario: Source-IP context API
- **WHEN** an authorized user reads source-IP context
- **THEN** the API SHALL include recent canonical outcomes for that source IP with selected action, decision source, execution mode/state, executed boolean, summary, and related ids.

#### Scenario: Metrics APIs
- **WHEN** metrics summarize SOAR activity
- **THEN** they SHALL distinguish observed-only, simulation, tracking-only, real, awaiting approval, blocked, skipped, failed, and succeeded outcomes.

### Requirement: Dashboard Outcome Presentation
The dashboard SHALL show canonical response outcomes with consistent language and avoid ambiguous standalone "executed" labels.

#### Scenario: Required fields in every outcome display
- **WHEN** an analyst sees a response outcome anywhere in the UI
- **THEN** the UI SHALL show selected action, decision source, execution mode, execution state, executed truth, summary/reason, and related playbook/queue/approval ids where applicable.

#### Scenario: Alert Details display
- **WHEN** an analyst opens Alert Details or an expanded alert row
- **THEN** the UI SHALL show whether the alert is observed only, simulated, tracking-only, real-executed, failed, blocked, awaiting approval, or skipped.

#### Scenario: SOAR Queue display
- **WHEN** a super admin opens SOAR Queue
- **THEN** each queue row and detail view SHALL show canonical outcome language instead of ambiguous queue-only status copy.

#### Scenario: Approval Requests display
- **WHEN** an analyst opens Approval Requests
- **THEN** approval cards and detail views SHALL show what action is awaiting approval, what will happen if approved, and whether denial/expiration blocked execution.

#### Scenario: Playbooks Panel display
- **WHEN** an analyst opens Playbooks Panel or execution timeline
- **THEN** the UI SHALL label each step as simulation, tracking-only, real, observed, blocked, skipped, failed, or awaiting approval using canonical outcome language.

#### Scenario: SOC Command Center display
- **WHEN** an analyst opens SOC Command Center
- **THEN** command-center summaries and incident workspace SHALL distinguish observed-only, simulated, tracking-only, real-executed, blocked, awaiting approval, skipped, and failed response work.

#### Scenario: Source-IP Context display
- **WHEN** an analyst opens source-IP context from SOC Command Center, Alert Details, or Attack Map
- **THEN** the drawer/popup SHALL display recent canonical outcomes for that IP with selected action and execution mode/state.

#### Scenario: Attack Map popup display
- **WHEN** the Attack Map popup displays response or source-IP context status
- **THEN** it SHALL use canonical outcome labels and SHALL NOT show a vague `executed` value without mode.

#### Scenario: Blocklist Manager display
- **WHEN** Blocklist Manager shows entries created by SOAR or manual alert actions
- **THEN** it SHALL identify tracking-only state and SHALL NOT imply firewall enforcement unless a real enforcement outcome exists.

### Requirement: Migration and Backfill Strategy
The system SHALL provide a conservative migration/backfill strategy for existing records.

#### Scenario: Backfill observed alerts
- **WHEN** an existing alert has no response action, queue, response log, playbook step, approval, notification delivery, or blocklist evidence
- **THEN** backfill SHALL create or infer an observed-only outcome.

#### Scenario: Backfill simulated logs
- **WHEN** an existing response log or playbook step clearly represents simulation
- **THEN** backfill SHALL create or infer `execution_mode=simulation`, an appropriate state, and `executed=false`.

#### Scenario: Backfill tracking-only logs
- **WHEN** an existing response log or blocklist entry clearly represents SIEM tracking-only state
- **THEN** backfill SHALL create or infer `execution_mode=tracking_only`, `execution_state=succeeded`, and `executed=true` with a summary that says no firewall enforcement occurred.

#### Scenario: Backfill notification deliveries
- **WHEN** existing notification delivery attempts include `mode`, `status`, and metadata
- **THEN** backfill SHALL map those records to canonical outcomes without changing the delivery attempt record.

#### Scenario: Conservative unknowns
- **WHEN** existing records are ambiguous
- **THEN** backfill SHALL avoid marking them real-executed and SHALL include an inferred/legacy reason code.

#### Scenario: Re-runnable verification
- **WHEN** backfill validation is run repeatedly
- **THEN** it SHALL produce stable counts and SHALL NOT create duplicate canonical outcomes.

### Requirement: Rollout Plan
The system SHALL support phased rollout without breaking current SOAR behavior.

#### Scenario: Schema-only rollout
- **WHEN** the first implementation phase deploys additive schema
- **THEN** existing APIs and UI SHALL continue functioning without requiring canonical outcomes.

#### Scenario: Dual-write rollout
- **WHEN** backend writers begin writing canonical outcomes
- **THEN** legacy tables SHALL continue receiving existing writes until UI and API consumers are migrated.

#### Scenario: API compatibility rollout
- **WHEN** APIs add canonical outcome payloads
- **THEN** legacy response fields SHALL remain available until a later approved cleanup.

#### Scenario: UI incremental rollout
- **WHEN** frontend screens migrate to canonical outcome components
- **THEN** each screen SHALL preserve old data readability and SHALL show compatibility labels for older inferred records.

### Requirement: Rollback Plan
The system SHALL allow safe rollback of behavior introduced by this change.

#### Scenario: Disable canonical writes
- **WHEN** canonical outcome writing must be rolled back
- **THEN** the system SHALL be able to stop writing outcome rows while preserving legacy alert, queue, playbook, approval, notification, response log, and blocklist behavior.

#### Scenario: Revert UI consumers
- **WHEN** canonical outcome UI must be rolled back
- **THEN** the UI SHALL be able to fall back to existing legacy fields without requiring destructive database changes.

#### Scenario: Retain additive data
- **WHEN** rollback occurs after schema migration
- **THEN** additive tables and nullable columns SHOULD be left in place unless a separate approved rollback migration removes them.

### Requirement: Test Coverage
The implementation SHALL include tests for every layer affected by canonical SOAR outcomes.

#### Scenario: Data model tests
- **WHEN** schema and model tests run
- **THEN** they SHALL verify enum constraints, executed boolean rules, correlation id propagation, safe metadata redaction, and backfill idempotency.

#### Scenario: Backend writer tests
- **WHEN** backend helper tests run
- **THEN** they SHALL verify manual, queue, playbook, approval, notification, tracking-only, skipped, blocked, failed, and observed-only outcome writing.

#### Scenario: API contract tests
- **WHEN** route tests run
- **THEN** they SHALL verify canonical outcome payloads for alerts, queue, playbooks, approvals, notifications, incidents, metrics, source-IP context, and blocklist where applicable.

#### Scenario: Frontend tests
- **WHEN** frontend tests run
- **THEN** they SHALL verify shared badges/components and each affected screen distinguish observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.

#### Scenario: End-to-end traceability tests
- **WHEN** integration tests simulate an alert through decision, queue, playbook, approval, adapter, log, and dashboard payloads
- **THEN** the test SHALL prove the primary question can be answered from canonical data.
