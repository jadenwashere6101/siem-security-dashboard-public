# Tasks: SOAR Playbook Trigger Execution Records

Implement later in small backend-only steps. Do not implement as part of this spec-only
change.

## Step 1: Reconfirm Transaction Boundaries

- [ ] Read `routes/ingest_routes.py`.
- [ ] Identify every existing post-commit `enqueue_committed_alerts` call.
- [ ] Identify every existing post-commit incident creation call.
- [ ] Confirm the primary detection/correlation transaction commits before any playbook
      matching is added.
- [ ] Read `engines/playbook_engine.py`.
- [ ] Read `core/playbook_store.py`.
- [ ] Read `engines/soar_enqueue_orchestrator.py` for post-commit logging style.

Stop if the implementation would require moving the primary ingest `conn.commit()`.

## Step 2: Add Idempotency Constraint If Needed

File:

```text
schema.sql
```

- [ ] Add only a tiny additive unique partial index if needed:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_executions_playbook_alert_unique
ON playbook_executions (playbook_id, alert_id)
WHERE alert_id IS NOT NULL;
```

- [ ] Do not add columns.
- [ ] Do not drop or rename anything.
- [ ] Do not change existing indexes.

Verification:

```bash
python3 -c "import os, psycopg2; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(); cur.execute(open('schema.sql').read()); conn.commit(); conn.close(); print('schema OK')"
```

Stop if idempotency requires more than this additive index.

## Step 3: Add Store Helper Tests

File:

```text
tests/test_playbook_store.py
```

Add tests for the future helper:

- [ ] First insert creates `status='pending'`.
- [ ] First insert returns execution ID.
- [ ] Duplicate `(playbook_id, alert_id)` returns `None` or a duplicate marker.
- [ ] Duplicate insert does not update existing row fields.
- [ ] Same alert with different playbooks creates separate rows.
- [ ] Same playbook with different alerts creates separate rows.
- [ ] Helper does not commit internally.
- [ ] Helper does not create SOAR queue rows.
- [ ] Helper does not create response action log rows.

## Step 4: Add Idempotent Store Helper

File:

```text
core/playbook_store.py
```

- [ ] Add `create_pending_playbook_execution_once(conn, playbook_id, alert_id, incident_id=None)`.
- [ ] Require non-null `alert_id` for this helper.
- [ ] Insert only `status='pending'`.
- [ ] Return new execution ID when inserted.
- [ ] Return `None` for duplicate.
- [ ] Do not update existing rows.
- [ ] Do not call `update_execution_status`.
- [ ] Do not touch SOAR queue tables.
- [ ] Do not touch response action logs.
- [ ] Do not commit internally.

Verification:

```bash
python3 -m py_compile core/playbook_store.py
python3 -m pytest tests/test_playbook_store.py
```

## Step 5: Add Orchestrator Tests

New file:

```text
tests/test_playbook_execution_orchestrator.py
```

Cover:

- [ ] Empty alert list returns empty result.
- [ ] Non-dict alert entry is skipped.
- [ ] Alert without `alert_id` is skipped.
- [ ] No matching enabled playbooks creates no execution rows.
- [ ] One matching enabled playbook creates one pending execution.
- [ ] Multiple matching enabled playbooks create multiple pending executions.
- [ ] Disabled playbook does not create execution row.
- [ ] Repeated orchestration call does not duplicate rows.
- [ ] Missing alert ID is skipped safely.
- [ ] Match exception is caught and logged.
- [ ] Insert exception is caught and logged.
- [ ] Orchestrator does not call SOAR queue enqueue helpers.
- [ ] Orchestrator does not call playbook executor or `update_execution_status`.
- [ ] Orchestrator does not create approvals.
- [ ] Orchestrator does not create `response_actions_log` rows.

## Step 6: Add Orchestrator Module

New file:

```text
engines/playbook_execution_orchestrator.py
```

- [ ] Add `create_pending_executions_for_committed_alerts(alerts_created, conn)`.
- [ ] Accept the existing `alerts_created` list shape.
- [ ] Extract only valid `alert_id` values.
- [ ] Call `match_playbooks(conn, alert_id)` for each valid alert.
- [ ] Call `create_pending_playbook_execution_once` for each matched playbook.
- [ ] Record result entries for created, duplicate, skipped, and error outcomes.
- [ ] Use Python logging, not `print`.
- [ ] Do not commit internally.
- [ ] Do not import queue worker, SOAR executor, approvals, integrations, detection,
      correlation, or ingest modules.

Verification:

```bash
python3 -m py_compile engines/playbook_execution_orchestrator.py
python3 -m pytest tests/test_playbook_execution_orchestrator.py
```

## Step 7: Wire Minimal Post-Commit Calls

File:

```text
routes/ingest_routes.py
```

- [ ] Import `create_pending_executions_for_committed_alerts`.
- [ ] Add a small post-commit try/except block in each existing ingest handler.
- [ ] Place the block only after the primary alert commit.
- [ ] Keep existing SOAR queue enqueue behavior unchanged.
- [ ] Keep existing incident creation behavior unchanged.
- [ ] Commit after successful pending execution creation.
- [ ] Roll back only the playbook scheduling transaction on scheduling error.
- [ ] Log scheduling errors and do not fail the ingest response.
- [ ] Do not alter response payload shape unless tests already permit it.
- [ ] Do not refactor detection/correlation transaction flow.

Verification:

```bash
python3 -m py_compile routes/ingest_routes.py
python3 -m pytest tests/test_ingest_api_contracts.py
```

## Step 8: Add Ingest-Orchestration Tests

Add focused tests in the most appropriate existing ingest/playbook test file.

Cover:

- [ ] Ingest that creates a matching alert creates a pending `playbook_executions` row.
- [ ] Ingest with no matching playbook does not create execution rows.
- [ ] Disabled playbook does not create execution rows.
- [ ] Repeated post-commit orchestration does not duplicate rows.
- [ ] Playbook scheduling failure does not fail ingest response.
- [ ] Existing SOAR queue rows are still created exactly as before.
- [ ] No response action log rows are created by playbook scheduling.
- [ ] No approval rows are created by playbook scheduling.

## Six Regression Test Requirements

Run these after any step that touches `routes/ingest_routes.py`:

```bash
python3 -m pytest tests/test_failed_login_detection.py
python3 -m pytest tests/test_password_spraying_detection.py
python3 -m pytest tests/test_correlated_activity.py
python3 -m pytest tests/test_targeted_correlation.py
python3 -m pytest tests/test_ingest_api_contracts.py
python3 -m pytest tests/test_alert_mutation_api_contracts.py
```

If any fail, roll back the current implementation step before continuing.

## Full Verification Commands

Focused playbook checks:

```bash
python3 -m py_compile core/playbook_store.py engines/playbook_execution_orchestrator.py routes/ingest_routes.py
python3 -m pytest tests/test_playbook_store.py
python3 -m pytest tests/test_playbook_engine.py
python3 -m pytest tests/test_playbook_execution_orchestrator.py
python3 -m pytest tests/test_playbook_read_apis.py
python3 -m pytest tests/test_playbook_definition_management_api.py
```

SOAR safety checks:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py
python3 -m pytest tests/test_soar_enqueue_orchestrator.py
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

- [ ] Stop if matching would run before alert commit.
- [ ] Stop if implementation requires detection or correlation refactors.
- [ ] Stop if implementation requires a playbook executor.
- [ ] Stop if implementation enqueues SOAR actions.
- [ ] Stop if implementation creates approvals.
- [ ] Stop if implementation calls Slack, email, firewall, dry-run adapter, or integrations.
- [ ] Stop if implementation changes existing SOAR queue behavior.
- [ ] Stop if implementation changes existing incident behavior.
- [ ] Stop if implementation requires a broad ingest refactor.
- [ ] Stop if schema changes exceed the optional unique partial index.
- [ ] Roll back the current step if any six pipeline regression tests fail.
- [ ] Roll back the current step if SOAR queue, approval, incident, or adapter tests regress.
