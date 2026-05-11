# Design: Decouple Response Execution from Detection

---

## 1. Current State

Detection functions insert alert rows inside the ingest transaction and then call
`execute_response_action()` before the transaction commits. That function writes
to `response_actions_log` and returns `"executed"`, after which the detection
function updates the alert's `response_status` to that value.

The route layer now also calls `enqueue_committed_alerts(alerts_created, conn)`
after `conn.commit()`. That post-commit path inserts queue rows into
`response_actions_queue` using the alert metadata returned by detection.

Current detection flow:

```text
ingest route opens transaction
  -> ingest_normalized_event()
    -> detection function inserts alert
    -> detection function calls execute_response_action()
    -> response_actions_log row is written inside ingest transaction
    -> alert.response_status becomes "executed"
  -> route commits ingest transaction
  -> route enqueues alert post-commit
  -> route commits queue insert
```

Target detection flow:

```text
ingest route opens transaction
  -> ingest_normalized_event()
    -> detection function inserts alert
    -> detection function returns alert_id/source_ip/response_action
    -> alert.response_status remains deferred/pending
  -> route commits ingest transaction
  -> route enqueues alert post-commit
  -> route commits queue insert
  -> worker executes queued action
  -> worker records execution in response_actions_log
```

---

## 2. Full `execute_response_action()` Call-Site Analysis

### Function definition

`core/ip_helpers.py`

- Defines `execute_response_action(cur, alert_id, source_ip, response_action, ...)`.
- Simulates automatic `block_ip`, `flag_high_priority`, and `monitor` actions by
  logging details and inserting into `response_actions_log`.
- Can optionally create a blocklist record when called with
  `create_blocklist_record=True`; this mode is used by manual alert execution,
  not by detection.

### Detection call sites: in scope

`engines/detection_engine.py` imports:

```python
from core.ip_helpers import determine_response_action, execute_response_action, lookup_ip_reputation
```

The following 7 functions call `execute_response_action()` immediately after
reading the inserted alert ID with `currval()`:

| Function | Current behavior | Target behavior |
|---|---|---|
| `_generate_failed_login_alerts_core` | Execute action, update `response_status`, append alert metadata | Do not execute; leave/defer `response_status`; append same metadata |
| `_generate_http_error_alerts_core` | Same | Same target |
| `_generate_port_scan_alerts_core` | Same | Same target |
| `_generate_password_spraying_alerts_core` | Same | Same target |
| `_generate_successful_login_after_spray_alerts_core` | Same | Same target |
| `_generate_application_exception_alerts_core` | Same | Same target |
| `_generate_high_request_rate_alerts_core` | Same | Same target |

Each function already has these values in scope:

- `alert_id`
- `source_ip`
- `response_action`

Those values must remain in `alerts_created` so the existing post-commit enqueue
path continues to work.

### Correlation call sites: out of scope

`engines/correlation_engine.py` imports and calls `execute_response_action()` in:

- `generate_correlated_activity_alerts`
- `generate_targeted_correlation_alerts`

These calls must remain unchanged in this change. Correlation alerts are not part
of the route-level `alerts_created` return list and are not yet queueable without
changing correlation return types. That is explicitly deferred.

### Manual route call site: out of scope

`routes/alert_mutation_routes.py` calls `execute_response_action()` from the manual
alert execution endpoint. That behavior remains synchronous because it is a
user-requested action, not an ingest-time automated detection side effect.

---

## 3. Detection Code Change Shape

For each detection function, remove only this block:

```python
execution_status = execute_response_action(
    cur,
    alert_id,
    str(source_ip),
    response_action
)

cur.execute(
    """
    UPDATE alerts
    SET response_status = %s
    WHERE id = %s
    """,
    (execution_status, alert_id)
)
```

Do not remove:

- the alert insert
- the `currval()` call
- `alert_id = cur.fetchone()[0]`
- the `alerts_created.append(...)` call
- `response_action` computation
- reputation lookup
- location lookup
- duplicate suppression
- any SQL that creates alerts

