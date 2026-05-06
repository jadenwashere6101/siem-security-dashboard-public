# Tasks: SOAR Worker Runner Command

---

## Task 1 — Create `scripts/soar_worker_run.py` skeleton

Create `scripts/soar_worker_run.py` with:

- `main()` function.
- `if __name__ == "__main__": main()` guard.
- Imports: `os`, `sys`, `logging`, `psycopg2`, `psycopg2.extras.RealDictCursor`.
- Import of `process_batch` from `engines.soar_action_worker`.
- Import of `SimulationExecutor` from `engines.soar_executor`.

Do not implement any logic yet. Just establish the module and confirm it is
importable without side effects.

**Acceptance:** `python -c "import scripts.soar_worker_run"` exits 0 with no
output.

---

## Task 2 — Implement Flask context guard

In `main()`, before any DB or config logic:

- Attempt to import `flask.current_app` and access `._get_current_object()`.
- If it succeeds (active Flask context), print an error to stderr and
  `sys.exit(1)`.
- If it raises `RuntimeError` (no active context), continue.

**Acceptance:** A unit test that monkeypatches an active Flask context confirms
the runner exits 1 without calling `process_batch`.

---

## Task 3 — Implement config reading and validation

Read from environment:

- `SOAR_EXECUTION_MODE` — default `"simulation"`.
- `SOAR_RUNNER_BATCH_SIZE` — default `10`.

Validate:

- `SOAR_EXECUTION_MODE` must be `"simulation"` or `"real"`. Unknown value →
  exit 1.
- `SOAR_RUNNER_BATCH_SIZE` must parse as int. Non-integer → exit 1.
- `SOAR_RUNNER_BATCH_SIZE` must be ≥ 1. Below 1 → exit 1.
- `SOAR_RUNNER_BATCH_SIZE` must be ≤ 50 (constant, not configurable). Above 50
  → clamp to 50 and log a WARNING.

**Acceptance:** Unit tests for all six config cases (default, valid, clamp,
below-1, non-integer, unknown mode) pass without a DB connection.

---

## Task 4 — Implement startup header printer

Before any processing, print to stdout:

```
=== SOAR Worker Runner ===
Mode:        <mode>
Batch size:  <batch_size>
Started at:  <ISO 8601 UTC timestamp>
=========================
```

If mode is `real`, append:

```
WARNING: Real execution mode is active. Actions will be dispatched to adapters.
```

**Acceptance:** Header appears in output for both `simulation` and `real` mode
runs in tests. `real` mode run includes the WARNING line.

---

## Task 5 — Implement DB connection setup

Open a `psycopg2` connection using `DATABASE_URL` from env:

- If `DATABASE_URL` is not set → exit 1 with clear message.
- Use `RealDictCursor`.
- Set `autocommit = False`.
- Wrap in a `try/finally` so `conn.close()` is always called.

**Acceptance:** Unit test monkeypatches `psycopg2.connect` to confirm it is
called with `DATABASE_URL`. Test for missing `DATABASE_URL` confirms exit 1.

---

## Task 6 — Implement executor selection

After config is validated:

- If `SOAR_EXECUTION_MODE == "simulation"`: instantiate `SimulationExecutor()`.
- If `SOAR_EXECUTION_MODE == "real"`: instantiate `AdapterBackedExecutor` from
  the adapter registry using existing registry/config helpers. The runner does
  not configure adapters directly — it defers to the registry.

**Acceptance:** Unit test confirms `SimulationExecutor` is selected by default.
Unit test confirms `AdapterBackedExecutor` is selected when `real` is set
(monkeypatch registry).

---

## Task 7 — Implement `process_batch` call and result aggregation

After executor selection and DB connection:

```python
results = process_batch(conn, limit=batch_size, executor=executor)
```

Aggregate results:

```python
processed = len(results)
success   = sum(1 for r in results if r["outcome"] == "success")
failed    = sum(1 for r in results if r["outcome"] == "failed")
skipped   = sum(1 for r in results if r["outcome"] == "skipped")
requeued  = sum(1 for r in results if r["outcome"] == "requeued")
```

Field name `"outcome"` must match what `process_batch` actually returns. Verify
against `engines/soar_action_worker.py` before implementing.

**Acceptance:** Aggregation logic is unit-tested with a mocked `process_batch`
returning a known list of result dicts.

---

## Task 8 — Implement exit summary printer

After aggregation, always print to stdout:

```
--- SOAR Runner Summary ---
Processed:  <n>
  Success:  <n>
  Failed:   <n>
  Skipped:  <n>
  Requeued: <n>
Done.
```

If `processed == 0`:

```
--- SOAR Runner Summary ---
Processed:  0 (queue empty or all actions in terminal state)
Done.
```

**Acceptance:** Summary output is captured in tests for both zero and non-zero
result cases.

---

## Task 9 — Implement exit codes

- Exit 0: `process_batch` returned (even if some actions failed/skipped).
- Exit 1: config error, missing `DATABASE_URL`, Flask guard triggered, DB
  connection failure, unknown execution mode.
- Exit 2: uncaught exception from `process_batch` or aggregation. Wrap the
  batch call in a top-level `except Exception` that prints the traceback and
  exits 2.

**Acceptance:** Unit tests confirm exit codes for all three conditions.

---

## Task 10 — DB-backed end-to-end test (simulation)

In `tests/test_soar_worker_runner.py` (or closest equivalent test file):

- Seed 3 pending `block_ip` queue rows with valid public IPs.
- Call the runner's batch logic directly (not via subprocess) with
  `SimulationExecutor` and a real DB connection.
- Assert: `processed=3`, `success=3`, `failed=0`, `skipped=0`, `requeued=0`.
- Assert: all 3 queue rows are in `success` state.
- Assert: no new `response_actions_log` entries were written during the run.

---

## Task 11 — DB-backed partial failure test (simulation)

- Seed 2 valid `block_ip` rows and 1 `block_ip` row with a private IP
  (`10.0.0.1`).
- Run runner batch logic with `SimulationExecutor`.
- Assert: `processed=3`, `success=2`, `skipped=1`.
- Assert: the private IP row is in `skipped` state.

---

## Task 12 — Empty queue test

- Run with no pending queue rows.
- Assert: `processed=0`, exit 0.
- Assert: summary includes "queue empty" language.

---

## Task 13 — Regression check

Confirm that the following existing test suites remain green after the runner is
added:

- `test_response_action_queue.py`
- `test_soar_action_worker.py`
- Ingest/detection/correlation test suites.

No existing test file may be modified to accommodate the runner. If a conflict
arises, stop and re-plan.

---

## Task 14 — Review against stop conditions

Before marking this change complete, verify:

- `engines/soar_action_worker.py` was not modified.
- `core/response_action_queue_store.py` was not modified.
- No new DB schema changes were introduced.
- No subprocess, shell execution, or `sudo` is present anywhere in the runner.
- No real firewall commands are triggered by any test.
- The runner is not wired to any ingest, detection, or request flow.

If any of these are violated, stop. Do not work around them.
