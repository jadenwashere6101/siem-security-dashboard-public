## ADDED Requirements

### Requirement: Canonical Response Outcome Model
The system SHALL define one canonical response outcome model for SOAR decisions and execution results across alerts, manual actions, queue actions, playbook steps, approvals, notification deliveries, response logs, incidents, audit log, source-IP context, SOC Command Center, Attack Map context, and blocklist views.

#### Scenario: Observed-only alert
- **WHEN** an alert exists and no response action has been selected, queued, simulated, tracked, or really executed
- **THEN** the canonical outcome SHALL use `execution_mode=observed`, `execution_state=observed`, `external_executed=false`, `tracking_recorded=false`, `simulated=false`, and an outcome summary that says detection occurred but no response was selected.

#### Scenario: Simulated response
- **WHEN** a queue action, playbook step, or adapter result completes in simulation mode
- **THEN** the canonical outcome SHALL use `execution_mode=simulation`, SHALL use an appropriate terminal or active `execution_state`, SHALL set `simulated=true`, SHALL set `external_executed=false`, SHALL set `tracking_recorded=false`, and SHALL NOT imply provider delivery, firewall enforcement, or local enforcement occurred.

#### Scenario: Tracking-only response
- **WHEN** the SIEM records internal state only, such as a blocklist tracking record without firewall enforcement
- **THEN** the canonical outcome SHALL use `execution_mode=tracking_only`, SHALL set `tracking_recorded=true` only after the internal tracking state is durably recorded, SHALL set `external_executed=false`, SHALL set `simulated=false`, and SHALL include an outcome summary that states no external or local enforcement occurred.

#### Scenario: Real external execution
- **WHEN** an external provider action or actual local enforcement action happens and returns explicit success evidence
- **THEN** the canonical outcome SHALL use `execution_mode=real`, `execution_state=succeeded`, `external_executed=true`, `tracking_recorded=false`, `simulated=false`, and SHALL include the provider or enforcement surface in safe metadata.

#### Scenario: Failed response
- **WHEN** a selected response fails before or during simulation, tracking-only recording, or real execution
- **THEN** the canonical outcome SHALL use `execution_state=failed`, SHALL preserve the effective `execution_mode`, SHALL set execution booleans according to known side effects only, and SHALL include a sanitized reason.

#### Scenario: Blocked by approval
- **WHEN** an approval denial or approval expiration prevents a selected response from continuing
- **THEN** the canonical outcome SHALL use `execution_state=blocked`, SHALL set `external_executed=false`, SHALL set `tracking_recorded=false`, SHALL set `simulated=false`, and SHALL link the relevant approval request where available.

#### Scenario: Awaiting approval
- **WHEN** a selected response is paused pending human approval
- **THEN** the canonical outcome SHALL use `execution_state=awaiting_approval`, SHALL set all execution booleans false, and SHALL identify the approval request, playbook step, or queue row that is awaiting approval.

#### Scenario: Skipped response
- **WHEN** a response is skipped because of validation, protected target policy, duplicate prevention, unsupported action, terminal status, abandonment, or operator choice
- **THEN** the canonical outcome SHALL use `execution_state=skipped`, SHALL set all execution booleans false, and SHALL include a reason code and analyst-readable summary.

### Requirement: Execution Mode Semantics
The system SHALL use exactly four canonical execution modes: `observed`, `simulation`, `tracking_only`, and `real`.

#### Scenario: Observed mode
- **WHEN** the mode is `observed`
- **THEN** the system SHALL treat the record as detection or visibility only, with no response selected or executed.

#### Scenario: Simulation mode
- **WHEN** the mode is `simulation`
- **THEN** the system SHALL treat the record as a non-real response path and SHALL require `simulated=true`, `external_executed=false`, and `tracking_recorded=false`.

#### Scenario: Tracking-only mode
- **WHEN** the mode is `tracking_only`
- **THEN** the system SHALL treat the record as an internal SIEM state change and SHALL NOT describe it as firewall, provider, external, or local enforcement.

#### Scenario: Real mode
- **WHEN** the mode is `real`
- **THEN** the system SHALL require evidence that an external provider action or actual local enforcement action occurred before setting `external_executed=true`.

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

### Requirement: Execution Boolean Semantics
The system SHALL define `external_executed`, `tracking_recorded`, and `simulated` as separate booleans and SHALL NOT use an ambiguous canonical `executed` boolean as the source of truth.

