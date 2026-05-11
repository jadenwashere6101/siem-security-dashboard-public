# Tasks: SOAR Playbook Read APIs

Implement later in small, read-only steps. Do not implement as part of this spec-only
change.

Run these regression tests after implementation steps that touch route registration or shared
auth/bootstrap behavior:

```bash
python3 -m pytest tests/test_failed_login_detection.py
python3 -m pytest tests/test_password_spraying_detection.py
python3 -m pytest tests/test_correlated_activity.py
python3 -m pytest tests/test_targeted_correlation.py
python3 -m pytest tests/test_ingest_api_contracts.py
python3 -m pytest tests/test_alert_mutation_api_contracts.py
```

## Step 1: Read Existing Patterns

- [ ] Read `routes/admin_routes.py`, `routes/incident_routes.py`, and `routes/approval_routes.py`.
- [ ] Confirm the auth decorator to use for playbook visibility.
- [ ] Read `siem_backend.py` and confirm the Blueprint registration pattern.
- [ ] Read `core/playbook_store.py` and identify whether a new read helper is needed for
      listing all definitions, including disabled definitions.

Stop if the desired route permissions are unclear.

## Step 2: Add Read-Only Store Helper If Needed

File:

```text
core/playbook_store.py
```

- [ ] Add only read helper(s) needed by the route layer, such as
      `list_playbook_definitions(conn, enabled=None, limit=50)`.
- [ ] Use `SELECT` only.
- [ ] Do not call `create_playbook_definition`, `create_playbook_execution`, or
      `update_execution_status`.
- [ ] Do not commit.
- [ ] Preserve existing return shape for definition dicts.

Verification:

```bash
python3 -m py_compile core/playbook_store.py
python3 -m pytest tests/test_playbook_store.py
```

## Step 3: Add Route Module

File:

```text
routes/playbook_routes.py
```

- [ ] Create a Blueprint for playbook read APIs.
- [ ] Add serializers for playbook definitions and executions.
- [ ] Serialize timestamps consistently with existing backend route style.
- [ ] Preserve JSON fields as parsed objects/arrays:
      `trigger_config`, `steps`, and `steps_log`.
- [ ] Preserve nullable foreign keys as JSON `null`.
- [ ] Keep all routes read-only.

Do not import or call:

- `engines/playbook_engine.match_playbooks`
- any playbook executor
- SOAR queue worker or queue mutation helpers
- ingest, detection, or correlation modules
- integration adapters

Verification:

```bash
python3 -m py_compile routes/playbook_routes.py
```

## Step 4: Add Definition Endpoints

Add:

```text
GET /playbooks
GET /playbooks/<id>
```

- [ ] `GET /playbooks` returns `items`, `limit`, and `enabled`.
- [ ] Support optional `enabled=true|false` filter.
- [ ] Validate malformed `enabled` values with `400`.
- [ ] Validate or clamp `limit` according to the implementation choice.
- [ ] `GET /playbooks/<id>` returns one definition.
- [ ] Missing definition returns `404`.
- [ ] Endpoint calls do not mutate `playbook_definitions`.

## Step 5: Add Execution Endpoints

Add:

```text
GET /playbook-executions
GET /playbook-executions/<id>
```

- [ ] `GET /playbook-executions` returns `items`, `limit`, `playbook_id`, and `status`.
- [ ] Support optional `playbook_id` filter.
- [ ] Support optional `status` filter.
- [ ] Validate status against `pending`, `running`, `success`, `failed`, and `abandoned`.
- [ ] Validate or clamp `limit` according to the implementation choice.
- [ ] `GET /playbook-executions/<id>` returns one execution record.
- [ ] Missing execution returns `404`.
- [ ] Endpoint calls do not mutate `playbook_executions`.

## Step 6: Register Blueprint

File:

```text
siem_backend.py
```

- [ ] Register the new Blueprint only if explicit registration is the existing pattern.
- [ ] Keep registration scoped to the new route module.
- [ ] Do not restructure app creation.
- [ ] Do not change existing route prefixes.

