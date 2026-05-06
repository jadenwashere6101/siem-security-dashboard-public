# Design: SOAR Queue Visibility API

---

## 1. API Shape

Add read-only admin endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /admin/soar/queue/status` | Queue status counts and summary health |
| `GET /admin/soar/queue/recent` | Recent queue items, newest first |
| `GET /admin/soar/queue/<id>` | Optional single queue item detail |

All endpoints return JSON and use existing Flask session auth.

---

## 2. Auth and Authorization

Use the existing admin route pattern:

```python
@login_required
@super_admin_required
```

These endpoints belong under the existing admin surface because queue state can
reveal operational security activity and response targets.

Expected behavior:

- unauthenticated -> `401`
- authenticated viewer/analyst -> `403`
- super admin -> `200`

If the project later introduces a broader admin role distinct from super admin,
this endpoint can move to that guard, but initial implementation should match the
current `routes/admin_routes.py` admin-only pattern.

---

## 3. Route Placement

Recommended placement:

```text
routes/admin_routes.py
```

Rationale:

- existing admin blueprint is already registered
- existing auth decorators and DB pattern are established there
- no new frontend route or Blueprint registration needed

If route growth becomes unwieldy later, a future refactor can extract
`routes/soar_admin_routes.py`, but this change should avoid route-registration
churn.

---

## 4. Queue Store Helpers

Use existing helper:

```python
get_queue_status_counts(conn)
```

Add read-only helpers only where missing:

```python
list_recent_queue_actions(conn, limit=50, status=None)
get_queue_action_detail(conn, queue_id)
```

These helpers must:

- perform only `SELECT`
- not use `FOR UPDATE`
- not call claim/mark/requeue/recover helpers
- not commit
- not change queue row timestamps
- return plain dicts using the same row shape as `_queue_row_from_record`

No schema change is expected.

---

## 5. Endpoint Details

### `GET /admin/soar/queue/status`

Response:

```json
{
  "counts": {
    "pending": 2,
    "running": 1,
    "success": 10,
    "failed": 1,
    "skipped": 3
  },
  "total": 17,
  "generated_at": "2026-05-06T12:00:00+00:00"
}
```

Include all known statuses even when count is zero:

- `pending`
- `running`
- `success`
- `failed`
- `skipped`

Do not include queue payload secrets. Current queue rows have no secrets, but the
endpoint should keep the response limited to counts.

### `GET /admin/soar/queue/recent`

Query params:

| Param | Default | Notes |
|---|---:|---|
| `limit` | `50` | Clamp to a safe max, e.g. `100` |
| `status` | none | Optional filter: pending/running/success/failed/skipped |

Response:

```json
{
  "items": [
    {
      "id": 123,
      "alert_id": 42,
      "alert_reference": {
        "status": "linked",
        "label": "Alert 42"
      },
      "source_ip": "203.0.113.10",
      "action": "block_ip",
      "status": "pending",
      "retry_count": 0,
      "max_retries": 3,
      "last_error": null,
      "created_at": "2026-05-06 12:00:00+00:00",
      "updated_at": "2026-05-06 12:00:00+00:00"
    }
  ],
  "limit": 50,
  "status": null
}
```

For `alert_id = null`:

```json
{
  "alert_id": null,
  "alert_reference": {
    "status": "deleted_or_missing",
    "label": "Deleted alert"
  }
}
```

Do not expose `idempotency_key` in list responses. It is not a secret, but it is
internal implementation detail and adds noise.

### `GET /admin/soar/queue/<id>`

Optional detail endpoint.

Response should include the same fields as recent items and may include:

- `idempotency_key`
- terminal audit log rows for the queue action if they can be found safely by
  `(alert_id, source_ip, action)`

Keep this endpoint read-only. If audit-log association is ambiguous, omit logs
rather than guessing.

Return `404` when queue item is not found.

---

## 6. Nullable and Deleted Alert Handling

Queue rows allow `alert_id = NULL` because alerts can be deleted while queue rows
remain. Visibility endpoints must not assume a live alert row exists.

Rules:

- serialize `alert_id` as JSON `null`
- do not join with `INNER JOIN alerts`
- use `LEFT JOIN alerts` only if alert metadata is needed
- expose safe `alert_reference` metadata
- never crash when the alert is missing

Recommended `alert_reference.status` values:

- `linked` — `alert_id` is non-null and referenced alert exists
- `deleted_or_missing` — `alert_id` is null or referenced alert cannot be found

The list endpoint can avoid joining alerts entirely and derive:

- `linked` when `alert_id is not None`
- `deleted_or_missing` when `alert_id is None`

The detail endpoint may use a `LEFT JOIN` to distinguish a stale non-null foreign
key only if such a case is possible in the current schema.

---

## 7. Read-Only Safety

These endpoints must not call:

- `claim_next_pending_action`
- `mark_action_success`
- `mark_action_skipped`
- `mark_action_failed`
- `record_action_failure`
- `requeue_failed_action`
- `recover_stale_running_actions`
- `process_next_action`
- `process_batch`

They should not call `conn.commit()` except harmlessly after read-only queries if
that is part of existing route cleanup style. Prefer simply closing the
connection.

Tests should verify no queue row changes after endpoint calls.

---

## 8. Serialization Rules

Use stable JSON keys:

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

Convert timestamps with `str(...)` or a shared timestamp formatter consistent
with existing backend routes.

Do not expose:

- secrets
- credentials
- adapter config
- raw stack traces
- raw exception objects

`last_error` may contain adapter error text. Keep it as currently stored, but
avoid adding new sensitive data to it in this API.

---

## 9. Tests

Add or extend backend contract tests.

Recommended new file:

```text
tests/test_soar_queue_visibility_api.py
```

Coverage:

- unauthenticated `GET /admin/soar/queue/status` returns `401`
- non-admin `GET /admin/soar/queue/status` returns `403`
- super admin status endpoint returns all count keys
- status counts reflect seeded queue rows
- recent endpoint returns stable item shape
- recent endpoint honors `limit`
- recent endpoint rejects or safely handles invalid status filters
- recent endpoint serializes `alert_id: null`
- recent endpoint includes safe deleted/missing alert reference
- optional detail endpoint returns `404` for missing queue ID
- optional detail endpoint returns stable shape for existing queue item
- visibility endpoint calls do not mutate queue status, retry count, or timestamps

Patch `get_db_connection` in `routes.admin_routes` when using the Flask test
client, matching existing route test patterns.

---

## 10. Error Handling

On unexpected backend errors:

- log server-side with `current_app.logger.error(...)`
- return `{"error": "Unable to read SOAR queue"}` or similarly generic message
- do not expose raw DB errors

Invalid query params:

- invalid `limit` -> `400`
- invalid `status` -> `400`

Clamp excessive limits rather than allowing unbounded result sets.

---

## 11. Non-Goals

Do not implement:

- retry/replay
- delete queue item
- force worker run
- recover stale running rows
- change queue schema
- frontend UI
- playbook/incident links
- real firewall/cloud execution

