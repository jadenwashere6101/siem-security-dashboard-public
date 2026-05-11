# Proposal: SOAR Worker Response Action Logging

## Status
Proposed

## Problem

Detection alerts no longer call `execute_response_action()` synchronously. Instead, they enqueue after commit and are processed by the SOAR worker. This means the asynchronous execution path — the only active path for detection-triggered response actions — produces no rows in `response_actions_log`. The audit trail for automated actions is now completely absent.

Manual response actions (fired from `alert_mutation_routes.py`) still write to `response_actions_log` via `execute_response_action()` and are unaffected by this change.

## Goal

Make the SOAR worker write to `response_actions_log` at each terminal outcome so detection alerts retain a complete audit trail.

## Approach

Introduce a dedicated log-writer module (`soar_log_writer.py`) with a single function — `log_response_action()` — that inserts a row into `response_actions_log`. The SOAR worker calls this function at each terminal transition point (success, skipped, final failure). Retryable failures that will be re-queued do NOT produce a log row.

The log write happens over the same database connection used by the queue status transition, ensuring the audit row and the queue row reach their final state together.

No changes are required to the executor, the queue store, the queue schema, the detection/ingest flow, or the manual execution path.

## Out of Scope

- Real firewall or cloud-provider blocking
- Playbooks and incidents
- Frontend queue UI
- Correlation alert enqueueing
- Schema changes to `response_actions_queue`
- Changes to detection, correlation, or ingest flows
- Changes to the manual `execute_response_action()` path

## Risks

1. **Duplicate log rows on stale-action recovery.** If a running action is recovered and re-queued after the stale timeout (15 min), it can execute twice. Each execution will produce a separate log row. This is intentional — two executions are two audit events — but it should be documented clearly.

2. **Partial commit on connection failure.** If the log write succeeds but the connection drops before the queue status update commits (or vice versa), the two tables diverge. The fix is to write both in the same transaction, which the design enforces.

3. **Log rows for retried actions across attempts.** Retryable errors that exhaust `max_retries` produce one log row (at final failure). Intermediate retries produce no rows. This keeps the log from being polluted with transient failures, but means the log does not show retry history. The queue row's `retry_count` and `last_error` fields carry that context.
