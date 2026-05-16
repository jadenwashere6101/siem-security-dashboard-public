# Design: SOAR Dead Letter Queue

## Overview

Add a durable SOAR dead letter queue for failed playbook/action work. The queue is an operator-facing reliability record, not an execution engine. It stores enough context to review a failure, decide whether it is safe to retry, dismiss known failures, and measure backlog depth.

The design builds on existing systems:

- playbook executions and lease ownership
- approval request flow
- response action queue/log tables
- notification delivery tracking
- audit logging
- RBAC/session identity
- migration-managed schema history

No autonomous retry loop is introduced. Retry is manual and routed through existing safe execution paths.

---

## 1. Data Model

Create a migration-managed table, tentatively named `soar_dead_letters`.

Suggested columns:

- `id SERIAL PRIMARY KEY`
- `source_type VARCHAR(64) NOT NULL`
  - examples: `playbook_execution`, `playbook_step`, `response_action`, `notification_delivery`
- `source_id INTEGER`
- `playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL`
- `playbook_id VARCHAR(100)`
- `playbook_step_index INTEGER`
- `response_action_queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL`
- `notification_delivery_attempt_id INTEGER REFERENCES notification_delivery_attempts(id) ON DELETE SET NULL`
- `approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL`
- `alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL`
- `incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL`
- `status VARCHAR(32) NOT NULL`
  - proposed values: `open`, `retry_requested`, `retry_scheduled`, `retried`, `dismissed`, `resolved`
- `failure_class VARCHAR(64)`
  - examples: `transient`, `permanent`, `approval_denied`, `approval_expired`, `lease_exhausted`, `adapter_failed`, `timeout`, `circuit_open`, `unknown`
