# Tasks: SOAR Worker Response Action Logging

## T1 — Create `soar_log_writer.py`

**File:** `engines/soar_log_writer.py`

Implement `log_response_action(conn, row, log_status, details)`:

- Accepts a psycopg2 connection (already in-transaction), a queue row dict, a log status string, and a details string.
- Executes an INSERT into `response_actions_log` with fields: `alert_id`, `source_ip`, `action`, `status`, `details`. Let `executed_at` default via the DB.
- `alert_id` may be `None` (alert was deleted; queue has ON DELETE SET NULL). Write NULL — do not skip the log row.
- `source_ip` may be `None`. Write NULL.
- `log_status` must be one of: `"executed"`, `"skipped"`, `"failed"`. Raise `ValueError` for anything else so invalid values fail loudly at call time, not silently.
- No commit inside the function; caller owns the transaction boundary.
- No logging to stdout/stderr inside the function; logging belongs to the caller.

---

## T2 — Wire log calls into `soar_action_worker.py`

**File:** `engines/soar_action_worker.py`

Import `log_response_action` from `soar_log_writer`.

In `process_next_action()`, add calls at the following points:

### T2a — Success branch

After `mark_action_success()` is called (queue reaches `"success"`):

```
log_response_action(
    conn,
    row,
    log_status="executed",
    details=execution_result["message"]
)
```

### T2b — SkippedAction branch

After `mark_action_skipped()` is called (queue reaches `"skipped"`):

```
log_response_action(
    conn,
    row,
    log_status="skipped",
    details=str(exc)   # the SkippedAction exception message
)
```

### T2c — Final failure branch (retries exhausted or non-retryable)

After `record_action_failure()` determines the action will NOT be re-queued (i.e., the queue reaches terminal `"failed"`):

```
log_response_action(
    conn,
    row,
    log_status="failed",
    details=str(exc)
)
```

### T2d — Retryable failure that will be re-queued

When `record_action_failure()` determines the action WILL be re-queued (retry count < max_retries, retryable=True): **do not call `log_response_action()`**. No log row for intermediate retry attempts.

**Implementation note:** `record_action_failure()` currently returns nothing useful for distinguishing these cases. The worker needs to inspect `row["retry_count"]` and `row["max_retries"]` before calling `record_action_failure()`, or `record_action_failure()` needs to return whether it re-queued. Prefer inspecting `retry_count` vs `max_retries` in the worker to avoid changing the queue store contract.

---

## T3 — Unit tests for `soar_log_writer.py`

**File:** `tests/test_soar_log_writer.py`

Use a real test database (no mocks for the DB connection). Each test runs in a transaction that is rolled back after the test.

### T3-1: Success status writes correct row

Call `log_response_action(conn, row, "executed", "simulated block")`. Fetch the resulting row from `response_actions_log`. Assert:
- `alert_id`, `source_ip`, `action` match the input row
- `status == "executed"`
- `details == "simulated block"`
- `executed_at` is not null

### T3-2: Skipped status writes correct row

Same as T3-1 with `log_status="skipped"`, `details="private IP rejected"`. Assert `status == "skipped"`.

### T3-3: Failed status writes correct row

Same as T3-1 with `log_status="failed"`, `details="connection timeout"`. Assert `status == "failed"`.

### T3-4: Null alert_id is written as NULL (alert was deleted)

Pass a row with `alert_id=None`. Assert the inserted row has `alert_id IS NULL`. The insert must not raise.

### T3-5: Null source_ip is written as NULL

Pass a row with `source_ip=None`. Assert the inserted row has `source_ip IS NULL`.

### T3-6: Invalid log_status raises ValueError

Call `log_response_action(conn, row, "unknown_status", "x")`. Assert `ValueError` is raised before any INSERT.

### T3-7: No commit inside log_response_action

After calling `log_response_action()`, roll back the connection, then query `response_actions_log`. Assert zero rows — confirming the function did not auto-commit.

---

## T4 — Worker integration tests

**File:** `tests/test_soar_action_worker.py` (new file, or extend `test_response_action_queue.py`)

These tests verify that `process_next_action()` triggers the correct logging behavior end-to-end. Use a real test database; use a custom executor fixture where needed.

### T4-1: Success → log row written with status "executed"

Enqueue one valid action. Run `process_next_action()`. Assert:
- Queue row status is `"success"`
- Exactly one row in `response_actions_log` for this `alert_id`
- Log row `status == "executed"`
- Log row `details` equals the executor's `message` field

### T4-2: SkippedAction → log row written with status "skipped"

Use a custom executor that raises `SkippedAction("private IP")`. Enqueue and run. Assert:
- Queue row status is `"skipped"`
- Log row `status == "skipped"`
- Log row `details` contains the skip reason string

### T4-3: Non-retryable failure → log row written with status "failed"

Use a custom executor that raises a plain `Exception("unexpected error")`. Enqueue and run. Assert:
- Queue row status is `"failed"`
- Log row `status == "failed"`
- Log row `details` contains the error message

### T4-4: Retryable failure with retries remaining → no log row

Use a custom executor that raises `RetryableActionError("timeout")`. Ensure `max_retries > 0` and `retry_count == 0`. Enqueue and run. Assert:
- Queue row is re-queued to `"pending"` (retry_count incremented)
- Zero rows in `response_actions_log` for this `alert_id`

### T4-5: Retryable failure, retries exhausted → log row written

Enqueue with `retry_count = max_retries - 1` (one retry left). Use an executor that always raises `RetryableActionError`. Run `process_next_action()`. Assert:
- Queue row status is `"failed"` (not re-queued)
- Log row `status == "failed"`

### T4-6: No duplicate log rows on single execution

Run `process_next_action()` once on a pending action. Assert exactly one log row for the alert. Confirm the queue row is terminal (success/skipped/failed) and would not be claimed again.

### T4-7: Manual logging path unaffected

Call `execute_response_action()` directly (the manual path). Assert one row in `response_actions_log`. Then run `process_next_action()` for a separate queued action. Assert that log row count for the second alert is one and the first log row is unchanged. The two paths must not interfere.

### T4-8: Null alert_id (deleted alert) still produces a log row

Enqueue with `alert_id` pointing to a real alert, then delete the alert. Confirm the queue row has `alert_id = NULL` (ON DELETE SET NULL). Run `process_next_action()`. Assert a log row is written with `alert_id IS NULL`.

---

## Recommended Implementation Order

1. **T1** — Write `soar_log_writer.py` and its unit tests (T3). These are fully self-contained and can be verified in isolation.
2. **T2** — Wire the log calls into `soar_action_worker.py`. The success, skipped, and final-failure branches can be tackled in any order; the retry-suppression logic (T2d) is the most delicate and should come last.
3. **T4** — Write the worker integration tests against the wired-up code. Run the full test suite to confirm no regressions in `test_response_action_queue.py` or `test_soar_executor.py`.
