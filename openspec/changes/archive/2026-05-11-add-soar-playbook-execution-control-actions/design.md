# Design: SOAR Playbook Execution Control Actions

## Current State

`playbook_executions` rows are created by `engines/soar_playbook_orchestrator.py` post-commit
and consumed by the simulation executor. The store already has full state-transition helpers
for all six statuses: `pending`, `running`, `awaiting_approval`, `success`, `failed`,
`abandoned`. The approval system already links approval requests to playbook executions via
`approval_requests.playbook_execution_id` and `playbook_step_index`.

`routes/playbook_routes.py` has GET routes for executions only. No POST mutation routes
exist. `PlaybooksPanel.js` is read-only.

One existing bug: the route-level `_VALID_EXECUTION_STATUSES` constant (line 37,
`playbook_routes.py`) does not include `awaiting_approval`, which means filtering the
execution list by that status returns HTTP 400. This must be fixed as part of this change.

One existing schema issue must be fixed before retry is implemented: the current
`idx_playbook_executions_playbook_alert_unique` index is unique on `(playbook_id, alert_id)`
for every non-null `alert_id`. That blocks immutable retry history because a retry needs to
create a new execution row with the same `playbook_id` and `alert_id` as a historical
`failed` or `abandoned` source row.

Replace it with an active-only partial unique index:
```sql
DROP INDEX IF EXISTS idx_playbook_executions_playbook_alert_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_executions_playbook_alert_unique
    ON playbook_executions (playbook_id, alert_id)
    WHERE alert_id IS NOT NULL
      AND status IN ('pending', 'running', 'awaiting_approval');
```

This preserves idempotency for active scheduling while allowing historical `success`,
`failed`, and `abandoned` rows to coexist for the same playbook and alert.

---

## Execution State Transition Rules

All valid states and their meanings:

| Status | Meaning | Terminal? |
|---|---|---|
| `pending` | Queued, not yet claimed by executor | No |
| `running` | Currently being processed by executor | No |
| `awaiting_approval` | Paused at an approval-gated step | No |
| `success` | All steps completed successfully | Yes |
| `failed` | Executor stopped due to step failure | Yes |
| `abandoned` | Operator-terminated | Yes |

Terminal states: `success`, `failed`, `abandoned`. Rows in terminal states accumulate as
immutable history.

### Control action → allowed source states

| Action | Allowed Source States | Resulting State |
|---|---|---|
| retry | `failed`, `abandoned` | New `pending` row created |
| abandon | `pending`, `running`, `awaiting_approval` | `abandoned` (terminal) |
| resume | `awaiting_approval` only | `pending` |

Retry does not mutate the original row. It creates a new execution row.

---

## Retry Semantics

**Endpoint:** `POST /playbook-executions/<id>/retry`

**Source states:** `failed`, `abandoned` only. Any other state returns HTTP 409.

**Behavior:**
1. Fetch the source execution by id. If not found, return HTTP 404.
2. Verify `status` is `failed` or `abandoned`. If not, return HTTP 409 with a message
   identifying the current status.
3. Verify the referenced `playbook_id` still exists (the definition may have been deleted).
   If not found, return HTTP 409 with a clear message.
4. Verify there is no active execution (`pending`, `running`, or `awaiting_approval`) for the
   same non-null `playbook_id + alert_id` pair. If one exists, return HTTP 409. The
   active-only unique index is the final safety guard.
5. Call `create_retry_execution(conn, source_execution_id)` to INSERT a new execution row
   with `status='pending'`, `steps_log=[]`, `last_completed_step=NULL`, and the same
   `playbook_id`, `alert_id`, `incident_id` as the source.
6. Commit.
7. Write audit log entry: action `PLAYBOOK_EXECUTION_RETRY`, details include source
   execution id and new execution id.
8. Return HTTP 201 with the new execution id and a simulation-labeled message.

**Immutability guarantee:**
The source execution row is never touched. It remains in its terminal state as permanent
history. The new row starts fresh with no step history.

