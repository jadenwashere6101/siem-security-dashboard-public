# Design: Approval Foundation

---

## Current state

The system has:
- DB-backed SOAR response action queue.
- Worker runner and simulation executor.
- Adapter abstraction and dry-run firewall adapter.
- Incident schema, store, APIs, auto-linking, and UI.

The approval request schema, immutable event table, `core/approval_store.py`, and approval API
routes now exist. The worker does not pause for approvals, queue rows do not carry approval
state, and incidents do not have approval workflows. Phase 2.5C adds frontend approval
visibility and decision UI without wiring approvals into execution.

---

## Schema additions

All schema work is additive and uses `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`. Existing tables are not modified.

### `approval_requests`

```sql
CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE RESTRICT,
    queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE RESTRICT,
    requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    action TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'high'
        CHECK (risk_level IN ('medium', 'high', 'critical')),
    request_reason TEXT,
    decision_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (incident_id IS NOT NULL OR queue_id IS NOT NULL),
    CHECK (
        (status = 'pending' AND decided_at IS NULL)
        OR (status IN ('approved', 'denied', 'expired') AND decided_at IS NOT NULL)
    ),
    CHECK (
        (status = 'approved' AND approved_by IS NOT NULL)
        OR status IN ('pending', 'denied', 'expired')
    )
);
```

Field notes:
- `incident_id` ties the request to analyst case context.
- `queue_id` ties the request to a future queued execution target.
- At least one of `incident_id` or `queue_id` is required. Both may be present.
- `approved_by` is populated only for approved requests and references `users(id)`.
- `decided_by` records the actor for approved, denied, or manually expired decisions.
- `requested_by` is nullable so system-created requests can be represented.
- `action` stores the requested action name, for example `block_ip` or a future playbook step.
- `risk_level` supports future policy rules without changing schema.
- `request_reason` describes why approval is required.
- `decision_comment` stores analyst decision rationale.
- `expires_at` is required for every request so expiration semantics are deterministic.

