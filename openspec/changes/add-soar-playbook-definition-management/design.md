# Design: SOAR Playbook Definition Management

## Proposed API Endpoints

Extend the existing playbook route surface with super-admin-only mutation endpoints.

Recommended endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/playbooks` | Create a new playbook definition. |
| `PUT` | `/playbooks/<id>` | Replace editable fields on an existing definition. |
| `PATCH` | `/playbooks/<id>/enabled` | Enable or disable an existing definition. |

Do not add execution endpoints, run controls, retry controls, delete endpoints, or queue
enqueue endpoints in this change.

### `POST /playbooks`

Request body:

```json
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
  "enabled": false
}
```

Response:

- `201` with the created definition object.
- `400` for invalid payloads.
- `409` for duplicate `id`.

Default behavior:

- `trigger_config` defaults to `{}` when omitted.
- `description` defaults to `null` or empty according to existing store conventions.
- `enabled` should default to `false` for new API-created definitions unless the request
  explicitly sets it. This keeps new policy visible but inert for future trigger matching
  until an operator intentionally enables it.

### `PUT /playbooks/<id>`

Replaces editable fields on an existing definition.

Allowed editable fields:

- `name`
- `description`
- `trigger_config`
- `steps`
- `enabled`

Rules:

- Path `id` identifies the row and is not changed by this endpoint.
- Unknown definition returns `404`.
- Invalid payload returns `400`.
- Successful update returns `200` with the updated definition object.
- `updated_at` should be refreshed if the existing schema supports it.

Do not allow renaming the definition ID in this change. ID renames would complicate existing
foreign keys from `playbook_executions`.

### `PATCH /playbooks/<id>/enabled`

Small, explicit endpoint for toggling availability.

Request body:

```json
{
  "enabled": true
}
```

Response:

- `200` with the updated definition object.
- `400` when `enabled` is missing or not boolean.
- `404` when the definition does not exist.

Enabling a definition only flips stored config state. It must not match alerts, create
executions, enqueue actions, or run steps.

## Auth/Permission Behavior

Read behavior remains unchanged:

- Analysts may keep read-only access through existing `GET` playbook endpoints.
- Super admins may read through the same endpoints.

Mutation behavior:

- `POST /playbooks`: `@login_required` + `@super_admin_required`.
- `PUT /playbooks/<id>`: `@login_required` + `@super_admin_required`.
- `PATCH /playbooks/<id>/enabled`: `@login_required` + `@super_admin_required`.

Expected responses:

- Unauthenticated caller: existing login-required denial, typically `401`.
- Authenticated analyst: `403`.
- Authenticated viewer: `403`.
- Authenticated super admin: allowed when payload is valid.

## Validation Rules

Validate before writing. A failed validation must not partially mutate the database.

Definition ID:

- Required on create.
- String.
- Stable slug format, recommended regex: `^[a-z0-9][a-z0-9_-]{1,63}$`.
- Not editable through update endpoint.

Name:

- Required on create and update.
- Non-empty string after trimming.
- Reasonable max length such as 200 characters.

Description:

- Optional.
- `null` or string.
- Trim if string.

Trigger config:

- Optional, defaults to `{}`.
- Must be a JSON object.
- Supported keys may remain forward-compatible with `engines/playbook_engine.py`:
  `alert_type`, `min_severity`, `source`, `correlation_flag`, `reputation_score_min`.
- Unknown keys may be accepted for forward compatibility, but the route should reject
  obviously invalid root types.

Steps:

- Required on create and update.
- Must be a list.
- Pass the list to `engines.playbook_registry.validate_playbook_steps`.
- Reject when validation returns errors.
- Do not validate adapter params beyond shape needed for JSON safety; action-specific params
  remain executor-time validation once an executor exists.

Enabled:

- Optional on create, default `false`.
- Optional on full update if the implementation chooses partial-tolerant behavior; if using
  strict replacement semantics, require it explicitly.
- Required on `/enabled` patch.
- Must be boolean.

## Data Flow

```text
HTTP mutation request
  -> routes/playbook_routes.py
  -> login + super_admin guard
  -> request JSON validation
  -> engines.playbook_registry.validate_playbook_steps
  -> core.playbook_store definition helper
  -> conn.commit()
  -> serialized definition JSON response
