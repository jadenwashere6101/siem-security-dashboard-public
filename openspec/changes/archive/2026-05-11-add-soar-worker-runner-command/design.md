# Design: SOAR Worker Runner Command

---

## 1. Problem

The SOAR pipeline layers are in place:

- `response_actions_queue` schema and enqueue helper.
- `engines/soar_action_worker.py` — `process_next_action`, `process_batch`.
- `engines/soar_executor.py` — `SimulationExecutor`, `AdapterBackedExecutor`,
  validation.
- `engines/soar_errors.py` — `SkippedAction`, `RetryableActionError`.
- `integrations/soar_adapters/linux_firewall.py` — dry-run adapter.
- Post-commit enqueue wired to detection alerts.

There is no CLI-invocable way to process queued actions outside of the test
harness. Development and operational validation require writing throwaway scripts
or triggering test flows. A stable runner command is the missing piece.

---

## 2. Goal

A single, safe, manually invocable CLI command that:

1. Opens a database connection.
2. Selects an executor based on configuration.
3. Calls `process_batch` with a configured batch size.
4. Prints a structured summary.
5. Exits with a meaningful code.

The runner is a thin orchestration shell over existing, tested code. It
introduces no new business logic.

---

## 3. CLI and Module Placement

### Entry point

```
scripts/soar_worker_run.py
```

Invoked as:

```bash
python scripts/soar_worker_run.py
```

Or, if `__main__` is added:

```bash
python -m scripts.soar_worker_run
```

### Why `scripts/`

- `scripts/` is the established location for one-off operator tooling in this
  project.
- The runner is not a library module. It has a `main()` function and exits.
- It must not be importable as a library used by ingest or request flows.
- `engines/` is for reusable orchestration modules — the runner is not that.
- `core/` is for infrastructure (DB, IP helpers) — not appropriate.
- A root-level script is acceptable, but `scripts/` communicates intent.

### Module structure

```
scripts/
  soar_worker_run.py      ← NEW: CLI entry point, main(), summary printer

engines/
  soar_action_worker.py   ← existing, unchanged
  soar_executor.py        ← existing, unchanged
  soar_errors.py          ← existing, unchanged

integrations/
  soar_adapters/
    linux_firewall.py     ← existing, unchanged

core/
  response_action_queue_store.py  ← existing, unchanged
```

The runner imports from `engines/` and `core/`. It does not reach into
`integrations/soar_adapters/` directly — that is the registry/executor's job.

---

## 4. Execution Flow

```
START
  │
  ├─ Read config (env vars)
  ├─ Validate config (batch size ≤ max, mode is known value)
  ├─ Guard: refuse if inside Flask request context
  │
  ├─ Print header: mode, batch size, timestamp
  │
  ├─ Open DB connection (psycopg2, using existing app db config)
  │
  ├─ Select executor:
  │     SOAR_EXECUTION_MODE == "real"
  │       → build AdapterBackedExecutor from registry
  │     else (default)
  │       → SimulationExecutor()
  │
  ├─ Call: results = process_batch(conn, limit=batch_size, executor=executor)
  │
  ├─ Aggregate results:
  │     processed = len(results)
  │     success   = count where outcome == "success"
  │     failed    = count where outcome == "failed"
  │     skipped   = count where outcome == "skipped"
  │     requeued  = count where outcome == "requeued"
  │
  ├─ Print summary (see Section 6)
  │
  └─ Exit 0 (successful run, even if some actions failed)
       Exit 1 on: config error, DB connection failure, startup guard triggered
       Exit 2 on: unexpected uncaught exception
```

`process_batch` already handles individual action failures gracefully and
returns a list of result objects. The runner does not wrap each action in
additional try/except — it trusts the worker's existing error containment.

---

## 5. Configuration and Safety Defaults

All configuration is via environment variables. No config file, no CLI argument
parsing library required.

| Env Var | Default | Allowed Values | Purpose |
|---|---|---|---|
| `SOAR_EXECUTION_MODE` | `simulation` | `simulation`, `real` | Executor selection |
| `SOAR_RUNNER_BATCH_SIZE` | `10` | 1–50 | Actions per run |
| `SOAR_RUNNER_MAX_BATCH_SIZE` | `50` | fixed constant | Upper safety ceiling |

