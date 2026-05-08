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

- [ ] Read `schema.sql` and confirm `approval_requests` and `approval_request_events` do not exist.
- [ ] Add `approval_requests` table using `CREATE TABLE IF NOT EXISTS`.
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
- [ ] Add `approval_request_events` table using `CREATE TABLE IF NOT EXISTS`.
  - `id SERIAL PRIMARY KEY`
  - `approval_request_id INTEGER NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE`
  - `event_type TEXT NOT NULL CHECK (...)`
  - `actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
  - `previous_status TEXT`
  - `new_status TEXT NOT NULL`
  - `comment TEXT`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- [ ] Add indexes:
  - `idx_approval_requests_status`
  - `idx_approval_requests_incident_id`
  - `idx_approval_requests_queue_id`
  - `idx_approval_requests_expires_at`
  - `idx_approval_requests_pending_expiry` partial index where `status = 'pending'`
  - `idx_approval_request_events_request_id`
  - `idx_approval_request_events_created_at`
- [ ] Apply `schema.sql` to a fresh test database through the existing `postgres_db` fixture.

---

## Step 2: Implement `core/approval_store.py`

- [ ] Create `core/approval_store.py`.
  - Import `logging`.
  - Use `logging.getLogger(__name__)`.
  - Import `log_audit_event` from `core.audit_helpers`.
  - Do not import Flask routes, worker modules, ingest, detection, or correlation code.
- [ ] Define constants:
  - `APPROVAL_STATUSES`
  - `TERMINAL_APPROVAL_STATUSES`
  - `DEFAULT_APPROVAL_TTL_MINUTES`
- [ ] Add row-to-dict helpers for approval request rows and event rows.
- [ ] Implement `create_approval_request(...)`.
  - Requires incident or queue target.
  - Requires non-empty action.
  - Computes expiration when explicit `expires_at` is not provided.
  - Inserts pending request.
  - Inserts immutable `created` event.
  - Writes `approval_request_created` audit event.
  - Does not commit.
- [ ] Implement `get_approval_request(conn, approval_request_id)`.
  - Returns request with `events` list.
  - Returns `None` for unknown ID.
- [ ] Implement `list_approval_requests(...)`.
  - Supports status, incident, and queue filters.
  - Caps limit at 100.
  - Orders by `created_at DESC`.
- [ ] Implement `approve_request(...)`.
  - Locks row with `FOR UPDATE`.
  - Requires pending state.
  - Materializes expiration if `expires_at <= now`.
  - Sets `approved_by`, `decided_by`, `decided_at`, `decision_comment`.
  - Inserts immutable `approved` event.
  - Writes `approval_request_approved` audit event.
  - Does not commit.
- [ ] Implement `deny_request(...)`.
  - Locks row with `FOR UPDATE`.
  - Requires pending state.
  - Materializes expiration if `expires_at <= now`.
  - Leaves `approved_by` null.
  - Sets `decided_by`, `decided_at`, `decision_comment`.
  - Inserts immutable `denied` event.
  - Writes `approval_request_denied` audit event.
  - Does not commit.
- [ ] Implement `expire_pending_requests(conn, *, now=None, limit=100)`.
  - Locks eligible pending rows with `FOR UPDATE SKIP LOCKED`.
  - Updates only expired pending rows.
  - Inserts immutable `expired` event for each row.
  - Writes expiration audit event(s).
  - Does not commit.

---

## Step 3: Schema tests

- [ ] Create `tests/test_approval_store.py`.
- [ ] Test `approval_requests` and `approval_request_events` tables exist.
- [ ] Test invalid approval status is rejected.
- [ ] Test invalid risk level is rejected.
- [ ] Test missing both `incident_id` and `queue_id` is rejected.
- [ ] Test `approved` without `approved_by` is rejected.
- [ ] Test `pending` with `decided_at` is rejected.
- [ ] Test unknown approval event type is rejected.

---

## Step 4: Store tests

- [ ] `create_approval_request` creates pending request tied to an incident.
- [ ] `create_approval_request` creates pending request tied to a queue item.
- [ ] `create_approval_request` can include both incident and queue item.
- [ ] `create_approval_request` computes `expires_at` from TTL.
- [ ] `create_approval_request` writes a `created` event.
- [ ] `create_approval_request` writes an audit event.
- [ ] `create_approval_request` raises for missing target.
- [ ] `create_approval_request` raises for empty action.
- [ ] `get_approval_request` returns request plus event history.
- [ ] `get_approval_request` returns `None` for unknown ID.
- [ ] `list_approval_requests` filters by status.
- [ ] `list_approval_requests` filters by incident.
- [ ] `list_approval_requests` filters by queue item.
- [ ] `list_approval_requests` caps limit at 100.
- [ ] `approve_request` transitions pending to approved.
- [ ] `approve_request` sets `approved_by`, `decided_by`, `decided_at`, and `decision_comment`.
- [ ] `approve_request` writes immutable approved event.
- [ ] `approve_request` writes audit event.
- [ ] `deny_request` transitions pending to denied.
- [ ] `deny_request` leaves `approved_by` null.
- [ ] `deny_request` writes immutable denied event.
- [ ] `deny_request` writes audit event.
- [ ] Approving an approved/denied/expired request raises.
- [ ] Denying an approved/denied/expired request raises.
- [ ] Approving an expired pending request materializes expiration and raises.
- [ ] Denying an expired pending request materializes expiration and raises.
- [ ] `expire_pending_requests` expires only pending requests past `expires_at`.
- [ ] `expire_pending_requests` skips approved, denied, expired, and future pending requests.
- [ ] `expire_pending_requests` writes immutable expired events.
- [ ] Store helpers do not commit; caller rollback undoes request/event writes.

---

## Step 5: Regression and safety audit

- [ ] Run `python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py`.
- [ ] Run `python3 -m pytest tests/test_approval_store.py -x --tb=short -v`.
- [ ] Run `python3 -m pytest tests/test_incident_store.py tests/test_incident_routes.py -x --tb=short -v`.
- [ ] Run `python3 -m pytest tests/test_response_action_queue.py -x --tb=short -v`.
- [ ] Run `python3 -m pytest tests/ -x --tb=short -v`.
- [ ] Confirm no frontend files changed.
- [ ] Confirm no route implementation was added.
- [ ] Confirm no worker pause/resume was added.
- [ ] Confirm no queue execution behavior changed.
- [ ] Confirm no ingest, detection, or correlation files changed.
- [ ] Confirm no background scheduler was added.