#### Scenario: Simulated result
- **WHEN** a response outcome has `execution_mode=simulation`
- **THEN** the system SHALL set `simulated=true`, `external_executed=false`, and `tracking_recorded=false` even when the simulation completed successfully.

#### Scenario: Observed result
- **WHEN** a response outcome has `execution_mode=observed`
- **THEN** the system SHALL set `external_executed=false`, `tracking_recorded=false`, and `simulated=false`.

#### Scenario: Tracking-only success
- **WHEN** a tracking-only internal SIEM state change is durably recorded
- **THEN** the system SHALL set `tracking_recorded=true`, SHALL set `external_executed=false`, SHALL set `simulated=false`, and SHALL label the mode as `tracking_only` in every API/UI surface.

#### Scenario: Real success
- **WHEN** a real external provider action or actual local enforcement action is confirmed successful
- **THEN** the system SHALL set `external_executed=true`, SHALL set `tracking_recorded=false`, SHALL set `simulated=false`, and SHALL label the mode as `real`.

#### Scenario: Ambiguous or failed real attempt
- **WHEN** a real-capable adapter times out, is blocked, fails closed, or cannot confirm success
- **THEN** the system SHALL set `external_executed=false` unless positive evidence proves the action occurred.

### Requirement: Decision and Execution Semantics
The system SHALL record response decision facts separately from execution outcome facts.

#### Scenario: Allowed decision sources
- **WHEN** a response decision is recorded
- **THEN** `decision_source` SHALL be one of `detection_default`, `correlation`, `playbook`, `manual`, or `migration`.

#### Scenario: Allowed execution actors
- **WHEN** an outcome event is recorded
- **THEN** `execution_actor` SHALL be one of `queue_worker`, `playbook_worker`, `adapter`, `approval_service`, `manual`, or `system`.

#### Scenario: Detection default decision
- **WHEN** detection or correlation selects a default response action for an alert
- **THEN** the system SHALL record the selected action, `decision_source=detection_default` or `decision_source=correlation`, the alert id, source IP, selected timestamp, and decision summary.

#### Scenario: Manual decision
- **WHEN** an analyst or super admin manually selects a response action
- **THEN** the system SHALL record `decision_source=manual`, the actor user id, selected action, alert id, source IP, and a separate SOAR correlation id or child decision.

#### Scenario: Playbook decision
- **WHEN** a playbook step selects or represents a response action
- **THEN** the system SHALL record `decision_source=playbook`, the playbook id, playbook execution id, step index, selected action, and related alert or incident ids where available.

#### Scenario: Approval outcome
- **WHEN** an approval is requested, approved, denied, or expired
- **THEN** the system SHALL record an outcome event linked to the approval request using `execution_actor=approval_service` and SHALL represent denied or expired approval as blocked response work, not as successful execution.

#### Scenario: Adapter result
- **WHEN** an adapter returns a result for a notification or response step
- **THEN** the system SHALL record an outcome event using `execution_actor=adapter`, adapter/provider identity, effective execution mode, execution state, execution booleans, and safe metadata.

### Requirement: SOAR Correlation ID Strategy
The system SHALL use a safe `soar_correlation_id` to link related records across alert, queue, playbook, approval, adapter, response log, incident, audit log, source-IP context, and UI views.

#### Scenario: New alert response lifecycle
- **WHEN** a response is first selected for an alert
- **THEN** the system SHALL create or assign one safe SOAR correlation id and propagate it to subsequent queue, playbook, approval, delivery, log, audit, and outcome records.

#### Scenario: Child lifecycle event
- **WHEN** a playbook step, adapter delivery, approval decision, or manual follow-up represents a child event under an existing lifecycle
- **THEN** the system SHALL preserve the parent SOAR correlation id or explicitly record a child decision linked to the parent.

#### Scenario: Legacy backfill
- **WHEN** historical records do not have a SOAR correlation id
- **THEN** the backfill SHALL assign deterministic legacy SOAR correlation ids that do not contain secrets and that are stable across repeated migration validation.

#### Scenario: SOAR correlation id safety
- **WHEN** a SOAR correlation id is stored, returned, logged, or shown in the UI
- **THEN** it SHALL NOT contain webhooks, tokens, passwords, provider payloads, raw source payloads, or unsafe user input.

### Requirement: Database Schema Changes
The system SHALL add an additive canonical decision and outcome-event data model while preserving existing tables and records.

