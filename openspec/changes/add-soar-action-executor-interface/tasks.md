## SOAR Action Executor Interface Tasks

- [x] Inspect current worker placeholder and executor injection pattern
  - Review `placeholder_execute_action()` in `engines/soar_action_worker.py`.
  - Confirm `process_next_action()` executor parameter and default behavior.
  - Confirm `RetryableActionError` and `SkippedAction` definitions and current import locations.
  - Confirm `_result_code()` and `_result_message()` fallback behavior in worker.

- [x] Create `engines/soar_errors.py`
  - Move `RetryableActionError` and `SkippedAction` out of `engines/soar_action_worker.py` and into this file.
  - `soar_errors.py` must have no imports from other SOAR modules.
  - Update `engines/soar_action_worker.py` to import both classes from `engines.soar_errors`.
  - Confirm existing `test_response_action_queue.py` still passes after the move.

- [x] Create `engines/soar_executor.py`
  - Define `SUPPORTED_ACTIONS = {"block_ip", "flag_high_priority", "monitor"}`.
  - Import `RetryableActionError` and `SkippedAction` from `engines.soar_errors`.
  - Implement `_validate_action(row)` helper covering all per-action validation rules.
  - Implement `SimulationExecutor` class with `__call__(self, row) -> dict`.
  - Implement per-action simulation behavior (`block_ip`, `flag_high_priority`, `monitor`) using `logging.getLogger(__name__)`, not `current_app`.
  - Raise `SkippedAction` with `code="unsupported_action"` for unknown action types.
  - Do NOT import `requests`, `urllib`, or any external/cloud SDK.
  - Do NOT write to `response_actions_log` or `blocked_ips`.

- [x] Update `engines/soar_action_worker.py`
  - Remove `placeholder_execute_action` and `SUPPORTED_PLACEHOLDER_ACTIONS`.
  - Replace default executor with `SimulationExecutor()` in `process_next_action()`.
  - Add result validation immediately after executor return: assert result is a dict with non-empty `code` and `message`; raise a non-retryable `Exception` if either is missing. Remove reliance on `_result_code()` / `_result_message()` silent fallbacks for the success path.
  - Confirm no existing tests depend directly on `placeholder_execute_action` by name.

- [x] Add tests for `SimulationExecutor` — success paths
  - `block_ip` with valid public IP returns `code="simulated_block_ip"` and non-empty `message`.
  - `flag_high_priority` with valid `alert_id` returns `code="simulated_flag_high_priority"`.
  - `monitor` with `source_ip` present returns `code="simulated_monitor"`.
  - `monitor` with only `alert_id` present returns `code="simulated_monitor"`.

- [x] Add tests for validation — SkippedAction paths
  - Unknown action type raises `SkippedAction(code="unsupported_action")`.
  - `block_ip` with `source_ip=None` raises `SkippedAction(code="validation_null_source_ip")`.
  - `block_ip` with `source_ip="127.0.0.1"` raises `SkippedAction(code="validation_private_ip")`.
  - `block_ip` with `source_ip="10.0.0.1"` raises `SkippedAction(code="validation_private_ip")`.
  - `block_ip` with `source_ip="192.168.1.1"` raises `SkippedAction(code="validation_private_ip")`.
  - `block_ip` with `source_ip="not-an-ip"` raises `SkippedAction(code="validation_invalid_ip_format")`.
  - `flag_high_priority` with `alert_id=None` raises `SkippedAction(code="validation_missing_alert_id")`.
  - `monitor` with both `source_ip=None` and `alert_id=None` raises `SkippedAction(code="validation_no_target")`.
  - Assert no validation path ever raises `RetryableActionError`.

- [x] Add worker + SimulationExecutor integration tests
  - `process_next_action(conn, executor=SimulationExecutor())` with enqueued `block_ip` row (valid public IP) → `outcome="success"`, queue row status = `success`.
  - Same for `flag_high_priority` with valid `alert_id`.
  - Same for `monitor` with valid `source_ip`.
  - `process_next_action` with invalid IP (private) → `outcome="skipped"`, queue row status = `skipped`.
  - `process_next_action` with unknown action type → `outcome="skipped"`, queue row status = `skipped`.

- [x] Verify no external calls happen through SimulationExecutor
  - Assert `engines/soar_executor.py` does not import `requests`, `urllib`, `boto3`, or any cloud SDK.
  - Confirm no test in this phase makes real network requests.
  - Confirm no executor test writes to `response_actions_log`.

- [x] Verify existing behavior unchanged
  - Run `test_response_action_queue.py` — all tests green.
  - Run ingest/detection/correlation test suites — no regressions.
  - Confirm `response_actions_log` contents are not modified by any executor test.
  - Run full `pytest` backend suite.
