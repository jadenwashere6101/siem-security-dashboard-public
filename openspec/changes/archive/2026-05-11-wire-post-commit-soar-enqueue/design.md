# Design: Wire Post-Commit SOAR Enqueue into Ingest Routes

---

## 1. Which Ingest Routes Create `alerts_created`

All four routes in `routes/ingest_routes.py` call `ingest_normalized_event` and
capture its return value as `alerts_created`. Each has exactly one `conn.commit()`
call that closes the ingest transaction, immediately before a `return jsonify(...)`.

| Route | Function | `conn.commit()` line | Return |
|---|---|---|---|
| `POST /ingest` | `add_event` | line 99 | line 101 |
| `POST /ingest/web-log` | `add_web_log_event` | line 190 | line 192 |
| `POST /ingest/azure` | `add_azure_event` | line 276 | line 278 (batch) |
| `POST /ingest/otlp` | `add_otel_event` | line 348 | line 350 (batch) |

`add_azure_event` and `add_otel_event` are batch routes: they loop over
`normalized_events`, calling `ingest_normalized_event` for each item and extending
`alerts_created`. Both have a single `conn.commit()` after the full loop, not one
per item. The enqueue must also happen once, after the single commit, passing the
full accumulated `alerts_created` list.

---

## 2. What Shape `alerts_created` Currently Has

Each detection function appends a dict to `alerts_created` and returns the list.
The dicts vary by function:

| Detection Function | Current Dict Keys |
|---|---|
| `_generate_failed_login_alerts_core` | `source_ip`, `attempts` |
| `_generate_http_error_alerts_core` | `source_ip`, `attempts` |
| `_generate_port_scan_alerts_core` | `source_ip`, `attempts` |
| `_generate_password_spraying_alerts_core` | `source_ip`, `distinct_username_count` |
| `_generate_successful_login_after_spray_alerts_core` | `source_ip`, `success_at` |
| `_generate_application_exception_alerts_core` | `source_ip`, `attempts` |
| `_generate_high_request_rate_alerts_core` | `source_ip`, `attempts` |

`enqueue_committed_alerts` requires `alert_id`, `source_ip`, and `response_action`
in each dict. Without `alert_id` and `response_action`, every alert is skipped with
`skip_reason="missing_alert_id"` — no queue rows would ever be inserted.

---

## 3. What Fields Are Missing

Both `alert_id` and `response_action` are in local scope at the
`alerts_created.append()` call in every detection function:

- `alert_id` is read from `currval` immediately before the `.append()` call:
  ```python
  cur.execute("SELECT currval(pg_get_serial_sequence('alerts', 'id'))")
  alert_id = cur.fetchone()[0]
  execute_response_action(cur, alert_id, str(source_ip), response_action)
  ...
  alerts_created.append({"source_ip": source_ip, "attempts": attempts})
  ```

- `response_action` is assigned from `determine_response_action(reputation_score)`
  earlier in the same loop body.

No new DB reads, no new logic, no new imports are needed. The fix is purely
additive: include both fields in the `.append()` dict.

---

## 4. Safest Way to Add `alert_id` and `response_action` to Detection Dicts

**Rule: no changes to function signatures, no changes to logic, no changes to SQL.**

Each of the 7 functions has one `alerts_created.append({...})` call. Extend each
dict with `"alert_id": alert_id, "response_action": response_action`:

```python
# Before
alerts_created.append({
    "source_ip": source_ip,
    "attempts": attempts,
})

# After
alerts_created.append({
    "source_ip": source_ip,
    "attempts": attempts,
    "alert_id": alert_id,
    "response_action": response_action,
})
```

`_generate_password_spraying_alerts_core` uses `distinct_username_count` instead of
`attempts`; `_generate_successful_login_after_spray_alerts_core` uses `success_at`.
Both get the same `alert_id` and `response_action` additions.

**Test impact:** All existing detection test assertions use field-by-field key access
(`alerts_created[0]["source_ip"]`, `alerts_created[0]["attempts"]`). No test uses
full-dict equality (`==`) against the full alert dict. Adding new keys does not
break any existing assertion. No existing test files need to be changed.

---

## 5. Whether to Wire Standard Detection Alerts First and Defer Correlation

**Yes — wire detection alerts only. Correlation alerts are deferred.**