#### Scenario: Decision table
- **WHEN** schema migration for this change is applied
- **THEN** it SHALL create an additive `soar_response_decisions` table with fields for SOAR correlation id, parent SOAR correlation id, related entity ids, source IP, selected action, decision source, actor user, decision summary, reason code, safe JSON metadata, and timestamps.

#### Scenario: Outcome event table
- **WHEN** schema migration for this change is applied
- **THEN** it SHALL create an additive append-only `soar_response_outcome_events` table with fields for decision id, SOAR correlation id, event type, related entity ids, source IP, execution mode, execution state, execution booleans, execution actor, outcome summary, reason code, provider/adapter metadata, idempotency key, safe JSON metadata, and timestamps.

#### Scenario: Existing table linkage
- **WHEN** schema migration for this change is applied
- **THEN** it SHOULD add nullable linkage fields such as `soar_correlation_id`, `decision_id`, and `latest_outcome_event_id` to existing SOAR tables where they improve traceability without breaking old records.

#### Scenario: Avoid duplicated legacy truth
- **WHEN** existing tables are extended
- **THEN** they SHALL NOT duplicate every canonical outcome field unless the duplicated fields are explicitly documented as snapshot-only and canonical decision/event records remain authoritative.

#### Scenario: Schema constraints
- **WHEN** the outcome schema stores canonical enums and booleans
- **THEN** it SHALL constrain execution modes, execution states, decision sources, execution actors, reason codes, and execution boolean compatibility to approved values.

#### Scenario: Required indexes
- **WHEN** the canonical schema is added
- **THEN** it SHALL include indexes or query paths for `alert_id`, `incident_id`, `source_ip`, `soar_correlation_id`, `decision_id`, and `created_at`.

#### Scenario: Additional query support
- **WHEN** the canonical schema is added
- **THEN** it SHOULD include indexes or query paths for queue id, playbook execution/step, approval request, notification delivery, execution mode/state, idempotency key, and recent outcomes.

#### Scenario: Secret-free metadata
- **WHEN** the outcome schema stores JSON metadata
- **THEN** metadata SHALL be safe and sanitized and SHALL NOT store secrets, webhooks, raw provider payloads, raw headers, raw responses, raw passwords, or raw unsafe exception strings.

### Requirement: Latest Outcome Read Model
The system SHALL provide a derived latest-outcome read model or API query for canonical outcome display.

#### Scenario: Latest outcome by decision
- **WHEN** an API needs current response status for a decision
- **THEN** it SHALL derive the latest outcome from append-only outcome events by decision id and deterministic event ordering.

#### Scenario: Latest outcome by context
- **WHEN** an API needs current response status for an alert, incident, source IP, queue row, playbook execution, approval request, notification delivery, or SOAR correlation id
- **THEN** it SHALL use canonical decisions/events and compatibility inference to return the latest relevant outcome.

#### Scenario: Derived cache
- **WHEN** a materialized view or cache is used for latest outcomes
- **THEN** it SHALL be treated as derived data and SHALL NOT replace append-only outcome events as the canonical trail.

### Requirement: Backend Outcome Writer
The system SHALL centralize canonical decision creation, outcome event creation, validation, serialization, idempotency, latest-outcome reads, and compatibility inference in backend helper modules.

#### Scenario: Writer validates decisions
- **WHEN** backend code writes a canonical decision
- **THEN** the writer SHALL validate decision source, selected action, SOAR correlation id safety, actor metadata, and metadata safety before persistence.

#### Scenario: Writer validates outcome events
- **WHEN** backend code writes a canonical outcome event
- **THEN** the writer SHALL validate execution mode, execution state, execution actor, execution boolean compatibility, reason code, SOAR correlation id safety, idempotency key, and metadata safety before persistence.

#### Scenario: Writer preserves old behavior
- **WHEN** existing detection, queue, playbook, approval, notification, audit, or manual action flows write canonical decisions/events
- **THEN** they SHALL preserve existing side effects and SHALL NOT change detection thresholds, approval policy, SOAR queue semantics, or playbook matching semantics.

#### Scenario: Compatibility resolver
- **WHEN** an API reads an older record without canonical decision/event rows
- **THEN** the backend SHALL return a conservative inferred canonical latest outcome with `decision_source=migration` or equivalent compatibility metadata.

### Requirement: Queue And Manual Runtime Outcome Wiring
The system SHALL dual-write canonical response decisions and outcome events for live queue, response-log, and manual alert execution paths without changing existing queue, manual action, or response log side effects.

