# Tasks: SOAR Playbook Definition Management

Implement later in small, isolated backend steps. Do not implement as part of this
spec-only change.

## Step 1: Reconfirm Existing Patterns

- [ ] Read `routes/playbook_routes.py`.
- [ ] Read `routes/admin_routes.py` for `super_admin_required` mutation patterns.
- [ ] Read `core/playbook_store.py`.
- [ ] Read `engines/playbook_registry.py`.
- [ ] Read existing playbook read API tests.
- [ ] Confirm analysts retain read-only access and only super admins can mutate.

Stop if the permission model is unclear.

## Step 2: Add Store Helper Tests First

File:

```text
tests/test_playbook_store.py
```

Add tests for new store helpers before implementation:

- [ ] `update_playbook_definition` updates name, description, trigger_config, steps, and
      enabled.
- [ ] `update_playbook_definition` returns `None` for unknown ID.
- [ ] Update preserves the playbook ID.
- [ ] Update rejects unsupported step action through existing validation.
- [ ] `set_playbook_definition_enabled` sets enabled to `true`.
- [ ] `set_playbook_definition_enabled` sets enabled to `false`.
- [ ] `set_playbook_definition_enabled` returns `None` for unknown ID.
- [ ] Store helpers do not create `playbook_executions`.

## Step 3: Add Store Helpers

File:

```text
core/playbook_store.py
```

- [ ] Add `update_playbook_definition(conn, playbook_id, *, name, description, trigger_config, steps, enabled)`.
- [ ] Add `set_playbook_definition_enabled(conn, playbook_id, enabled)`.
- [ ] Use parameterized SQL only.
- [ ] Validate `trigger_config` is a dict.
- [ ] Validate `steps` with `validate_playbook_steps`.
- [ ] Return updated definition dicts.
- [ ] Return `None` when no row exists.
- [ ] Refresh `updated_at` on successful updates if supported by schema.
- [ ] Do not commit inside helpers.
- [ ] Do not touch `playbook_executions`.

Verification:

```bash
python3 -m py_compile core/playbook_store.py
python3 -m pytest tests/test_playbook_store.py
```

## Step 4: Add Route-Level Payload Validation

File:

```text
routes/playbook_routes.py
```

- [ ] Add private validation helpers for definition payloads.
- [ ] Validate create `id` with a stable slug rule.
- [ ] Validate `name` is non-empty.
- [ ] Validate `description` is null or string.
- [ ] Validate `trigger_config` is an object.
- [ ] Validate `steps` is a list.
- [ ] Validate steps through `validate_playbook_steps`.
- [ ] Validate `enabled` is boolean when provided.
- [ ] Return safe `400` errors for invalid payloads.
- [ ] Do not import playbook engine, executor, queue worker, ingest, detection, correlation,
      approvals, incidents, or adapters.

Verification:

```bash
python3 -m py_compile routes/playbook_routes.py
```

## Step 5: Add Create Endpoint

Add:

```text
POST /playbooks
```

- [ ] Require `@login_required`.
- [ ] Require `@super_admin_required`.
- [ ] Validate JSON body.
- [ ] Default `enabled` to `false` if omitted.
- [ ] Use `create_playbook_definition`.
- [ ] Commit only after successful insert.
- [ ] Roll back on validation/database failure.
- [ ] Return `201` with the created definition.
- [ ] Return `409` for duplicate ID.
- [ ] Do not create executions.
- [ ] Do not enqueue SOAR actions.

## Step 6: Add Update Endpoint

Add:

```text
PUT /playbooks/<id>
```

- [ ] Require `@login_required`.
- [ ] Require `@super_admin_required`.
- [ ] Validate JSON body.
- [ ] Do not allow changing the path ID.
- [ ] Use `update_playbook_definition`.
- [ ] Return `404` for unknown ID.
- [ ] Return `200` with the updated definition.
- [ ] Roll back on failure.
- [ ] Do not create executions.
- [ ] Do not enqueue SOAR actions.

## Step 7: Add Enable/Disable Endpoint

Add:

```text
PATCH /playbooks/<id>/enabled
```