**New execution behavior:**
The new `pending` row sits in the queue until the operator manually runs the executor.
No automatic execution is triggered by the retry endpoint.

**New store function — `create_retry_execution(conn, source_execution_id: int) -> int`:**
```
1. Fetch source execution by id. Raise ValueError if not found.
2. Raise ValueError if status is not in {'failed', 'abandoned'}.
3. INSERT new playbook_executions row with:
   - playbook_id = source.playbook_id
   - alert_id = source.alert_id
   - incident_id = source.incident_id
   - status = 'pending'
   - steps_log = '[]'
   - last_completed_step = NULL
4. If the INSERT conflicts with the active-only uniqueness rule, raise `ValueError` with a
   message indicating an active execution already exists for the same playbook and alert.
5. RETURNING id — return as int.
Caller commits. No lock on source row required.
```

---

## Abandon Semantics

**Endpoint:** `POST /playbook-executions/<id>/abandon`

**Source states:** `pending`, `running`, `awaiting_approval`. Idempotent on `abandoned`.
Returns HTTP 409 for `success` and `failed`.

**Behavior:**
1. Fetch the execution by id. If not found, return HTTP 404.
2. If status is `abandoned`, return HTTP 200 with `{"outcome": "no_op", ...}` — no DB write,
   no audit entry. Idempotent.
3. If status is `success` or `failed`, return HTTP 409. These are terminal states that
   represent completed work; abandoning them is a logic error.
4. If status is `pending`, `running`, or `awaiting_approval`, call
   `abandon_playbook_execution(conn, execution_id)` which transitions to `abandoned` and
   sets `completed_at`.
5. Commit.
6. Write audit log entry: action `PLAYBOOK_EXECUTION_ABANDON`, details include previous
   status.
7. Return HTTP 200 with `{"outcome": "abandoned", ...}`.

**Running state consideration:**
If an execution is in `running` state, the executor may be actively processing it in
a concurrent CLI invocation. The `FOR UPDATE SKIP LOCKED` pattern in the store means
the executor holds a row lock while processing. If the executor holds the lock, the
abandon transition will block until the lock is released. This is acceptable behavior
for a manual, non-daemon system — concurrent CLI runs are rare, and the lock is
short-lived. The implementer must not add a `SKIP LOCKED` to the abandon transition,
or else a running row could be abandoned while the executor is mid-step.

**New store function — `abandon_playbook_execution(conn, execution_id: int) -> str`:**
```
1. Run UPDATE ... WHERE id = %s AND status IN ('pending', 'running', 'awaiting_approval').
   SET status = 'abandoned', completed_at = NOW().
   RETURNING status.
2. If no row returned, fetch current status.
   - If 'abandoned': return 'no_op'.
   - If 'success' or 'failed': raise ValueError (caller returns 409).
   - If None (row doesn't exist): raise ValueError with 404-style message.
3. Otherwise return 'ok'.
Caller commits.
```

---

## Resume Semantics

**Endpoint:** `POST /playbook-executions/<id>/resume`

**Source states:** `awaiting_approval` only. Any other state returns HTTP 409.

**Behavior:**
1. Fetch the execution by id. If not found, return HTTP 404.
2. Verify `status` is `awaiting_approval`. If not, return HTTP 409 with current status.
3. Determine the gating step index. The gating step is the step the execution is paused
   at. Derive it from `steps_log`: the last entry with `status = 'awaiting_approval'` holds
   the step index. If `steps_log` contains no such entry, fall back to
   `(last_completed_step or -1) + 1`.
4. Call `get_latest_playbook_step_approval_request(conn, playbook_execution_id=id,
   playbook_step_index=gating_step_index)` from `core.approval_store`.
5. If the result is None or `result["status"] != "approved"`, return HTTP 409 with a message
   stating the approval for this step is not in `approved` state.
6. Call `update_execution_status(conn, execution_id, 'pending')` to re-queue the
   execution. This uses the existing generic status transition.
