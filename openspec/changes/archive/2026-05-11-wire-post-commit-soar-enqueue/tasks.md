# Tasks: Wire Post-Commit SOAR Enqueue into Ingest Routes

Follow these tasks in exact order. Do not proceed past a task until its verification
passes. If a verification fails, revert the changes for that task before
investigating.

---

## Task 1 — Augment `alerts_created` dicts in `engines/detection_engine.py`

**Scope:** `engines/detection_engine.py` only. No other file.

For each of the 7 detection functions, find the `alerts_created.append({...})` call
and add `"alert_id": alert_id` and `"response_action": response_action` to the dict.

Both `alert_id` and `response_action` are already in scope at each `.append()` call —
`alert_id` is assigned from `currval` immediately before `execute_response_action()`,
and `response_action` is assigned from `determine_response_action()` earlier in the
same loop body. No new variables, no new DB queries, no logic changes.

Functions to update:

1. `_generate_failed_login_alerts_core`
   - Current: `{"source_ip": source_ip, "attempts": attempts}`
   - After: `{"source_ip": source_ip, "attempts": attempts, "alert_id": alert_id, "response_action": response_action}`

2. `_generate_http_error_alerts_core`
   - Current: `{"source_ip": source_ip, "attempts": attempts}`
   - After: same pattern

3. `_generate_port_scan_alerts_core`
   - Current: `{"source_ip": source_ip, "attempts": attempts}`
   - After: same pattern

4. `_generate_password_spraying_alerts_core`
   - Current: `{"source_ip": source_ip, "distinct_username_count": distinct_username_count}`
   - After: `{"source_ip": source_ip, "distinct_username_count": distinct_username_count, "alert_id": alert_id, "response_action": response_action}`

5. `_generate_successful_login_after_spray_alerts_core`
   - Current: `{"source_ip": source_ip, "success_at": str(success_at)}`
   - After: `{"source_ip": source_ip, "success_at": str(success_at), "alert_id": alert_id, "response_action": response_action}`

6. `_generate_application_exception_alerts_core`
   - Current: `{"source_ip": source_ip, "attempts": attempts}`
   - After: same as (1)

7. `_generate_high_request_rate_alerts_core`
   - Current: `{"source_ip": source_ip, "attempts": attempts}`
   - After: same as (1)

**Verify Task 1:**
```bash
python3 -m py_compile engines/detection_engine.py
```
```bash
pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py -v
```
All tests must pass. No test file was changed — the existing assertions are all
field-by-field key access (not full-dict equality), so adding new keys cannot break them.

**Stop condition:** If any test fails after this change, the `.append()` dict was
edited incorrectly. Revert `detection_engine.py` and inspect the failing assertion
before retrying.

---

## Task 2 — Add import and enqueue block to `routes/ingest_routes.py`

**Scope:** `routes/ingest_routes.py` only. No other file.

**Step 2a — Add import**

Add one import to the existing import block:

```python
from engines.soar_enqueue_orchestrator import enqueue_committed_alerts
```

Place it with the other `engines` imports (after `from engines.ingest_engine import
ingest_normalized_event`).

**Step 2b — Wire enqueue in `add_event` (POST /ingest)**

Locate the block:
```python
        conn.commit()

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201
```

Replace with:
```python
        conn.commit()

        try:
            enqueue_committed_alerts(alerts_created, conn)
            conn.commit()
        except Exception as enqueue_error:
            current_app.logger.error(
                "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
                enqueue_error,
            )

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201
```

**Step 2c — Wire enqueue in `add_web_log_event` (POST /ingest/web-log)**

Locate the block:
```python
        conn.commit()

        return jsonify({
            "message": "Event added successfully",
            "alerts_created": alerts_created
        }), 201
```

Apply the identical enqueue block between `conn.commit()` and the return.

**Step 2d — Wire enqueue in `add_azure_event` (POST /ingest/azure)**

Locate the block (after the `alerts_created` loop finishes):
```python
        conn.commit()

        success_message = "Events added successfully" if len(normalized_events) > 1 else "Event added successfully"
        return jsonify({
            "message": success_message,
            "alerts_created": alerts_created,
        }), 201
```

Apply the identical enqueue block between `conn.commit()` and the `success_message`
assignment.

**Step 2e — Wire enqueue in `add_otel_event` (POST /ingest/otlp)**

Same as Step 2d — locate the equivalent block and apply the enqueue pattern.

**Verify Task 2:**
```bash
python3 -m py_compile routes/ingest_routes.py
```
```bash
pytest tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```
All must pass. The existing ingest contract tests do not assert on the
`alerts_created` dict shape and will not be affected by the new import or the
enqueue block (which is guarded and never raises to the outer handler).

