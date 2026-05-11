# Design: Improve SOAR Worker Runner Visibility

---

## 1. Current State

`scripts/soar_worker_run.py` exists and is fully functional when driven by env
vars. The specific gaps this change addresses:

**Arg wiring is dead code.** `argparse` is imported. `--batch-size` is defined
on the parser. But `parser.parse_known_args()` is called and its return value
is never used. CLI args have no effect today. `_load_and_validate_config()`
reads only env vars.

**No `--mode` arg.** Mode must be set via `SOAR_EXECUTION_MODE` env var.

**No `--json` flag.** All output is human-readable plain text. Tests that verify
output content use string matching, which is fragile.

**No queue visibility.** There is no way to see how many actions are pending,
running, or stuck without writing a manual SQL query or triggering processing.

**`core/response_action_queue_store.py` has no read-only count function.**
Every exported function either claims a row (mutating) or looks up a single
row by ID. A status count query does not exist.

---

## 2. Goal

Deliver four targeted improvements with no business logic changes:

1. Wire CLI args so they override env vars for `--batch-size` and new `--mode`.
2. Add `--json` output mode.
3. Add `--dry-run-info` visibility-only mode.
4. Add the supporting read-only count helper to the queue store.

---

## 3. Argument Parsing Design

### Precedence rule

For each configurable value, the resolution order is:

```
CLI arg (if provided)  >  env var (if set)  >  hardcoded default
```

This is implemented inside `_load_and_validate_config()`. The function must
accept an `args` parameter (the parsed `argparse.Namespace`) and apply the
precedence logic inline. It must not call `parse_args()` itself — that stays
in `main()`.

### Updated arg definitions

Replace `parser.parse_known_args()` call with `parser.parse_args()`.

```python
parser = argparse.ArgumentParser(description="Run one SOAR worker batch and exit.")

parser.add_argument(
    "--batch-size",
    type=int,
    default=None,
    help=f"Number of actions to process (1–{MAX_BATCH_SIZE}). Overrides SOAR_RUNNER_BATCH_SIZE.",
)
parser.add_argument(
    "--mode",
    choices=["simulation", "real"],
    default=None,
    help="Execution mode. Overrides SOAR_EXECUTION_MODE.",
)
parser.add_argument(
    "--json",
    action="store_true",
    default=False,
    help="Emit all output as a single JSON object.",
)
parser.add_argument(
    "--dry-run-info",
    action="store_true",
    default=False,
    help="Print queue status counts and exit without processing any actions.",
)
```

### Precedence implementation inside `_load_and_validate_config(args)`

```python
# Mode
raw_mode = args.mode or os.getenv("SOAR_EXECUTION_MODE", "simulation").strip().lower()

# Batch size
if args.batch_size is not None:
    raw_batch_size = str(args.batch_size)
else:
    raw_batch_size = os.getenv("SOAR_RUNNER_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)).strip()
```

Validation rules are unchanged from the existing implementation.

---

## 4. `--dry-run-info` Mode

### Purpose

Show queue health at a glance without touching any rows.

### Behavior

When `--dry-run-info` is passed:

1. Flask context guard runs (same as normal mode).
2. Config is NOT loaded (no mode/batch-size needed).
3. DB connection is opened (same as normal mode).
4. `get_queue_status_counts(conn)` is called (new read-only function, see
   Section 7).
5. Output is printed (plain text or JSON depending on `--json`).
6. Exit 0.

`process_batch` is never called. No rows are claimed or modified.

### Plain text output

```
=== SOAR Queue Status ===
  Pending:  12
  Running:   0
  Failed:    3
  Skipped:  47
  Success: 198
=========================
```

### JSON output (`--dry-run-info --json`)

```json
{
  "mode": "dry_run_info",
  "queue_counts": {
    "pending": 12,
    "running": 0,
    "failed": 3,
    "skipped": 47,
    "success": 198
  }
}
```

### Safety properties

- Read-only. `SELECT COUNT(*) GROUP BY status` with no `FOR UPDATE`.
- No retry count increment.
- No row state changes.
- Not blocked by `--mode` or `--batch-size` (those args are ignored when
  `--dry-run-info` is set).
- `--dry-run-info` and normal run are mutually exclusive branches in `main()`.

---

## 5. `--json` Output Mode

When `--json` is passed, all output is written to stdout as a single JSON
object after processing completes. Intermediate progress lines are suppressed.

