# Proposal: SOAR Playbook Execution Control Actions

## Problem

`playbook_executions` rows are created post-commit by the playbook orchestrator and can be
consumed by `scripts/run_playbook_executor_once.py`. But once an execution finishes or
gets stuck, there is no operator path forward. A `failed` execution sits permanently in
that state. An `abandoned` execution is a dead end. An `awaiting_approval` execution can only
be unblocked if the executor happens to be re-run after the approval is granted — and even
then, only if the executor specifically handles the resume path.

There are also no controls to proactively abandon a stuck `pending` or `running` execution
when something is clearly wrong.

Operators have visibility into execution state through `PlaybooksPanel` but zero ability to
act on what they see. For a simulation-only system this is manageable, but it means the panel
is purely observational and provides no feedback loop.

---

## Goals

- Give `super_admin` operators three tightly scoped simulation-only actions on individual
  `playbook_executions` rows: **retry**, **abandon**, and **resume**.
- Keep the actions narrow, explicit, and audited.
- Preserve complete execution history: no existing row is mutated in a way that destroys audit
  state.
- Keep the backend stateless and idempotent-safe: no hidden automatic loops, no scheduler
  coupling, no executor invocation from within the route handler.
- Update `PlaybooksPanel` to surface these controls for `super_admin` users only, with clear
  simulation-only labeling throughout.

---

## Scope

**Backend:**
- New store helpers in `core/playbook_store.py`:
  `create_retry_execution`, `abandon_playbook_execution`.
- Three new POST route handlers added to `routes/playbook_routes.py`:
  - `POST /playbook-executions/<id>/retry`
  - `POST /playbook-executions/<id>/abandon`
  - `POST /playbook-executions/<id>/resume`
- All three require `@super_admin_required`.
- All three write audit log entries via `core.audit_helpers.log_audit_event`.
- Fix the `_VALID_EXECUTION_STATUSES` filter set in `playbook_routes.py` to include
  `awaiting_approval`, which is currently missing.

**Frontend:**
- Three new API calls added to `frontend/src/services/playbookService.js`:
  `retryExecution`, `abandonExecution`, `resumeExecution`.
- `PlaybooksPanel.js`:
  - Per-row execution controls (Retry / Abandon / Resume) rendered only for `super_admin`.
  - Controls appear only when the action is valid for the row's current status.
  - Abandon prompts a confirmation before calling the API.
  - All control buttons carry visible "simulation" context.
  - Subtitle copy updated to reflect that simulation controls exist for super_admin.
  - After any control action succeeds, execution list refreshes quietly.
  - Per-row in-flight state and per-row error feedback.

**Tests:**
- New `tests/test_playbook_control_actions.py` covering all state-transition cases, auth
  enforcement, idempotency, and resume approval-check behavior.

---

## Out of Scope

- No real remediation, firewall command, blocklist write, adapter call, or subprocess.
- No SOAR queue (`response_actions_queue`) coupling or mutation.
- No approval creation or decision — resume only reads approval state.
- No daemon, background thread, systemd unit, APScheduler job, or cron.
- No automatic retry on failure — all control actions are explicit operator invocations.
- No ingest, detection, or correlation changes.
- No broad `App.js` restructuring.
- No changes to analyst-visible routes or analyst UI behavior.
- No changes to the existing SOAR queue, approval decisions, or incident management.

---

## Success Criteria

- `POST /playbook-executions/<id>/retry` from a `failed` or `abandoned` execution creates a
  new `pending` execution row referencing the same playbook definition, alert, and incident.
  The original row is unchanged. Returns the new execution id.

- `POST /playbook-executions/<id>/retry` from any non-terminal state returns HTTP 409.

- `POST /playbook-executions/<id>/abandon` from `pending`, `running`, or `awaiting_approval`
  transitions the execution to `abandoned` and sets `completed_at`.

- `POST /playbook-executions/<id>/abandon` on an already-`abandoned` execution returns HTTP
  200 with a no-op indicator — idempotent.

- `POST /playbook-executions/<id>/abandon` on `success` or `failed` returns HTTP 409.

- `POST /playbook-executions/<id>/resume` from `awaiting_approval` with an `approved`
  approval on the gating step transitions the execution to `pending`, making it eligible
  for the next executor run.

- `POST /playbook-executions/<id>/resume` from `awaiting_approval` with no approved approval
  returns HTTP 409 with a message that names the missing condition.

- `POST /playbook-executions/<id>/resume` from any non-`awaiting_approval` state returns
  HTTP 409.

- All three endpoints return HTTP 403 for analyst users and HTTP 401 for unauthenticated
  requests.

- All three endpoints write an audit log entry on every successful action.

- Retry, abandon, and resume controls are visible in `PlaybooksPanel` execution rows for
  `super_admin` only, gated by valid-state logic. Analyst users see no control buttons.

- No test in the new test file makes a real network connection, calls a real adapter, or
  writes to `blocked_ips` or any firewall-related table.
