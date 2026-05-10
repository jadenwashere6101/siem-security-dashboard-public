# Tasks: SOAR Playbook Execution Control Actions

Run these six regression tests after every backend step. If any fail, revert the step before
continuing.

```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

Do not touch ingest, detection, correlation, or any existing SOAR queue/approval/incident
behavior.

---

## Pre-implementation: Resolve Retry Index Constraint

Before writing any code, read `schema.sql` and locate the partial unique index on
`playbook_executions`. Confirm whether `ON CONFLICT (playbook_id, alert_id) WHERE alert_id
IS NOT NULL` would block a retry INSERT for the same `(playbook_id, alert_id)` pair.

- [ ] Read the index definition in `schema.sql`.
- [ ] If the index would block retries: replace it with an active-only partial unique index
  using `WHERE alert_id IS NOT NULL AND status IN ('pending', 'running', 'awaiting_approval')`.
  This must still block duplicate active scheduling for the same `playbook_id + alert_id`
  while allowing historical `success`, `failed`, and `abandoned` rows. Add the replacement
  DDL to `schema.sql` before adding route/control code. The DDL should drop the previous
  broad index by name and recreate it with the active-only predicate. Run the existing
  backend tests after the schema change.
- [ ] Update `create_pending_playbook_execution_once` to use the same active-only
  `ON CONFLICT (playbook_id, alert_id) WHERE alert_id IS NOT NULL AND status IN ('pending',
  'running', 'awaiting_approval') DO NOTHING` predicate. The index predicate and store
  conflict predicate must match.
- [ ] If the index does not block retries (e.g., it was already narrowed during the
  orchestrator implementation): document this and proceed without schema changes.

**Stop condition:** Do not implement `create_retry_execution` until this is resolved.
Ambiguity in the index scope will cause `IntegrityError` in production if not addressed here.
Do not drop uniqueness entirely.

---

## Step 1: Store Additions — core/playbook_store.py

Read `core/playbook_store.py` fully before making any changes. The existing
`_TERMINAL_EXECUTION_STATUSES`, `_VALID_EXECUTION_STATUSES`, and `_execution_row_to_dict`
are already defined — do not duplicate them.

### 1A: create_retry_execution

- [ ] Add `create_retry_execution(conn, source_execution_id: int) -> int` after the existing
  `create_pending_playbook_execution_once` function.
- [ ] Fetch the source execution via `get_playbook_execution(conn, source_execution_id)`.
  Raise `ValueError("execution not found")` if None.
- [ ] Raise `ValueError` if source status is not in `{"failed", "abandoned"}`. Include the
  current status in the error message.
- [ ] INSERT a new row: `playbook_id`, `alert_id`, `incident_id` copied from source.
  `status = 'pending'`, `steps_log = '[]'` (via `Json([])`), `last_completed_step = NULL`.
  RETURNING id.
- [ ] If an active `pending`, `running`, or `awaiting_approval` execution already exists for
  the same non-null `playbook_id + alert_id`, raise `ValueError` so the route can return
  HTTP 409. The active-only unique index is the final guard.
- [ ] Return the new `int` execution id.
- [ ] Do NOT use `ON CONFLICT DO NOTHING`. Do NOT copy `steps_log` or `last_completed_step`
  from the source. Do NOT touch the source row.

Verification:
- [ ] Run `python3 -m py_compile core/playbook_store.py`.
- [ ] Run regression suite — all six green.

### 1B: abandon_playbook_execution

- [ ] Add `abandon_playbook_execution(conn, execution_id: int) -> str` after
  `create_retry_execution`.
- [ ] Run:
  ```sql
  UPDATE playbook_executions
  SET status = 'abandoned', completed_at = NOW()
  WHERE id = %s
    AND status IN ('pending', 'running', 'awaiting_approval')
  RETURNING status
  ```
- [ ] If RETURNING returns a row: return `'ok'`.
- [ ] If no row returned, fetch current row by `get_playbook_execution(conn, execution_id)`.
  - Row is None → raise `ValueError("execution not found")`.
  - Status is `'abandoned'` → return `'no_op'`.
  - Status is `'success'` or `'failed'` → raise `ValueError("cannot abandon terminal execution with status '{status}'")`
    (caller converts to HTTP 409).
- [ ] Do NOT commit — caller commits.

Verification:
- [ ] Run `python3 -m py_compile core/playbook_store.py`.
- [ ] Run regression suite — all six green.

---

## Step 2: Route Fix and New Handlers — routes/playbook_routes.py

Read `routes/playbook_routes.py` fully before making changes. Read `core/approval_store.py`
to understand `get_latest_playbook_step_approval_request`.

### 2A: Fix _VALID_EXECUTION_STATUSES

- [ ] Locate the `_VALID_EXECUTION_STATUSES` constant (near line 37). Add `"awaiting_approval"`
  to the frozenset. The corrected definition:
  ```python
  _VALID_EXECUTION_STATUSES = frozenset(
      {"pending", "running", "awaiting_approval", "success", "failed", "abandoned"}
  )
  ```
- [ ] Confirm no other code in the file needs updating after this change.

Verification:
- [ ] `GET /playbook-executions?status=awaiting_approval` returns HTTP 200, not 400.
- [ ] Run regression suite — all six green.

### 2B: Import additions

- [ ] Add to the imports in `playbook_routes.py`:
  ```python
  from core.audit_helpers import log_audit_event
  from core.approval_store import get_latest_playbook_step_approval_request
  from core.playbook_store import (
      # existing imports ...
      abandon_playbook_execution,
      create_retry_execution,
      update_execution_status,
  )
  ```
- [ ] Confirm no circular import is introduced.

### 2C: POST /playbook-executions/<id>/retry

- [ ] Add route handler `retry_playbook_execution_route(execution_id)`.
- [ ] Decorators: `@playbook_bp.route("/playbook-executions/<int:execution_id>/retry", methods=["POST"])`,
  `@login_required`, `@super_admin_required`.
- [ ] Fetch execution; return 404 if not found.
- [ ] Verify status is `failed` or `abandoned`; return 409 if not.
  Response body: `{"error": "retry requires failed or abandoned execution; current status: <status>"}`.
- [ ] Verify `playbook_id` still exists via `get_playbook_definition`; return 409 if deleted.
- [ ] Return 409 if an active `pending`, `running`, or `awaiting_approval` execution already
  exists for the same non-null `playbook_id + alert_id`.
- [ ] Call `create_retry_execution(conn, execution_id)`. Commit.
- [ ] Write audit log: action `"PLAYBOOK_EXECUTION_RETRY"`, include
  `source_execution_id`, `new_execution_id`, `playbook_id`.
- [ ] Return 201:
  ```json
  {
    "source_execution_id": <int>,
    "new_execution_id": <int>,
    "status": "pending",
    "message": "New simulation execution created. No steps have run yet."
  }
  ```
- [ ] Wrap in try/except; rollback on error; return 500 on unexpected error.

Verification:
- [ ] Run regression suite — all six green.

### 2D: POST /playbook-executions/<id>/abandon

- [ ] Add route handler `abandon_playbook_execution_route(execution_id)`.
- [ ] Decorators: `@playbook_bp.route("/playbook-executions/<int:execution_id>/abandon", methods=["POST"])`,
  `@login_required`, `@super_admin_required`.
- [ ] Fetch execution; return 404 if not found.
- [ ] Call `abandon_playbook_execution(conn, execution_id)`.
  - Returns `'no_op'` → commit (no-op), return 200 `{"outcome": "no_op", "execution_id": id}`.
    Do NOT write audit log for no-ops.
  - Raises `ValueError` containing "cannot abandon terminal" → rollback, return 409.
  - Returns `'ok'` → commit, write audit log `"PLAYBOOK_EXECUTION_ABANDON"` with
    `execution_id` and `previous_status`, return 200
    `{"outcome": "abandoned", "execution_id": id}`.
- [ ] Wrap in try/except; rollback on error; return 500 on unexpected error.

Verification:
- [ ] Run regression suite — all six green.

### 2E: POST /playbook-executions/<id>/resume

- [ ] Add route handler `resume_playbook_execution_route(execution_id)`.
- [ ] Decorators: `@playbook_bp.route("/playbook-executions/<int:execution_id>/resume", methods=["POST"])`,
  `@login_required`, `@super_admin_required`.
- [ ] Fetch execution; return 404 if not found.
- [ ] Verify status is `awaiting_approval`; return 409 with current status if not.
- [ ] Derive gating step index:
  - Scan `steps_log` (a list) for the last entry with `status == 'awaiting_approval'`.
    If found, use its `step_index`.
  - Fallback: `(execution["last_completed_step"] if execution["last_completed_step"] is not None else -1) + 1`.
- [ ] Call `get_latest_playbook_step_approval_request(conn, playbook_execution_id=execution_id,
  playbook_step_index=gating_step_index)`.
- [ ] If result is None → return 409:
  `{"error": "no approval request found for gating step <index>"}`.
- [ ] If `result["status"] != "approved"` → return 409:
  `{"error": "approval for step <index> is not approved; current status: <approval_status>"}`.
- [ ] Call `update_execution_status(conn, execution_id, "pending")`. Commit.
- [ ] Write audit log: action `"PLAYBOOK_EXECUTION_RESUME"`, include `execution_id`,
  `playbook_id`, `gating_step_index`, `approval_request_id`.
- [ ] Return 200:
  ```json
  {
    "execution_id": <int>,
    "status": "pending",
    "message": "Simulation execution re-queued. Run the executor to continue."
  }
  ```
- [ ] Wrap in try/except; rollback on error; return 500 on unexpected error.

Verification:
- [ ] Run regression suite — all six green.

---

## Step 3: Service Additions — frontend/src/services/playbookService.js

Read `frontend/src/services/playbookService.js` before editing. Match the existing
fetch/error pattern for mutation calls (same as definition PUT/PATCH).

- [ ] Add `retryExecution(executionId)`:
  ```js
  POST /playbook-executions/<executionId>/retry
  ```
  Returns parsed JSON on success. Throws on non-2xx.

- [ ] Add `abandonExecution(executionId)`:
  ```js
  POST /playbook-executions/<executionId>/abandon
  ```

- [ ] Add `resumeExecution(executionId)`:
  ```js
  POST /playbook-executions/<executionId>/resume
  ```

- [ ] No request body is required for any of the three calls (all context comes from the
  execution id in the URL).

Verification:
- [ ] Run `npm run build` (or equivalent) in the frontend directory — no compile errors.

---

## Step 4: PlaybooksPanel Controls — frontend/src/components/PlaybooksPanel.js

Read `PlaybooksPanel.js` fully before editing. Pay attention to the `isSuperAdmin` check,
the existing in-flight state patterns (`defSubmitting`, `formSubmitting`), and how
`loadExecutions({ quiet: true })` is called.

### 4A: State additions

- [ ] Add `executionActionInProgress` state: a dict/object keyed by execution id, value bool.
  `const [executionActionInProgress, setExecutionActionInProgress] = useState({})`.
- [ ] Add `executionActionError` state: same shape, value is error string or null.
  `const [executionActionError, setExecutionActionError] = useState({})`.

### 4B: Helper to check valid actions

- [ ] Add a pure helper `getExecutionControls(status, isSuperAdmin)` that returns an object:
  ```js
  { canRetry: bool, canAbandon: bool, canResume: bool }
  ```
  Based on the state transition table in the design doc. Returns all false if `!isSuperAdmin`.

### 4C: Control handler functions

- [ ] Add `handleRetryExecution(executionId)`:
  - Set `executionActionInProgress[executionId] = true`, clear error for that id.
  - Call `retryExecution(executionId)` from the service.
  - On success: clear in-progress, call `loadExecutions({ quiet: true })`.
  - On error: set `executionActionError[executionId]` to the error message.
  - Always clear in-progress in a finally block.

- [ ] Add `handleAbandonExecution(executionId)`:
  - Show `window.confirm` with the message:
    "Abandon this execution? It will stop and cannot be resumed."
  - If confirmed: same pattern as retry handler.
  - If not confirmed: no-op.

- [ ] Add `handleResumeExecution(executionId)`:
  - Same pattern as retry handler, calling `resumeExecution(executionId)`.

### 4D: Control buttons in execution row

- [ ] In the executions table body, add a new `Actions` column header (only when
  `isSuperAdmin`): `{isSuperAdmin && <th>Actions</th>}`.
- [ ] In each execution row, render `{isSuperAdmin && <td>...</td>}` with the control
  buttons. Use `getExecutionControls(row.status, isSuperAdmin)` to decide which buttons to
  show:
  - Retry button: visible when `canRetry`, label "Retry simulation".
  - Abandon button: visible when `canAbandon`, label "Abandon".
  - Resume button: visible when `canResume`, label "Resume simulation".
  - Buttons are disabled when `executionActionInProgress[row.id]` is true.

- [ ] Below the buttons for that row, show `executionActionError[row.id]` in a small error
  style if set.

### 4E: Subtitle and labeling

- [ ] Update the `PlaybooksPanel` subtitle paragraph. Change:
  "Playbooks are visible only; execution is not enabled yet. This view loads configured
  definitions and execution records using read-only APIs."
  To:
  "Simulation-only playbook controls. Retry, abandon, and resume actions are available to
  super_admin users. Analyst users have read-only access."

- [ ] Confirm no button label uses the words "execute", "real", "firewall", or "block".

Verification:
- [ ] Manually confirm in browser (or via test):
  - As super_admin: Retry button visible on a failed/abandoned execution row.
  - As super_admin: Abandon button visible on a pending/running/awaiting_approval row.
  - As super_admin: Resume button visible on an awaiting_approval row.
  - As super_admin: No buttons on success rows.
  - As analyst: No control buttons visible anywhere.

---

## Step 5: Tests — tests/test_playbook_control_actions.py

Read `tests/test_soar_queue_visibility_api.py` and `tests/test_soar_worker_admin_run_control.py`
before writing. Use the Flask test client with a real test database. Do not mock the DB.

- [ ] Create `tests/test_playbook_control_actions.py`.

**Fixtures:**
- [ ] Create a helper that inserts a `playbook_definitions` row and a `playbook_executions`
  row in a given status. Reuse the DB setup pattern from existing integration tests.
- [ ] Ensure each test uses an isolated DB state (no shared rows across tests).

**Retry tests:**
- [ ] Duplicate active `pending` executions for the same non-null `playbook_id + alert_id`
  are blocked.
- [ ] Duplicate active `running` executions for the same non-null `playbook_id + alert_id`
  are blocked.
- [ ] Duplicate active `awaiting_approval` executions for the same non-null
  `playbook_id + alert_id` are blocked.
- [ ] Historical `success`, `failed`, and `abandoned` executions for the same non-null
  `playbook_id + alert_id` are allowed to coexist.
- [ ] From `failed` → 201, new execution row in DB with status `pending`, source row
  unchanged, `steps_log = []`, `last_completed_step` is null.
- [ ] From `abandoned` → 201, same assertions.
- [ ] Retry from `failed` or `abandoned` is blocked with 409 if an active `pending`,
  `running`, or `awaiting_approval` execution already exists for the same non-null
  `playbook_id + alert_id`.
- [ ] From `pending` → 409.
- [ ] From `running` → 409.
- [ ] From `awaiting_approval` → 409.
- [ ] From `success` → 409.
- [ ] `new_execution_id` in response body.
- [ ] Audit log contains a row with action `PLAYBOOK_EXECUTION_RETRY` after success.
- [ ] Analyst auth → 403.
- [ ] Unauthenticated → 401.

**Abandon tests:**
- [ ] From `pending` → 200, `outcome: abandoned`, row has `status = 'abandoned'` and
  `completed_at` is set.
- [ ] From `running` → 200, same.
- [ ] From `awaiting_approval` → 200, same.
- [ ] Already `abandoned` → 200, `outcome: no_op`, row unchanged.
- [ ] From `success` → 409.
- [ ] From `failed` → 409.
- [ ] No audit entry for no-op.
- [ ] Audit log contains `PLAYBOOK_EXECUTION_ABANDON` on non-no-op.
- [ ] Analyst auth → 403.
- [ ] Unauthenticated → 401.

**Resume tests:**
- [ ] From `awaiting_approval` with `approved` approval → 200, execution transitions to
  `pending`.
- [ ] From `awaiting_approval` with `pending` approval → 409.
- [ ] From `awaiting_approval` with `denied` approval → 409.
- [ ] From `awaiting_approval` with `expired` approval → 409.
- [ ] From `awaiting_approval` with no approval record → 409.
- [ ] Approval request unchanged after resume.
- [ ] From `pending` → 409.
- [ ] From `running` → 409.
- [ ] From `success` → 409.
- [ ] From `failed` → 409.
- [ ] From `abandoned` → 409.
- [ ] Audit log contains `PLAYBOOK_EXECUTION_RESUME` on success.
- [ ] Analyst auth → 403.
- [ ] Unauthenticated → 401.

**Status filter fix regression:**
- [ ] `GET /playbook-executions?status=awaiting_approval` → 200 (not 400).

**General:**
- [ ] Execution not found → 404 for all three endpoints.
- [ ] No test calls the simulation executor, writes to `blocked_ips`, or opens a network
  connection.

- [ ] Run: `pytest tests/test_playbook_control_actions.py -x --tb=short -v`
- [ ] Run regression suite — all six green.

---

## Step 6: Regression and Safety Audit

- [ ] Run full backend suite: `pytest tests/ -x --tb=short -v`
- [ ] Confirm all pre-existing tests pass without modification.
- [ ] Confirm `routes/playbook_routes.py` new handlers do NOT import from:
  - `engines/soar_executor.py`
  - `engines/soar_action_worker.py`
  - `core/response_action_queue_store.py`
  - `integrations/soar_adapters/`
- [ ] Confirm no `subprocess`, `os.system`, or real firewall call appears in any new code.
- [ ] Confirm no new row was inserted into `response_actions_queue` during any test run.
- [ ] Confirm no new row was inserted into `blocked_ips` during any test run.
- [ ] Confirm `PlaybooksPanel.js` does not render any control button for analyst-role users.
- [ ] Confirm no daemon, background thread, cron, or scheduler was introduced.
- [ ] Confirm `routes/ingest_routes.py`, `engines/detection_engine.py`,
  `engines/correlation_engine.py`, and `engines/ingest_engine.py` were not modified.
- [ ] Confirm `git diff --stat HEAD` shows only the files introduced by this change:
  - `schema.sql` (only if partial index was narrowed in pre-implementation step)
  - `core/playbook_store.py`
  - `routes/playbook_routes.py`
  - `frontend/src/services/playbookService.js`
  - `frontend/src/components/PlaybooksPanel.js`
  - `tests/test_playbook_control_actions.py`

---

## Rollback / Stop Conditions

**Stop and do not proceed if:**

- The partial unique index on `(playbook_id, alert_id)` blocks retry INSERTs and you have
  not resolved the schema question in the pre-implementation step.
- Any of the six regression tests fail after any backend step.
- `routes/playbook_routes.py` after editing causes an import error or 500 on existing GET
  routes.
- The resume endpoint modifies an approval request row rather than just reading it.
- Any new route handler imports from adapter, queue, or executor modules.

**To roll back any individual step:** revert changes to the affected file and re-run the
regression suite. Confirm it is green before stopping.

---

## Suggested Verification Commands

```bash
# Syntax check
python3 -m py_compile core/playbook_store.py routes/playbook_routes.py

# New test file only
pytest tests/test_playbook_control_actions.py -x --tb=short -v

# Regression suite
pytest tests/test_failed_login_detection.py \
       tests/test_password_spraying_detection.py \
       tests/test_correlated_activity.py \
       tests/test_targeted_correlation.py \
       tests/test_ingest_api_contracts.py \
       tests/test_alert_mutation_api_contracts.py \
       -x --tb=short -v

# Full suite
pytest tests/ -x --tb=short -v

# Confirm files changed
git diff --stat HEAD
git status --short

# Frontend build
cd frontend && npm run build
```
