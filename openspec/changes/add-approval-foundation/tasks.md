# Tasks: Approval Foundation

Run targeted regression after each implementation step:

```
python3 -m pytest tests/test_incident_store.py tests/test_incident_routes.py -x --tb=short -v
python3 -m pytest tests/test_response_action_queue.py -x --tb=short -v
```

Run the full backend suite before final handoff:

```
python3 -m pytest tests/ -x --tb=short -v
```

---

## Step 1: Schema additions

- [x] Read `schema.sql` and confirm `approval_requests` and `approval_request_events` do not exist.
- [x] Add `approval_requests` table using `CREATE TABLE IF NOT EXISTS`.
  - `id SERIAL PRIMARY KEY`
  - `incident_id INTEGER REFERENCES incidents(id) ON DELETE RESTRICT`
  - `queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE RESTRICT`
  - `requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL`
  - `approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL`
  - `decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL`
  - `status TEXT NOT NULL DEFAULT 'pending' CHECK (...)`
  - `action TEXT NOT NULL`
  - `risk_level TEXT NOT NULL DEFAULT 'high' CHECK (...)`
  - `request_reason TEXT`
  - `decision_comment TEXT`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
  - `decided_at TIMESTAMPTZ`
  - `expires_at TIMESTAMPTZ NOT NULL`
  - CHECK at least one of `incident_id` or `queue_id` is present.
  - CHECK terminal states have `decided_at`.
  - CHECK `approved` has `approved_by`.