7. Commit.
8. Write audit log entry: action `PLAYBOOK_EXECUTION_RESUME`, details include gating step
   index and the linked approval request id.
9. Return HTTP 200 with a message indicating the execution is re-queued for simulation.

**Approval safety guarantee:**
Resume does not approve the approval request. It only reads the approval state. The
approval must already be in `approved` state through the normal `POST /approvals/<id>/decision`
flow. If the approval is `pending`, `denied`, or `expired`, resume returns 409 and the
execution remains in `awaiting_approval`.

**What happens after resume:**
The execution is now `pending`. It will be picked up by the next invocation of
`scripts/run_playbook_executor_once.py`. The executor should check the approval state
again before continuing past the gated step (defense-in-depth — the store's
`set_playbook_execution_resumed_running` already enforces `WHERE status = 'awaiting_approval'`
as a guard, but the resume endpoint transitions to `pending`, so the executor uses
`claim_next_pending_playbook_execution` to pick it up).

**No new store function required.** Resume uses the existing `update_execution_status` after
verifying approval state in the route handler.

---

## Auth Rules

| Endpoint | Required role |
|---|---|
| `POST /playbook-executions/<id>/retry` | `super_admin_required` |
| `POST /playbook-executions/<id>/abandon` | `super_admin_required` |
| `POST /playbook-executions/<id>/resume` | `super_admin_required` |
| All GET execution routes (existing) | `analyst_or_super_admin_required` (unchanged) |

Analysts see execution state but cannot trigger any control action. Auth enforcement is via
existing `@login_required` + `@super_admin_required` decorators in `playbook_routes.py`.

---

## UI Behavior

### PlaybooksPanel.js — Executions tab

Add per-row control buttons visible only when `isSuperAdmin === true`.

**Button visibility by status:**

| Execution status | Retry shown | Abandon shown | Resume shown |
|---|---|---|---|
| `pending` | No | Yes | No |
| `running` | No | Yes | No |
| `awaiting_approval` | No | Yes | Yes |
| `failed` | Yes | No | No |
| `abandoned` | Yes | No | No |
| `success` | No | No | No |

Do not show controls for `success` — it is complete with no valid action.

**Button labels:**
- Retry: "Retry simulation"
- Abandon: "Abandon"
- Resume: "Resume simulation"

**Abandon confirmation:**
Before calling the abandon API, render a `window.confirm` or inline confirmation prompt with
the message: "Abandon this execution? It will be moved to abandoned state and will not
continue." If the operator cancels, no API call is made.

**In-flight state:**
Each row tracks its own in-flight state (e.g., `actionInProgress[id]`). Buttons for that
row are disabled while the call is in progress. Other rows are unaffected.

**Per-row error feedback:**
Display a short error message below or beside the control buttons if the API returns an
error. Clear it on the next successful action or refresh. Do not use global panel-level
error state for per-row control failures.

**After success:**
Quietly re-fetch the execution list (`loadExecutions({ quiet: true })`) to reflect the
updated status. Do not reset the status filter or other panel state.

**Subtitle update:**
Change the `PlaybooksPanel` subtitle from "Playbooks are visible only; execution is not
enabled yet." to a copy that reflects simulation controls exist for super_admin. Suggested:
"Simulation-only playbook controls. Analyst users have read-only access."

**Simulation labeling:**
The words "real execution", "block", "firewall", or "remediation" must not appear in control
button labels, confirmation text, or success feedback. Use "simulation", "simulate", or
"retry simulation" consistently.

---

## Audit and Logging

Use `log_audit_event` from `core.audit_helpers` (same pattern as existing admin routes).

| Control action | Audit action constant |
|---|---|
| retry | `PLAYBOOK_EXECUTION_RETRY` |
| abandon | `PLAYBOOK_EXECUTION_ABANDON` |
| resume | `PLAYBOOK_EXECUTION_RESUME` |

**Details to include per audit entry:**

- retry: `source_execution_id`, `new_execution_id`, `playbook_id`
- abandon: `execution_id`, `previous_status`, `playbook_id`
- resume: `execution_id`, `playbook_id`, `gating_step_index`, `approval_request_id`

