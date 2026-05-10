# Tasks: SOAR Integration Adapter Health APIs

## Implementation steps
- [ ] Inspect existing route registration and auth helpers.
- [ ] Choose the smallest route location for a read-only integration status endpoint.
- [ ] Add `GET /integrations/status` using existing auth and role patterns.
- [ ] Return mode, simulated status, real-mode disabled status, adapter names, and supported actions.
- [ ] Ensure the route does not call real provider clients, test connections, adapters' external methods, or network code.
- [ ] Register the route only where existing backend route registration patterns require it.
- [ ] Add focused backend route tests.
- [ ] Confirm no schema, frontend, executor, SOAR queue, ingest, detection, or correlation files changed.

## Exact backend test requirements
- [ ] Test authenticated analyst read access.
- [ ] Test authenticated super-admin read access if role fixtures are available.
- [ ] Test unauthenticated access is rejected using existing project behavior.
- [ ] Test the response includes simulation mode and real mode disabled/fail-closed status.
- [ ] Test the response includes `slack`, `email`, `firewall`, and `webhook`.
- [ ] Test supported actions are present for each adapter.
- [ ] Test no network calls are made by monkeypatching network primitives to fail.
- [ ] Test no secrets are required by clearing integration-related environment variables.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If the final test filename differs, replace `tests/test_integration_routes.py` with the actual focused route test file.

## Stop and rollback conditions
- Stop if implementation requires real network calls or real provider clients.
- Stop if implementation requires secrets.
- Stop if implementation requires schema changes.
- Stop if implementation requires frontend changes.
- Stop if implementation requires executor behavior changes.
- Stop if implementation requires SOAR queue, ingest, detection, or correlation changes.
- Roll back the route and tests if the endpoint cannot remain read-only and simulation-only.
