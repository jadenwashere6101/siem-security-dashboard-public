## Context

The current SIEM implementation executes response actions synchronously as part of the ingest transaction. The ingest → detection → correlation pipeline runs inside a single PostgreSQL transaction, and detection/correlation rely on reading uncommitted writes through the same cursor.

The SOAR upgrade roadmap calls for decoupling response action execution from ingest and building a durable async foundation. This change defines the database and helper contract for that foundation without implementing worker execution or altering the current ingest transaction flow.

## Goals / Non-Goals

**Goals:**
- Define a DB-backed `response_actions_queue` design for future async response execution.
- Preserve the current ingest/detection/correlation transaction behavior.
- Specify queue record status semantics, retry metadata, and idempotency behavior.
- Define an enqueue helper contract that is safe for post-commit use.
- Explain how this foundation will connect to existing `response_actions_log` later.

**Non-Goals:**
- No worker implementation or action execution logic.
- No changes to the ingest pipeline, detection engine, correlation engine, or routes.
- No API or frontend changes.
- No modifications to existing transaction boundaries or current synchronous response behavior.

## Decisions

- **DB-backed queue vs in-memory queue:** A DB-backed queue is chosen because it survives process restarts, keeps a durable record for audit and retries, and can be integrated safely with the existing PostgreSQL-backed system. This foundation avoids adding in-memory state that would need later migration.

- **Table schema design:** Use a dedicated `response_actions_queue` table with status values `pending`, `running`, `success`, `failed`, and `skipped`. Include `retry_count`, `max_retries`, `last_error`, `created_at`, and `updated_at` to support retry and observability.

- **Idempotency key:** Add an `idempotency_key` field to the queue record. This key is used to detect duplicate enqueue attempts and prevent duplicate execution of the same logical action if the worker retries or sees the same action again.

- **enqueue_response_action() helper contract:** Define a helper that creates a queue record and returns a stable identifier. The helper must be designed for post-commit execution in the future and must not require access to the ingest transaction cursor once the commit is complete.

- **Connection to `response_actions_log`:** The queue is a separate record set from `response_actions_log`. The existing log remains the audit trail of what actions were executed, while the queue tracks intended future execution. The design should leave room for each queue record to reference a `response_actions_log` row once execution occurs, but it must not replace or rewrite the log schema in this phase.

## Risks / Trade-offs

- [Altering transaction boundaries] → If the queue is enqueued inside ingest, it could violate the existing transaction guarantee and break detection/correlation. Mitigation: clearly document that enqueueing must happen after `conn.commit()` and leave actual enqueue invocation for a later phase.

- [Two data stores for response actions] → Having both `response_actions_queue` and `response_actions_log` adds cross-table coordination risk. Mitigation: keep the first phase focused on queue foundation only and define the relationship without changing the log semantics.

- [Retry complexity] → Retry metadata adds complexity before execution exists. Mitigation: limit this phase to schema/contract definitions and make worker execution a future responsibility.

- [Idempotency ambiguity] → Incorrect idempotency key semantics can cause duplicate or skipped actions. Mitigation: define a precise idempotency key policy and require the helper to compute it deterministically.

## Worker Safety Requirements

The following requirements apply to any future worker that processes `response_actions_queue` rows. No worker is implemented in this phase, but these contracts must be respected by whatever implementation picks up queue rows later.

**Separate DB connection:** The worker MUST open its own DB connection independent of the ingest pipeline. The ingest transaction will already be committed (or rolled back) by the time the worker runs. The worker must not attempt to reuse or assume access to the ingest cursor.

**Idempotent retry behavior:** Before executing any action, the worker MUST check the `idempotency_key` on the queue row. If a row with the same `idempotency_key` already has status `success` or `skipped`, the worker MUST NOT re-execute the action. This prevents duplicate side effects on retry.

**Status update protocol:** The worker MUST transition `status` to `running` before executing, then to `success` or `failed` after the outcome is known, and update `updated_at` on each transition. On failure, it MUST increment `retry_count` and record `last_error`. If `retry_count` reaches `max_retries`, the worker MUST mark the row `failed` without retrying further.

**No ingest transaction state:** The worker MUST NOT assume any write made during ingest is still uncommitted. All data the worker reads (alert rows, event rows) must be read via its own query against the committed database state.

## Integration Guidance for Future Worker Execution

When a future phase wires up a worker to consume `response_actions_queue`:

- **No changes to the ingest transaction are required.** The ingest → detection → correlation pipeline currently runs inside a single PostgreSQL transaction. That transaction boundary is unchanged by this foundation. The worker connects and reads committed rows only.
- **Enqueue invocation is a post-commit step.** `enqueue_response_action()` must be called after `conn.commit()` completes in whatever caller initiates enqueueing. It must not be called inside the ingest transaction.
- **The queue and log coexist.** `response_actions_queue` tracks pending/in-progress execution intent. `response_actions_log` remains the audit trail of what was executed. The worker should write to `response_actions_log` upon successful execution, linking the log row back to the queue row via `alert_id` and action metadata.
- **Verification:** Before shipping any worker, verify that running the full integration test suite (`python3 -m pytest tests/ -x --tb=short`) with the worker idle produces zero failures — confirming the ingest pipeline is unaffected.

## Open Questions

- Should the queue table include a foreign key to `alert.id`, or should it be nullable to support future non-alert-driven actions? The current design favors a nullable `alert_id` column so the queue can evolve beyond single-alert actions.
- How should the queue record link to `response_actions_log` once execution occurs? The initial design will treat that link as optional metadata rather than mandatory in this phase.