### Batch size rules

- Read `SOAR_RUNNER_BATCH_SIZE` from env, parse as int.
- If not set or empty: use default of `10`.
- If set but not a valid integer: exit 1 with clear error message.
- If set but > `SOAR_RUNNER_MAX_BATCH_SIZE` (50): clamp to 50 and log a
  warning. Do not exit — clamping is safer than blocking the run entirely.
- If set but < 1: exit 1 with clear error message.

The maximum of 50 is a constant in code, not an env var. It cannot be
overridden without a code change. This is intentional.

### Execution mode rules

- If `SOAR_EXECUTION_MODE` is unset or `simulation`: use `SimulationExecutor`.
- If `SOAR_EXECUTION_MODE=real`:
  - Require `SOAR_ADAPTER_BLOCK_IP` to be set (registry-level requirement).
  - Require the selected adapter to be explicitly enabled (e.g.
    `SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED=true`).
  - The runner does not validate adapter config directly — that is the
    registry's job. The runner only confirms `SOAR_EXECUTION_MODE=real` is
    intentional and logs it prominently before processing.
- Any unknown value for `SOAR_EXECUTION_MODE`: exit 1.

### Flask/ingest guard

At startup, before any DB operation, the runner must check it is not running
inside a Flask application context. The guard:

```python
try:
    from flask import current_app
    _ = current_app._get_current_object()
    # If this succeeds, we are inside a Flask context — refuse to run
    print("ERROR: soar_worker_run must not be invoked from inside a Flask request context.", file=sys.stderr)
    sys.exit(1)
except RuntimeError:
    pass  # No active Flask context — safe to proceed
```

This prevents the runner from being accidentally imported and called inside
ingest or a request handler.

---

## 6. Logging and Output

### Startup header (always printed)

```
=== SOAR Worker Runner ===
Mode:        simulation
Batch size:  10
Started at:  2026-05-06T14:32:00Z
=========================
```

If mode is `real`:

```
=== SOAR Worker Runner ===
Mode:        REAL [AdapterBackedExecutor]
Batch size:  10
Started at:  2026-05-06T14:32:00Z
WARNING: Real execution mode is active. Actions will be dispatched to adapters.
=========================
```

### Per-action logging

The runner does not print per-action detail itself. That is handled by:

- `engines/soar_action_worker.py` — claim/transition logging.
- `engines/soar_executor.py` — `[SIMULATED]` prefix logs.
- `integrations/soar_adapters/linux_firewall.py` — dry-run plan logs.

All of these use Python `logging` module at INFO/WARNING level. The runner
configures basic logging at startup so these messages reach stdout/stderr in
development.

### Exit summary (always printed, even on partial failure)

```
--- SOAR Runner Summary ---
Processed:  8
  Success:  5
  Failed:   1
  Skipped:  1
  Requeued: 1
Done.
```

If zero actions were processed:

```
--- SOAR Runner Summary ---
Processed:  0 (queue empty or all actions in terminal state)
Done.
```

### Logging setup

The runner calls `logging.basicConfig(level=logging.INFO)` unless the
environment already configures a logging handler. This is sufficient for
development. Production systemd wiring can redirect stdout/stderr to journald
without changes to this setup.

---

## 7. Database Connection

The runner opens its own DB connection using the same configuration as the
Flask app. It does not use Flask's `db` connection pool — it is running
outside of a Flask context.

Connection approach:

```python
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)
conn.autocommit = False
```

- `DATABASE_URL` is required. If not set: exit 1 with clear message.
- The connection is closed in a `finally` block regardless of outcome.
- The runner does not use a connection pool. One connection per run is
  sufficient for a manual batch runner.

---

## 8. Testing Strategy

Tests for the runner go in `tests/test_soar_worker_runner.py` (or equivalent
test directory).

### What to test

**Config validation**
- Default batch size is 10 when env var is unset.
- Batch size is clamped to 50 when set above 50.
- Batch size below 1 causes exit 1.
- Non-integer batch size causes exit 1.
- Unknown `SOAR_EXECUTION_MODE` value causes exit 1.