Abandon on an already-`abandoned` execution (no-op path) does NOT write an audit entry —
idempotent no-ops are silent.

---

## Store Additions: core/playbook_store.py

Two new functions are added. One existing function is updated for the active-only uniqueness
predicate.

### Active-only idempotency predicate

`create_pending_playbook_execution_once` currently uses:
```sql
ON CONFLICT (playbook_id, alert_id)
    WHERE alert_id IS NOT NULL
    DO NOTHING
```

It must be updated to match the new active-only index:
```sql
ON CONFLICT (playbook_id, alert_id)
    WHERE alert_id IS NOT NULL
      AND status IN ('pending', 'running', 'awaiting_approval')
    DO NOTHING
```

The schema index and store conflict predicate must remain aligned. Do not drop uniqueness
entirely.

### `create_retry_execution(conn, source_execution_id: int) -> int`

Creates a new `pending` execution copying `playbook_id`, `alert_id`, `incident_id` from the
source. Source must be in `failed` or `abandoned`. Raises `ValueError` otherwise. Returns
the new execution id.

Does not mutate the source row. It intentionally creates immutable retry history, but it must
not permit duplicate active executions. If a `pending`, `running`, or `awaiting_approval`
execution already exists for the same non-null `playbook_id + alert_id`, the active-only
unique index must block the insert and the helper/route must convert that into a conflict.

### `abandon_playbook_execution(conn, execution_id: int) -> str`

Returns `'ok'` on successful transition, `'no_op'` if already abandoned, raises `ValueError`
for `success`/`failed`/not-found cases. Caller commits.

---

## Route Fix: _VALID_EXECUTION_STATUSES in playbook_routes.py

The constant on line 37 of `playbook_routes.py` currently reads:
```python
_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "success", "failed", "abandoned"}
)
```

It is missing `"awaiting_approval"`. This causes the `GET /playbook-executions?status=awaiting_approval`
filter to return HTTP 400. Fix this at the top of the implementation step, before adding new
routes. The fix is a one-line addition:
```python
_VALID_EXECUTION_STATUSES = frozenset(
    {"pending", "running", "awaiting_approval", "success", "failed", "abandoned"}
)
```

---

## Test Strategy

New file: `tests/test_playbook_control_actions.py`. Uses the real test database. Follows the
Flask test client pattern established in `tests/test_soar_queue_visibility_api.py`.

### Retry tests

- Duplicate active `pending`, `running`, and `awaiting_approval` executions for the same
  non-null `playbook_id + alert_id` are blocked by the active-only uniqueness rule.
- Historical `success`, `failed`, and `abandoned` rows for the same non-null
  `playbook_id + alert_id` can coexist.
- From `failed` → HTTP 201, new execution row in `pending`, source row unchanged.
- From `abandoned` → HTTP 201, new execution row in `pending`, source row unchanged.
- Retry is blocked with HTTP 409 if an active `pending`, `running`, or `awaiting_approval`
  execution already exists for the same non-null `playbook_id + alert_id`.
- From `pending` → HTTP 409.
- From `running` → HTTP 409.
- From `awaiting_approval` → HTTP 409.
- From `success` → HTTP 409.
- Retry with a deleted `playbook_id` → HTTP 409.
- New execution has empty `steps_log` and null `last_completed_step`.
- Response body contains `new_execution_id`.
- Audit log contains `PLAYBOOK_EXECUTION_RETRY` entry after success.
- Analyst request → HTTP 403.
- Unauthenticated → HTTP 401.

### Abandon tests

- From `pending` → HTTP 200, status becomes `abandoned`, `completed_at` is set.
- From `running` → HTTP 200, status becomes `abandoned`.
- From `awaiting_approval` → HTTP 200, status becomes `abandoned`.
- Already `abandoned` → HTTP 200, `outcome: no_op`, row unchanged, no audit entry.
- From `success` → HTTP 409.
- From `failed` → HTTP 409.
- Audit log contains `PLAYBOOK_EXECUTION_ABANDON` entry (non-no-op only).
- Analyst request → HTTP 403.
- Unauthenticated → HTTP 401.

