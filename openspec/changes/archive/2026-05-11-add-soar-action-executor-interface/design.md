## Current state

Phase 1B is complete. The relevant files are:

- `engines/soar_action_worker.py` — worker orchestration (`process_next_action`, `process_batch`), retry flow, `placeholder_execute_action`. Currently also defines `RetryableActionError` and `SkippedAction` — these will be extracted in this phase.
- `core/response_action_queue_store.py` — queue DB helpers (claim, transitions, stale recovery).
- `core/ip_helpers.py` — `execute_response_action()` (synchronous, called inside ingest transaction, writes to `response_actions_log`). Untouched in this phase.

The current placeholder executor:

```python
def placeholder_execute_action(row):
    if row["action"] not in SUPPORTED_PLACEHOLDER_ACTIONS:
        raise SkippedAction(
            f"Unsupported response action: {row['action']}",
            code="unsupported_action",
        )
    return {
        "code": "placeholder_success",
        "message": f"Placeholder worker accepted {row['action']}",
    }
```

This passes the worker's `_result_code()` / `_result_message()` checks but performs no validation and has no action-type-specific behavior. The worker already accepts `executor=None` and defaults to the placeholder, so the injection point is established.

---

## Executor interface contract

An executor is any callable with the following signature:

```python
def execute(row: dict) -> dict:
    ...
```

### Input: `row` dict

The row dict is the raw result of `claim_next_pending_action()` — a psycopg2 `RealDictRow`. The executor may read any field but must not modify it. Guaranteed fields at call time:

| Field | Type | Description |
|---|---|---|
| `id` | int | Queue row ID |
| `action` | str | `block_ip`, `flag_high_priority`, or `monitor` |
| `source_ip` | str \| None | Target IP address |
| `alert_id` | int \| None | Originating alert ID |
| `retry_count` | int | Current attempt number |
| `max_retries` | int | Retry ceiling |
| `status` | str | Will be `running` at call time |

### Output: result dict

On success the executor must return a dict with at minimum:

```python
{
    "code": str,      # machine-readable outcome code, e.g. "simulated_block_ip"
    "message": str,   # human-readable summary for logs/observability
}
```

An optional `details` key may carry action-specific metadata:

```python
{
    "code": "simulated_block_ip",
    "message": "Simulated IP block for 1.2.3.4",
    "details": {
        "source_ip": "1.2.3.4",
        "alert_id": 42,
    },
}
```

Both mandatory fields must be present. The worker will validate the result dict immediately after executor return and raise a non-retryable `Exception` if either field is missing or empty. The existing `_result_code()` / `_result_message()` silent fallbacks are replaced by this explicit check. A missing `code` or `message` is a bug in the executor, not a recoverable action failure.

### Exception contract

| Condition | What to raise | Worker outcome |
|---|---|---|
| Action should be skipped (validation failure, unsupported type) | `SkippedAction(message, code=...)` | `skipped` — terminal |
| Action failed but is worth retrying | `RetryableActionError(message, code=...)` | `failed → pending` if retries remain |
| Unexpected failure | any other `Exception` | `failed` — terminal, non-retryable |

`RetryableActionError` and `SkippedAction` are extracted into `engines/soar_errors.py` in this phase. Both `engines/soar_action_worker.py` and `engines/soar_executor.py` import from there. Future `adapters/` code does the same. No module imports exception classes from another module that uses them as a peer.

---

## Validation rules

Validation runs inside the executor before any side effect. All validation failures raise `SkippedAction` with a specific error code. `RetryableActionError` is never raised for validation failures — retrying cannot fix a missing or invalid field.

### All actions

| Check | SkippedAction code |
|---|---|
| `action` not in `{"block_ip", "flag_high_priority", "monitor"}` | `unsupported_action` |

### block_ip

| Check | SkippedAction code |
|---|---|
| `source_ip` is `None` | `validation_null_source_ip` |
| `source_ip` is not a valid IP string (cannot be parsed by `ipaddress.ip_address()`) | `validation_invalid_ip_format` |
| `source_ip` is loopback (`127.x.x.x`, `::1`) | `validation_private_ip` |
| `source_ip` is private/reserved (`10.x`, `172.16–31.x`, `192.168.x`, link-local, etc.) | `validation_private_ip` |

The private-IP guard uses `ipaddress.ip_address(source_ip).is_private` and `.is_loopback` and `.is_link_local`. This prevents accidentally queuing a block action against internal infrastructure.

### flag_high_priority

| Check | SkippedAction code |
|---|---|
| `alert_id` is `None` | `validation_missing_alert_id` |

Cannot escalate an alert that has no linked alert_id. The alert_id is required for any downstream notification to be actionable.

### monitor

| Check | SkippedAction code |
|---|---|
| Both `source_ip` and `alert_id` are `None` | `validation_no_target` |

At least one target must be present. A monitor action with no identifiable subject is meaningless.

---

## SimulationExecutor behavior

`SimulationExecutor` is a class that implements the executor interface. It:
- Runs all validation rules.
- Logs each action with a `[SIMULATED]` prefix via `logging.getLogger(__name__)` (no Flask `current_app` dependency — the executor must be callable outside Flask request context).
- Returns a structured result dict.
- Does NOT write to `response_actions_log`.
- Does NOT create blocklist entries.
- Does NOT call any external API, network endpoint, or cloud service.

### Per-action simulation behavior

