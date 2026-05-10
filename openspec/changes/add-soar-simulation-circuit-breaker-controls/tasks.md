# Tasks: SOAR Simulation Circuit Breaker Controls

## Implementation steps
- [ ] Inspect existing integration circuit breaker state and metadata helpers.
- [ ] Inspect integration status route, frontend panel, auth patterns, and audit helpers.
- [ ] Choose route shape for manual breaker actions.
- [ ] Add super-admin-only manual reset-to-closed control.
- [ ] Add super-admin-only manual force-open control.
- [ ] Add super-admin-only manual half-open probe enablement control.
- [ ] Require explicit operator action for every state-changing path.
- [ ] Add audit events for all successful breaker control actions.
- [ ] Define failure behavior when audit logging fails.
- [ ] Return updated breaker state after each successful control action.
- [ ] Expose manual action metadata through integration status if available.
- [ ] Add UI visibility for current breaker state and super-admin-only controls.
- [ ] Ensure analysts retain read-only visibility and cannot invoke controls.
- [ ] Ensure controls do not execute probes, run playbooks, call adapters, enqueue queue rows, or mutate playbook executions.
- [ ] Document restart behavior in status response or operator-visible metadata.
- [ ] Confirm no real integrations, queue redesign, daemon/scheduler behavior, or ingest/detection/correlation changes were introduced.

## Exact backend test requirements
- [ ] Test unauthenticated control requests return existing unauthorized behavior.
- [ ] Test analyst control requests are forbidden.
- [ ] Test viewer control requests are forbidden.
- [ ] Test super-admin can reset an eligible breaker to `closed`.
- [ ] Test reset clears failure/cooldown metadata according to the chosen state model.
- [ ] Test super-admin can force-open a breaker.
- [ ] Test force-open prevents later adapter-backed simulated execution until explicitly changed.
- [ ] Test super-admin can enable `half_open` probe eligibility.
- [ ] Test enabling half-open does not execute a probe.
- [ ] Test every successful control writes an audit event with previous state, new state, adapter, actor, reason, and timestamp.
- [ ] Test invalid adapter names fail safely.
- [ ] Test invalid requested actions fail safely.
- [ ] Test unknown or corrupt breaker state fails closed and does not self-heal on read.
- [ ] Test status reads do not mutate breaker state.
- [ ] Test controls do not call adapter execution methods.
- [ ] Test controls do not run the playbook executor.
- [ ] Test controls do not retry, resume, abandon, or otherwise mutate playbook executions.
- [ ] Test controls do not enqueue SOAR queue rows.
- [ ] Test controls do not mutate `blocked_ips`.
- [ ] Test controls do not make network calls.
- [ ] Test controls do not call subprocesses.
- [ ] Test `INTEGRATION_MODE=real` remains disabled or fail-closed.

## Exact frontend test requirements
- [ ] Test integration status UI displays breaker state and manual action metadata.
- [ ] Test simulation-only notice remains visible.
- [ ] Test analyst users do not see enabled mutation controls.
- [ ] Test super-admin users see only eligible controls for the current breaker state.
- [ ] Test force-open, reset, and half-open actions call the intended service methods.
- [ ] Test successful actions refresh status.
- [ ] Test failed actions show error feedback without changing local state optimistically.
- [ ] Test UI text does not imply real Slack, email, webhook, firewall, blocklist, or external remediation occurred.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_metrics_routes.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
npm test -- --watchAll=false IntegrationStatusPanel.test.js
npm run build
git status --short
```

Adjust frontend command paths to match the existing frontend test runner if needed.

## Stop and rollback conditions
- Stop if implementation introduces autonomous retries.
- Stop if implementation introduces automatic replay.
- Stop if implementation introduces daemon or scheduler behavior.
- Stop if implementation makes real outbound calls.
- Stop if implementation enables `INTEGRATION_MODE=real`.
- Stop if implementation requires Redis/Celery/RQ migration.
- Stop if implementation redesigns queue architecture.
- Stop if implementation performs background healing.
- Stop if implementation creates hidden recovery behavior.
- Stop if implementation mutates firewall, blocklist, or `blocked_ips`.
- Stop if implementation changes ingest, detection, or correlation internals.
- Roll back if controls cannot remain simulation-only, fail-closed, operator-visible, explicit, and auditable.
