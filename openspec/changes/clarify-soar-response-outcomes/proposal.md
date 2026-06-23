## Why

The SIEM/SOAR can detect alerts, enqueue responses, run playbooks, request approvals, record simulated outcomes, track internal blocklist state, and execute some real-capable provider actions. Those lifecycle records do not share one analyst-facing language. Operators need every SOAR view to clearly answer: "What happened, what response was selected, what playbook ran, and was anything actually executed?"

## What Changes

- Define a canonical response outcome model for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.
- Replace ambiguous `executed` semantics with explicit `external_executed`, `tracking_recorded`, and `simulated` booleans while preserving `execution_mode`.
- Split decision facts from execution facts with `decision_source` and `execution_actor`.
- Define a hybrid data model with `soar_response_decisions` for selected responses and append-only `soar_response_outcome_events` for lifecycle evidence.
- Rename lifecycle correlation to `soar_correlation_id` and define propagation across alerts, queue rows, playbooks, approvals, adapter deliveries, response logs, incidents, source-IP context, and dashboard views.
- Specify minimal additive linkage fields on existing tables: `soar_correlation_id`, `decision_id`, and `latest_outcome_event_id` where useful.
- Specify latest-outcome API/read-model behavior so UI screens can display the current state without duplicating outcome fields into every legacy table.
- Define migration/backfill dry-run, compatibility verification, retention/archive, idempotency, rollout, rollback, and multi-session task phases.

## Capabilities

### New Capabilities
- `soar-response-outcomes`: Canonical response decision and execution outcome semantics across SIEM/SOAR storage, APIs, and UI.

### Modified Capabilities
- None.

## Impact

- Backend data model: new canonical decision/event tables plus minimal linkage on `alerts`, `response_actions_queue`, `response_actions_log`, `playbook_executions`, `approval_requests`, `approval_request_events`, `notification_delivery_attempts`, `incidents`, `audit_log`, and related stores where useful.
- Backend APIs: alerts, queue, playbooks, approvals, incidents, notification delivery, metrics, source-IP context, SOC Command Center data, blocklist views, and map context payloads.
- Frontend: Alert Details, SOAR Queue, Approval Requests, Playbooks Panel, SOC Command Center, Source-IP Context, Attack Map popup, Blocklist Manager, metrics, and shared badges/components.
- Tests: schema migration/backfill, backend helpers, API contracts, frontend rendering, read-model/latest-outcome behavior, and end-to-end outcome traceability.
