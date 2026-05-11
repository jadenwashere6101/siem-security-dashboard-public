# Tasks: Improve SOAR Worker Runner Visibility

---

## Completion Checklist

- [x] Task 1 — Wire `parse_args()` and thread `args` through `main()`
- [x] Task 2 — Add `--mode` and `--json` arg definitions
- [x] Task 3 — Update `_load_and_validate_config` to accept `args` and apply precedence
- [x] Task 4 — Add `get_queue_status_counts` to queue store
- [x] Task 5 — Implement `--dry-run-info` branch in `main()`
- [x] Task 6 — Implement `--json` output path
- [x] Task 7 — Arg wiring unit tests
- [x] Task 8 — `--dry-run-info` DB-backed tests
- [x] Task 9 — `--json` output tests
- [x] Task 10 — `get_queue_status_counts` DB-backed tests
- [x] Task 11 — Regression check

---

## Task 1 — Wire `parse_args()` and thread `args` through `main()`

In `scripts/soar_worker_run.py`:

Replace the current:

```python
parser.parse_known_args()
```

with:

```python
args = parser.parse_args()
```

Pass `args` to `_load_and_validate_config(args)` where config is read.

Also pass `args.json` and `args.dry_run_info` as flags through the relevant
branches of `main()`.

Do not change any validation logic yet — just thread the args object through.

**Acceptance:** Existing tests that call `main()` directly (without setting
`sys.argv`) continue to pass. `parser.parse_args()` with no explicit argv in
pytest reads `sys.argv[1:]`, which pytest sets to its own flags — confirm
that does not collide by using `sys.argv` isolation in new tests (see Task 7).

---

## Task 2 — Add `--mode` and `--json` arg definitions

Extend the `ArgumentParser` in `main()` with:

```python
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
    help="Emit all output as a single JSON object to stdout.",
)
parser.add_argument(
    "--dry-run-info",
    action="store_true",
    default=False,
    help="Print queue status counts and exit without processing any actions.",
)
```

The existing `--batch-size` definition is already present. Do not redefine it.
Change its `default` to `None` if it is currently set to anything else, so the
precedence logic in Task 3 can distinguish "arg not passed" from "arg passed as
0".

**Acceptance:** `python scripts/soar_worker_run.py --help` shows all four args.
`--mode invalid` is rejected by argparse with a non-zero exit.

---

## Task 3 — Update `_load_and_validate_config` to accept `args` and apply precedence

Change the signature from:

```python
def _load_and_validate_config():
```

to:

```python
def _load_and_validate_config(args):
```

Apply precedence for each configurable value:

**Mode:**
```python
raw_mode = args.mode or os.getenv("SOAR_EXECUTION_MODE", "simulation").strip().lower()
```

**Batch size:**
```python
if args.batch_size is not None:
    raw_batch_size = str(args.batch_size)
else:
    raw_batch_size = os.getenv("SOAR_RUNNER_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)).strip()
```

All existing validation logic (mode allowlist, int parsing, range check, clamp)
remains exactly as-is. Only the source of the raw values changes.

**Acceptance:**
- `_load_and_validate_config(args)` with `args.batch_size=5` and
  `SOAR_RUNNER_BATCH_SIZE=20` → returns batch size 5.
- `_load_and_validate_config(args)` with `args.batch_size=None` and
  `SOAR_RUNNER_BATCH_SIZE=15` → returns batch size 15.
- `_load_and_validate_config(args)` with `args.mode="real"` and
  `SOAR_EXECUTION_MODE=simulation` → returns mode `"real"`.
- `_load_and_validate_config(args)` with `args.mode=None` and
  `SOAR_EXECUTION_MODE` unset → returns mode `"simulation"`.

---

## Task 4 — Add `get_queue_status_counts` to `core/response_action_queue_store.py`

Add one new function. Do not modify any existing function.

```python
def get_queue_status_counts(conn):
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

Also add the following normalization constant and helper to
`scripts/soar_worker_run.py` (not to the store):

```python
_KNOWN_STATUSES = ["pending", "running", "failed", "skipped", "success"]

def _normalize_queue_counts(raw):
    return {s: raw.get(s, 0) for s in _KNOWN_STATUSES}
```

**Acceptance:**
- Empty queue → `get_queue_status_counts` returns `{}`.
- Queue with 2 pending rows → returns `{"pending": 2}`.
- `_normalize_queue_counts({})` → returns all five statuses as 0.
- `_normalize_queue_counts({"pending": 3, "failed": 1})` → returns all five
  statuses with pending=3, failed=1, others=0.

---

## Task 5 — Implement `--dry-run-info` branch in `main()`

In `main()`, after the Flask context guard and before config loading, add:

```python
if args.dry_run_info:
    return _run_dry_run_info(args)
