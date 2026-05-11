# Tasks: SOAR Playbook Execution Metrics

## Implementation steps
- [ ] Inspect existing playbook read route auth and role patterns.
- [ ] Inspect existing route registration and any current metrics route conventions.
- [ ] Choose the smallest backend route location for `GET /metrics/playbooks`.
- [ ] Add read-only SQL/helper logic for total execution counts.
- [ ] Add read-only status bucket counts for `pending`, `running`, `awaiting_approval`, `success`, `failed`, and `abandoned`.
- [ ] Add read-only counts grouped by `playbook_id`.
- [ ] Add recent success/failure counts using a documented time window.
- [ ] Add approval-gated execution counts only if existing read-only data supports them safely.
- [ ] Ensure all known status keys are present with zero values when absent.
- [ ] Register the route only where existing backend route registration patterns require it.
- [ ] Add focused backend tests.
- [ ] Confirm no frontend, schema, executor, adapter, SOAR queue, ingest, detection, or correlation files changed.

## Exact backend test requirements
- [ ] Test unauthenticated access is rejected using existing project behavior.
- [ ] Test analyst read access if analysts can read playbook state.
- [ ] Test super-admin read access.
- [ ] Test viewer access is forbidden if viewers are forbidden by existing playbook read APIs.
- [ ] Test empty execution data returns zero counts for all known statuses.
- [ ] Test total execution count.
- [ ] Test counts by status for `pending`, `running`, `awaiting_approval`, `success`, `failed`, and `abandoned`.
- [ ] Test counts grouped by `playbook_id`.
- [ ] Test recent success and failure counts.
- [ ] Test approval-gated counts when linked approval data exists.
- [ ] Test the endpoint does not mutate playbook executions, approvals, SOAR queue rows, or response action logs.
- [ ] Test the endpoint does not call the playbook executor.
- [ ] Test the endpoint does not call integration adapter execution paths or network code.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_playbook_metrics_routes.py -v
python3 -m pytest tests/test_playbook_routes.py tests/test_playbook_step_executor.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_approval_routes.py tests/test_approval_store.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If the final focused metrics test file uses a different name, replace `tests/test_playbook_metrics_routes.py` with the actual test file.

## Stop and rollback conditions
- Stop if implementation requires schema changes for the initial endpoint.
- Stop if implementation requires frontend changes.
- Stop if implementation requires playbook executor behavior changes.
- Stop if implementation requires retry, abandon, or resume behavior changes.
- Stop if implementation requires real integrations, secrets, network calls, or adapter execution.
- Stop if implementation requires daemon, systemd, Celery, APScheduler, or background worker changes.
- Stop if implementation requires SOAR queue changes.
- Stop if implementation requires ingest, detection, or correlation changes.
- Roll back the route and tests if the endpoint cannot remain read-only.
