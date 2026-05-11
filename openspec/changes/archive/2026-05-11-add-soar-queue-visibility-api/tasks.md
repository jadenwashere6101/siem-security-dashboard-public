# Tasks: SOAR Queue Visibility API

Implement later in small, read-only steps.

---

## Task 1 — Add read-only queue store helpers

File:

```text
core/response_action_queue_store.py
```

Use existing:

- `get_queue_status_counts(conn)`
- `get_queue_action(conn, queue_id)`

Add only if needed:

- `list_recent_queue_actions(conn, limit=50, status=None)`

Rules:

- SELECT only
- no `FOR UPDATE`
- no mutation helper calls
- no commits
- return dict rows
- do not expose idempotency key in recent list unless detail endpoint needs it

---

## Task 2 — Add serializers

Location options:

- private helpers in `routes/admin_routes.py`
- or small helper module if the route would become too large

Serialize queue rows with:

- `id`
- `alert_id`
- `alert_reference`
- `source_ip`
- `action`
- `status`
- `retry_count`
- `max_retries`
- `last_error`
- `created_at`
- `updated_at`

For `alert_id is None`, return:

```json
"alert_reference": {
  "status": "deleted_or_missing",
  "label": "Deleted alert"
}
```

For linked alerts:

```json
"alert_reference": {
  "status": "linked",
  "label": "Alert 42"
}
```

---

## Task 3 — Add status endpoint

File:

```text
routes/admin_routes.py
```

Add:

```text
GET /admin/soar/queue/status
```

Decorators:

- `@login_required`
- `@super_admin_required`

Response includes:

- `counts`
- `total`
- `generated_at`

Ensure all statuses appear with zero defaults:

- pending
- running
- success
- failed
- skipped

---

## Task 4 — Add recent endpoint

Add:

```text
GET /admin/soar/queue/recent
```

Query params:

- `limit`, default `50`, max `100`
- `status`, optional enum

Rules:

- validate params
- SELECT only
- newest first
- no mutation
- no worker execution

---

## Task 5 — Add optional detail endpoint

Add if implementation remains small:

```text
GET /admin/soar/queue/<id>
```

Rules:

- return `404` if missing
- return stable queue item shape
- include `idempotency_key` only on detail if useful
- handle nullable `alert_id`
- no mutation

If this endpoint creates ambiguity around audit log association, omit audit logs
from the first implementation.

---

## Task 6 — Add auth tests

New test file:

```text
tests/test_soar_queue_visibility_api.py
```

Cover:

- unauthenticated status endpoint -> `401`
- non-admin status endpoint -> `403`
- super admin status endpoint -> `200`
- repeat auth checks for recent endpoint
- repeat auth checks for detail endpoint if implemented

---

## Task 7 — Add response shape tests

Cover:

- status counts includes all known statuses
- total equals sum of counts
- recent response has `items`, `limit`, and `status`
- recent item has stable keys
- detail response has stable keys if endpoint implemented
- invalid status filter returns `400`
- invalid limit returns `400`
- excessive limit is clamped or rejected per implementation choice

---

## Task 8 — Add nullable alert tests

Seed a queue row with `alert_id = NULL`.

Assert:

- recent endpoint returns `"alert_id": null`
- `alert_reference.status == "deleted_or_missing"`
- endpoint does not crash
- detail endpoint handles the row if implemented

---

## Task 9 — Add no-mutation tests

Seed queue rows with distinct:

- status
- retry_count
- max_retries
- last_error
- updated_at

Call visibility endpoints.

Re-read rows directly from DB and assert the queue fields did not change.

---

## Verification

Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py
```

Run:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py -x --tb=short -v
```

Then:

```bash
python3 -m pytest tests/ -x --tb=short -v
```

No frontend build is required because this change must not touch frontend.

---

## Explicit Non-Tasks

Do not:

- mutate queue rows
- retry/replay queue actions
- execute worker actions
- add worker execution endpoints
- add frontend UI
- add real firewall execution
- change queue schema unless absolutely necessary
- change ingest/detection/correlation flow
- add playbooks/incidents