- `failure_code VARCHAR(128)`
- `failure_message TEXT`
- `retryable BOOLEAN NOT NULL DEFAULT false`
- `retry_count INTEGER NOT NULL DEFAULT 0`
- `last_retry_at TIMESTAMPTZ`
- `dismissed_at TIMESTAMPTZ`
- `dismissed_by INTEGER REFERENCES users(id) ON DELETE SET NULL`
- `dismiss_reason TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Recommended indexes:

- `(status, created_at DESC)`
- `(source_type, source_id)`
- `(playbook_execution_id)`
- `(response_action_queue_id)`
- `(notification_delivery_attempt_id)`
- `(alert_id)`
- `(incident_id)`
- partial unique index for active source identity:
  - `(source_type, source_id)` where `status IN ('open', 'retry_requested', 'retry_scheduled')` and `source_id IS NOT NULL`

The table should not store secrets, raw webhook URLs, raw provider responses, or credentials.

---

## 2. Source Capture

Initial dead letter creation should be explicit and narrow.

Candidates:

- Failed playbook execution after terminal failure.
- Failed playbook step where the step outcome is not retry-safe through normal execution state alone.
- Response action queue item that reaches terminal `failed`.
- Notification delivery attempt with terminal `failed`, `timeout`, or `blocked` when it is operator-actionable.

Implementation should start with one source family per slice to keep semantics testable. The store helper should accept structured source information and produce a normalized dead letter record.

Duplicate prevention:

- A helper should create or return the existing active dead letter for the same source.
- Retried/resolved/dismissed records should not block future dead letters for a later distinct failure.
- Do not create duplicate dead letters on repeated route reads, metrics reads, or retry inspection.

---

## 3. Store Helpers

Add a `core/soar_dead_letter_store.py` module or equivalent local pattern.

Suggested helpers:

- `create_dead_letter_once(conn, *, source_type, source_id, ... )`
- `get_dead_letter(conn, dead_letter_id)`
- `list_dead_letters(conn, *, status=None, source_type=None, retryable=None, limit=..., offset=...)`
- `mark_dead_letter_retry_requested(conn, dead_letter_id, actor_user_id, now=None)`
- `mark_dead_letter_retried(conn, dead_letter_id, retry_result, now=None)`
- `dismiss_dead_letter(conn, dead_letter_id, actor_user_id, reason, now=None)`
- `get_dead_letter_metrics(conn, *, now=None)`

All helpers should:

- Leave commit/rollback to callers.
- Validate enums and required text.
- Sanitize metadata before persistence.
- Never invoke adapters, send notifications, or execute playbooks.
- Be safe to rerun where appropriate.

---

## 4. Routes

Add authenticated routes for operator review.

Suggested endpoints:

- `GET /soar/dead-letters`
  - list with filters: `status`, `source_type`, `retryable`, `limit`, `offset`
- `GET /soar/dead-letters/<id>`
  - detail view
- `POST /soar/dead-letters/<id>/retry`
  - request or perform a safe retry according to source type
- `POST /soar/dead-letters/<id>/dismiss`
  - dismiss with required reason
- `GET /metrics/soar/dead-letters`
  - open count, retryable count, oldest age, counts by source/failure class

Authorization should follow existing SOAR mutation rules:

- Read access can match analyst/operator read permissions if existing RBAC supports it.
- Retry and dismiss should require super admin/operator-level mutation permissions.
- All mutations should be audited.

Routes must not expose secrets from metadata or raw failure payloads.

---

## 5. Retry Semantics

Retry is manual only.

Safe retry policy:

- If the source is a failed playbook execution, create a new pending execution only through the existing retry path, preserving current retry rules.
- If the failed execution is awaiting or dependent on approval, do not bypass approval; require the existing approval resume path or create a new execution that will encounter approval normally.
- If the source is a response action, retry through the response action queue semantics rather than direct adapter calls.
- If the source is notification delivery, retry should initially be conservative:
  - either create a new playbook execution through normal flow, or
  - mark retry requested for operator/manual handling until notification idempotency constraints are explicit enough.
- If idempotency cannot be proven, the route should return a conflict and leave the dead letter open.

Retry should update dead letter state and counts only after the retry request is safely created. It must not dispatch real adapters directly.

---

## 6. Approval Awareness

Dead letter retry must preserve approval semantics:

- Never transition `awaiting_approval` directly to execution from a dead letter route.
- Never mark approval denied/expired failures as retryable unless the policy explicitly creates a new execution requiring approval again.
- Link dead letters to approval requests when failures are caused by approval denial/expiration.
- Show approval context in detail responses without mutating approval records.

---

## 7. Metrics

Add dead letter metrics that are read-only and mutation-free:

- total open dead letters
- retryable open dead letters
- dismissed/resolved counts in a recent window if useful
- oldest open age
- counts by `source_type`
- counts by `failure_class`

Metrics should not expose metadata values, secrets, or failure payload details.

---

## 8. Operational Safety

The first implementation should be additive:

- migration only for schema changes
- no `schema.sql` edits except reference snapshot update if the migration workflow requires it
- no VM actions until separately requested
- no autonomous workers
- no direct adapter invocation from routes
- no notification sending from dead letter creation, list, detail, metrics, retry validation, or dismissal

Dead letter routes should be safe to call repeatedly and should not mutate unless they are explicit mutation endpoints.

---

## 9. Testing Strategy

Unit and route tests should cover:

- creation idempotency for duplicate source identities
- list/detail filters and response shape
- metadata redaction
- retry allowed path for a known safe source
- retry blocked when approval/idempotency rules are not satisfied
- dismissal with actor/reason
- metrics counts/depth
- no mutation from list/detail/metrics
- no notifications or adapter calls
- ingest/detection/correlation regression suite remains unchanged

---

## 10. Future Work

Later changes may add:

- frontend review panel
- richer operator notes
- escalation policies
- retention/archival policy
- unique idempotency constraints for notification delivery retries
- scheduled reports
- automated retry policies for explicitly safe transient classes

Those are intentionally out of scope for the first implementation.