This applies to both normal processing and `--dry-run-info`.

### Normal processing JSON output schema

```json
{
  "mode": "simulation",
  "batch_size": 10,
  "started_at": "2026-05-06T14:32:00Z",
  "results": [
    {
      "queue_id": 42,
      "prior_status": "pending",
      "new_status": "success",
      "outcome": "success",
      "retryable": false,
      "retry_count": 0,
      "max_retries": 3,
      "error_code": null,
      "reason": null,
      "message": "Simulated IP block for 8.8.8.8"
    }
  ],
  "summary": {
    "processed": 1,
    "success": 1,
    "failed": 0,
    "skipped": 0,
    "requeued": 0
  }
}
```

`results` is the raw list returned by `process_batch`. Each item is already a
dict — the runner serializes it with `json.dumps(..., default=str)` to handle
`datetime` fields.

### Empty queue JSON output

```json
{
  "mode": "simulation",
  "batch_size": 10,
  "started_at": "2026-05-06T14:32:00Z",
  "results": [],
  "summary": {
    "processed": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "requeued": 0
  }
}
```

### Error JSON output (config/startup errors)

When `--json` is passed and a `RunnerConfigError` occurs before processing:

```json
{
  "error": "SOAR_EXECUTION_MODE must be one of ['real', 'simulation']; got 'invalid'"
}
```

Exit code is still 1.

### Implementation note

The runner accumulates output when `--json` is set rather than printing
incrementally. Specifically:

- The header dict is built but not printed.
- `process_batch` runs normally.
- After `_aggregate_results`, a single `json.dumps()` call writes the complete
  document.
- Logging calls (`logging.info`, `logging.warning`) are unaffected by `--json`
  — they go to stderr via the logging framework and do not pollute stdout.

The worker and executor `logging.info` calls already go through the logging
module (not `print`) so they naturally land on stderr. No suppression is needed.

---

## 6. Updated `main()` Control Flow

```
START
  │
  ├─ parser.parse_args()
  │
  ├─ Guard: Flask context check (same as before)
  │
  ├─ Branch: --dry-run-info?
  │     YES:
  │       ├─ Open DB connection
  │       ├─ get_queue_status_counts(conn)
  │       ├─ Print counts (plain or JSON)
  │       └─ Exit 0
  │
  │     NO (normal processing):
  │       ├─ _load_and_validate_config(args)
  │       ├─ _print_start_header(mode, batch_size)   [suppressed if --json]
  │       ├─ _read_database_url()
  │       ├─ _build_executor(mode)
  │       ├─ Open DB connection
  │       ├─ process_batch(conn, limit=batch_size, executor=executor)
  │       ├─ _aggregate_results(results)
  │       ├─ _print_summary(counts)   [or json.dumps(...)]
  │       └─ Exit 0 (or 1/2 on error)
```

---

## 7. Queue Count Helper (`core/response_action_queue_store.py`)

Add one new function. No existing function is modified.

```python
def get_queue_status_counts(conn):
    """
    Returns a dict of {status: count} for all statuses present in the queue.
    Statuses with zero rows are not included.
    Read-only — no FOR UPDATE, no state changes.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM response_actions_queue
            GROUP BY status
            """
        )
        return {row[0]: row[1] for row in cur.fetchall()}
```

The runner normalizes this dict before displaying, ensuring all expected
statuses appear (defaulting absent ones to 0):

```python
KNOWN_STATUSES = ["pending", "running", "failed", "skipped", "success"]

def _normalize_counts(raw):
    return {s: raw.get(s, 0) for s in KNOWN_STATUSES}
```

`_normalize_counts` lives in the runner, not the store. The store function
returns raw DB counts. Presentation logic stays out of the store.

---

## 8. File Change Surface

| File | Change |
|---|---|
| `scripts/soar_worker_run.py` | Wire arg parsing; add `--mode`, `--json`, `--dry-run-info`; update `_load_and_validate_config` signature; add JSON output path; add dry-run-info branch |
| `core/response_action_queue_store.py` | Add `get_queue_status_counts(conn)` — read-only, no other changes |
| `tests/test_soar_worker_runner.py` | Add new tests (see Section 9) |
| `tests/test_response_action_queue.py` | Add `get_queue_status_counts` tests |

**No other files change.** In particular:

