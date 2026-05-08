# Proposal: Approval Foundation

## Problem

The SOAR foundation now has durable async response actions, a worker runner, adapter
abstraction, dry-run firewall planning, incident management, incident APIs/UI, and
post-commit incident orchestration. That is enough structure to start thinking about
automation, but it is not yet safe to move directly into real remediation or autonomous
playbooks.

High-risk actions need a durable human approval layer before the system is allowed to
execute real firewall changes, external notifications, or branching playbooks. Without an
approval foundation, future phases would either have to block execution in ad hoc ways or
retrofit approval state into queue/playbook code after the fact.

## This change

Add OpenSpec coverage for the first backend-only approval foundation slice. This slice defines
the schema and helper/store contracts for approval requests, decision state, expiration, and
audit logging. It is intentionally additive and does not wire approvals into execution yet.

## In scope

- `approval_requests` schema design.
- Optional immutable approval event/audit table design.
- Approval lifecycle states: `pending`, `approved`, `denied`, `expired`.
- Approval request linkage to `incident_id` and/or `response_actions_queue.id`.
- Approval decision fields:
  - `approved_by` references `users(id)`.
  - `decided_by` references `users(id)` for denied/expired decisions as well.
  - `created_at`, `decided_at`, `expires_at`.
  - decision `reason`/comment field.
- Approval helper/store contract.
- Explicit timeout and expiration semantics.
- Audit logging behavior.
- PostgreSQL indexes and constraints.
- Unit and DB-backed testing strategy.

## Out of scope

- No frontend/UI.
- No worker pause/resume implementation.
- No Slack/email notifications.
- No playbook engine.
- No firewall integrations.
- No execution gating wiring.
- No background scheduler.
- No approval API route implementation in this first slice.
- No ingest, detection, or correlation changes.
- No SOAR queue execution behavior changes.

## Success criteria

- The schema is safe and additive.
- Approval requests can represent a pending approval tied to an incident, a queue item, or both.
- Terminal states are explicit: `approved`, `denied`, and `expired`.
- Pending approvals can be expired deterministically by a helper called from tests or future
  routes/workers; no background scheduler is required in this slice.
- Approval decisions preserve an immutable audit trail via append-only audit/event records.
- Store helpers do not commit or close cursors; callers own transaction boundaries.
- Existing SOAR queue execution, ingest transactions, detection, and correlation behavior remain
  unchanged.
