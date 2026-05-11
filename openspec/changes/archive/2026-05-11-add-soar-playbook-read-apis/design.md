# Design: SOAR Playbook Read APIs

## Proposed Architecture

Add a dedicated read-only Flask route module for SOAR playbook visibility:

```text
routes/playbook_routes.py
```

The module should expose a Blueprint and use the existing database connection pattern used
by other route modules. It should call `core/playbook_store.py` for reads, serialize rows to
stable JSON, and close/clean up connections according to local route conventions.

The API surface is intentionally observational. It does not execute playbooks, create
execution rows, enqueue response actions, mutate queue state, or wire into ingest.

If the existing app registration pattern requires explicit Blueprint registration,
`siem_backend.py` may import and register the new Blueprint. No other application bootstrap
changes are expected.

## Files Likely To Change

- `routes/playbook_routes.py` — new read-only API routes and serializers.
- `siem_backend.py` — register `playbook_bp` only if explicit route registration remains the
  existing pattern.
- `core/playbook_store.py` — add only narrowly scoped read helpers if existing helpers do not
  support a required read path, such as listing all definitions instead of enabled-only
  definitions.
- `tests/test_playbook_read_apis.py` — route tests for auth, response shape, filters,
  not-found behavior, and no mutation.

No schema, frontend, executor, queue, ingest, detection, or correlation files should change.

## API Endpoint Behavior

### `GET /playbooks`

Lists playbook definitions ordered by stable ID.

Query params:

| Param | Default | Notes |
|---|---:|---|
| `enabled` | none | Optional boolean filter: `true` or `false`. Omitted returns all definitions. |
| `limit` | `50` | Clamp to a safe maximum such as `100`. |

Response shape:

```json
{
  "items": [
    {
      "id": "block_high_reputation_ip",
      "name": "Block high reputation IP",
      "description": "Blocks high-confidence abusive sources",
      "trigger_config": {
        "min_severity": "HIGH",
        "reputation_score_min": 75
      },
      "steps": [
        {
          "action": "block_ip",
          "params": {},
          "on_failure": "abort"
        }
      ],
      "enabled": true,
      "created_at": "2026-05-09T12:00:00+00:00",
      "updated_at": "2026-05-09T12:00:00+00:00"
    }
  ],
  "limit": 50,
  "enabled": null
}
```

Definitions must be returned as stored configuration only. Do not evaluate trigger matches
or validate execution readiness from this endpoint.

### `GET /playbooks/<id>`

Returns one playbook definition by slug ID.

Response is the same definition object used in the list endpoint. Return `404` when the
definition does not exist.

The route must not infer whether a playbook has executions unless that is added as a
separate read-only summary later. Keep the first implementation focused on the definition
record itself.

### `GET /playbook-executions`

Lists playbook execution records ordered by `created_at DESC`.

Query params:

| Param | Default | Notes |
|---|---:|---|
| `playbook_id` | none | Optional exact playbook definition ID filter. |
| `status` | none | Optional execution status filter. |
| `limit` | `50` | Clamp to a safe maximum such as `100`. |

Allowed status values:

- `pending`
- `running`
- `success`
- `failed`
- `abandoned`

Response shape:

```json
{
  "items": [
    {
      "id": 123,
      "playbook_id": "block_high_reputation_ip",
      "alert_id": 42,
      "incident_id": 7,
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "last_completed_step": null,
      "steps_log": [],
      "created_at": "2026-05-09T12:05:00+00:00"
    }
  ],
  "limit": 50,
  "playbook_id": null,
  "status": null
}
```

The list endpoint should not join alerts or incidents for the first implementation. Preserve
nullable `alert_id` and `incident_id` as JSON `null`.

### `GET /playbook-executions/<id>`

Returns one playbook execution record by integer ID.

Response is the same execution object used in the list endpoint. Return `404` when the
execution does not exist. Malformed non-integer IDs should be handled by Flask routing or a
safe 404/400 response consistent with existing routes.

## Auth/Permission Expectations

Use existing auth and role decorators already present in the repo. The recommended initial
permission level is the same operator/admin read access used for incident and alert
visibility if available; otherwise use the stricter existing SOAR/admin pattern.

Expected behavior must be explicit in tests:

- Unauthenticated caller: denied according to existing app behavior, typically `401`.
- Authenticated user without the required role: `403`.
- Authorized operator/admin: `200`.

These endpoints expose response policy and execution history, so they must not be public.

## Data Flow

```text
HTTP GET
  -> routes/playbook_routes.py
  -> auth/role decorators
  -> read-only store helper in core/playbook_store.py
  -> serializer
  -> JSON response
```

No route should call:

- `engines/playbook_engine.match_playbooks`
- any future playbook executor
- `create_playbook_execution`
- `update_execution_status`
- SOAR queue claim/mark/requeue/recover helpers
- ingest routes or detection/correlation modules

## Safety Boundaries

- APIs are read-only.
- Do not add POST, PUT, PATCH, or DELETE playbook endpoints.
- Do not create `playbook_executions` from alerts.
- Do not enqueue SOAR queue actions.
- Do not run playbook steps.
- Do not call Slack, email, firewall, dry-run firewall, or other adapters.
- Do not touch ingest, detection, correlation, SOAR queue, approvals, incidents, or protected
  target policy behavior.
- Do not add schema columns, indexes, or tables.
- Do not expose stack traces or raw database errors in JSON responses.

## Failure Behavior

- Missing playbook definition: `404`.
- Missing execution record: `404`.
- Invalid `enabled` filter: `400`.
- Invalid execution `status` filter: `400`.
- Invalid `limit`: `400` or clamp, but choose one behavior and test it.
- Database failure: log server-side and return a safe `500` JSON response consistent with
  local route style.

Route handlers should not call `conn.commit()` after reads unless existing route cleanup
style requires it. They must not mutate timestamps or status fields.

## Test Strategy

Add route tests using the existing Flask test client and auth fixture patterns.

Cover:

- Auth denial for unauthenticated callers.
- Role denial for authenticated users without required permission.
- Authorized list of definitions.
- Authorized single definition lookup.
- Definition `404`.
- Optional `enabled=true` and `enabled=false` filtering.
- Authorized execution list.
- Execution list filters by `playbook_id` and `status`.
- Execution detail lookup.
- Execution `404`.
- Invalid filters return `400`.
- `alert_id=None` and `incident_id=None` serialize as JSON `null`.
- `steps`, `trigger_config`, and `steps_log` remain parsed JSON objects/arrays.
- No mutation after read endpoints by re-reading seeded rows directly from the database.

Keep existing store, registry, and trigger-matching tests unchanged.

## Risks/Stop Conditions

- Stop if implementing the API appears to require schema changes.
- Stop if route registration requires broad app bootstrap restructuring.
- Stop if tests require touching ingest, detection, or correlation fixtures in a way that
  changes pipeline behavior.
- Stop if any route needs to call playbook matching, execution, queue enqueueing, or adapter
  code to produce its response.
- Stop if permission expectations are ambiguous enough that the route could expose playbook
  policy to ordinary users.