After all 7 blocks are removed, update the import to:

```python
from core.ip_helpers import determine_response_action, lookup_ip_reputation
```

No function signatures change.

---

## 4. `response_status` Behavior

Detection currently sets `response_status = "pending"` before inserting each
alert, then changes it to `"executed"` after the synchronous action call.

After this change, detection should leave the inserted value as `"pending"`.

Rationale:

- The action has not executed inside the detection transaction.
- A queued action row represents intent, not completion.
- The worker path is the only path that should mark execution complete in a later
  implementation phase.
- Keeping `"pending"` is backward-compatible with the current schema and avoids
  adding queue-specific statuses or changing queue schema.

This spec does not require a new status value such as `"queued"` or `"deferred"`.
Those would be broader UI/API semantics and are out of scope.

---

## 5. `response_actions_log` Behavior

### What changes

Detection tests should no longer expect `response_actions_log` rows immediately
after a detection function runs. Removing the synchronous call means detection no
longer writes to `response_actions_log` inside the ingest transaction.

### What stays preserved

`response_actions_log` remains the audit trail for executed actions. The audit row
is preserved by deferring it to the queued execution path:

```text
detection creates alert
  -> route enqueues post-commit
  -> SOAR worker executes queued action
  -> executor/action path records response_actions_log
```

The implementation phase must verify that the current worker/executor path writes
or continues to write a `response_actions_log` row for completed queue items. If
the worker path does not yet write the same audit row, add that audit behavior in
the queue worker/executor layer, not in detection.

### What must not happen

- Do not preserve audit logging by leaving a detection-side
  `execute_response_action()` call in place.
- Do not insert synthetic `response_actions_log` rows from detection to represent
  queued intent.
- Do not change `response_actions_log` schema.
- Do not drop existing manual or correlation audit behavior.

---

## 6. How Queued Actions Replace Synchronous Execution

The replacement path already exists for detection alerts:

1. Detection inserts alert rows and appends dicts containing:
   - `alert_id`
   - `source_ip`
   - `response_action`
2. The ingest route commits the ingest transaction.
3. The ingest route calls `enqueue_committed_alerts(alerts_created, conn)`.
4. The orchestrator inserts `response_actions_queue` rows with idempotency keys.
5. The route commits the queue inserts.
6. The worker claims pending queue rows and executes them through the SOAR
   executor/action path.

The implementation should not add new queue columns or change queue idempotency.
It should rely on the existing queue contract.

---

## 7. Tests That Need Updates

### Detection tests

The following test files currently assert synchronous `response_actions_log`
behavior for detection-created alerts and must be updated:

- `tests/test_failed_login_detection.py`
- `tests/test_http_error_detection.py`
- `tests/test_port_scan_detection.py`
- `tests/test_password_spraying_detection.py`
- `tests/test_successful_login_after_spray_detection.py`
- `tests/test_application_exception_detection.py`
- `tests/test_high_request_rate_detection.py`

Expected updates:

- Keep assertions that alert rows are created.
- Keep assertions that `alerts_created` includes the expected detection-specific
  fields plus `alert_id` and `response_action`.
- Change `response_status` expectations from `"executed"` to `"pending"` for
  detection-created alerts.
- Remove or replace joins against `response_actions_log` for detection-created
  alerts.
- Add assertions that no synchronous `response_actions_log` row is created by the
  detection function itself.

### Ingest enqueue tests

`tests/test_wire_soar_enqueue_post_commit.py` should remain the primary route-level
proof that detection alert metadata is passed to `enqueue_committed_alerts()` only
after commit.

Additional coverage may be added there or in a focused new test:

- The route returns 201 after detection alert creation.
- `enqueue_committed_alerts()` is called with the detection alert dict containing
  `alert_id`, `source_ip`, and `response_action`.
- The detection path does not call `execute_response_action()` when patched at
  `engines.detection_engine.execute_response_action` before the import is removed,
  or by asserting the symbol no longer exists after removal.