Verification:

```bash
python3 -m py_compile siem_backend.py
```

## Step 7: Add Auth And Role Tests

New test file:

```text
tests/test_playbook_read_apis.py
```

Cover:

- [ ] Unauthenticated `GET /playbooks` is denied.
- [ ] Unauthorized authenticated `GET /playbooks` returns `403`.
- [ ] Authorized `GET /playbooks` returns `200`.
- [ ] Repeat auth/role checks for `GET /playbook-executions`.
- [ ] Cover detail endpoints with at least one authorized and one denied case each.

Use existing auth fixtures/patterns. Do not introduce a new auth model.

## Step 8: Add Response Shape Tests

Cover:

- [ ] Definition list returns `items`, `limit`, and `enabled`.
- [ ] Definition item includes `id`, `name`, `description`, `trigger_config`, `steps`,
      `enabled`, `created_at`, and `updated_at`.
- [ ] Definition detail returns the same stable definition shape.
- [ ] Definition detail returns `404` for unknown ID.
- [ ] Execution list returns `items`, `limit`, `playbook_id`, and `status`.
- [ ] Execution item includes `id`, `playbook_id`, `alert_id`, `incident_id`, `status`,
      `started_at`, `completed_at`, `last_completed_step`, `steps_log`, and `created_at`.
- [ ] Execution detail returns the same stable execution shape.
- [ ] Execution detail returns `404` for unknown ID.
- [ ] `alert_id=None` and `incident_id=None` serialize as JSON `null`.

## Step 9: Add Filter And Validation Tests

Cover:

- [ ] `GET /playbooks?enabled=true` returns enabled definitions only.
- [ ] `GET /playbooks?enabled=false` returns disabled definitions only.
- [ ] Invalid `enabled` filter returns `400`.
- [ ] `GET /playbook-executions?playbook_id=<id>` returns matching executions only.
- [ ] `GET /playbook-executions?status=running` returns matching executions only.
- [ ] Invalid execution status returns `400`.
- [ ] Invalid limit returns the chosen safe behavior.
- [ ] Excessive limit is clamped or rejected according to the chosen implementation.

## Step 10: Add No-Mutation Tests

Seed playbook definitions and executions, call every read endpoint, then re-read rows
directly from the database.

Assert:

- [ ] `playbook_definitions` rows are unchanged.
- [ ] `playbook_executions.status` is unchanged.
- [ ] `started_at`, `completed_at`, `last_completed_step`, and `steps_log` are unchanged.
- [ ] No SOAR queue rows are created or changed.
- [ ] No `response_actions_log` rows are created.

## Final Verification

Run:

```bash
python3 -m py_compile core/playbook_store.py routes/playbook_routes.py siem_backend.py
python3 -m pytest tests/test_playbook_store.py
python3 -m pytest tests/test_playbook_registry.py
python3 -m pytest tests/test_playbook_engine.py
python3 -m pytest tests/test_playbook_read_apis.py
python3 -m pytest tests/test_soar_queue_visibility_api.py
python3 -m pytest tests/test_soar_worker_admin_run_control.py
python3 -m pytest tests/test_soar_adapter_interface.py
python3 -m pytest tests/test_failed_login_detection.py
python3 -m pytest tests/test_password_spraying_detection.py
python3 -m pytest tests/test_correlated_activity.py
python3 -m pytest tests/test_targeted_correlation.py
python3 -m pytest tests/test_ingest_api_contracts.py
python3 -m pytest tests/test_alert_mutation_api_contracts.py
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires schema changes.
- [ ] Stop if implementation requires creating playbook executions from alerts.
- [ ] Stop if implementation requires playbook executor logic.
- [ ] Stop if implementation touches ingest, detection, or correlation.
- [ ] Stop if implementation changes SOAR queue, approval, incident, protected-target, or
      adapter behavior.
- [ ] Roll back the current implementation step if any listed regression test fails.
