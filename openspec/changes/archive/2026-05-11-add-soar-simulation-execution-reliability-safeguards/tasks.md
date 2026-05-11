# Tasks: SOAR Simulation Execution Reliability Safeguards

## Implementation steps
- [ ] Inspect current `playbook_executions` schema, execution store helpers, and execution control routes.
- [ ] Decide whether attempt metadata can be safely represented with existing fields or requires additive schema columns.
- [ ] Define allowed execution statuses, including whether to add `permanently_failed`.
- [ ] Add attempt metadata helpers without changing ingest, detection, correlation, SOAR queue, or adapter behavior.
- [ ] Enforce `max_attempts` before simulation step execution starts.
- [ ] Expose `attempt_count`, derived `retry_count`, `max_attempts`, and remaining-attempt visibility in execution read APIs.
- [ ] Add dead-letter style terminal handling for exhausted attempts.
- [ ] Add stale `running` detection using timestamps and a conservative threshold.
- [ ] Add timeout metadata only; do not add timers, jobs, or background mutation.
- [ ] Add metrics visibility for retries, failures, stale-running executions, and permanently failed executions.
- [ ] Preserve immutable retry history by creating new retry records only when allowed.
- [ ] Ensure approval-gated executions cannot bypass approval decisions through retry or stale handling.
- [ ] Confirm no frontend, real integration, SOAR queue, ingest, detection, or correlation files changed unless explicitly required by route registration patterns.

## Exact backend test requirements
- [ ] Test attempt count starts at the expected default for newly scheduled executions.
- [ ] Test attempt count increments when the simulation executor claims or starts an execution attempt.
- [ ] Test `retry_count` visibility is correct after retry history exists.
- [ ] Test `max_attempts` blocks execution before any step or adapter simulation runs.
- [ ] Test exhausted attempts transition to `permanently_failed` or the chosen dead-letter style terminal state.
- [ ] Test `permanently_failed` executions are not eligible for ordinary retry or resume.
- [ ] Test retry preserves immutable history and does not mutate prior terminal execution rows.
- [ ] Test completed successful steps are not re-run during safe resume behavior.
- [ ] Test approval-gated executions do not bypass pending, denied, or expired approval state.
- [ ] Test stale `running` executions are reported without automatic resume.
- [ ] Test stale handling, if an explicit action is added, is super-admin only and does not execute steps.
- [ ] Test timeout metadata is visible but does not cause automatic state transition.
- [ ] Test metrics include retry, failure, stale-running, and permanently failed counts.
- [ ] Test no `blocked_ips` rows are written.
- [ ] Test no network calls are made by monkeypatching network primitives to fail.
- [ ] Test no subprocess calls are made by monkeypatching subprocess entry points to fail.
- [ ] Test no SOAR queue rows are enqueued by playbook reliability safeguards.
- [ ] Run detection, ingest, and correlation regression tests to prove protected internals remain unchanged.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_approval_routes.py tests/test_approval_store.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If focused reliability or metrics tests are created with new filenames, include those files in the playbook test command.

## Stop and rollback conditions
- Stop if implementation requires daemon workers.
- Stop if implementation requires automatic background retries.
- Stop if implementation requires cron, systemd, Celery, APScheduler, or scheduler integration.
- Stop if implementation requires real integrations, real remediation, secrets, network calls, or subprocess execution.
- Stop if implementation mutates `blocked_ips`.
- Stop if implementation redesigns the SOAR queue or enqueues queue work from playbook reliability paths.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if implementation makes execution autonomous.
- Stop if implementation rewrites immutable execution history instead of appending safe retry history.