#### Scenario: Idempotent queue enqueue
- **WHEN** post-commit alert enqueue attempts to create a `response_actions_queue` row and the queue insert is suppressed by existing idempotency behavior
- **THEN** the system SHALL NOT create duplicate canonical decisions or queued events for the same queue lifecycle.

#### Scenario: Durable queue row created
- **WHEN** post-commit alert enqueue creates a durable `response_actions_queue` row
- **THEN** the system SHALL create or link one canonical decision, store `decision_id` and `soar_correlation_id` on the queue row where schema allows, and append a `queued` outcome event with a deterministic idempotency key.

#### Scenario: Duplicate enqueue represented canonically
- **WHEN** duplicate enqueue suppression is recorded as a canonical outcome
- **THEN** the system SHALL use `execution_state=skipped`, `reason_code=duplicate_suppressed`, all execution booleans false, and a deterministic idempotency key.

#### Scenario: Queue helper linkage
- **WHEN** backend queue helper functions return queue rows for get, list, claim, transition, requeue, or stale-recovery paths
- **THEN** returned queue row payloads SHALL include `decision_id` and `soar_correlation_id` where the columns exist so callers can write correctly linked canonical events.

#### Scenario: Worker early-claim commit
- **WHEN** a queue worker claims pending or approved awaiting-approval work and changes the queue row to `running`
- **THEN** the system SHALL append the `running` outcome event in the same transaction as the claim before the existing early-claim commit is preserved.

#### Scenario: Worker re-entry after claim
- **WHEN** a worker restarts or re-enters after a claim has already written a `running` event
- **THEN** deterministic idempotency keys SHALL prevent duplicate running events from creating misleading lifecycle evidence.

#### Scenario: Retryable queue failure
- **WHEN** a queue action fails with a retryable worker error and is returned to `pending`
- **THEN** the system SHALL append a failed-attempt outcome event, then append a queued or requeued event, both with deterministic idempotency keys and sanitized summaries.

#### Scenario: Exhausted or non-retryable queue failure
- **WHEN** a queue action reaches terminal `failed` status because retries are exhausted or the failure is not retryable
- **THEN** the system SHALL append a terminal `failed` outcome event with a sanitized summary and SHALL link the related response log row where one is written.

#### Scenario: Queue approval required
- **WHEN** a queue action is paused for approval
- **THEN** the system SHALL append an `awaiting_approval` outcome event linked to the queue row and approval request where available, with all execution booleans false.

#### Scenario: Queue approval denied or expired
- **WHEN** approval denial or expiration prevents queued response execution
- **THEN** the system SHALL append a `blocked` outcome event with `reason_code=approval_denied`, all execution booleans false, and an outcome summary that distinguishes denied from expired.

#### Scenario: Queue simulation success
- **WHEN** the queue worker completes a simulated action successfully
- **THEN** the system SHALL append `execution_mode=simulation`, `execution_state=succeeded`, `simulated=true`, `external_executed=false`, and `tracking_recorded=false`, and SHALL link the response log row where one is written.

#### Scenario: Queue skipped outcome
- **WHEN** the queue worker skips work because of protected target policy, validation, unsupported action, duplicate prevention, or operator policy
- **THEN** the system SHALL append a `skipped` outcome event with a canonical reason code, all execution booleans false, and a sanitized analyst-readable summary.

#### Scenario: Response log linkage
- **WHEN** runtime code writes a terminal `response_actions_log` row for a queue or manual action
- **THEN** the log writer SHALL accept `decision_id` and `soar_correlation_id`, write those nullable linkage fields where schema allows, and return the inserted log id so outcome events can reference `response_action_log_id`.

#### Scenario: Manual simulated action
- **WHEN** an analyst manually records monitor or escalation behavior through `/alerts/<id>/execute`
- **THEN** the system SHALL create a manual decision and append a simulation outcome event unless positive evidence proves tracking-only or real execution.

#### Scenario: Manual tracking-only blocklist
- **WHEN** an analyst manually selects `block_ip` and the system records only internal SIEM blocklist state
- **THEN** the canonical outcome SHALL use `execution_mode=tracking_only`, `execution_state=succeeded`, `tracking_recorded=true`, `external_executed=false`, `simulated=false`, and a summary that says no firewall, provider, external, or local enforcement occurred.

#### Scenario: Manual blocklist insertion failure
- **WHEN** manual `block_ip` tracking fails validation, duplicates an active block, or otherwise does not durably insert internal blocklist state
- **THEN** the system SHALL NOT write a tracking-only success event.