- [x] Add `approval_request_events` table using `CREATE TABLE IF NOT EXISTS`.
  - `id SERIAL PRIMARY KEY`
  - `approval_request_id INTEGER NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE`
  - `event_type TEXT NOT NULL CHECK (...)`
  - `actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
  - `previous_status TEXT`
  - `new_status TEXT NOT NULL`
  - `comment TEXT`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- [x] Add indexes:
  - `idx_approval_requests_status`
  - `idx_approval_requests_incident_id`
  - `idx_approval_requests_queue_id`
  - `idx_approval_requests_expires_at`
  - `idx_approval_requests_pending_expiry` partial index where `status = 'pending'`
  - `idx_approval_request_events_request_id`
  - `idx_approval_request_events_created_at`
- [x] Apply `schema.sql` to a fresh test database through the existing `postgres_db` fixture.

---

## Step 2: Implement `core/approval_store.py`

- [x] Create `core/approval_store.py`.
  - Import `logging`.
  - Use `logging.getLogger(__name__)`.
  - Import `log_audit_event` from `core.audit_helpers`.
  - Do not import Flask routes, worker modules, ingest, detection, or correlation code.
- [x] Define constants:
  - `APPROVAL_STATUSES`
  - `TERMINAL_APPROVAL_STATUSES`
  - `DEFAULT_APPROVAL_TTL_MINUTES`
- [x] Add row-to-dict helpers for approval request rows and event rows.
- [x] Implement `create_approval_request(...)`.
  - Requires incident or queue target.
  - Requires non-empty action.
  - Computes expiration when explicit `expires_at` is not provided.
  - Inserts pending request.
  - Inserts immutable `created` event.
  - Writes `approval_request_created` audit event.
  - Does not commit.
- [x] Implement `get_approval_request(conn, approval_request_id)`.
  - Returns request with `events` list.
  - Returns `None` for unknown ID.
- [x] Implement `list_approval_requests(...)`.
  - Supports status, incident, and queue filters.
  - Caps limit at 100.
  - Orders by `created_at DESC`.
- [x] Implement `approve_request(...)`.
  - Locks row with `FOR UPDATE`.
  - Requires pending state.
  - Materializes expiration if `expires_at <= now`.
  - Sets `approved_by`, `decided_by`, `decided_at`, `decision_comment`.
  - Inserts immutable `approved` event.
  - Writes `approval_request_approved` audit event.
  - Does not commit.
- [x] Implement `deny_request(...)`.
  - Locks row with `FOR UPDATE`.
  - Requires pending state.
  - Materializes expiration if `expires_at <= now`.
  - Leaves `approved_by` null.
  - Sets `decided_by`, `decided_at`, `decision_comment`.
  - Inserts immutable `denied` event.
  - Writes `approval_request_denied` audit event.
  - Does not commit.
- [x] Implement `expire_pending_requests(conn, *, now=None, limit=100)`.
  - Locks eligible pending rows with `FOR UPDATE SKIP LOCKED`.
  - Updates only expired pending rows.
  - Inserts immutable `expired` event for each row.
  - Writes expiration audit event(s).
  - Does not commit.

---

## Step 3: Schema tests

- [x] Create `tests/test_approval_store.py`.
- [x] Test `approval_requests` and `approval_request_events` tables exist.
- [x] Test invalid approval status is rejected.
- [x] Test invalid risk level is rejected.
- [x] Test missing both `incident_id` and `queue_id` is rejected.
- [x] Test `approved` without `approved_by` is rejected.
- [x] Test `pending` with `decided_at` is rejected.
- [x] Test unknown approval event type is rejected.

---

## Step 4: Store tests

- [x] `create_approval_request` creates pending request tied to an incident.
- [x] `create_approval_request` creates pending request tied to a queue item.
- [x] `create_approval_request` can include both incident and queue item.
- [x] `create_approval_request` computes `expires_at` from TTL.
- [x] `create_approval_request` writes a `created` event.
- [x] `create_approval_request` writes an audit event.
- [x] `create_approval_request` raises for missing target.
- [x] `create_approval_request` raises for empty action.
- [x] `get_approval_request` returns request plus event history.
- [x] `get_approval_request` returns `None` for unknown ID.
- [x] `list_approval_requests` filters by status.
- [x] `list_approval_requests` filters by incident.
- [x] `list_approval_requests` filters by queue item.
- [x] `list_approval_requests` caps limit at 100.
- [x] `approve_request` transitions pending to approved.
- [x] `approve_request` sets `approved_by`, `decided_by`, `decided_at`, and `decision_comment`.
- [x] `approve_request` writes immutable approved event.
- [x] `approve_request` writes audit event.
- [x] `deny_request` transitions pending to denied.
- [x] `deny_request` leaves `approved_by` null.
- [x] `deny_request` writes immutable denied event.
- [x] `deny_request` writes audit event.
- [x] Approving an approved/denied/expired request raises.
- [x] Denying an approved/denied/expired request raises.
- [x] Approving an expired pending request materializes expiration and raises.
- [x] Denying an expired pending request materializes expiration and raises.
- [x] `expire_pending_requests` expires only pending requests past `expires_at`.
- [x] `expire_pending_requests` skips approved, denied, expired, and future pending requests.
- [x] `expire_pending_requests` writes immutable expired events.
- [x] Store helpers do not commit; caller rollback undoes request/event writes.

---

## Step 5: Regression and safety audit

- [x] Run `python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py`.
- [x] Run `python3 -m pytest tests/test_approval_store.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/test_incident_store.py tests/test_incident_routes.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/test_response_action_queue.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/ -x --tb=short -v`.
- [x] Confirm no frontend files changed.
- [x] Confirm no route implementation was added.
- [x] Confirm no worker pause/resume was added.
- [x] Confirm no queue execution behavior changed.
- [x] Confirm no ingest, detection, or correlation files changed.
- [x] Confirm no background scheduler was added.

---

## Step 6: Phase 2.5B approval API routes

- [x] Read existing auth/role patterns in `core/auth.py` and route patterns in `routes/incident_routes.py`.
- [x] Add a focused approval route module, for example `routes/approval_routes.py`.
  - Use `login_required`.
  - Use `analyst_or_super_admin_required` for read routes.
  - Use `super_admin_required` for the decision route unless the current role model clearly
    defines a lower-risk approval policy.
  - Import only DB/auth/store helpers needed by the approval routes.
  - Do not import worker, ingest, detection, correlation, playbook, or frontend code.
- [x] Register the approval blueprint in the backend bootstrap.
- [x] Implement `GET /approvals`.
  - Supports optional `status`, `incident_id`, `queue_id`, `limit`, and `offset` filters.
  - Rejects invalid status and non-integer or negative numeric filters with `400`.
  - Caps `limit` at `100`.
  - Returns `{ "approvals": [...], "count": <n> }`.
- [x] Implement `GET /approvals/<id>`.
  - Returns `{ "approval": ... }`.
  - Includes immutable `events` from `get_approval_request`.
  - Returns `404` for missing approvals.
- [x] Implement `POST /approvals/<id>/decision`.
  - Accepts `{ "decision": "approved" | "denied", "reason": "..." }`.
  - Rejects missing or invalid `decision` with `400`.
  - Uses `approve_request` for `approved`.
  - Uses `deny_request` for `denied`.
  - Uses the authenticated current user as the decision actor.
  - Commits only after the store helper succeeds.
  - Rolls back on validation, missing approval, invalid transition, and unexpected errors.
  - Returns `404` for missing approvals.
  - Returns `400` for invalid lifecycle transitions.
- [x] Confirm the route implementation does not create approval requests.
- [x] Confirm the route implementation does not mutate alerts.
- [x] Confirm the route implementation does not mutate SOAR queue rows or queue execution behavior.
- [x] Confirm the route implementation does not add worker pause/resume or execution gating.
- [x] Confirm the route implementation does not touch ingest, detection, or correlation.

## Step 7: Phase 2.5B route tests

- [x] Create `tests/test_approval_routes.py`.
- [x] Test unauthenticated `GET /approvals` is rejected.
- [x] Test unauthenticated `GET /approvals/<id>` is rejected.
- [x] Test unauthenticated `POST /approvals/<id>/decision` is rejected.
- [x] Test unauthorized role, including `viewer`, is rejected for list/detail.
- [x] Test unauthorized role, including `viewer` and `analyst`, is rejected for decisions.
- [x] Test `analyst` can list approvals.
- [x] Test `super_admin` can list approvals.
- [x] Test `analyst` can view approval detail.
- [x] Test `super_admin` can view approval detail.
- [x] Test valid super admin approve succeeds.
- [x] Test valid super admin deny succeeds.
- [x] Test invalid decision is rejected with `400`.
- [x] Test missing approval returns `404`.
- [x] Test invalid terminal-state transition is rejected with `400`.
- [x] Test a valid approve creates an immutable `approved` event row.
- [x] Test a valid deny creates an immutable `denied` event row.

## Step 8: Phase 2.5B verification

- [x] Run `python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py`.
- [x] Run `python3 -m pytest tests/test_approval_store.py tests/test_approval_routes.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/test_incident_store.py tests/test_incident_routes.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/test_response_action_queue.py -x --tb=short -v`.
- [x] Run `python3 -m pytest tests/ -x --tb=short -v`.
- [x] Confirm no frontend files changed.
- [x] Confirm no worker pause/resume was added.
- [x] Confirm no queue execution behavior changed.
- [x] Confirm no ingest, detection, or correlation files changed.
- [x] Confirm no schema changes were made unless explicitly required by implementation.
