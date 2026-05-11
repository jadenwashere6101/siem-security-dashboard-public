# Tasks: Wire SOAR Simulation Adapters To Playbook Executor

## Implementation Steps

- [ ] Read `engines/playbook_step_executor.py` before editing.
- [ ] Read `integrations/base_integration.py` and `integrations/integration_registry.py`.
- [ ] Add a narrow action-to-adapter mapping for:
  - `notify_slack` -> adapter `slack`, adapter action `send_message`
  - `notify_email` -> adapter `email`, adapter action `send_email`
  - `block_ip` -> adapter `firewall`, adapter action `block_ip`
  - `notify_webhook` -> adapter `webhook`, adapter action `post_event`
- [ ] Update the executor step simulation path to dispatch mapped actions through the
  adapter registry.
- [ ] Pass step `params` as adapter params.
- [ ] Pass execution context to adapters: `execution_id`, `playbook_id`, `alert_id`,
  `incident_id`, and `step_index`.
- [ ] Write adapter results into `steps_log[*].output.adapter_result`.
- [ ] If adapter result has `success: true`, mark the step `success`.
- [ ] If adapter result has `success: false`, mark the step `failed` and preserve existing
  `on_failure` behavior.
- [ ] If registry mode fails closed because `INTEGRATION_MODE` is not `simulation`, record a
  failed simulated step and do not perform real execution.
- [ ] Preserve existing non-adapter simulation behavior.
- [ ] Preserve existing approval gate behavior.
- [ ] Do not wire adapters into routes, ingest, detection, correlation, SOAR queue, frontend,
  daemon/systemd worker, or execution controls.

## Exact Backend Test Requirements

- [ ] Update or add focused tests in `tests/test_playbook_step_executor.py`.
- [ ] Test `notify_slack` succeeds and records a nested Slack `adapter_result`.
- [ ] Test `notify_email` succeeds and records a nested email `adapter_result`.
- [ ] Test `block_ip` succeeds and records a nested firewall `adapter_result`.
- [ ] Test `notify_webhook` succeeds and records a nested webhook `adapter_result`.
- [ ] Assert adapter-backed step log entries include:
  - `mode: simulation`
  - `simulated: true`
  - `executed: false`
  - `output.adapter_result.simulated: true`
  - `output.adapter_result.executed: false`
- [ ] Test no network primitives are called for adapter-backed steps.
- [ ] Test firewall adapter-backed steps do not mutate `blocked_ips`.
- [ ] Test adapter-backed steps do not insert `response_actions_queue` rows.
- [ ] Test unsupported adapter result or registry error marks the step failed safely.
- [ ] Test non-simulation `INTEGRATION_MODE` fails closed without network calls.
- [ ] Re-run existing approval gate tests to prove pause/resume/deny/expire behavior is
  unchanged.

## Verification Commands

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py

python3 -m pytest tests/test_integration_adapters.py tests/test_playbook_step_executor.py -v

python3 -m pytest tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v

python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v

git status --short
```

## Stop / Rollback Conditions

- [ ] Stop if implementation requires secrets.
- [ ] Stop if implementation requires real Slack, email, webhook, firewall, or provider
  clients.
- [ ] Stop if implementation makes network calls.
- [ ] Stop if real mode must be implemented.
- [ ] Stop if implementation mutates firewall, blocklist, `blocked_ips`, or SOAR queue state.
- [ ] Stop if implementation requires schema changes.
- [ ] Stop if implementation requires frontend changes.
- [ ] Stop if implementation requires ingest, detection, correlation, approval, execution
  control, daemon, or systemd changes.
- [ ] Stop if existing approval gate behavior regresses.
- [ ] Roll back by reverting the executor/test changes and rerunning the verification
  commands.