#### Scenario: Deferred blocked IP direct linkage
- **WHEN** Phase 4 records manual tracking-only blocklist outcomes without a new approved migration
- **THEN** the system SHALL NOT require `blocked_ips.decision_id`, `blocked_ips.soar_correlation_id`, or outcome-event `blocked_ip_id`; it MAY link through `alert_id`, `source_ip`, `decision_id`, `soar_correlation_id`, and `response_action_log_id`.

### Requirement: Backend API Response Contracts
The system SHALL expose canonical response outcome payloads from SOAR-related APIs while preserving existing legacy fields during rollout.

#### Scenario: Required latest outcome fields
- **WHEN** an API returns a canonical latest outcome
- **THEN** the payload SHALL include selected action, decision source, execution actor where available, execution mode, execution state, `external_executed`, `tracking_recorded`, `simulated`, summary/reason, SOAR correlation id, decision id, latest outcome event id, and related playbook/queue/approval ids where applicable.

#### Scenario: Alert detail API
- **WHEN** an authorized user reads an alert detail or alert list item
- **THEN** the API SHALL include canonical response outcome data or an inferred observed-only outcome.

#### Scenario: SOAR Queue API
- **WHEN** an authorized super admin reads SOAR queue status, list, or detail
- **THEN** the API SHALL include canonical execution mode/state, selected action, execution booleans, decision source, execution actor where available, outcome summary, SOAR correlation id, and linked approval/playbook/log ids where available.

#### Scenario: Playbook API
- **WHEN** an authorized user reads playbook executions or a playbook execution detail
- **THEN** the API SHALL include canonical outcome summaries for the execution and for each step where available.

#### Scenario: Approval API
- **WHEN** an authorized user reads approval list or detail
- **THEN** the API SHALL include linked canonical outcomes and SHALL represent denied or expired approvals as blocked, not executed.

#### Scenario: Notification delivery API
- **WHEN** an authorized user reads notification delivery attempts
- **THEN** the API SHALL expose canonical execution mode/state and execution booleans derived from delivery status, mode, and adapter result metadata.

#### Scenario: Incident API
- **WHEN** an authorized user reads incidents or incident timeline
- **THEN** the API SHALL include related canonical outcomes in timeline or detail context without mutating incident state.

#### Scenario: Source-IP context API
- **WHEN** an authorized user reads source-IP context
- **THEN** the API SHALL include recent canonical outcomes for that source IP with selected action, decision source, execution mode/state, execution booleans, summary, and related ids.

#### Scenario: Metrics APIs
- **WHEN** metrics summarize SOAR activity
- **THEN** they SHALL distinguish observed-only, simulation, tracking-only, real, awaiting approval, blocked, skipped, failed, succeeded, external-executed, tracking-recorded, and simulated outcomes.

### Requirement: Dashboard Outcome Presentation
The dashboard SHALL show canonical response outcomes with consistent language and avoid ambiguous standalone "executed" labels.

#### Scenario: Required fields in every outcome display
- **WHEN** an analyst sees a response outcome anywhere in the UI
- **THEN** the UI SHALL show selected action, decision source, execution mode, execution state, whether real external/local enforcement happened, whether internal tracking was recorded, whether the action was simulated, summary/reason, and related playbook/queue/approval ids where applicable.

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

### Requirement: Migration, Backfill, and Idempotency Strategy
The system SHALL provide a conservative migration/backfill strategy for existing records.

#### Scenario: Backfill dry-run before broad UI migration
- **WHEN** implementation reaches compatibility verification
- **THEN** dry-run backfill and compatibility reports SHALL run before broad UI screens are migrated to canonical-only display.

#### Scenario: Backfill observed alerts
- **WHEN** an existing alert has no response action, queue, response log, playbook step, approval, notification delivery, or blocklist evidence
- **THEN** backfill SHALL create or infer an observed-only outcome.

#### Scenario: Backfill simulated logs
- **WHEN** an existing response log or playbook step clearly represents simulation
- **THEN** backfill SHALL create or infer `execution_mode=simulation`, an appropriate state, `simulated=true`, `external_executed=false`, and `tracking_recorded=false`.

#### Scenario: Backfill tracking-only logs
- **WHEN** an existing response log or blocklist entry clearly represents SIEM tracking-only state
- **THEN** backfill SHALL create or infer `execution_mode=tracking_only`, `execution_state=succeeded`, `tracking_recorded=true`, `external_executed=false`, and a summary that says no firewall enforcement occurred.