**Stop condition:** If `test_ingest_api_contracts.py` fails after this change,
check whether the import or enqueue block was placed inside the wrong scope or
accidentally altered a `return` statement. Revert and inspect the diff.

---

## Task 3 — Write new tests in `tests/test_wire_soar_enqueue_post_commit.py`

**Scope:** New test file only. No existing test file is modified.

All tests patch `enqueue_committed_alerts` at the route module import path:
`routes.ingest_routes.enqueue_committed_alerts`. Use the Flask test client from
`conftest.py` fixtures.

**T1 — Enqueue called after commit, not before**

```
- Patch enqueue_committed_alerts with a side effect that records whether
  conn.commit was already called.
- POST to /ingest with a valid payload that triggers no alert (to avoid real DB work).
- Assert enqueue was called.
- Assert at the time of the enqueue call, the commit had already been invoked.
```

Implementation hint: use a `MagicMock` with a `side_effect` function that captures
the `conn.commit.call_count` at the moment of the enqueue call. If `call_count >= 1`
at that moment, the ordering is correct. This requires injecting a mock conn — use
the existing `patch("routes.ingest_routes.get_db_connection")` pattern from
`conftest.py` or `test_ingest_api_contracts.py`.

**T2 — Enqueue failure does not affect 201**

```
- Patch enqueue_committed_alerts to raise RuntimeError("queue unavailable").
- POST to /ingest with a valid payload.
- Assert response status is 201.
- Assert response JSON contains "message": "Event added successfully".
- Assert response does not contain "error".
```

**T3 — No enqueue on pre-commit error path**

```
- Patch ingest_normalized_event to raise RuntimeError("detection failed").
- POST to /ingest with a valid payload.
- Assert response status is 500.
- Assert enqueue_committed_alerts was never called.
```

**T4 — Enqueue receives empty list when no alerts created**

```
- Patch ingest_normalized_event to return [].
- POST to /ingest with a valid payload.
- Assert enqueue_committed_alerts was called once with an empty list as first argument.
```

**T5 — Batch route: enqueue called once with full accumulated list**

```
- Patch ingest_normalized_event to return [{"alert_id": 1, "source_ip": "1.2.3.4",
  "response_action": "block_ip", "attempts": 3}] for every call.
- POST to /ingest/azure with a batch of 2 items.
- Assert enqueue_committed_alerts was called exactly once.
- Assert the first positional argument to that call is a list of length 2.
```

**T6 — Second conn.commit() called after enqueue**

```
- Patch enqueue_committed_alerts to return [].
- Use a mock conn that records commit call count.
- POST to /ingest with a valid payload.
- Assert conn.commit was called at least twice (once for ingest tx, once for queue).
```

**T7 — Second conn.commit() failure does not affect 201**

```
- Patch enqueue_committed_alerts to return [] (success).
- Patch conn.commit to raise on the second call only
  (side_effect=[None, RuntimeError("commit failed")]).
- POST to /ingest with a valid payload.
- Assert response is 201.
```

**Verify Task 3:**
```bash
pytest tests/test_wire_soar_enqueue_post_commit.py -v
```
All 7 tests must pass.

---

## Task 4 — Full regression sweep

Run the complete suite:

```bash
pytest tests/test_failed_login_detection.py \
       tests/test_password_spraying_detection.py \
       tests/test_correlated_activity.py \
       tests/test_targeted_correlation.py \
       tests/test_ingest_api_contracts.py \
       tests/test_alert_mutation_api_contracts.py \
       tests/test_wire_soar_enqueue_post_commit.py \
       -v
```

Then run the full suite:

```bash
python3 -m pytest -v -rs
```

Expected result: all existing tests pass, new tests pass, total count increases by
the number of tests added in Task 3. The `116 passed, 2 warnings` baseline must be
fully intact.

**Stop condition:** Any pre-existing test that was passing before this change is now
failing. Identify which task introduced the regression, revert that task, and
investigate before proceeding.

---

## Out of Scope for This Change

The following items are explicitly deferred and must NOT be implemented here:

- Removing or moving `execute_response_action()` out of detection functions. It
  still runs synchronously inside the transaction. The roadmap addresses this in a
  separate step (Phase 1 Step 3).
- Enqueueing correlation alerts. Requires changing correlation function return types.
- Any playbook, incident, or notification work.
- Any frontend changes.
- Any firewall or external integration.
- Any changes to `engines/correlation_engine.py`.
- Any changes to `engines/ingest_engine.py`.
- Any changes to existing test files.
