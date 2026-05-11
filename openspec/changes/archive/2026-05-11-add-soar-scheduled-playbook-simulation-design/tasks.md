# Tasks: SOAR Scheduled Playbook Simulation Design

## Design tasks
- [ ] Define scheduled playbook metadata and whether schedules should live on `playbook_definitions` or a separate schedule record.
- [ ] Define enabled, disabled, paused, and resumed schedule lifecycle semantics.
- [ ] Define `last_run_at`, `next_run_at`, `last_success_at`, `last_failure_at`, and last execution linkage.
- [ ] Define safe missed-run policies: `skip`, `record_only`, and bounded `run_once`.
- [ ] Define schedule execution history linkage without fake alerts.
- [ ] Define manual pause/resume behavior and audit requirements.
- [ ] Define bounded concurrency rules, defaulting to one active run per schedule.
- [ ] Define interaction with approval-gated playbooks.
- [ ] Define interaction with `permanently_failed` executions.
- [ ] Define interaction with circuit breaker state and manual circuit breaker controls.
- [ ] Define interaction with retry metadata and attempt limits.
- [ ] Define interaction with stale execution detection.
- [ ] Define scheduler startup/restart fail-closed behavior.
- [ ] Define read-only metrics visibility.
- [ ] Define audit logging expectations.
- [ ] Document risks and stop conditions before implementation.

## Future implementation test requirements
- [ ] Test disabled schedules do not create executions.
- [ ] Test paused schedules do not create executions.
- [ ] Test enabled schedules create at most one eligible simulation execution.
- [ ] Test active scheduled executions block overlapping runs.
- [ ] Test missed-run default behavior skips or records without replaying all missed intervals.
- [ ] Test bounded `run_once` catch-up creates at most one execution when explicitly configured.
- [ ] Test scheduler startup does not execute hidden work.
- [ ] Test restart ambiguity fails closed.
- [ ] Test approval-gated scheduled executions pause at `awaiting_approval`.
- [ ] Test approval backlog blocks overlapping scheduled runs.
- [ ] Test `permanently_failed` executions are not retried automatically.
- [ ] Test open circuit breaker state is respected and visible.
- [ ] Test stale running scheduled executions block new scheduled runs.
- [ ] Test metrics endpoints are read-only.
- [ ] Test audit events for schedule create/update/enable/disable/pause/resume and scheduled execution creation.
- [ ] Test no network calls are made.
- [ ] Test no subprocess calls are made.
- [ ] Test no `blocked_ips` mutation occurs.
- [ ] Test no SOAR queue redesign or queue enqueueing from schedule design paths.
- [ ] Test no ingest, detection, or correlation behavior changes.

## Verification expectations for future implementation
When a future implementation change is created, run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_playbook_routes.py tests/test_playbook_step_executor.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_metrics_routes.py tests/test_integration_routes.py tests/test_circuit_breaker.py -v
python3 -m pytest tests/test_approval_routes.py tests/test_approval_store.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

Add focused scheduled-playbook tests when implementation exists.

## Out-of-scope guardrails
- [ ] Do not implement a daemon.
- [ ] Do not implement APScheduler, Celery, Redis, RQ, cron, or systemd worker behavior.
- [ ] Do not add background autonomous retries.
- [ ] Do not add real integrations.
- [ ] Do not enable `INTEGRATION_MODE=real`.
- [ ] Do not mutate firewall, blocklist, or `blocked_ips`.
- [ ] Do not redesign the queue.
- [ ] Do not implement execution behavior in this design change.
- [ ] Do not implement frontend behavior in this design change.
- [ ] Do not change ingest, detection, or correlation internals.

## Stop and rollback conditions for future implementation
- Stop if scheduler restart behavior cannot fail closed.
- Stop if missed-run replay cannot be bounded.
- Stop if schedule state cannot be made operator-visible.
- Stop if overlapping execution prevention requires broad executor rewrites.
- Stop if approval-gated scheduled runs would bypass approval controls.
- Stop if circuit breaker handling would auto-reset or bypass breaker state.
- Stop if retry behavior would create replay storms.
- Stop if implementation needs real integrations, external APIs, queue redesign, or protected ingest/detection/correlation changes.