#### Scenario: Backfill notification deliveries
- **WHEN** existing notification delivery attempts include `mode`, `status`, and metadata
- **THEN** backfill SHALL map those records to canonical outcomes without changing the delivery attempt record.

#### Scenario: Conservative notification real execution inference
- **WHEN** compatibility or backfill logic infers `external_executed=true` for notification delivery history
- **THEN** it SHALL require `mode=real`, `status=success`, metadata `executed=true`, metadata `simulated=false`, and provider success evidence.

#### Scenario: Conservative unknowns
- **WHEN** existing records are ambiguous
- **THEN** backfill SHALL avoid marking them real-executed and SHALL include an inferred/legacy reason code.

#### Scenario: Re-runnable verification
- **WHEN** backfill validation is run repeatedly
- **THEN** it SHALL produce stable counts and SHALL NOT create duplicate canonical decisions or outcome events.

### Requirement: Reason Code Taxonomy
The system SHALL use a canonical reason-code taxonomy for blocked, skipped, failed, inferred, and explanatory outcomes.

#### Scenario: Supported reason codes
- **WHEN** a canonical reason code is stored or returned
- **THEN** it SHALL be one of `approval_required`, `approval_denied`, `simulation_mode`, `tracking_only`, `adapter_unavailable`, `provider_error`, `policy_blocked`, `duplicate_suppressed`, or `unsupported_action`.

#### Scenario: Reason code summary
- **WHEN** a reason code is present
- **THEN** the outcome summary SHALL provide analyst-readable context without exposing secrets or unsafe raw errors.

### Requirement: Retention and Archive Strategy
The system SHALL define retention and archive behavior for canonical decision and outcome-event records.

#### Scenario: Retain canonical records during rollout
- **WHEN** canonical decisions or outcome events are created
- **THEN** rollback SHALL NOT delete them by default.

#### Scenario: Archive old events
- **WHEN** outcome events age out of the active query window under an approved retention policy
- **THEN** archive behavior SHALL preserve enough decision, latest outcome, SOAR correlation, selected action, and related-id data to answer the primary analyst question.

#### Scenario: Metrics retention clarity
- **WHEN** metrics are computed from canonical outcomes
- **THEN** the system SHALL either include archived summaries or clearly document the live retention window used by those metrics.

### Requirement: Rollout Plan
The system SHALL support phased rollout without breaking current SOAR behavior.

#### Scenario: Schema-only rollout
- **WHEN** the first implementation phase deploys additive schema
- **THEN** existing APIs and UI SHALL continue functioning without requiring canonical outcomes.

#### Scenario: Compatibility before broad UI migration
- **WHEN** broad frontend screens are migrated to canonical outcome components
- **THEN** latest-outcome read helpers and compatibility inference SHALL already be available.

#### Scenario: Dual-write rollout
- **WHEN** backend writers begin writing canonical decisions/events
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
- **THEN** the system SHALL be able to stop writing decision/event rows while preserving legacy alert, queue, playbook, approval, notification, response log, and blocklist behavior.

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
- **THEN** they SHALL verify enum constraints, execution boolean rules, SOAR correlation id propagation, linkage fields, safe metadata redaction, idempotency, and backfill compatibility.

#### Scenario: Backend writer tests
- **WHEN** backend helper tests run
- **THEN** they SHALL verify manual, queue, playbook, approval, notification, tracking-only, skipped, blocked, failed, and observed-only decision/outcome-event writing.

#### Scenario: Latest-outcome tests
- **WHEN** read-model tests run
- **THEN** they SHALL verify latest outcome selection by decision id, alert id, incident id, source IP, queue id, playbook execution id, approval request id, notification delivery id, and SOAR correlation id.

#### Scenario: API contract tests
- **WHEN** route tests run
- **THEN** they SHALL verify canonical outcome payloads for alerts, queue, playbooks, approvals, notifications, incidents, metrics, source-IP context, and blocklist where applicable.

#### Scenario: Frontend tests
- **WHEN** frontend tests run
- **THEN** they SHALL verify shared badges/components and each affected screen distinguish observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.

#### Scenario: End-to-end traceability tests
- **WHEN** integration tests simulate an alert through decision, queue, playbook, approval, adapter, log, and dashboard payloads
- **THEN** the test SHALL prove the primary question can be answered from canonical data.
