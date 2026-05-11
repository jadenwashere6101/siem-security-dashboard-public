## Current state (context only)

All 4 ingest route handlers share this structure:

```
conn = get_db_connection()
cur = conn.cursor()
alerts_created = ingest_normalized_event(event_dict, conn, cur)  # detection + correlation
conn.commit()
return jsonify({...}), 201
finally:
    cur.close()
    conn.close()
```

Inside `ingest_normalized_event()`, detection functions call `execute_response_action()` synchronously inside the open transaction, writing to `response_actions_log`. The `alerts_created` list returned to the route currently contains dicts like:

```python
{"source_ip": ..., "attempts": ...}
```

`alert_id` and `response_action` are **not included**. This is the data gap that prevents route-level post-commit enqueueing. Addressing that gap is Phase 1D-b, not this phase.

Correlation alerts (`correlated_activity`, `web_to_app_attack_pattern`, etc.) are never returned from `ingest_normalized_event()` — they are a side effect. Enqueueing them requires changes to correlation function return types and is deferred beyond Phase 1D-b.

---

## This phase: enqueue orchestration helper only

`engines/soar_enqueue_orchestrator.py` is a standalone module that does not touch routes, detection functions, or the ingest transaction. It can be called from tests, CLI scripts, or eventually the route layer.

### Public interface

```python
def enqueue_committed_alerts(alerts_created: list, conn) -> list:
    """
    Enqueues response actions for a list of committed alert dicts.
    Must be called after the ingest transaction has committed.
    Does not commit — the caller is responsible for committing after this returns.

    Each dict in alerts_created must contain:
        alert_id (int)
        source_ip (str)
        response_action (str)

    Dicts missing any of these fields are skipped with a warning log.
    Returns a list of result dicts, one per processed alert.
    """
```

### Input dict contract

The orchestrator accepts any list of dicts. It does not assume any particular shape — it extracts `alert_id`, `source_ip`, and `response_action` by key and skips any dict where any of those keys is absent or `None`.

This design means the orchestrator is safe to call even before the detection functions are updated to include `alert_id` — it will simply skip every dict and return an empty result list. No route call will fail.

In Phase 1D-b, detection functions will add `alert_id` and `response_action` to their returned dicts, and the orchestrator will start processing them.

### Result dict per alert

```python
{
    "alert_id": int,
    "source_ip": str,
    "action": str,
    "queue_id": int | None,   # None means already enqueued (idempotent skip)
    "skipped": False,
}
```

For dicts that were skipped due to missing fields:

```python
{
    "alert_id": None,
    "source_ip": None,
    "action": None,
    "queue_id": None,
    "skipped": True,
    "skip_reason": "missing_alert_id",  # or missing_source_ip, missing_response_action
}
```

### Internal behavior

1. Open a cursor on the committed connection.
2. For each dict in `alerts_created`:
   - Extract `alert_id`, `source_ip`, `response_action`.
   - If any is `None` or absent: log warning, append skipped result, continue.
   - Call `enqueue_response_action(cur, alert_id, str(source_ip), response_action)`.
   - Log `[SOAR ENQUEUE] alert_id=... queue_id=...` or `queue_id=None (already enqueued)`.
   - Append result dict.
3. Return result list.

The orchestrator does NOT commit — the caller commits. The orchestrator does NOT close the cursor — the caller owns the connection lifecycle.

The orchestrator does NOT catch exceptions from `enqueue_response_action()`. If the DB write fails, the exception propagates to the caller. In Phase 1D-b, the route handler will wrap the call in `try/except` to prevent enqueue failure from masking a committed ingest. In this phase, test callers handle exceptions directly.

### Logging

Successful enqueue:
```
[SOAR ENQUEUE] alert_id=42 source_ip=1.2.3.4 action=block_ip queue_id=17
```

Already enqueued (idempotent skip):
```
[SOAR ENQUEUE] alert_id=42 source_ip=1.2.3.4 action=block_ip queue_id=None (already enqueued)
```

Skipped due to missing field:
```
[SOAR ENQUEUE WARNING] Skipping alert dict missing required field 'alert_id': {...}
```