```

Implement `_run_dry_run_info(args)`:

1. Open DB connection (same pattern as normal mode; exit 1 on failure).
2. Call `get_queue_status_counts(conn)`.
3. Normalize counts with `_normalize_queue_counts`.
4. If `args.json`:
   ```json
   {
     "mode": "dry_run_info",
     "queue_counts": { "pending": 0, "running": 0, "failed": 0, "skipped": 0, "success": 0 }
   }
   ```
5. Else (plain text):
   ```
   === SOAR Queue Status ===
     Pending:  <n>
     Running:  <n>
     Failed:   <n>
     Skipped:  <n>
     Success:  <n>
   =========================
   ```
6. Close DB connection.
7. Return 0.

`_load_and_validate_config` is NOT called in this branch. Mode and batch size
are irrelevant.

**Acceptance:**
- `--dry-run-info` with 2 pending rows in DB → prints correct counts.
- `--dry-run-info` calls `get_queue_status_counts` and never calls
  `process_batch` (assert via monkeypatch).
- All queue rows are in the same state before and after `--dry-run-info` runs.
- `--dry-run-info --json` returns valid JSON with `"mode": "dry_run_info"`.

---

## Task 6 — Implement `--json` output path

When `args.json` is `True` in normal (non-dry-run-info) mode:

1. Suppress all `print()` calls in `_print_start_header`.
2. Accumulate the header metadata as a dict.
3. After `_aggregate_results`, serialize the complete output as one JSON object:
   ```python
   import json
   output = {
       "mode": mode,
       "batch_size": batch_size,
       "started_at": started_at.isoformat(),
       "results": results,
       "summary": counts,
   }
   print(json.dumps(output, default=str))
   ```
   `default=str` handles any `datetime` values in result dicts.

For `RunnerConfigError` with `--json`:
```python
print(json.dumps({"error": str(error)}))
return 1
```

`logging` calls in the worker and executor write to stderr and are unaffected.

**Refactor note:** `_print_start_header` currently both builds and prints the
header. For the JSON path, the header values are needed without printing.
Extract `_build_header_dict(mode, batch_size)` as a pure function returning a
dict. Both the plain-text and JSON paths call it. The plain-text path formats
and prints it. The JSON path stores it for later serialization.

**Acceptance:**
- `--json` output is a single valid JSON object parseable by `json.loads`.
- JSON object contains all five top-level keys: `mode`, `batch_size`,
  `started_at`, `results`, `summary`.
- `summary["processed"]` equals `len(results)`.
- `--json` with an empty queue → `"results": []`, `"summary"."processed": 0`.
- `--json` with a `RunnerConfigError` → `{"error": "..."}` on stdout, exit 1.
- Logging output from `SimulationExecutor` does not appear in stdout when
  `--json` is active (it goes to stderr via logging module).

---

## Task 7 — Arg wiring unit tests

Add to `tests/test_soar_worker_runner.py`. Each test uses
`monkeypatch.setattr(sys, "argv", ["soar_worker_run", ...])` to control CLI
input, or calls `_load_and_validate_config(args)` directly with a fabricated
`argparse.Namespace`.

Tests to add:

- `--batch-size 5` with `SOAR_RUNNER_BATCH_SIZE=20` → batch size is 5.
- `--mode real` with `SOAR_EXECUTION_MODE=simulation` → mode is `real`.
- No `--batch-size`, `SOAR_RUNNER_BATCH_SIZE=15` → batch size is 15.
- No `--mode`, `SOAR_EXECUTION_MODE` unset → mode is `simulation`.
- `--batch-size 0` → `_load_and_validate_config` raises `RunnerConfigError`.
- `--batch-size 99` → batch size clamped to 50 (existing clamp test updated to
  pass `args`).

Do not modify the six existing env-var config tests. They must remain green.
If threading `args` through `_load_and_validate_config` breaks them, adjust
the existing tests to pass `argparse.Namespace(batch_size=None, mode=None)`
as the `args` argument — this mirrors "no CLI arg passed."

---

## Task 8 — `--dry-run-info` DB-backed tests

Add to `tests/test_soar_worker_runner.py`:

- Empty queue → all five counts are 0 in output.
- 2 pending + 1 failed in queue → counts match.
- Queue row statuses are unchanged after `--dry-run-info` (read before and
  after, assert equal).
- `process_batch` is never called (monkeypatch and assert `call_count == 0`).
- `--dry-run-info --json` → stdout is valid JSON with `"mode": "dry_run_info"`
  and `"queue_counts"` key containing all five status keys.

---

## Task 9 — `--json` output tests

Add to `tests/test_soar_worker_runner.py`. Use `capsys` to capture stdout.

- Normal run with `--json` → `json.loads(stdout)` succeeds.
- All five top-level keys present in JSON output.
- `summary["processed"]` matches result count.
- Empty queue with `--json` → `"results": []`, `summary["processed"] == 0`.
- Config error (`SOAR_EXECUTION_MODE=invalid`) with `--json` → stdout JSON has
  `"error"` key, exit code is 1.
- Confirm logging output is not in stdout: after a simulation run with
  `--json`, parse stdout as JSON (succeeds = no log lines mixed in).

---

## Task 10 — `get_queue_status_counts` DB-backed tests

Add to `tests/test_response_action_queue.py`:

- Empty queue → returns `{}`.
- 2 pending rows → returns `{"pending": 2}`.
- 1 pending + 1 success + 1 failed → returns correct counts for all three.
- No row in the queue is modified after the call (assert statuses unchanged).

Add to `tests/test_soar_worker_runner.py` (unit):

- `_normalize_queue_counts({})` → all five statuses present, all 0.
- `_normalize_queue_counts({"pending": 3, "failed": 1})` → five keys, correct
  values for pending and failed, 0 for others.
- `_normalize_queue_counts` does not include unknown statuses beyond the five
  defined in `_KNOWN_STATUSES`.

---

## Task 11 — Regression check

Before marking this change complete, verify:

- All existing `test_soar_worker_runner.py` tests pass without modification
  (or with only the minimal `argparse.Namespace` arg addition noted in Task 7).
- All existing `test_response_action_queue.py` tests pass.
- All existing `test_soar_action_worker.py` tests pass.
- Ingest/detection/correlation test suites pass.
- `engines/soar_action_worker.py` was not modified.
- `integrations/soar_adapters/` was not modified.
- No schema migrations were introduced.
- No subprocess, shell execution, or `sudo` is present in the runner.