- `engines/soar_action_worker.py` — unchanged.
- `engines/soar_executor.py` — unchanged.
- `engines/soar_errors.py` — unchanged.
- `integrations/soar_adapters/` — unchanged.
- All ingest/detection/correlation modules — unchanged.
- No schema migrations.

---

## 9. Testing Strategy

### Arg wiring tests (unit, no DB)

- `--batch-size 5` overrides `SOAR_RUNNER_BATCH_SIZE=20` → batch size is 5.
- `--mode real` overrides `SOAR_EXECUTION_MODE=simulation` → mode is `real`.
- No `--batch-size` arg, `SOAR_RUNNER_BATCH_SIZE=15` → batch size is 15.
- No `--mode` arg, `SOAR_EXECUTION_MODE` unset → mode is `simulation`.
- `--batch-size 0` exits 1 (validation still applies to CLI-sourced values).
- `--mode invalid` is rejected by `argparse` itself (choices constraint).

### `--dry-run-info` tests (DB-backed)

- Empty queue → all counts are 0.
- Queue with 2 pending, 1 failed → counts match.
- `--dry-run-info` does not change any row statuses (assert queue unchanged
  before and after).
- `--dry-run-info` with `--json` returns a JSON document with
  `"mode": "dry_run_info"` and `"queue_counts"` key.
- `process_batch` is never called when `--dry-run-info` is set (monkeypatch
  and assert not called).

### `--json` output tests (unit, mocked DB)

- Normal run with `--json` → stdout is valid JSON parseable by `json.loads`.
- JSON output contains `"mode"`, `"batch_size"`, `"started_at"`, `"results"`,
  `"summary"` keys.
- `summary.processed` matches `len(results)`.
- Empty result list → `"results": []`, `"summary"."processed": 0`.
- Config error with `--json` → stdout JSON has `"error"` key, exit 1.
- `--json` does not suppress logging module output (no assertion needed, but
  confirm logging calls are not redirected to stdout by checking stdout is
  valid JSON after a run that produces log output).

### `get_queue_status_counts` tests (DB-backed)

- Empty queue → returns `{}`.
- 2 pending rows → returns `{"pending": 2}`.
- Mixed statuses → returns correct count per status.
- Does not modify any row (assert all rows unchanged after call).

### Env fallback regression tests

The six existing env-var config tests in `test_soar_worker_runner.py` must
remain green without modification. These tests do not pass CLI args and must
continue to exercise the env var path correctly.

---

## 10. Risks and Stop Conditions

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| CLI `--mode real` used in an environment where the adapter is misconfigured | Low | Adapter itself guards against misconfiguration; runner prints real-mode WARNING regardless of arg source |
| `--json` and logging both write to stdout | Low | Logging module writes to stderr via handlers; `print()` writes to stdout. These are separate file descriptors. Verify in a test. |
| `parse_args()` breaks existing test fixtures that call `main()` without args | Low | `parse_args()` with empty argv (in pytest) reads `sys.argv[1:]`; pytest sets that to test args. Use `monkeypatch.setattr(sys, "argv", [...])` or call `_load_and_validate_config(args)` directly in unit tests. |
| Confusion between `--dry-run-info` and adapter dry-run | Low | Name is different. `--dry-run-info` is a runner flag about queue inspection. Adapter dry-run is about execution safety. Document both clearly in `--help`. |
| `get_queue_status_counts` takes a long time on a large queue | Negligible | COUNT(*) GROUP BY status is a simple scan; no row-level lock; acceptable for a visibility helper |

### Stop conditions

Stop and re-plan if:

- Wiring CLI args requires modifying `engines/soar_action_worker.py` or any
  queue store function other than adding `get_queue_status_counts`.
- `--json` output requires changes to how `process_batch` returns results.
- `--dry-run-info` triggers any row state change in any test.
- Any test requires real network or firewall access.
- Adding `parse_args()` breaks existing test cases in a way that requires
  modifying those test cases.
- `get_queue_status_counts` requires a schema migration.

---

## 11. Future Considerations

This change is intentionally minimal. Future improvements that are out of scope here:

- `--recover-stale` flag to surface stale running rows via `recover_stale_running_actions`.
- `--watch` mode that loops and re-runs the batch on a timer (daemon territory — separate spec).
- Structured per-action output in plain text mode (currently suppressed in favor of logging).
- Queue-status API endpoint (frontend/API territory — separate spec).
- `--output-file` flag to write JSON to a file rather than stdout.
