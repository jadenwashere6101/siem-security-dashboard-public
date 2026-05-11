# Tasks: SOAR Integration Adapter Simulation Foundation

## Implementation Steps

- [ ] Read existing `integrations/` package structure and tests before editing.
- [ ] Add `integrations/base_integration.py` with a small base adapter contract.
- [ ] Define the stable simulation `execute()` result fields:
  - `adapter`
  - `action`
  - `mode`
  - `simulated`
  - `executed`
  - `success`
  - `message`
  - `params`
  - `context`
  - `metadata`
- [ ] Add `integrations/integration_registry.py`.
- [ ] Implement `INTEGRATION_MODE` resolution with default `simulation`.
- [ ] Reject non-`simulation` modes for this change.
- [ ] Add a Slack simulation adapter.
- [ ] Add an email simulation adapter.
- [ ] Add a firewall simulation adapter.
- [ ] Add a webhook simulation adapter only if it can be implemented without any HTTP client
  or network behavior.
- [ ] Ensure adapters do not require secrets in simulation mode.
- [ ] Ensure the registry does not instantiate real clients in simulation mode.
- [ ] Ensure no playbook executor wiring is added in this change.
- [ ] Ensure no SOAR queue, approval, ingest, detection, correlation, schema, frontend, or
  daemon/systemd files are changed.

## Exact Backend Test Requirements

- [ ] Add `tests/test_integration_registry.py`.
- [ ] Test registry default mode is `simulation`.
- [ ] Test registry returns simulation adapters for `slack`, `email`, `firewall`, and
  `webhook` if webhook is included.
- [ ] Test adapter name lookup is case-insensitive.
- [ ] Test unknown adapter names fail locally with a clear error.
- [ ] Test non-`simulation` mode fails closed.
- [ ] Add `tests/test_integration_simulation_adapters.py`.
- [ ] Test every adapter result includes the stable result fields.
- [ ] Test every adapter result has `mode == "simulation"`, `simulated is True`, and
  `executed is False`.
- [ ] Test unsupported actions return a local simulated failure and do not raise unexpected
  exceptions.
- [ ] Test simulation mode does not require Slack, email, firewall, webhook, or provider
  secrets.
- [ ] Monkeypatch network primitives so tests fail if a simulation adapter calls network code.
- [ ] Test firewall simulation does not insert or update `blocked_ips`.
- [ ] Test adapters do not insert `response_actions_queue` rows.
- [ ] Run existing playbook executor tests to prove behavior is unchanged.

## Verification Commands

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py

python3 -m pytest tests/test_integration_registry.py tests/test_integration_simulation_adapters.py -v

python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_store.py tests/test_playbook_routes.py -v

python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v

git status --short
```

## Stop / Rollback Conditions

- [ ] Stop if implementation requires real Slack, email, webhook, firewall, or PagerDuty
  clients.
- [ ] Stop if implementation requires secrets in simulation mode.
- [ ] Stop if any test needs network access.
- [ ] Stop if any adapter mutates firewall, blocklist, `blocked_ips`, or SOAR queue state.
- [ ] Stop if playbook executor wiring is required.
- [ ] Stop if implementation requires daemon/systemd/scheduler behavior.
- [ ] Stop if implementation requires ingest, detection, correlation, frontend, approval
  decision, incident, or SOAR queue changes.
- [ ] To roll back, remove the new integration adapter files and new tests, then rerun the
  verification commands.