```

The route must not call:

- `engines.playbook_engine.match_playbooks`
- any playbook executor
- `create_playbook_execution`
- `update_execution_status`
- SOAR queue enqueue or worker helpers
- approval mutation helpers
- incident mutation helpers
- detection, correlation, ingest, or adapter modules

## Store Helper Changes

Use existing `core/playbook_store.py` conventions: functions accept `conn`, return dicts,
and leave transaction boundaries to callers.

Likely helper additions:

```python
def update_playbook_definition(
    conn,
    playbook_id: str,
    *,
    name: str,
    description: str | None,
    trigger_config: dict,
    steps: list[dict],
    enabled: bool,
) -> dict | None:
    ...

def set_playbook_definition_enabled(
    conn,
    playbook_id: str,
    enabled: bool,
) -> dict | None:
    ...
```

Existing `create_playbook_definition` can be reused if its default enabled behavior is
overridden by the route.

Rules:

- Use parameterized SQL.
- Validate steps through `validate_playbook_steps` either in route validation, store helper,
  or both.
- Do not touch `playbook_executions`.
- Do not commit inside store helpers.
- Return `None` for not found updates.
- Refresh `updated_at` on successful updates if supported by schema.

No schema change is expected. A schema change should only be considered if implementation
proves `updated_at` cannot be maintained safely with the existing column.

## Safety Boundaries

- Definition management must not execute anything.
- Creating or enabling a playbook must not create `playbook_executions`.
- Creating or enabling a playbook must not enqueue SOAR actions.
- Creating or enabling a playbook must not call trigger matching.
- Do not add a delete endpoint in this change.
- Do not add frontend mutation UI in this change.
- Do not touch ingest, detection, correlation, queue worker, queue UI, approvals, incidents,
  protected targets, dry-run adapter, or integration code.
- Do not change existing read endpoint response shapes unless strictly necessary and covered
  by tests.

## Failure Behavior

- Invalid JSON body: `400`.
- Missing required field: `400`.
- Invalid ID format: `400`.
- Duplicate create ID: `409`.
- Unsupported step action: `400` with safe validation message.
- Unknown definition on update/toggle: `404`.
- Unauthorized mutation: `403`.
- Database failure: rollback, log server-side, return safe `500`.

Responses must not expose stack traces, raw SQL, connection strings, environment variables,
or adapter configuration.

## Test Strategy

Add or extend backend route tests around playbook definition mutation.

Auth and permission tests:

- Unauthenticated create/update/toggle denied.
- Analyst create/update/toggle returns `403`.
- Viewer create/update/toggle returns `403`.
- Super admin create/update/toggle succeeds with valid payload.
- Existing analyst read-only access still succeeds.

Validation tests:

- Create requires valid ID.
- Create rejects duplicate ID.
- Create/update reject missing or blank name.
- Create/update reject non-object `trigger_config`.
- Create/update reject non-list `steps`.
- Create/update reject unsupported step action via `validate_playbook_steps`.
- Toggle rejects missing or non-boolean `enabled`.

Behavior tests:

- Create returns definition JSON with stable fields.
- Update changes editable fields and preserves ID.
- Toggle changes only enabled state plus `updated_at` if supported.
- Unknown update/toggle returns `404`.
- Creating enabled or disabled definitions does not create executions.
- Enabling an existing definition does not create executions.
- Mutations do not enqueue SOAR queue actions or write response action logs.
- Mutations do not alter approvals, incidents, protected targets, or existing queue rows.

Regression tests:

- Existing playbook read API tests still pass.
- Existing playbook store, registry, and trigger matching tests still pass.
- Existing SOAR queue/admin/protected-target tests still pass.
- Ingest/detection/correlation contract tests remain green.

## Risks/Stop Conditions

- Stop if implementation requires a playbook executor.
- Stop if implementation needs ingest, detection, or correlation changes.
- Stop if enabling a definition would require immediately matching historical alerts.
- Stop if mutation routes need to create `playbook_executions`.
- Stop if mutation routes need to enqueue queue actions.
- Stop if schema changes expand beyond a tiny additive maintenance field.
- Stop if permission boundaries conflict with existing auth model.
- Stop if frontend mutation UI becomes necessary; that belongs in a later spec.
