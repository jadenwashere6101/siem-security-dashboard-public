# Tasks: Approval Expiration + Lifecycle Cleanup (Phase 2.5D)

Read each file before editing it.
Run `pytest` after each step that modifies Python files.
Run the full suite before marking any step complete: `pytest tests/ -x -q`.

**Stop conditions:**
- If any existing approval, worker, or queue store test fails after a step, revert that step
  before proceeding.
- Do not commit until all steps pass the full suite.

---

## Step 0: Pre-flight — verify index coverage

Before writing any code, verify that `approval_requests` has an index suitable for the
`WHERE status = 'pending' AND expires_at <= now` query that `expire_pending_requests` issues.
The admin endpoint calls this function, so index coverage affects endpoint performance.

- [ ] Read `schema.sql`. Search for index definitions on `approval_requests`.
- [ ] Confirm an index exists that covers `(status, expires_at)` or a partial index on
  `status = 'pending'` including `expires_at`. Either is sufficient.
- [ ] If no suitable index exists: add one to `schema.sql`:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_approval_requests_status_expires_at
      ON approval_requests (status, expires_at)
      WHERE status = 'pending';
  ```
- [ ] Run `pytest tests/ -x -q` — passes (schema-only change if needed, no code touched).

---

## Step 1: Add `sweep_terminal_approval_queue_rows` to `response_action_queue_store.py`

Read `core/response_action_queue_store.py` and `skip_next_terminal_approval_action` before
implementing. The new function mirrors its SQL structure.

- [ ] Add the following function after `skip_next_terminal_approval_action`:

  ```python
  def sweep_terminal_approval_queue_rows(conn, *, now=None, limit=100):
      cap = min(max(int(limit), 0), 100)
      with conn.cursor() as cur:
          cur.execute(
              f"""
              WITH candidates AS (
                  SELECT q.id,
                         approval.status AS approval_status
                  FROM response_actions_queue q
                  JOIN LATERAL (
                      SELECT status
                      FROM approval_requests
                      WHERE queue_id = q.id
                        AND action = q.action
                      ORDER BY created_at DESC, id DESC
                      LIMIT 1
                  ) approval ON TRUE
                  WHERE q.status = 'awaiting_approval'
                    AND approval.status IN ('denied', 'expired')
                  ORDER BY q.id
                  FOR UPDATE OF q SKIP LOCKED
                  LIMIT %s
              )
              UPDATE response_actions_queue AS queue
              SET status = 'skipped',
                  last_error = CASE
                      WHEN candidates.approval_status = 'denied' THEN 'approval denied'
                      ELSE 'approval expired'
                  END,
                  updated_at = COALESCE(%s::timestamptz, NOW())
              FROM candidates
              WHERE queue.id = candidates.id
              RETURNING queue.id, queue.alert_id, host(queue.source_ip), queue.action,
                        queue.status, queue.retry_count, queue.max_retries,
                        queue.last_error, queue.idempotency_key,
                        queue.created_at, queue.updated_at,
                        candidates.approval_status
              """,
              (cap, now),
          )
          rows = cur.fetchall()
          result = []
          for row in rows:
              queue_row = _queue_row_from_record(row[:11])
              queue_row["approval_status"] = row[11]
              result.append(queue_row)
          return result
  ```

- [ ] Run `pytest tests/ -x -q` — all existing tests pass.

---

## Step 2: Test `sweep_terminal_approval_queue_rows`

Read the existing `tests/test_response_action_queue_store.py` (or the file that tests
`skip_next_terminal_approval_action`) before writing tests. Match its fixture and setup patterns.
Add the new tests to that file.

- [ ] Import `sweep_terminal_approval_queue_rows` in the test file.

- [ ] **Test: empty queue returns empty list**
  - No queue rows present. `sweep_terminal_approval_queue_rows(conn)` returns `[]`.

- [ ] **Test: pending queue row (non-awaiting) is not swept**
  - Insert a `pending` queue row with an associated `expired` approval.
  - Call `sweep_terminal_approval_queue_rows(conn)`.
  - Queue row remains `pending`. Returns `[]`.

- [ ] **Test: awaiting_approval row with approved approval is not swept**
  - Insert an `awaiting_approval` queue row with a linked approval at `status = 'approved'`.
  - Call sweep. Row remains `awaiting_approval`. Returns `[]`.

- [ ] **Test: awaiting_approval row with expired approval is swept to skipped**
  - Insert an `awaiting_approval` queue row with a linked expired approval.
  - `conn.commit()` before calling sweep (so the setup is visible).
  - Call `sweep_terminal_approval_queue_rows(conn)`.
  - Returns 1 item. `item["status"] == "skipped"`. `item["last_error"] == "approval expired"`.
  - `conn.commit()`. Re-read queue row — `status == "skipped"`.

- [ ] **Test: awaiting_approval row with denied approval is swept to skipped**
  - Same as above but with `status = 'denied'` approval.
  - `item["last_error"] == "approval denied"`.

- [ ] **Test: retry_count is not incremented**
  - Insert `awaiting_approval` row with `retry_count = 1, max_retries = 3` and expired approval.
  - Sweep. `item["retry_count"] == 1` (unchanged).

- [ ] **Test: multiple rows are swept in batch**
  - Insert 3 `awaiting_approval` rows, each with a terminal approval.
  - Call sweep. Returns 3 items. All transitioned to `skipped`.

- [ ] **Test: limit is respected**
  - Insert 5 `awaiting_approval` rows with terminal approvals.
  - Call `sweep_terminal_approval_queue_rows(conn, limit=2)`.
  - Returns exactly 2 items. Other 3 remain `awaiting_approval`.

- [ ] **Test: approved/denied requests are not affected**
  - Insert 1 `awaiting_approval` row with `approved` approval.
  - Insert 1 `awaiting_approval` row with `expired` approval.
  - Sweep. Only the `expired` row is swept. Approved row unchanged.

- [ ] Run `pytest tests/ -x -q` — all tests pass.

---

## Step 3: Add `POST /admin/soar/approvals/expire-pending` to `admin_routes.py`

Read `routes/admin_routes.py` in full before editing. Note the import block and the rate
limiter pattern on existing endpoints.

- [ ] Add imports at the top of `admin_routes.py` (with existing imports):
  ```python
  from core.approval_store import expire_pending_requests
  from core.response_action_queue_store import sweep_terminal_approval_queue_rows
  ```
  If `expire_pending_requests` is already imported, do not duplicate it.

- [ ] Add the new endpoint after the last existing `admin/soar` endpoint:

  ```python
  @admin_bp.route("/admin/soar/approvals/expire-pending", methods=["POST"])
  @limiter.limit("10 per minute")
  @login_required
  @super_admin_required
  def expire_pending_approvals():
      conn = None
      try:
          conn = get_db_connection()
          expired = expire_pending_requests(conn)
          swept = sweep_terminal_approval_queue_rows(conn)
          conn.commit()
          return jsonify({
              "expired_approvals": len(expired),
              "skipped_queue_rows": len(swept),
              "expired_approval_ids": [r["id"] for r in expired],
              "skipped_queue_ids": [r["id"] for r in swept],
          }), 200
      except Exception:
          if conn:
              conn.rollback()
          current_app.logger.exception("Error in expire_pending_approvals")
          return jsonify({"error": "Unable to expire approvals"}), 500
      finally:
          if conn:
              conn.close()
  ```

- [ ] Run `pytest tests/ -x -q` — all existing tests pass.

---

## Step 4: Test `POST /admin/soar/approvals/expire-pending` in `test_soar_worker_admin_run_control.py`

Read `tests/test_soar_worker_admin_run_control.py` in full before editing.

- [ ] **Test: unauthenticated request returns 401**
  - `POST /admin/soar/approvals/expire-pending` with no session.
  - Response 401.

- [ ] **Test: viewer returns 403**
  - Authenticated as viewer role.
  - Response 403.

- [ ] **Test: analyst returns 403**
  - Authenticated as analyst role.
  - Response 403.

- [ ] **Test: super_admin with no expired approvals returns zero counts**
  - Authenticated as super_admin. No expired approvals in DB.
  - Response 200. `expired_approvals == 0`. `skipped_queue_rows == 0`.
  - `expired_approval_ids == []`. `skipped_queue_ids == []`.

- [ ] **Test: endpoint expires overdue pending approvals**
  - Insert a `pending` approval with past `expires_at` (`postgres_db` fixture).
  - `POST /admin/soar/approvals/expire-pending` (super_admin).
  - Response 200. `expired_approvals == 1`. ID is in `expired_approval_ids`.
  - Re-read approval from DB — `status == "expired"`.

- [ ] **Test: endpoint sweeps awaiting_approval queue rows**
  - Insert an `awaiting_approval` queue row with a linked approval already at `expired`.
  - `POST /admin/soar/approvals/expire-pending`.
  - Response `skipped_queue_rows == 1`. ID in `skipped_queue_ids`.
  - Re-read queue row — `status == "skipped"`, `last_error == "approval expired"`.

- [ ] **Test: endpoint expires approvals AND sweeps queue rows in one call**
  - Insert a `pending` approval with past `expires_at`, linked to an `awaiting_approval`
    queue row.
  - `POST /admin/soar/approvals/expire-pending`.
  - Response: `expired_approvals == 1` AND `skipped_queue_rows == 1`.
  - Approval status `expired`. Queue row status `skipped`.

- [ ] **Test: endpoint is idempotent**
  - Call endpoint once → processes 1 approval and 1 queue row.
  - Call endpoint again → `expired_approvals == 0`, `skipped_queue_rows == 0`.
  - No DB errors on second call.

- [ ] **Test: retry_count not incremented by endpoint**
  - Queue row has `retry_count = 1`, `max_retries = 3`. Expired approval linked.
  - Call endpoint.
  - Queue row `retry_count == 1` after sweep.

- [ ] Run `pytest tests/ -x -q` — all tests pass.

---

## Step 5: Final audit

- [ ] Confirm only these files were created or modified:
  - `schema.sql` — index addition only (Step 0, if needed).
  - `core/response_action_queue_store.py` — `sweep_terminal_approval_queue_rows` only.
  - `routes/admin_routes.py` — two imports + one endpoint.
  - `tests/test_response_action_queue_store.py` (or equivalent) — new sweep tests.
  - `tests/test_soar_worker_admin_run_control.py` — new admin endpoint tests.

- [ ] Confirm `routes/approval_routes.py` was NOT modified. GET routes remain read-only.
- [ ] Confirm no scheduler, cron, thread, or daemon was introduced.
- [ ] Confirm no frontend files were modified.
- [ ] Confirm `soar_action_worker.py` was not modified.
- [ ] Confirm `approval_store.py` was not modified (only imported in admin_routes).
- [ ] Confirm no `retry_count` increment appears in any new code path.
- [ ] Confirm `sweep_terminal_approval_queue_rows` does not call `conn.commit()`.

- [ ] Run full suite: `pytest tests/ -x -q` — clean.
- [ ] Check count: confirm total test count is at or above 409 (the pre-phase baseline).