**Executor selection**
- `SOAR_EXECUTION_MODE=simulation` (or unset) selects `SimulationExecutor`.
- `SOAR_EXECUTION_MODE=real` selects `AdapterBackedExecutor`.

**Flask guard**
- Simulate an active Flask context — confirm the runner exits 1 without
  processing any actions.

**End-to-end simulation (DB-backed)**
- Seed queue with 3 pending `block_ip` rows (valid public IPs).
- Run `process_batch` via the runner's logic with `SimulationExecutor`.
- Assert summary counts: `processed=3`, `success=3`.
- Assert queue rows are in `success` state.
- Assert no `response_actions_log` entries were written (simulation mode
  does not write to that log — the worker's audit log call is for real
  actions).

**Empty queue**
- Run with an empty queue.
- Assert summary: `processed=0`, exit 0.

**Partial failure**
- Seed with 2 valid and 1 invalid (private IP) `block_ip` row.
- Assert summary: `processed=3`, `success=2`, `skipped=1`, exit 0.

**No external I/O**
- No test may open a real firewall command, network socket, or cloud client.
- Monkeypatch `process_batch` in unit-level tests to avoid DB dependency
  where DB is not relevant to the assertion.

**Regression guard**
- Existing `test_response_action_queue.py` tests remain green.
- Existing `test_soar_action_worker.py` tests remain green.
- Existing ingest/detection/correlation tests remain green.

---

## 9. Risks and Stop Conditions

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator sets `SOAR_EXECUTION_MODE=real` without reading docs | Medium | Prominent WARNING in header; adapter still has its own safety guards (dry-run flag, IP validation) |
| Batch size set very high and stalls DB | Low | Hard cap at 50 in code; cannot be raised without code change |
| Runner invoked from inside ingest via import | Low | Flask context guard at startup; scripts/ placement discourages import |
| `DATABASE_URL` missing in operator shell | Medium | Clear error message, exit 1 immediately |
| Confusion between `failed` and `skipped` in output | Low | Both are counted and labeled separately in summary |
| Real firewall adapter accidentally registered | Low | Adapter requires `SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED=true` and `SOAR_EXECUTION_MODE=real` simultaneously |

### Stop conditions

Stop implementation and re-plan if any of the following arise:

- The runner requires changes to `engines/soar_action_worker.py` beyond
  importing existing public functions.
- The runner requires changes to `core/response_action_queue_store.py`.
- The runner requires any new database column, table, or schema migration.
- The runner is being wired to run automatically on any event (ingest,
  detection, correlation, HTTP request).
- The runner requires `subprocess`, shell execution, `sudo`, or any OS-level
  privilege.
- Real firewall actions are being triggered in tests.
- The batch processing introduces any non-determinism or threading.

---

## 10. Future Systemd / Scheduler Phase

This runner is designed to be wrapped without code changes.

A future systemd service unit would look like:

```ini
[Unit]
Description=SOAR Action Worker

[Service]
ExecStart=/usr/bin/python scripts/soar_worker_run.py
Environment=SOAR_EXECUTION_MODE=simulation
Environment=SOAR_RUNNER_BATCH_SIZE=25
Restart=on-success
RuntimeMaxSec=60
```

A future cron job:

```
*/5 * * * * cd /app && python scripts/soar_worker_run.py >> /var/log/soar_runner.log 2>&1
```

Neither of these requires any code change to the runner. The runner's clean
exit code, configurable batch size, and stdout/stderr output are already
compatible with both patterns.

The runner is explicitly not a daemon. It processes one batch and exits. A
scheduler calls it repeatedly. This is intentional — it keeps the runner
testable, observable, and free of signal handling, pid file management, and
restart logic.

---

## 11. Module Dependency Summary

```
scripts/soar_worker_run.py
  ├── engines.soar_action_worker   (process_batch)
  ├── engines.soar_executor        (SimulationExecutor, AdapterBackedExecutor)
  ├── engines.soar_errors          (SkippedAction, RetryableActionError — not directly, via worker)
  └── os, sys, logging, psycopg2   (stdlib + driver)

No dependency on:
  ├── Flask app or current_app (runner refuses if context is active)
  ├── routes/
  ├── core/ip_helpers.py (IP validation is the executor's job)
  └── integrations/soar_adapters/ (runner does not select adapters directly)
```