### Queue/worker tests

The following tests should carry the replacement audit responsibility:

- `tests/test_response_action_queue.py`
- `tests/test_soar_executor.py`

Expected coverage:

- A queued action can be executed successfully.
- Completed queued execution records the expected `response_actions_log` row.
- Queue idempotency prevents duplicate queue rows.
- Worker/executor failures do not recreate synchronous detection behavior.

### Tests that should not change for this scope

- `tests/test_correlated_activity.py`
- `tests/test_targeted_correlation.py`
- `tests/test_alert_mutation_api_contracts.py`

These continue to validate currently synchronous correlation and manual execution
behavior.

---

## 8. Risks

### Risk 1: Audit log gap

If detection stops writing `response_actions_log` before the worker/executor path
is verified to write it, executed detection responses may lose their audit trail.

Mitigation:

- Verify queue/worker audit behavior before removing detection-side expectations.
- If missing, add audit logging to the queue execution layer in the implementation
  phase.

### Risk 2: UI/API still assumes immediate `"executed"`

Some API consumers may read `alerts.response_status` immediately after ingest and
expect `"executed"`.

Mitigation:

- Keep status as `"pending"` until queued execution completes.
- Update backend tests to document the new deferred state.
- Do not introduce new frontend semantics in this change.

### Risk 3: Removing too much at once

Removing detection execution, changing correlation behavior, changing queue
schema, and updating worker audit behavior in one implementation would make
regressions hard to isolate.

Mitigation:

- Remove only detection synchronous calls.
- Preserve correlation and manual execution.
- Preserve queue schema.
- Keep worker changes limited to audit preservation only if required.

### Risk 4: Hidden dependency on `execute_response_action()` side effects

`execute_response_action()` currently logs simulated action details and writes
`response_actions_log`. Detection callers may implicitly depend on those effects.

Mitigation:

- Replace only through the queued worker path.
- Confirm the worker/executor result includes equivalent action details.
- Keep manual action behavior untouched.

### Risk 5: Post-commit enqueue failure leaves pending alerts

After synchronous detection execution is removed, a post-commit enqueue failure
means the alert exists but no response action is queued.

Mitigation:

- Preserve existing route-level enqueue error logging.
- Keep this risk visible in tests and rollout notes.
- Roll back by restoring detection synchronous calls if queue reliability is not
  acceptable.
- Defer durable dead-letter/requeue improvements to a later hardening change.

---

## 9. Rollback Plan

Rollback must be narrow and non-destructive:

1. Restore the `execute_response_action` import in `engines/detection_engine.py`.
2. Restore the 7 detection-side execution/update blocks exactly as they existed.
3. Restore detection test expectations for immediate `"executed"` status and
   synchronous `response_actions_log` rows.
4. Leave the post-commit enqueue path in place unless it is the source of the
   failure.

If the problem is duplicate side effects after rollback, temporarily disable
worker processing rather than changing detection/correlation internals.

No schema rollback is required because this change must not alter schema.

---

## 10. Verification Strategy

Focused checks:

```bash
python3 -m py_compile engines/detection_engine.py
```

```bash
python3 -m pytest \
  tests/test_failed_login_detection.py \
  tests/test_http_error_detection.py \
  tests/test_port_scan_detection.py \
  tests/test_password_spraying_detection.py \
  tests/test_successful_login_after_spray_detection.py \
  tests/test_application_exception_detection.py \
  tests/test_high_request_rate_detection.py \
  tests/test_wire_soar_enqueue_post_commit.py \
  tests/test_response_action_queue.py \
  tests/test_soar_executor.py \
  -v
```

Regression guards that must remain green:

```bash
python3 -m pytest \
  tests/test_correlated_activity.py \
  tests/test_targeted_correlation.py \
  tests/test_ingest_api_contracts.py \
  tests/test_alert_mutation_api_contracts.py \
  -v
```

Final check:

```bash
python3 -m pytest -v -rs
```