**block_ip**
```python
# After validation passes:
logger.info("[SIMULATED BLOCK] queue_id=%s source_ip=%s alert_id=%s", row["id"], row["source_ip"], row["alert_id"])
return {
    "code": "simulated_block_ip",
    "message": f"Simulated IP block for {row['source_ip']}",
    "details": {"source_ip": row["source_ip"], "alert_id": row["alert_id"]},
}
```

**flag_high_priority**
```python
logger.info("[SIMULATED ESCALATION] queue_id=%s alert_id=%s source_ip=%s", row["id"], row["alert_id"], row["source_ip"])
return {
    "code": "simulated_flag_high_priority",
    "message": f"Simulated escalation for alert {row['alert_id']}",
    "details": {"alert_id": row["alert_id"], "source_ip": row["source_ip"]},
}
```

**monitor**
```python
logger.info("[SIMULATED MONITOR] queue_id=%s source_ip=%s alert_id=%s", row["id"], row["source_ip"], row["alert_id"])
return {
    "code": "simulated_monitor",
    "message": f"Monitoring only — no action taken for queue_id={row['id']}",
    "details": {"source_ip": row["source_ip"], "alert_id": row["alert_id"]},
}
```

Simulation mode is the executor itself, not a flag. Passing `executor=SimulationExecutor()` to `process_next_action()` is how simulation mode is engaged. No module-level flag is introduced.

---

## Module and file placement

```
engines/
  soar_action_worker.py     ← existing, updated: remove placeholder, import errors from soar_errors, add result validation
  soar_errors.py            ← NEW: RetryableActionError, SkippedAction
  soar_executor.py          ← NEW: SimulationExecutor, validation helpers, SUPPORTED_ACTIONS

core/
  response_action_queue_store.py  ← existing, unchanged
  ip_helpers.py                   ← existing, unchanged

adapters/
  (directory does not exist yet — created in Phase 3)
  firewall_adapter.py             ← Phase 3: real block_ip integration
  notification_adapter.py         ← Phase 3: real flag_high_priority integration
```

`engines/soar_errors.py` is the shared exception home. It has no imports from other SOAR modules, so there is no circular dependency risk regardless of which SOAR module imports it.

`engines/soar_executor.py` is the right location for the executor because:
- The executor is SOAR orchestration logic, not a general utility.
- It is consumed by the worker (also in `engines/`).
- It is not a core infrastructure helper (`core/` is for DB access and IP utilities).
- It is not an external adapter (`adapters/` is for third-party integrations).

The `placeholder_execute_action` function in `engines/soar_action_worker.py` is removed once `SimulationExecutor` is wired as the default. The `SUPPORTED_PLACEHOLDER_ACTIONS` constant moves to `engines/soar_executor.py` as `SUPPORTED_ACTIONS`.

---

## Future real integration points

Phase 3 adapters will live under `adapters/`. Each adapter implements the same callable interface:

```python
class FirewallAdapter:
    def __call__(self, row: dict) -> dict:
        # validate, call real API, return result dict
        ...
```

The worker is wired by injecting the adapter at startup:

```python
executor = FirewallAdapter(config=...)
process_next_action(conn, executor=executor)
```

The worker code does not change when adapters are added or swapped. The interface contract defined in this phase is the stable boundary.

`execute_response_action()` in `core/ip_helpers.py` is not modified in this phase. It continues to be called synchronously inside ingest transactions. The decoupling of that call site (moving it to post-commit and wiring through the queue) is a later phase and must be approached separately to avoid disrupting ingest transaction behavior.

---

## Testing strategy

Tests for `engines/soar_executor.py` (to be added in implementation step):

**SimulationExecutor — success paths**
- `block_ip` with valid public IP returns `code="simulated_block_ip"` and non-empty `message`.
- `flag_high_priority` with valid `alert_id` returns `code="simulated_flag_high_priority"`.
- `monitor` with at least one of `source_ip`/`alert_id` returns `code="simulated_monitor"`.

**Validation — SkippedAction paths**
- Unknown action type raises `SkippedAction` with `code="unsupported_action"`.
- `block_ip` with `source_ip=None` raises `SkippedAction` with `code="validation_null_source_ip"`.
- `block_ip` with `source_ip="127.0.0.1"` raises `SkippedAction` with `code="validation_private_ip"`.
- `block_ip` with `source_ip="10.0.0.1"` raises `SkippedAction` with `code="validation_private_ip"`.
- `block_ip` with `source_ip="not-an-ip"` raises `SkippedAction` with `code="validation_invalid_ip_format"`.
- `flag_high_priority` with `alert_id=None` raises `SkippedAction` with `code="validation_missing_alert_id"`.
- `monitor` with `source_ip=None` and `alert_id=None` raises `SkippedAction` with `code="validation_no_target"`.

**No validation failure raises `RetryableActionError`** — assert this explicitly.

**Worker integration — SimulationExecutor replaces placeholder**
- `process_next_action(conn, executor=SimulationExecutor())` with a valid `block_ip` row returns `outcome="success"`.
- Worker + SimulationExecutor end-to-end for all three action types: queue row goes from `pending → running → success`.
- Worker + SimulationExecutor with invalid IP: queue row goes from `pending → running → skipped`.

**No external calls**
- No test in this phase makes real network requests. SimulationExecutor must not call `requests`, `urllib`, or any cloud SDK. Assert absence of these imports in `soar_executor.py`.

**Regression guard**
- Existing `test_response_action_queue.py` tests remain green.
- Existing ingest/detection/correlation test suites remain green.
- `response_actions_log` contents are unchanged by executor execution.
