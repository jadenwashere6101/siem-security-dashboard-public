## Phase 1D-a: SOAR Enqueue Orchestrator Foundation

- [x] Inspect `enqueue_response_action()` interface and idempotency behavior
  - Read `core/ip_helpers.py` — confirm signature: `enqueue_response_action(cur, alert_id, source_ip, action, *, max_retries=3)`.
  - Confirm the `ON CONFLICT (idempotency_key) DO NOTHING` / `RETURNING id` behavior: returns the queue row ID on insert, `None` on conflict.
  - Confirm the idempotency key formula: `sha256(alert_id:source_ip:action)`.
  - Note that the caller must commit after calling — `enqueue_response_action()` does not commit.

- [x] Use `logging.getLogger(__name__)` for all orchestrator logging
  - Consistent with `engines/soar_action_worker.py`.
  - Keeps the orchestrator callable from tests and CLI scripts without a Flask app context.
  - No `current_app` import needed.

- [x] Create `engines/soar_enqueue_orchestrator.py`
  - Import `enqueue_response_action` from `core.ip_helpers`.
  - Import logger via `logging.getLogger(__name__)`.
  - Implement `enqueue_committed_alerts(alerts_created: list, conn) -> list`.
    - Open a cursor on the connection (`conn.cursor()`).
    - For each dict in `alerts_created`:
      - Extract `alert_id`, `source_ip`, `response_action`.
      - If any is `None` or missing: log warning with field name, append skipped result dict, `continue`.
      - Call `enqueue_response_action(cur, alert_id, str(source_ip), response_action)`.
      - Log result with `[SOAR ENQUEUE]` prefix.
      - Append result dict with `alert_id`, `source_ip`, `action`, `queue_id`, `skipped=False`.
    - Return result list.
  - Do NOT commit inside this function.
  - Do NOT close the cursor inside this function.
  - Do NOT catch exceptions from `enqueue_response_action()` — let them propagate.
  - Do NOT import from route modules, detection engines, or correlation engines.

- [x] Add tests: success path
  - Insert an alert row directly into the `alerts` table (or use a fixture) to obtain a real `alert_id`.
  - Build a valid alert dict: `{"alert_id": alert_id, "source_ip": "1.2.3.4", "response_action": "block_ip"}`.
  - Call `enqueue_committed_alerts([alert_dict], conn)` then `conn.commit()`.
  - Query `response_actions_queue` — confirm one row exists with correct `alert_id`, `source_ip`, `action`, `status='pending'`.
  - Confirm return list contains `{"alert_id": alert_id, "queue_id": <int>, "skipped": False, ...}`.
  - Repeat for `flag_high_priority` and `monitor` action types.

- [x] Add tests: idempotency
  - Call `enqueue_committed_alerts([alert_dict], conn)` and commit.
  - Call again with the same dict and commit.
  - Confirm exactly one row in `response_actions_queue` for that alert.
  - Confirm no exception on second call.
  - Confirm second call returns `queue_id=None` in result dict.

- [x] Add tests: missing field guards
  - Missing `alert_id`: pass `{"source_ip": "1.2.3.4", "response_action": "block_ip"}`.
    - Confirm no queue row created, no exception, result has `skipped=True, skip_reason="missing_alert_id"`.
  - Missing `source_ip`: pass `{"alert_id": 1, "response_action": "block_ip"}`.
    - Same expectations.
  - Missing `response_action`: pass `{"alert_id": 1, "source_ip": "1.2.3.4"}`.
    - Same expectations.
  - `alert_id=None` explicitly: pass `{"alert_id": None, "source_ip": "1.2.3.4", "response_action": "block_ip"}`.
    - Same expectations.

- [x] Add tests: mixed list
  - Pass a list with one valid dict and one dict missing `alert_id`.
  - Confirm exactly one queue row created (for the valid dict).
  - Confirm result list has two entries: one `skipped=False`, one `skipped=True`.

- [x] Add tests: empty list
  - Call `enqueue_committed_alerts([], conn)`.
  - Confirm no queue rows created.
  - Confirm return value is `[]`.
  - Confirm no exception.

- [x] Verify no existing code was touched
  - Confirm `routes/ingest_routes.py` is unchanged.
  - Confirm `engines/detection_engine.py` is unchanged.
  - Confirm `engines/correlation_engine.py` is unchanged.
  - Confirm `engines/ingest_engine.py` is unchanged.
  - Confirm no existing test file was modified.
  - Run full `pytest` backend suite — all existing tests green.

---

## Phase 1D-b (deferred — do not implement in this change)

The following work is explicitly out of scope for this change and will be addressed in a separate spec:

- Augment `alerts_created` return dicts in all 7 detection functions to include `alert_id` and `response_action`.
- Update all detection function test assertions to match the new dict shape.
- Wire `enqueue_committed_alerts()` into all 4 ingest route handlers after `conn.commit()`.
- Wrap route-level enqueue in `try/except` to prevent enqueue failure from masking committed ingest.
- Add integration tests for commit-vs-enqueue ordering, enqueue failure after commit, and batch route enqueue behavior.
- Document and test the dual-execution state (`execute_response_action()` + worker).
- Address correlation alert enqueueing (requires correlation function return type changes — separate phase).