### Resume tests

- From `awaiting_approval` with `approved` approval for gating step → HTTP 200, status
  becomes `pending`.
- From `awaiting_approval` with `pending` approval → HTTP 409.
- From `awaiting_approval` with `denied` approval → HTTP 409.
- From `awaiting_approval` with no approval record → HTTP 409.
- From `pending` → HTTP 409.
- From `running` → HTTP 409.
- From `success` → HTTP 409.
- From `failed` → HTTP 409.
- From `abandoned` → HTTP 409.
- After resume, execution is in `pending` (eligible for next executor run).
- Approval request is not modified by resume.
- Audit log contains `PLAYBOOK_EXECUTION_RESUME` entry after success.
- Analyst request → HTTP 403.
- Unauthenticated → HTTP 401.

### status filter fix regression

- `GET /playbook-executions?status=awaiting_approval` returns HTTP 200 (not 400).

### General

- Execution not found → HTTP 404 for all three endpoints.
- No test writes to `blocked_ips`, calls a real adapter, or opens a network connection.
- No test invokes the simulation executor — control action tests are route-only.

---

## Safety Boundaries

- No adapter, subprocess, or real integration is called from any of the three route handlers.
- No `response_actions_queue` rows are created or modified by any of the three endpoints.
- No approval requests are created or decided — resume only reads approval state.
- Retry creates a new execution row and nothing else. It does not start execution.
- Resume transitions to `pending` only — the executor is not invoked within the request.
- Abandon never touches `success` or `failed` rows. Completed simulation history is
  preserved.
- All three endpoints are `super_admin_required`. Analyst users cannot trigger any mutation.
- The abandon transition for `running` rows relies on DB locking, not application-level
  concurrency control. This is safe for the current non-daemon model.

---

## Risks / Stop Conditions

**Retry conflicts with the unique partial index.**
`playbook_executions` currently has a partial unique index `ON (playbook_id, alert_id) WHERE
alert_id IS NOT NULL`. That blocks retry. The implementation must replace it with the
active-only partial unique index before adding retry code. If the replacement cannot be made
safely, stop. Do not bypass uniqueness in application code and do not drop safety entirely.

**Abandon during active executor run.**
If `scripts/run_playbook_executor_once.py` is running concurrently and holds a row lock on a
`running` execution, the abandon transition will block until the executor finishes or aborts.
This is safe behavior — the executor either finishes (row moves to `success`/`failed` before
abandon attempts) or releases the lock (abandon then succeeds). Do NOT add `SKIP LOCKED` to
the abandon transition.

**Resume after partial approval state change.**
Between the resume endpoint verifying approval state and committing the status transition,
the approval could be expired or denied by the expiration cleanup endpoint. This is a TOCTOU
window. Mitigation: the resume route should run the approval verification inside the same
transaction as the status update, using `SELECT ... FOR UPDATE` on the approval row if the
schema supports it. If not, the window is short and the worst outcome is that the execution
returns to `pending` and the executor finds no valid approval when it tries to process — the
executor should handle that gracefully.

**`steps_log` gating step derivation.**
The resume endpoint derives the gating step index from `steps_log`. If the executor does not
consistently write a `steps_log` entry with a recognizable `status: 'awaiting_approval'`
marker, the fallback calculation `(last_completed_step or -1) + 1` may produce the wrong
step index, and the approval lookup will find nothing. Before implementing resume, confirm
the exact `steps_log` entry format the simulation executor writes for approval-gated steps.

**`PlaybooksPanel` control state on stale data.**
If an operator has the panel open and another operator acts on the same execution, the first
operator's panel will show stale status and incorrect control button visibility until they
refresh. For a simulation-only, super_admin-only system this is acceptable. Do not add
websocket or polling to address this in this change.