Use `logging.getLogger(__name__)` — consistent with `engines/soar_action_worker.py` and keeps the orchestrator callable from tests and CLI scripts without a Flask app context.

### Module placement

```
engines/
  soar_enqueue_orchestrator.py   ← NEW (this phase)
  soar_action_worker.py          ← existing, unchanged
  soar_errors.py                 ← existing, unchanged
  soar_executor.py               ← existing, unchanged

core/
  ip_helpers.py                  ← existing, unchanged (enqueue_response_action lives here)

routes/
  ingest_routes.py               ← unchanged (Phase 1D-b)
```

`engines/` is the right location: the orchestrator is SOAR coordination logic, not a DB helper (`core/`) and not a route handler.

---

## Phase 1D-b design (deferred, documented here for continuity)

Phase 1D-b requires these changes before the orchestrator is wired into ingest:

**Detection function return format augmentation.** Each of the 7 `_generate_*_core()` functions must add `alert_id` and `response_action` to the dict they append to `alerts_created`. Both variables already exist inside each function (`alert_id` from `currval()`, `response_action` from `determine_response_action()`). This is a one-line change per function but requires updating all detection test assertions that check `alerts_created` dict shape.

**Route handler integration.** In each of the 4 ingest route handlers, after `conn.commit()`:
```python
try:
    enqueue_committed_alerts(alerts_created, conn)
    conn.commit()
except Exception as enqueue_error:
    current_app.logger.error(
        "[SOAR ENQUEUE FAILED] %s | alerts=%s",
        enqueue_error,
        [(a.get("alert_id"), a.get("source_ip")) for a in alerts_created],
    )
    # Do not re-raise — committed ingest must not appear as 500.
```

**Why enqueue failure is swallowed.** The alert is committed. The caller (external system) sees 201. The enqueue failure is logged with structured context for manual re-queue. The queue is an intent record downstream of the source of truth; its failure must not invalidate the source of truth.

**Correlation alert gap.** Correlation alerts (`correlated_activity`, etc.) are side effects inside `ingest_normalized_event()` that return no alert IDs. They will not be enqueued in Phase 1D-b either. Addressing this requires changing correlation function signatures and is a separate phase.

**Dual-execution state.** When Phase 1D-b lands, both `execute_response_action()` (synchronous, inside transaction) and the worker (async, post-commit) will execute for every detection alert. This is an intentional, temporary stepping stone. The removal of `execute_response_action()` from detection functions is a later phase.

---

## Testing strategy (Phase 1D-a)

All tests call `enqueue_committed_alerts()` directly — no route calls, no Flask test client.

**Success path**
- Build a valid alert dict with `alert_id`, `source_ip`, `response_action`.
- Call `enqueue_committed_alerts([alert_dict], conn)`.
- Call `conn.commit()`.
- Query `response_actions_queue` — confirm one row exists with correct `alert_id`, `source_ip`, `action`, `status='pending'`.
- Confirm the result list contains `{"alert_id": ..., "queue_id": int, "skipped": False}`.

**Idempotency**
- Call `enqueue_committed_alerts([alert_dict], conn)` twice with the same dict.
- Commit after each call.
- Confirm only one queue row exists.
- Confirm no exception on either call.
- Confirm second call returns `queue_id=None`.

**Missing field guard — `alert_id` absent**
- Pass `{"source_ip": "1.2.3.4", "response_action": "block_ip"}` (no `alert_id`).
- Confirm no queue row is created.
- Confirm no exception propagates.
- Confirm result list contains `{"skipped": True, "skip_reason": "missing_alert_id"}`.

**Missing field guard — `source_ip` absent**
- Same pattern.

**Missing field guard — `response_action` absent**
- Same pattern.

**Mixed list**
- Pass a list with one valid dict and one dict missing `alert_id`.
- Confirm exactly one queue row is created (for the valid dict).
- Confirm result list has two entries: one with `skipped=False`, one with `skipped=True`.

**Empty list**
- Pass `[]`.
- Confirm no queue rows are created.
- Confirm result list is `[]`.
- Confirm no exception.

**Regression guard**
- Run `test_response_action_queue.py` — green.
- Run all detection, correlation, and ingest test suites — green, no changes needed since no production code outside the new file was touched.
