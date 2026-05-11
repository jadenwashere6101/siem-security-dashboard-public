# Design: SOAR Worker Response Action Logging

## 1. Where Logging Happens

Logging is the responsibility of the **worker** (`soar_action_worker.py`), not the executor or the queue store.

### Why not the executor?

The executor knows nothing about the queue row or the database. It receives a row dict and returns a result dict (or raises). Making it write to `response_actions_log` would mix execution and persistence concerns into a module that is deliberately side-effect-free.

### Why not the queue store?

The queue store owns one concern: queue row state transitions. Adding log-write calls to `mark_action_success()`, `mark_action_skipped()`, and `record_action_failure()` would give those functions two responsibilities and force them to accept extra parameters (executor result, source_ip) that don't belong to their contract.

### Why the worker?

`process_next_action()` in `soar_action_worker.py` is the only place that:
- Has the full queue row (alert_id, source_ip, action)
- Has the executor result (code, message, details) — or the exception
- Controls which terminal branch (success / skipped / final-failed) is taken
- Has access to the database connection

The worker is the correct integration point.

### New module: `soar_log_writer.py`

To keep `soar_action_worker.py` focused, the actual INSERT lives in a new, thin module:

```
engines/soar_log_writer.py
```

Single public function:

```python
def log_response_action(conn, row, log_status, details):
    """
    Write one row to response_actions_log.

    Parameters
    ----------
    conn       : psycopg2 connection (already in-transaction)
    row        : queue row dict with keys: alert_id, source_ip, action
    log_status : one of "executed", "skipped", "failed"
    details    : string describing the outcome (executor message or error message)
    """
```

The worker calls `log_response_action()` immediately before or after the corresponding queue-store call, within the same connection and transaction.

---

## 2. Fields Written to response_actions_log

| Column | Source | Notes |
|--------|--------|-------|
| `alert_id` | `row["alert_id"]` | May be NULL if the alert was deleted (queue has ON DELETE SET NULL) — insert NULL; the log row is still useful for forensics |
| `source_ip` | `row["source_ip"]` | INET; may be NULL |
| `action` | `row["action"]` | e.g. "block_ip", "flag_high_priority", "monitor" |
| `status` | derived (see §5) | "executed", "skipped", or "failed" |
| `details` | derived (see §5) | Executor message on success/skip; error string on failure |
| `executed_at` | DB default (NOW()) | Not supplied by the writer — let the database clock it |

No new columns are added to `response_actions_log`. The existing schema accommodates all outcomes.

---

## 3. Preserving Existing Manual Action Logging

`execute_response_action()` in `core/ip_helpers.py` is called only from the manual endpoint (`manual_execute_alert()` in `alert_mutation_routes.py`). It writes to `response_actions_log` with `status = "executed"`.

This path is **not touched**. The worker never calls `execute_response_action()`. The two logging paths are completely independent.

The only shared artifact is the `response_actions_log` table, which accommodates rows from both paths because:
- The schema has no column that distinguishes "manual" from "worker-queued"
- Both paths write the same logical fields
- A consumer reading the log does not need to distinguish source

If source-of-execution traceability becomes a future requirement, a `triggered_by` column (`"manual"` / `"worker"`) could be added later without touching the existing rows.

---

## 4. Preventing Duplicate Log Rows

### Guarantee: queue status is a one-way door

The queue store enforces status progression. Once a row reaches `success`, `failed`, or `skipped`, the worker's claim query (`WHERE status = 'pending'`) will never select it again. A terminal row cannot produce a second log entry from a second worker claim.

### Exception: stale-action recovery

`recover_stale_running_actions()` resets rows stuck in `running` back to `pending`. A stale-recovered row can be claimed again, executed again, and logged again. This produces **two legitimate audit rows** for two separate execution attempts. This is correct behavior and must be documented in the log writer's docstring.

### Exception: manual execution after queue execution

If a user manually executes an action for an alert that the worker already processed, the manual path writes a second row with status `"executed"`. These are two distinct user-initiated events and both should appear in the log. The schema does not and should not prevent this.

### No additional deduplication mechanism is required.

---

## 5. Outcome-to-Log Mapping

| Worker branch | Queue terminal status | log `status` | log `details` source |
|---|---|---|---|
| Executor returns success dict | `success` | `"executed"` | `execution_result["message"]` |
| `SkippedAction` raised | `skipped` | `"skipped"` | `str(exc)` (the skip reason) |
| Non-retryable exception | `failed` | `"failed"` | `str(exc)` |
| `RetryableActionError`, retries exhausted (queue goes to `failed`) | `failed` | `"failed"` | `str(exc)` |
| `RetryableActionError`, retries remain (queue re-queued to `pending`) | *(no log row)* | — | — |

The last row is the critical non-obvious rule: **a retryable failure that will be retried does not produce a log row.** Only the final disposition of an action — whether it ultimately succeeded, was skipped, or definitively failed — should appear in the audit log.

The worker already knows whether an action will be retried because `record_action_failure()` returns information about whether the row was re-queued. The logging call is conditioned on that return value.

---

## 6. Queue Status and Log Status Relationship

These two tables serve different purposes:

| | `response_actions_queue` | `response_actions_log` |
|---|---|---|
| Purpose | What the system intends to execute; tracks lifecycle | What the system actually executed; immutable audit |
| Mutability | Rows update through status transitions | Rows are append-only; never updated |
| Scope | One row per unique (alert_id, source_ip, action) | One row per terminal execution attempt |
| Lifetime | Row persists (for dashboards, retry UI) | Row persists (for compliance/forensics) |

The status strings map as follows:

```
queue "success"  →  log "executed"
queue "skipped"  →  log "skipped"
queue "failed"   →  log "failed"   (only when terminal, not retried)
queue "pending"  →  (no log row)
queue "running"  →  (no log row)
```

Note `"executed"` in the log vs `"success"` in the queue. The log uses `"executed"` to match the existing convention set by the manual execution path.

---

## 7. Transactional Safety

The log write and the queue status update must commit together. The implementation achieves this by:

1. Using the single `conn` object already passed to `process_next_action()`.
2. Calling `log_response_action(conn, ...)` within the same implicit transaction as the queue store call.
3. Relying on the caller (test harness or production scheduler) to issue `conn.commit()` after `process_next_action()` returns.

The worker currently does not call `conn.commit()` internally — status transitions commit via the connection the caller manages. The log writer follows the same pattern.

---

## 8. Affected Files (Implementation Reference)

| File | Change |
|------|--------|
| `engines/soar_log_writer.py` | New file — `log_response_action()` function |
| `engines/soar_action_worker.py` | Add `log_response_action()` calls at success, skipped, and final-failure branches |
| `tests/test_soar_log_writer.py` | New test file — unit tests for the log writer |
| `tests/test_soar_action_worker.py` | New or extended test file — integration tests verifying log rows are written |

No changes to: `soar_executor.py`, `soar_errors.py`, `soar_enqueue_orchestrator.py`, `response_action_queue_store.py`, `ip_helpers.py`, `alert_mutation_routes.py`, `schema.sql`, `ingest_routes.py`.
