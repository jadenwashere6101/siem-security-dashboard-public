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

Phase 2.5B extends this same approval foundation with backend approval API route coverage only.
The route slice exposes approval visibility and manual approve/deny decisions through existing
auth and role patterns, backed by `core/approval_store.py`. It still does not wire approvals into
workers, queues, ingest, detection, correlation, playbooks, or frontend UI.

Phase 2.5C adds frontend approval visibility and decision UI on top of the existing approval
routes. It gives analysts read-only approval visibility and gives super admins a controlled
approve/deny interface for pending approvals. It still does not add worker gating, queue
mutation controls, SOAR action execution controls, playbook integration, or backend/schema
changes unless implementation proves they are absolutely required.

Phase 2.5D defines approval-gated SOAR queue execution. It specifies how high-risk queued
actions can pause before execution, create or reuse approval requests, resume after approval,
and skip safely after denial or expiration. This phase is still simulation-first and does not add
real firewall execution, playbooks, Slack/email notifications, autonomous daemons, or changes to
ingest/detection/correlation.

## In scope

### Phase 2.5A: Schema and store foundation

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

### Phase 2.5B: Approval API routes

- `GET /approvals` for approval request listing.
- `GET /approvals/<id>` for approval request detail and immutable event history.
- `POST /approvals/<id>/decision` for manual approval decisions.
- Decision body:
  - `{ "decision": "approved" | "denied", "reason": "..." }`
- Existing authentication and role decorators.
- Analyst and super admin approval visibility.
- Super admin-only approval/denial for high-risk approvals unless the existing role model is
  explicitly expanded before implementation.
- Route-level transaction handling around store helper calls.
- Route tests for auth, RBAC, list/detail access, approve/deny decisions, invalid decisions,
  missing approvals, invalid transitions, and event creation.

### Phase 2.5C: Approval visibility and decision UI

- `frontend/src/services/approvalService.js`.
- `frontend/src/components/ApprovalsPanel.js`.
- Navigation tab for `analyst` and `super_admin` users.
- Approval list with status/risk/target filters as supported by the approval API.
- Approval detail view showing immutable event history.
- Super admin-only approve/deny controls for pending approvals.
- Analyst read-only approval visibility.
- Optional approve/deny reason handling.
- Loading, error, and empty states.
- Service tests.
- Component tests if the current frontend test setup supports them.
- Frontend build verification.

### Phase 2.5D: Approval-gated SOAR queue execution

- Worker approval-gating design for selected high-risk queue actions.
- V1 approval-required action policy, starting with `block_ip`.
- Safe queue waiting state design for actions blocked on approval.
- Duplicate approval prevention for the same queue action.
- Worker resume behavior after approval.
- Denial and expiration behavior.
- SimulationExecutor remains default.
- Queue/store/worker tests for approval gating behavior.

## Out of scope

- No frontend/UI.
- No worker pause/resume implementation.
- No Slack/email notifications.
- No playbook engine.
- No firewall integrations.
- No execution gating wiring.
- No background scheduler.
- No approval API route implementation in Phase 2.5A.
- No frontend work in Phase 2.5B.
- No worker pause/resume in Phase 2.5B.
- No queue execution behavior changes in Phase 2.5B.
- No schema changes in Phase 2.5B unless implementation proves they are absolutely required.
- No worker pause/resume in Phase 2.5C.
- No queue execution changes in Phase 2.5C.
- No playbook integration in Phase 2.5C.
- No Slack/email notification UI in Phase 2.5C.
- No real firewall execution UI in Phase 2.5C.
- No backend/schema changes in Phase 2.5C unless absolutely required.
- No real firewall execution in Phase 2.5D.
- No playbook engine in Phase 2.5D.
- No Slack/email notification in Phase 2.5D.
- No frontend changes in Phase 2.5D unless handled by a separate follow-up.
- No autonomous daemon changes in Phase 2.5D.
- No ingest, detection, or correlation changes.
- No ingest, detection, or correlation changes for approval gating.

## Success criteria

- The schema is safe and additive.
- Approval requests can represent a pending approval tied to an incident, a queue item, or both.
- Terminal states are explicit: `approved`, `denied`, and `expired`.
- Pending approvals can be expired deterministically by a helper called from tests or future
  routes/workers; no background scheduler is required in this slice.
- Approval decisions preserve an immutable audit trail via append-only audit/event records.
- Store helpers do not commit or close cursors; callers own transaction boundaries.
- Approval API routes expose list/detail/decision behavior without mutating alerts or queue
  execution.
- Invalid decisions and invalid lifecycle transitions return client errors without partial
  commits.
- Approval UI can list and inspect approvals through approval routes only.
- Approval UI exposes decision controls only for `super_admin` users and pending approvals.
- Analyst users can view approvals but cannot approve or deny them from the UI.
- Approval-gated worker behavior does not execute high-risk actions until an approved approval
  request exists for the queue item.
- Denied or expired approvals result in safe non-execution outcomes.
- Existing SOAR queue execution, ingest transactions, detection, and correlation behavior remain
  unchanged outside the explicit Phase 2.5D queue gating path.