Recommended indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_approval_requests_status
ON approval_requests (status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_incident_id
ON approval_requests (incident_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_queue_id
ON approval_requests (queue_id);

CREATE INDEX IF NOT EXISTS idx_approval_requests_expires_at
ON approval_requests (expires_at);

CREATE INDEX IF NOT EXISTS idx_approval_requests_pending_expiry
ON approval_requests (expires_at)
WHERE status = 'pending';
```

### `approval_request_events`

`approval_requests` is the current-state table. `approval_request_events` is append-only and
preserves an immutable history of approval lifecycle changes.

```sql
CREATE TABLE IF NOT EXISTS approval_request_events (
    id SERIAL PRIMARY KEY,
    approval_request_id INTEGER NOT NULL
        REFERENCES approval_requests(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('created', 'approved', 'denied', 'expired')),
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Recommended indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_approval_request_events_request_id
ON approval_request_events (approval_request_id);

CREATE INDEX IF NOT EXISTS idx_approval_request_events_created_at
ON approval_request_events (created_at);
```

No helper should update or delete rows from `approval_request_events`. Every lifecycle change
adds a new event row.

---

## Store/helper module

Create `core/approval_store.py` in the implementation phase. It must not import Flask route
modules, detection, correlation, queue worker modules, or frontend code. Use
`logging.getLogger(__name__)` if logging is needed.

Helpers do not commit and do not close the connection. The caller owns transaction boundaries.

### Constants

```python
APPROVAL_STATUSES = frozenset({"pending", "approved", "denied", "expired"})
TERMINAL_APPROVAL_STATUSES = frozenset({"approved", "denied", "expired"})
DEFAULT_APPROVAL_TTL_MINUTES = 60
```

### `create_approval_request`

```python
def create_approval_request(
    conn,
    *,
    incident_id: int | None = None,
    queue_id: int | None = None,
    action: str,
    requested_by: int | None = None,
    request_reason: str | None = None,
    risk_level: str = "high",
    expires_at=None,
    ttl_minutes: int = DEFAULT_APPROVAL_TTL_MINUTES,
) -> dict:
```

Responsibilities:
- Require at least one of `incident_id` or `queue_id`.
- Require non-empty `action`.
- Compute `expires_at = NOW() + ttl_minutes * INTERVAL '1 minute'` when explicit `expires_at`
  is not supplied.
- Insert `approval_requests` with `status='pending'`.
- Insert `approval_request_events` with `event_type='created'`.
- Call `log_audit_event()` for `approval_request_created`.
- Return the created request as a dict.

### `get_approval_request`

```python
def get_approval_request(conn, approval_request_id: int) -> dict | None:
```

Responsibilities:
- Return the request row plus related immutable events.
- Return `None` for unknown ID.

### `list_approval_requests`

```python
def list_approval_requests(
    conn,
    *,
    status: str | None = None,
    incident_id: int | None = None,
    queue_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
```

Responsibilities:
- Filter by status, incident, and queue item.
- Cap `limit` at 100.
- Order by `created_at DESC`.

### `approve_request`

```python
def approve_request(
    conn,
    approval_request_id: int,
    *,
    actor_user_id: int,
    decision_comment: str | None = None,
    now=None,
) -> dict:
```

Responsibilities:
- Lock the row with `FOR UPDATE`.
- Raise `ValueError("approval request not found")` when missing.
- Raise `ValueError("approval request is not pending")` for terminal requests.
- If `expires_at <= now`, expire the request instead of approving it and raise
  `ValueError("approval request expired")` after writing the expiration event.
- Set:
  - `status='approved'`
  - `approved_by=actor_user_id`
  - `decided_by=actor_user_id`
  - `decided_at=now`
  - `decision_comment=decision_comment`
- Append `approval_request_events.event_type='approved'`.
- Call `log_audit_event()` for `approval_request_approved`.
- Return the updated request dict.

### `deny_request`

```python
def deny_request(
    conn,
    approval_request_id: int,
    *,
    actor_user_id: int,
    decision_comment: str | None = None,
    now=None,
) -> dict:
```

Responsibilities:
- Lock the row with `FOR UPDATE`.
- Only pending requests can be denied.
- If expired at decision time, expire instead of denying and raise
  `ValueError("approval request expired")`.
- Set:
  - `status='denied'`
  - `approved_by=NULL`
  - `decided_by=actor_user_id`
  - `decided_at=now`
  - `decision_comment=decision_comment`
- Append `approval_request_events.event_type='denied'`.
- Call `log_audit_event()` for `approval_request_denied`.
- Return the updated request dict.

### `expire_pending_requests`

```python
def expire_pending_requests(conn, *, now=None, limit: int = 100) -> list[dict]:
```

Responsibilities:
- Find pending requests where `expires_at <= now`.
- Lock rows with `FOR UPDATE SKIP LOCKED`.
- Update each to `status='expired'`, `decided_at=now`, `decided_by=NULL`.
- Append `approval_request_events.event_type='expired'` for each request.
- Call `log_audit_event()` for each expiration or a single batch audit event with request IDs.
- Return the expired request dicts.
- Does not schedule itself. Future routes/workers may call it opportunistically.

---

## Timeout semantics

Expiration is explicit and deterministic:
- Every approval request must have `expires_at`.
- A pending request whose `expires_at <= now` is no longer approvable or deniable.
- Expiration is materialized by `expire_pending_requests()` or by a decision helper that sees
  the request is already expired.
- This slice does not add a scheduler. There is no background job.
- Future route or worker code may call `expire_pending_requests()` before listing approvals or
  before checking whether queued work is allowed to resume.

---

## Audit behavior

Approval history is immutable:
- `approval_request_events` is append-only.
- `audit_log` receives append-only entries through existing `log_audit_event()`.
- `approval_requests` stores current state only.
- Decision helpers never delete or rewrite event rows.

Suggested audit event types:
- `approval_request_created`
- `approval_request_approved`
- `approval_request_denied`
- `approval_request_expired`

Suggested audit details:
```python
{
    "approval_request_id": approval_request_id,
    "incident_id": incident_id,
    "queue_id": queue_id,
    "action": action,
    "previous_status": previous_status,
    "new_status": new_status,
    "decision_comment": decision_comment,
}
```

---

## Testing strategy

Schema tests:
- `approval_requests` and `approval_request_events` tables exist.
- Invalid status is rejected.
- Invalid risk level is rejected.
- Missing both `incident_id` and `queue_id` is rejected.
- `approved` without `approved_by` is rejected.
- `pending` with `decided_at` is rejected.
- Event type CHECK rejects unknown event types.

Store tests:
- `create_approval_request` creates a pending request with computed expiration.
- Creation requires incident or queue target.
- Creation writes a `created` event.
- Creation writes an audit event.
- List filters by status, incident, and queue item.
- Detail returns immutable event history.
- Unknown detail returns `None`.
- Approving a pending request succeeds and sets `approved_by`, `decided_by`, and `decided_at`.
- Denying a pending request succeeds and leaves `approved_by` null.
- Approving/denying terminal requests raises.
- Approving/denying an already-expired pending request materializes expiration and raises.
- `expire_pending_requests` expires only pending requests past `expires_at`.
- `expire_pending_requests` does not touch approved, denied, or future pending requests.
- Helpers do not commit; caller rollback should undo request and event writes.

Regression tests:
- Existing incident route/store tests remain green.
- Existing SOAR queue tests remain green.
- Existing ingest/detection/correlation tests remain green, because no execution flow is wired
  to approvals in this slice.

---

## Non-integration guarantees

This slice does not:
- Change `response_actions_queue.status` values.
- Change queue claim/worker behavior.
- Add worker pause/resume.
- Gate any queued action.
- Add frontend UI.
- Touch ingest, detection, or correlation code.
- Add background schedulers.

---

## Phase 2.5B: Approval API routes

Phase 2.5B adds backend routes only. These routes expose approval request visibility and manual
decision actions through the already-implemented approval store helpers. They do not create
approval requests, execute SOAR actions, mutate alerts, mutate queue rows, or gate workers.

### Route module

Add a focused approval route module following the existing route style, for example
`routes/approval_routes.py`, and register its blueprint from the existing backend bootstrap.

The route module should import:
- `login_required` from `flask_login`.
- `current_user` for decision actor metadata.
- `analyst_or_super_admin_required` for read routes.
- `super_admin_required` for decision routes.
- `get_db_connection`.
- Approval store helpers:
  - `get_approval_request`
  - `list_approval_requests`
  - `approve_request`
  - `deny_request`

It must not import worker modules, ingest modules, detection engines, correlation code, frontend
assets, or playbook code.

### `GET /approvals`

Purpose: list approval requests for analyst review.

Auth:
- Requires an authenticated session.
- Requires `analyst` or `super_admin` via the existing analyst/super-admin decorator.

Supported query parameters:
- `status`: optional; must be one of `pending`, `approved`, `denied`, `expired`.
- `incident_id`: optional non-negative integer.
- `queue_id`: optional non-negative integer.
- `limit`: optional non-negative integer, default `50`, capped at `100`.
- `offset`: optional non-negative integer, default `0`.

Response shape:

```json
{
  "approvals": [
    {
      "id": 1,
      "incident_id": 10,
      "queue_id": null,
      "requested_by": null,
      "approved_by": null,
      "decided_by": null,
      "status": "pending",
      "action": "block_ip",
      "risk_level": "high",
      "request_reason": "high risk containment",
      "decision_comment": null,
      "created_at": "2026-05-07T12:00:00+00:00",
      "decided_at": null,
      "expires_at": "2026-05-07T13:00:00+00:00"
    }
  ],
  "count": 1
}
```

### `GET /approvals/<id>`

Purpose: return one approval request plus immutable lifecycle events.

Auth:
- Requires an authenticated session.
- Requires `analyst` or `super_admin`.

Behavior:
- Return `404` when `get_approval_request()` returns `None`.
- Return detail including the `events` list from the store helper.

Response shape:

```json
{
  "approval": {
    "id": 1,
    "status": "pending",
    "action": "block_ip",
    "risk_level": "high",
    "events": [
      {
        "id": 1,
        "approval_request_id": 1,
        "event_type": "created",
        "actor_user_id": null,
        "previous_status": null,
        "new_status": "pending",
        "comment": "high risk containment",
        "created_at": "2026-05-07T12:00:00+00:00"
      }
    ]
  }
}
```

### `POST /approvals/<id>/decision`

Purpose: manually approve or deny a pending approval request.

Auth:
- Requires an authenticated session.
- Requires `super_admin` for high-risk approval decisions. For Phase 2.5B, use the existing
  `super_admin_required` decorator for all approve/deny route access unless implementation
  discovers an established lower-risk decision policy in the current role model.

Request body:

```json
{
  "decision": "approved",
  "reason": "Approved for containment"
}
```

Rules:
- `decision` is required.
- Valid values are exactly `approved` and `denied`.
- `reason` is optional but should be normalized to a stripped string or `None`.
- `approved` calls `approve_request(conn, id, actor_user_id=<current user id>, decision_comment=reason)`.
- `denied` calls `deny_request(conn, id, actor_user_id=<current user id>, decision_comment=reason)`.
- Commit only after the store helper succeeds.
- Roll back on `ValueError` or unexpected exceptions.
- Return `404` for `"approval request not found"`.
- Return `400` for invalid decisions and invalid state transitions, including already terminal
  requests or requests that expired at decision time.
- Return the updated approval request as `{ "approval": ... }`.

Event behavior:
- The store helper appends the immutable `approved`, `denied`, or materialized `expired` event.
- Route tests should assert that the expected event row exists after a valid decision.
- No route should update or delete `approval_request_events` directly.

### Route testing strategy

Add `tests/test_approval_routes.py`.

Required tests:
- Unauthenticated `GET /approvals`, `GET /approvals/<id>`, and `POST /approvals/<id>/decision`
  requests are rejected.
- Unauthorized roles, including `viewer`, are rejected.
- `analyst` and `super_admin` can list approvals.
- `analyst` and `super_admin` can view approval detail.
- Valid super admin approve request succeeds and creates an `approved` event row.
- Valid super admin deny request succeeds and creates a `denied` event row.
- Invalid decision values return `400`.
- Missing approval IDs return `404`.
- Invalid terminal-state transitions return `400`.
- Decision route does not mutate queue rows, alerts, ingest state, detection state, or correlation
  behavior.

Regression tests:
- Existing `tests/test_approval_store.py` remains green.
- Existing incident route/store tests remain green.
- Existing SOAR queue tests remain green.
- Full backend suite remains green.

---

## Phase 2.5C: Approval visibility and decision UI

Phase 2.5C adds frontend UI only. It consumes the existing approval API routes:
- `GET /approvals`
- `GET /approvals/<id>`
- `POST /approvals/<id>/decision`

The UI must not call queue mutation routes, alert mutation routes, SOAR action execution routes,
worker controls, ingest endpoints, detection endpoints, correlation endpoints, or any new backend
endpoint. Backend/schema changes are out of scope unless implementation proves they are
absolutely required.

### Service module

Add `frontend/src/services/approvalService.js` following existing frontend service patterns.

Responsibilities:
- `listApprovals(filters)` calls `GET /approvals`.
- `getApproval(id)` calls `GET /approvals/<id>`.
- `submitApprovalDecision(id, { decision, reason })` calls
  `POST /approvals/<id>/decision`.
- Serialize only supported list filters:
  - `status`
  - `risk_level` or local severity/risk filter only if supported by the route contract; otherwise
    filter client-side.
  - `incident_id`
  - `queue_id`
  - `limit`
  - `offset`
- Normalize optional decision reason by sending an empty or omitted string safely.
- Surface API errors in the same shape/pattern as existing frontend services.

The service must not include helpers for queue mutation, alert mutation, SOAR action execution,
worker execution, playbooks, Slack/email notifications, or firewall execution.

### `ApprovalsPanel`

Add `frontend/src/components/ApprovalsPanel.js`.

Primary behavior:
- Fetch and render approval list on mount.
- Provide filters for status and risk/severity.
  - Status filter values: `all`, `pending`, `approved`, `denied`, `expired`.
  - Risk/severity filter values should match stored approval risk values where available:
    `medium`, `high`, `critical`.
- Select an approval to show detail.
- Detail view shows:
  - approval ID
  - status
  - action
  - risk level
  - incident ID when present
  - queue ID when present
  - request reason when present
  - decision comment when present
  - created/decided/expires timestamps
  - immutable event history from `events`
- Handle `null` or missing decision fields safely.
- Show loading, error, and empty states for list and detail workflows.

Decision behavior:
- Show approve/deny controls only when:
  - current user role is `super_admin`
  - selected approval status is `pending`
- Hide or disable decision controls for analysts.
- Hide or disable decision controls for approved, denied, and expired approvals.
- Decision reason is optional.
- Sending a decision calls only `POST /approvals/<id>/decision`.
- After a successful decision, refresh the selected detail and list.
- Failed decisions should show an error without mutating local state as if the decision succeeded.

Safety controls:
- No queue mutation buttons.
- No alert mutation buttons.
- No SOAR action execution buttons.
- No worker run/pause/resume controls.
- No playbook execution controls.
- No Slack/email/firewall action controls.

### Navigation

Add a `SOAR Approvals` or `Approvals` nav tab for users with role `analyst` or `super_admin`.
Do not expose the tab to viewer users.

The tab should render `ApprovalsPanel` inside the existing authenticated application shell and
follow the same state/role propagation pattern used by existing incident/SOAR visibility UI.

### Frontend testing strategy

Service tests:
- `listApprovals` calls `GET /approvals` with supported filters.
- `getApproval` calls `GET /approvals/<id>`.
- `submitApprovalDecision` calls `POST /approvals/<id>/decision` with decision and optional
  reason.
- Service surfaces API failures.

Component tests, if current setup supports them:
- Loading state renders before data is available.
- Empty state renders when list is empty.
- Error state renders on service failure.
- Analyst can see approval list/detail but cannot see approve/deny controls.
- Super admin can see approve/deny controls for pending approvals.
- Super admin cannot see approve/deny controls for terminal approvals.
- Approve click submits `{ decision: "approved", reason }`.
- Deny click submits `{ decision: "denied", reason }`.
- Event history renders in detail.
- Filters update the list request or client-side filtered list according to implementation.

Build verification:
- Targeted frontend service/component tests pass.
- `npm run build` passes.

### Phase 2.5C non-integration guarantees

This UI slice does not:
- Add or change backend routes.
- Add or change schema.
- Add worker pause/resume.
- Gate queued execution.
- Mutate queue rows.
- Mutate alerts.
- Execute SOAR actions.
- Add playbook behavior.
- Add Slack/email behavior.
- Add real firewall execution.
- Touch ingest, detection, or correlation code.

---

## Phase 2.5D: Approval-gated SOAR queue execution

Phase 2.5D introduces worker-side approval gating for selected high-risk queued SOAR actions.
It does not change the default executor mode: `SimulationExecutor` remains the default executor.
The goal is to prevent high-risk queued actions from reaching the executor until a matching
approval request has been approved by a super admin.

This phase should be implemented as a narrow queue/store/worker change. It must not add real
firewall execution, playbooks, Slack/email notifications, autonomous daemons, frontend changes,
or ingest/detection/correlation changes.

### 1. Does the queue need a new status?

Yes. The current queue status model cannot represent “safe waiting for approval” cleanly.
Existing statuses are operational execution states:
- `pending`: eligible to be claimed by the worker.
- `running`: claimed and actively being processed.
- `success`: executed successfully.
- `failed`: execution failed.
- `skipped`: intentionally not executed.

Leaving an approval-blocked row as `pending` would cause later worker runs to repeatedly reclaim
the same row and recreate or re-check approval state. Holding it in `running` would make stale
recovery treat the row like an abandoned execution. Reusing `failed` or `skipped` before a human
decision would make the action look terminal even though it may resume after approval.

Recommended additive status:

```sql
awaiting_approval
```

Required schema/status update:
- Extend `response_actions_queue.status` CHECK constraint to include `awaiting_approval`.
- Update queue status normalization/visibility code to include `awaiting_approval`.
- Update queue visibility UI only in a separate frontend follow-up if needed.

Recommended helper additions:
- `mark_action_awaiting_approval(conn, queue_id, reason, now=None)`
  - Transitions only from `running` to `awaiting_approval`.
  - Writes `last_error` or equivalent details such as `approval required`.
  - Does not increment retry count.
- `mark_awaiting_approval_skipped(conn, queue_id, reason, now=None)`
  - Transitions only from `awaiting_approval` to `skipped`.
  - Used when approval is denied or expired.
- `claim_next_approved_action(conn, now=None)`
  - Claims an `awaiting_approval` row with a matching approved approval request by transitioning
    it back to `running`.
  - Should use `FOR UPDATE SKIP LOCKED`.

Alternative considered:
- Keep queue rows `pending` while waiting. Rejected because it creates noisy repeated worker
  attempts and makes duplicate-approval prevention harder.

### 2. Which actions require approval in v1?

V1 should use a small explicit allowlist of approval-required high-risk actions:

```python
APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})
```

Non-v1 actions:
- `monitor` should not require approval.
- `flag_high_priority` should not require approval unless a later policy expands the set.
- Unknown actions should continue through existing executor validation behavior and must not gain
  approval-specific behavior.

The policy should be local and deterministic, for example in a small helper module or queue
worker helper:

```python
def action_requires_approval(action: str) -> bool:
    return action in APPROVAL_REQUIRED_ACTIONS
```

### 3. How does the worker avoid duplicate approval requests?

The worker should use queue row locking plus approval lookup before creating a request.

Recommended flow for a pending high-risk action:
1. Claim the queue row using the existing pending-claim behavior, transitioning it to `running`.
2. Before executor invocation, check whether the action requires approval.
3. If approval is required, look for an existing approval request for the same `queue_id` and
   action where status is `pending`, `approved`, `denied`, or `expired`, ordered newest first.
4. If an approved request exists, continue to executor invocation.
5. If a pending request exists, transition the queue row to `awaiting_approval` and return a
   worker result such as `outcome="awaiting_approval"`.
6. If no request exists, create one using `create_approval_request(queue_id=..., action=...)`,
   transition the queue row to `awaiting_approval`, commit, and return `outcome="awaiting_approval"`.
7. If the latest request is denied or expired, transition the queue row to `skipped` and return a
   safe non-execution outcome.

Recommended DB guard:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_requests_queue_action_active
ON approval_requests (queue_id, action)
WHERE queue_id IS NOT NULL
  AND status IN ('pending', 'approved');
```

This index is additive and protects against duplicate active approval requests if future code
paths create requests concurrently. If implementation finds existing duplicate active data, pause
and resolve before applying this constraint.

### 4. How does the worker resume after approval?

Approval does not directly execute anything. A later worker run resumes safely.

Recommended resume flow:
1. Worker first claims normal `pending` rows as it does today.
2. If no eligible pending row exists, worker checks for `awaiting_approval` rows with a matching
   approved approval request.
3. The claim helper transitions the approved `awaiting_approval` row to `running` under row lock.
4. The worker re-runs the approval check.
5. Because the matching approval is approved, the worker invokes the executor.
6. Existing success/failure/skipped handling applies from `running`.

This keeps approval decisions decoupled from execution. The approval API and UI only update
approval state; the worker remains responsible for later execution.

### 5. What happens on denial?

Denied approvals should result in safe non-execution.

Recommended behavior:
- A worker run that sees an `awaiting_approval` queue row with a matching denied approval should
  transition the queue row to `skipped`.
- `last_error` should be set to a clear reason such as `approval denied`.
- The worker result should use `outcome="skipped"` or `outcome="approval_denied"` depending on
  current worker result conventions. Prefer preserving `new_status="skipped"` so existing queue
  visibility remains understandable.
- The executor must not be called.
- Retry count should not increment; denial is not an execution failure.
- A response action log row may be written with status `skipped` and details `approval denied`
  if consistent with current skipped-action logging.

### 6. What happens on expiration?

Expired approvals should also result in safe non-execution unless a later human creates a new
approval request through a future explicit workflow.

Recommended behavior:
- Before evaluating approval state, opportunistically materialize expired pending requests using
  `expire_pending_requests(conn, limit=...)` or a focused queue-specific expiration check.
- A worker run that sees an `awaiting_approval` queue row whose matching request is expired should
  transition the queue row to `skipped`.
- `last_error` should be set to `approval expired`.
- The executor must not be called.
- Retry count should not increment.
- Do not automatically create a fresh approval request for the same queue row after expiration in
  v1; that could create repeated approval churn. A future route or analyst workflow can requeue or
  recreate approval explicitly if needed.

### 7. Worker processing order

Recommended `process_next_action()` order:
1. Recover or handle stale `running` rows as existing code already does outside this function.
2. Claim the next `pending` queue row.
3. If no pending row exists, claim the next `awaiting_approval` row with approved approval.
4. If no executable row exists, inspect a small batch of `awaiting_approval` rows for denied or
   expired approvals and skip them safely.
5. Return `None` only when there is no executable or terminal approval cleanup work.

This lets approval cleanup happen during normal worker runs without adding an autonomous daemon.

### 8. Transaction boundaries

The worker must preserve the current post-claim safety model:
- Claim or waiting-state transitions happen in explicit transactions.
- Approval request creation and queue transition to `awaiting_approval` should commit together.
- Executor invocation should happen only after the worker has committed the claim and confirmed
  approval is approved or not required.
- If approval creation fails, roll back and fail or requeue according to the safest current queue
  error-handling behavior. Prefer not executing when approval gating cannot be established.

### 9. Required tests

Schema/store tests:
- `awaiting_approval` is an accepted queue status.
- Invalid queue statuses are still rejected.
- `mark_action_awaiting_approval` transitions `running` to `awaiting_approval`.
- `mark_action_awaiting_approval` rejects non-running rows.
- Approved `awaiting_approval` rows can be claimed for execution.
- Pending/denied/expired `awaiting_approval` rows are not claimed as executable.
- Duplicate active approval requests for the same `queue_id` and `action` are prevented if the
  unique index is added.

Worker tests:
- `block_ip` without approval creates one approval request and does not call executor.
- `block_ip` without approval transitions queue row to `awaiting_approval`.
- Re-running worker while approval is still pending does not create duplicate approval requests.
- Approved `block_ip` resumes on a later worker run and executes through `SimulationExecutor`.
- Denied `block_ip` transitions to `skipped` and does not call executor.
- Expired `block_ip` materializes expiration, transitions to `skipped`, and does not call
  executor.
- Non-gated actions such as `monitor` and `flag_high_priority` continue executing unchanged.
- Unknown actions keep existing skipped/failure behavior and are not approval-gated unless added
  to the explicit policy.
- Retry counts do not increment for approval pending, denied, or expired outcomes.
- Response action logs are written consistently for skipped denial/expiration outcomes if current
  logging conventions require them.

Regression tests:
- Existing approval store and route tests remain green.
- Existing queue visibility tests account for `awaiting_approval` counts.
- Existing worker runner tests remain green with `SimulationExecutor` as default.
- Existing ingest/detection/correlation tests remain green.

### Phase 2.5D non-integration guarantees

This gating slice does not:
- Add real firewall execution.
- Add playbook behavior.
- Add Slack/email behavior.
- Add frontend changes.
- Add autonomous daemon behavior.
- Change ingest transaction behavior.
- Touch detection internals.
- Touch correlation internals.
