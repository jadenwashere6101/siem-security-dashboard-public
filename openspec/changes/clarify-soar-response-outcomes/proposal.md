## Why

The SIEM/SOAR can detect alerts, enqueue responses, run playbooks, request approvals, and record simulated, tracking-only, or real-capable outcomes, but those lifecycle records do not share one analyst-facing language. Operators need every SOAR view to clearly answer: "What happened, what response was selected, what playbook ran, and was anything actually executed?"

## What Changes

- Define a canonical response outcome model for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.
- Define consistent `execution_mode`, `execution_state`, `executed`, `decision_source`, `outcome_summary`, and `correlation_id` semantics across alerts, queue actions, playbooks, approvals, notification deliveries, response logs, incidents, source-IP context, and dashboard views.
- Specify additive schema changes and compatibility behavior so existing records remain readable.
- Specify backend helpers/API contracts that normalize outcome language without deleting simulation mode or overstating real execution.
- Specify dashboard/UI updates so analysts see selected action, decision source, execution mode/state, executed truth, summary, and related IDs wherever SOAR outcomes are displayed.
- Define migration/backfill, rollout, rollback, and multi-session task phases.

## Capabilities

### New Capabilities
- `soar-response-outcomes`: Canonical response decision and execution outcome semantics across SIEM/SOAR storage, APIs, and UI.

### Modified Capabilities
- None.

## Impact

- Backend data model: `alerts`, `response_actions_queue`, `response_actions_log`, `playbook_executions`, `approval_requests`, `approval_request_events`, `notification_delivery_attempts`, `incidents`, and related stores.
- Backend APIs: alerts, queue, playbooks, approvals, incidents, notification delivery, metrics, source-IP context, SOC Command Center data, blocklist views, and map context payloads.
- Frontend: Alert Details, SOAR Queue, Approval Requests, Playbooks Panel, SOC Command Center, Source-IP Context, Attack Map popup, Blocklist Manager, metrics, and shared badges/components.
- Tests: schema migration/backfill, backend helpers, API contracts, frontend rendering, and end-to-end outcome traceability.