`generate_correlated_activity_alerts` and `generate_targeted_correlation_alerts`
return `False` or `True` (not lists). `ingest_engine.py` calls them for side effects
only and does not add their results to `alerts_created`. Any change to make
correlation results enqueueable requires altering those functions' return types,
which touches correlation internals — explicitly off-limits per the roadmap.

Because correlation results are not in `alerts_created`, no special handling is
needed in the route. The enqueue will only process detection alerts.

---

## 6. Exact Post-Commit Location in Each Route

The enqueue block goes in the `try` body of each route, between `conn.commit()` and
the existing `return` statement. It must be inside a nested `try/except` so that
enqueue failures do not propagate to the outer `except` (which calls
`conn.rollback()` — a rollback after a successful commit has no effect on the
already-committed rows, but it would produce confusing log noise and could
interfere with the connection state for the queue commit).

**Pattern (same for all 4 routes):**

```python
conn.commit()  # closes ingest transaction — alert/event rows now committed

try:
    enqueue_committed_alerts(alerts_created, conn)
    conn.commit()  # commits response_actions_queue inserts
except Exception as enqueue_error:
    current_app.logger.error(
        "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
        enqueue_error,
    )

return jsonify({"message": "...", "alerts_created": alerts_created}), 201
```

**Why a second `conn.commit()` is required:**

`enqueue_committed_alerts` opens a new cursor via `conn.cursor()` and calls
`enqueue_response_action`, which does an `INSERT INTO response_actions_queue`. These
inserts run in a new implicit transaction on the same connection (the first
`conn.commit()` closed the ingest transaction; psycopg2 immediately begins a new
transaction on the next statement). Without a second `conn.commit()`, those inserts
are uncommitted when `conn.close()` runs in the `finally` block, and psycopg2 will
roll them back.

**Why the enqueue block is inside its own `try/except`:**

If `enqueue_committed_alerts` raises — or the second `conn.commit()` raises — we
catch it, log it, and fall through to the `return`. The already-committed ingest
rows are not affected. We do NOT call `conn.rollback()` in the enqueue except
block because:
- If enqueue raised before any inserts: nothing to roll back.
- If enqueue inserted some rows but then raised: those inserts were not committed.
  `conn.close()` in the `finally` block will roll them back automatically.
- An explicit rollback here is safe but unnecessary; the `finally` cleanup handles it.

**Why the enqueue block must not be inside the outer `except`:**

The outer `except` only runs on pre-commit failure (e.g., an exception inside the
ingest transaction). If we placed the enqueue call there, it would run when there is
no committed alert data — and `conn.rollback()` would have already undone everything.

---

## 7. Failure Handling After Commit

| Failure scenario | Expected behavior |
|---|---|
| `enqueue_committed_alerts` raises immediately | Log ERROR, return 201 with committed data |
| Some alerts enqueue, then an exception | Partial queue inserts uncommitted; `conn.close()` rolls them back; log ERROR; return 201 |
| Second `conn.commit()` fails | Queue inserts rolled back by `conn.close()`; log ERROR; return 201 |
| No alerts triggered (empty `alerts_created`) | `enqueue_committed_alerts` returns `[]` immediately; second commit is a no-op; return 201 |
| All alerts already in queue (idempotency) | `enqueue_committed_alerts` returns all results with `status="duplicate_skipped"`; second commit is a no-op; return 201 |

**Queue rows lost on enqueue failure are acceptable for this phase.** The SOAR
roadmap Phase 5 dead-letter queue addresses durable retry of failed enqueue attempts.
For now, `execute_response_action()` still runs synchronously inside the detection
function, so a response action is always attempted even when the enqueue path fails.

---

## 8. Connection State After First Commit

After `conn.commit()`, the same `conn` object is valid and usable. `enqueue_committed_alerts` calls `conn.cursor()` to open its own cursor — it does not reuse the ingest route's `cur`. This is correct: the original `cur` is still open (it's closed in `finally`) but should not be used for post-commit work. The enqueue function's internal cursor is opened from the committed connection and is scoped entirely within `enqueue_committed_alerts`.

The original route `cur` is not passed to `enqueue_committed_alerts` and is not used
after `conn.commit()`. This is intentional and already matches the existing function
signature of `enqueue_committed_alerts(alerts_created, conn)`.

