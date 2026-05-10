# Tasks: SOAR Integration Circuit Breaker Simulation

## Implementation steps
- [ ] Inspect current simulation integration registry and adapter result shape.
- [ ] Inspect playbook executor adapter-backed step handling and reliability metadata.
- [ ] Define circuit breaker state model for `closed`, `open`, and `half_open`.
- [ ] Decide whether breaker state is in memory or stored through an additive persistence layer.
- [ ] Add consecutive failure tracking per adapter.
- [ ] Add cooldown metadata per adapter.
- [ ] Add explicit timeout metadata to simulated adapter result handling.
- [ ] Add transient and non-transient simulated failure classifications.
- [ ] Add adapter-level retry eligibility metadata.
- [ ] Enforce fail-closed behavior for `open`, unknown, invalid, or non-simulation states.
- [ ] Add bounded half-open recovery probing with explicit/manual semantics.
- [ ] Expose operator-visible breaker state through integration status or a narrow read-only extension.
- [ ] Integrate circuit-open failures with existing playbook execution failure handling.
- [ ] Ensure repeated circuit-open failures can contribute to `permanently_failed` through existing bounded reliability safeguards.
- [ ] Confirm approval gates are not bypassed by breaker checks or recovery probes.
- [ ] Confirm no daemon, scheduler, background replay, queue redesign, real integrations, or protected ingest/detection/correlation paths are changed.

## Exact backend test requirements
- [ ] Test initial adapter circuit state is `closed` in simulation mode.
- [ ] Test consecutive simulated transient failures increment per-adapter failure counters.
- [ ] Test failure threshold transitions state to `open`.
- [ ] Test `open` state fails closed and does not call adapter execution internals.
- [ ] Test cooldown metadata is visible.
- [ ] Test cooldown expiration does not automatically execute a probe.
- [ ] Test explicit half-open probe success transitions to `closed`.
- [ ] Test explicit half-open probe failure transitions back to `open`.
- [ ] Test timeout metadata is recorded without timers or background mutation.
- [ ] Test transient failures are retry eligible only within bounded retry limits.
- [ ] Test non-transient failures are not retry eligible.
- [ ] Test invalid or unknown breaker state fails closed.
- [ ] Test integration status exposes circuit breaker state for analyst and super-admin read access.
- [ ] Test viewer access follows existing integration status visibility rules.
- [ ] Test circuit-open playbook step failure preserves immutable execution history.
- [ ] Test repeated circuit-open failures interact safely with `permanently_failed`.
- [ ] Test approval-gated executions do not run adapter probes before approval.
- [ ] Test no `blocked_ips` rows are written.
- [ ] Test no subprocess calls are made.
- [ ] Test no network calls or external API clients are used.
- [ ] Test `INTEGRATION_MODE=real` remains disabled or fail-closed.
- [ ] Run protected ingest, detection, and correlation regression tests.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_playbook_metrics_routes.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If focused circuit breaker tests are created with new filenames, include those files in the integration adapter or route test command.

## Stop and rollback conditions
- Stop if implementation requires real outbound calls.
- Stop if implementation requires Slack, webhook, email, firewall, PagerDuty, or external service execution.
- Stop if implementation requires daemon or scheduler behavior.
- Stop if implementation creates automatic autonomous retries.
- Stop if implementation creates a background replay engine.
- Stop if implementation requires Redis, Celery, RQ, or queue backend migration.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if implementation rewrites SOAR queue architecture.
- Stop if implementation mutates `blocked_ips`.
- Stop if implementation calls subprocesses.
- Stop if implementation introduces external API dependencies or secrets.
- Stop if implementation enables `INTEGRATION_MODE=real`.
- Roll back if circuit breaker handling cannot remain simulation-only, bounded, fail-closed, and operator-visible.
