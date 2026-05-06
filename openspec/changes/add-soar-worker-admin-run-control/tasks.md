# Tasks: SOAR Worker Admin Run Control

Implement later as a small backend-only control.

---

## Task 1 — Inspect current worker and admin route contracts

Inspect:

- `engines/soar_action_worker.py`
- `engines/soar_executor.py`
- `scripts/soar_worker_run.py`
- `routes/admin_routes.py`
- `tests/test_soar_queue_visibility_api.py`

Confirm:

- `process_batch(conn, limit, executor)` is the only worker entry point needed
- `SimulationExecutor` can be used directly
- existing admin auth pattern is `login_required` + `super_admin_required`

---

## Task 2 — Add route constants/helpers

In `routes/admin_routes.py`, add:

- `DEFAULT_ADMIN_RUN_BATCH_SIZE = 10`
- `MAX_ADMIN_RUN_BATCH_SIZE = 25`
- batch-size parser/validator
- result summary aggregator

Keep helpers local unless reuse is clearly valuable.

---

## Task 3 — Add run-once endpoint

Add:

```text
POST /admin/soar/worker/run-once
```

Rules:

- login required
- super admin required
- open DB connection
- instantiate `SimulationExecutor()`
- call `process_batch(conn, limit=batch_size, executor=SimulationExecutor())`
- return summary and results
- do not call CLI script
- do not loop
- do not spawn threads
- do not use real adapters

---

## Task 4 — Enforce simulation-only behavior

Reject request bodies that try to set:

```json
{"mode": "real"}
```

Return `400`.

Ignore environment `SOAR_EXECUTION_MODE` for this endpoint. Tests should set the
env var to `real` and confirm the response still reports `"mode": "simulation"`.

---

## Task 5 — Add audit/logging

If `log_audit_event()` fits the current route pattern, write an audit event:

```text
SOAR_WORKER_RUN_ONCE
```

Include:

- actor
- role
- request path/method
- source IP
- requested batch size
- effective batch size
- summary counts

Do not include secrets or raw errors.

---

## Task 6 — Add tests

Create:

```text
tests/test_soar_worker_admin_run_control.py
```

Cover:

- unauthenticated rejected
- viewer/analyst rejected
- super admin accepted
- empty body uses default batch size
- excessive batch size clamps to hard max
- invalid batch size returns `400`
- `"mode": "real"` returns `400`
- env `SOAR_EXECUTION_MODE=real` does not enable real execution
- response shape is stable
- empty queue summary reports processed `0`
- pending rows are processed normally
- terminal rows are not mutated
- audit event is written if implemented

---

## Verification

Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py
```

Run:

```bash
python3 -m pytest tests/test_soar_worker_admin_run_control.py -x --tb=short -v
```

Then run the related SOAR/admin checks:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py tests/test_response_action_queue.py tests/test_soar_executor.py -x --tb=short -v
```

---

## Explicit Non-Tasks

Do not:

- add frontend button
- add scheduler/systemd
- add daemon
- enable real firewall execution
- add playbooks/incidents
- add retry/replay individual item controls
- change ingest/detection/correlation
- change schema