---

## 9. Tests Required

### New file: `tests/test_wire_soar_enqueue_post_commit.py`

All tests use the Flask test client and mock `enqueue_committed_alerts` at the route
module's import namespace (`routes.ingest_routes.enqueue_committed_alerts`) to avoid
real DB queue inserts.

**T1 — Enqueue is called only after `conn.commit()`**
- Use a mock for `enqueue_committed_alerts` with a side effect that records call
  order relative to `conn.commit()`. Verify enqueue is called after commit, not before.
- Alternatively: verify that `conn.commit.call_count >= 1` before enqueue is called
  by injecting an ordered side-effect.

**T2 — Enqueue failure does not affect 201 response**
- Patch `enqueue_committed_alerts` to raise `RuntimeError("queue failure")`.
- POST a valid ingest event that triggers an alert.
- Assert response is 201 with `{"message": "Event added successfully", ...}`.
- Assert no 500 is returned.

**T3 — No enqueue on pre-commit error path**
- Patch `ingest_normalized_event` to raise an exception.
- POST a valid ingest event.
- Assert response is 500.
- Assert `enqueue_committed_alerts` was never called.

**T4 — No enqueue when `alerts_created` is empty**
- POST an event type that triggers no detection alerts (e.g., `normal_activity` on a
  non-web source type that bypasses `_generate_high_request_rate_alerts_core`).
- Assert `enqueue_committed_alerts` is called with an empty list (or verify it's
  called with `[]`).
- Assert second `conn.commit()` is still attempted (enqueue with empty list is a
  no-op but the commit path still runs).

**T5 — Batch route: enqueue receives full accumulated `alerts_created`**
- POST to `/ingest/azure` with a batch of 2 items, each producing one alert.
- Assert `enqueue_committed_alerts` is called once (not twice) with a list of 2 dicts.

**T6 — Enqueue is called once per request on single-item routes**
- POST to `/ingest`, `/ingest/web-log`, `/ingest/otlp` with valid payloads.
- Assert `enqueue_committed_alerts` call count is 1 for each.

**T7 — Second `conn.commit()` failure does not affect 201 response**
- Patch the second `conn.commit()` call to raise.
- Assert response is still 201.

**Regression guard:**
- After all new tests pass, run the full suite:
  `pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py`
- All must pass at the existing `116 passed, 2 warnings` baseline.

---

## 10. Module Import Required in `ingest_routes.py`

Add one import to `routes/ingest_routes.py`:

```python
from engines.soar_enqueue_orchestrator import enqueue_committed_alerts
```

This is the only new import. No other file's imports change.

---

## 11. Risks and Stop Conditions

**Risk 1 — Double commit on connection with unexpected state (LOW)**
After the first `conn.commit()`, if the connection has drifted into an error state
for any reason, the second `conn.commit()` (for queue rows) will raise. This is
caught by the enqueue `try/except` and logged. The 201 is still returned. No action
needed, but if this appears in logs repeatedly it signals a psycopg2 connection
pooling issue.

**Risk 2 — `execute_response_action()` still runs synchronously inside detection
(KNOWN, ACCEPTED)**
After this change, both `execute_response_action()` (inline, inside transaction) and
`enqueue_committed_alerts()` (post-commit) run for the same alert. This is the
intentional dual-execution state documented in the roadmap. The queue row's
idempotency key prevents the worker from re-running the action when it drains the
queue. This state persists until Phase 1 Step 3 (decoupling `execute_response_action`
from detection) — which is a separate spec.

**Risk 3 — `currval` context (LOW, but verify)**
`alert_id` is read via `currval` inside the detection functions before the commit.
After the commit, that value is stable — the row exists in the DB with that ID. The
detection function appends the already-read integer to the dict. By the time
`enqueue_committed_alerts` runs post-commit, it's working with a committed `alert_id`.
No `currval` is called post-commit.

**Stop conditions:**
- Any of the 6 core regression tests fail after adding fields to detection dicts.
- Any route test suite fails after wiring the enqueue calls.
- The `conn` object is found to be in a broken state after the second commit in tests.

If any of these occur: revert `detection_engine.py` and `ingest_routes.py` changes,
leave `enqueue_committed_alerts` import in place, and investigate before retrying.