- [ ] Require `@login_required`.
- [ ] Require `@super_admin_required`.
- [ ] Require JSON boolean `enabled`.
- [ ] Use `set_playbook_definition_enabled`.
- [ ] Return `404` for unknown ID.
- [ ] Return `200` with the updated definition.
- [ ] Roll back on failure.
- [ ] Do not call trigger matching.
- [ ] Do not create executions.
- [ ] Do not enqueue SOAR actions.

## Step 8: Add Auth And Permission Tests

File:

```text
tests/test_playbook_definition_management_api.py
```

Cover:

- [ ] Unauthenticated create is denied.
- [ ] Analyst create returns `403`.
- [ ] Viewer create returns `403`.
- [ ] Super admin create succeeds.
- [ ] Analyst update returns `403`.
- [ ] Viewer update returns `403`.
- [ ] Super admin update succeeds.
- [ ] Analyst enable/disable returns `403`.
- [ ] Viewer enable/disable returns `403`.
- [ ] Super admin enable/disable succeeds.
- [ ] Analyst read-only `GET /playbooks` still succeeds.

## Step 9: Add Validation Tests

Cover:

- [ ] Create rejects missing ID.
- [ ] Create rejects invalid ID format.
- [ ] Create rejects duplicate ID with `409`.
- [ ] Create rejects missing or blank name.
- [ ] Create rejects non-object `trigger_config`.
- [ ] Create rejects non-list `steps`.
- [ ] Create rejects unsupported action from `validate_playbook_steps`.
- [ ] Update rejects blank name.
- [ ] Update rejects unsupported action.
- [ ] Update does not allow ID rename.
- [ ] Enable/disable rejects missing `enabled`.
- [ ] Enable/disable rejects non-boolean `enabled`.
- [ ] Unknown update returns `404`.
- [ ] Unknown enable/disable returns `404`.

## Step 10: Add Safety/No-Execution Tests

Seed existing playbook definitions, queue rows, response action logs, incidents, and
approvals as needed by local fixtures.

Assert after create/update/enable-disable:

- [ ] No `playbook_executions` rows are created.
- [ ] No `response_actions_queue` rows are created or changed.
- [ ] No `response_actions_log` rows are created.
- [ ] Existing approvals are unchanged.
- [ ] Existing incidents are unchanged.
- [ ] Existing queue rows are unchanged.
- [ ] No route calls `match_playbooks`, executor code, or queue worker code.

Use mocks only where needed to assert forbidden calls are not made.

## Verification Commands

Focused backend checks:

```bash
python3 -m py_compile core/playbook_store.py routes/playbook_routes.py
python3 -m pytest tests/test_playbook_store.py
python3 -m pytest tests/test_playbook_read_apis.py
python3 -m pytest tests/test_playbook_definition_management_api.py
python3 -m pytest tests/test_playbook_registry.py
python3 -m pytest tests/test_playbook_engine.py
```

SOAR regression checks:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py
python3 -m pytest tests/test_soar_worker_admin_run_control.py
python3 -m pytest tests/test_soar_adapter_interface.py
python3 -m pytest tests/test_soar_protected_targets.py
python3 -m pytest tests/test_approval_api.py
python3 -m pytest tests/test_incident_api.py
```

Pipeline regression checks:

```bash
python3 -m pytest tests/test_failed_login_detection.py
python3 -m pytest tests/test_password_spraying_detection.py
python3 -m pytest tests/test_correlated_activity.py
python3 -m pytest tests/test_targeted_correlation.py
python3 -m pytest tests/test_ingest_api_contracts.py
python3 -m pytest tests/test_alert_mutation_api_contracts.py
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires schema changes beyond a tiny additive field.
- [ ] Stop if implementation requires frontend changes.
- [ ] Stop if implementation requires a playbook executor.
- [ ] Stop if implementation creates `playbook_executions`.
- [ ] Stop if implementation enqueues SOAR actions.
- [ ] Stop if implementation touches ingest, detection, or correlation.
- [ ] Stop if implementation changes SOAR queue, approval, incident, protected-target, or
      adapter behavior.
- [ ] Roll back the current implementation step if focused playbook tests fail.
- [ ] Roll back the current implementation step if SOAR or pipeline regression tests fail.
