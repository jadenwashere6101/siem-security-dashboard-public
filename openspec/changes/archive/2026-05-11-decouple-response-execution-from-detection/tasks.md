# Tasks: Decouple Response Execution from Detection

Follow these tasks in order. Do not proceed past a task until its verification
passes. If a task fails, revert that task before continuing.

This change is intentionally narrow: detection execution is decoupled; correlation
and manual execution are preserved.

---

## Task 1 — Confirm current call-site inventory

Run:

```bash
rg -n "execute_response_action" core engines routes tests
```

Confirm production call sites:

- `core/ip_helpers.py` defines `execute_response_action()`.
- `engines/detection_engine.py` imports and calls it 7 times.
- `engines/correlation_engine.py` imports and calls it 2 times.
- `routes/alert_mutation_routes.py` imports and calls it 1 time.

Scope decision:

- Continue only with the 7 detection calls.
- Do not edit `engines/correlation_engine.py`.
- Do not edit `routes/alert_mutation_routes.py`.

Verification:

```bash
rg -n "execute_response_action" engines/detection_engine.py engines/correlation_engine.py routes/alert_mutation_routes.py
```

---

## Task 2 — Verify queued execution preserves audit logging

Before removing detection-side audit writes, verify the queue/worker path records
executed actions in `response_actions_log`.

Inspect:

- `engines/soar_executor.py`
- `engines/soar_action_worker.py`
- `tests/test_soar_executor.py`
- `tests/test_response_action_queue.py`

Expected result:

- A completed queued action has an execution audit row in `response_actions_log`.

If this is already true:

- Do not change worker/executor code in this task.
- Move to Task 3.

If this is missing:

- Add the minimum worker/executor-layer audit behavior needed to preserve
  `response_actions_log`.
- Do not put audit logging back into detection.
- Do not change queue schema.

Verification:

```bash
python3 -m pytest tests/test_soar_executor.py tests/test_response_action_queue.py -v
```

Stop condition:

- If queued execution cannot preserve `response_actions_log`, do not remove
  detection-side execution yet.

---

## Task 3 — Remove synchronous execution from detection only

Scope:

- `engines/detection_engine.py` only.

For each of the 7 detection functions, remove the block that:

1. calls `execute_response_action(...)`
2. assigns `execution_status`
3. updates `alerts.response_status` to `execution_status`

Functions:

1. `_generate_failed_login_alerts_core`
2. `_generate_http_error_alerts_core`
3. `_generate_port_scan_alerts_core`
4. `_generate_password_spraying_alerts_core`
5. `_generate_successful_login_after_spray_alerts_core`
6. `_generate_application_exception_alerts_core`
7. `_generate_high_request_rate_alerts_core`

Preserve in every function:

- `response_status = "pending"` before the alert insert
- `response_action = determine_response_action(...)`
- alert insert SQL
- `currval()` and `alert_id`
- `alerts_created.append(...)`
- `alert_id` and `response_action` in the returned dict

After removing all calls, update the import:

```python
from core.ip_helpers import determine_response_action, lookup_ip_reputation
```

Verification:

```bash
python3 -m py_compile engines/detection_engine.py
```

```bash
rg -n "execute_response_action" engines/detection_engine.py
```

Expected `rg` result: no matches.

Stop condition:

- If any detection function no longer returns `alert_id` and `response_action`,
  revert this task.

---

## Task 4 — Update detection tests for deferred execution

Scope:

- Detection test files only.

Update these files:

- `tests/test_failed_login_detection.py`
- `tests/test_http_error_detection.py`
- `tests/test_port_scan_detection.py`
- `tests/test_password_spraying_detection.py`
- `tests/test_successful_login_after_spray_detection.py`
- `tests/test_application_exception_detection.py`
- `tests/test_high_request_rate_detection.py`

Expected test changes:

- Change detection-created alert `response_status` expectations from
  `"executed"` to `"pending"`.
- Remove assertions that detection immediately writes a `response_actions_log`
  row.
- Add or keep assertions that `alerts_created[0]["alert_id"]` is present.
- Add or keep assertions that `alerts_created[0]["response_action"]` is present.
- Add a focused assertion that detection does not create a synchronous
  `response_actions_log` row.

Do not update:

- `tests/test_correlated_activity.py`
- `tests/test_targeted_correlation.py`
- `tests/test_alert_mutation_api_contracts.py`

Verification:

```bash
python3 -m pytest \
  tests/test_failed_login_detection.py \
  tests/test_http_error_detection.py \
  tests/test_port_scan_detection.py \
  tests/test_password_spraying_detection.py \
  tests/test_successful_login_after_spray_detection.py \
  tests/test_application_exception_detection.py \
  tests/test_high_request_rate_detection.py \
  -v
```

---

## Task 5 — Strengthen post-commit enqueue coverage

Scope:

- Prefer `tests/test_wire_soar_enqueue_post_commit.py`.
- Create a new focused test file only if the existing file becomes crowded.

Add coverage proving:

- route-level enqueue still receives detection alert dicts with `alert_id`,
  `source_ip`, and `response_action`
- enqueue happens only after route-level `conn.commit()`
- enqueue failure after commit still returns the existing successful ingest
  response
- detection no longer performs synchronous execution

Do not require queue rows for correlation alerts in this task.

Verification:

```bash
python3 -m pytest tests/test_wire_soar_enqueue_post_commit.py -v
```

---

## Task 6 — Verify correlation and manual execution remain unchanged

Run:

```bash
python3 -m pytest \
  tests/test_correlated_activity.py \
  tests/test_targeted_correlation.py \
  tests/test_alert_mutation_api_contracts.py \
  -v
```

Expected result:

- These tests remain green without changing correlation or manual route behavior.
- Correlation-created alerts may still have immediate `response_actions_log`
  behavior.
- Manual alert execution remains synchronous and can still create blocklist records
  when requested.

Stop condition:

- If these tests require behavior changes, stop and re-scope. This change must not
  modify correlation or manual execution.

---

## Task 7 — Run ingest and queue regression checks

Run:

```bash
python3 -m pytest \
  tests/test_ingest_api_contracts.py \
  tests/test_ingest_normalized_event.py \
  tests/test_response_action_queue.py \
  tests/test_soar_enqueue_orchestrator.py \
  tests/test_soar_executor.py \
  -v
```

Expected result:

- Ingest response shapes remain stable.
- `alerts_created` still carries queue-required metadata.
- Queue idempotency still works.
- SOAR executor/worker tests own execution audit behavior.

---

## Task 8 — Full regression

Run:

```bash
python3 -m pytest -v -rs
```

Expected result:

- Full suite passes.
- No frontend tests or files are involved.
- No schema migration is required.

---

## Rollback tasks

If implementation causes unacceptable queue/audit gaps:

1. Restore the detection-engine import of `execute_response_action`.
2. Restore the 7 removed execution/update blocks in `engines/detection_engine.py`.
3. Restore detection test expectations for synchronous `"executed"` status and
   immediate `response_actions_log` rows.
4. Keep post-commit enqueue code unless it is the source of the failure.

No queue schema rollback is needed.

---

## Explicit non-tasks

Do not perform these in this change:

- Edit `engines/correlation_engine.py`.
- Edit queue schema.
- Add playbooks.
- Add incidents.
- Add frontend queue UI.
- Add real firewall execution.
- Queue correlation alerts.
- Change manual alert execution behavior.
