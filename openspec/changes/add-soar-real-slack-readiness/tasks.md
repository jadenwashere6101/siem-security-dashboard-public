# Tasks: SOAR Real Slack Readiness

## Implementation planning
- [ ] Inspect current simulation Slack adapter result shape and supported action mapping.
- [ ] Inspect integration registry/config handling for `INTEGRATION_MODE`.
- [ ] Inspect circuit breaker enforcement around adapter-backed playbook execution.
- [ ] Decide the exact staging environment marker used to allow Slack real mode.
- [ ] Define Slack webhook env var validation without exposing the value.
- [ ] Define safe Slack payload allowlist and length bounds.
- [ ] Define secret redaction helper or reuse an existing redaction helper if present.
- [ ] Define Slack timeout default and config validation.
- [ ] Define Slack transient/non-transient failure mapping.
- [ ] Define Slack retry eligibility metadata without automatic retries.
- [ ] Define status API readiness fields for Slack only.
- [ ] Confirm all non-Slack adapters remain simulation-only even when Slack real mode is configured.

## Future implementation slice, if approved
- [ ] Add Slack real-mode adapter code behind explicit staging guardrails.
- [ ] Add registry/config guardrails so real mode is adapter-specific and Slack-only.
- [ ] Add fail-closed validation for missing or invalid `SLACK_WEBHOOK_URL`.
- [ ] Add bounded timeout handling for Slack HTTP calls.
- [ ] Add safe payload formatter for Slack notifications.
- [ ] Add secret redaction for logs, adapter results, audit details, status output, and tests.
- [ ] Integrate Slack real-mode attempts with existing circuit breaker checks.
- [ ] Add Slack retry eligibility metadata to adapter results.
- [ ] Extend integration status to show Slack readiness without exposing secrets.
- [ ] Preserve existing playbook execution, approval gate, reliability, metrics, and timeline behavior.
- [ ] Confirm firewall, email, webhook, and PagerDuty remain simulation-only.

## Required backend tests
- [ ] Test default configuration keeps Slack in simulation mode.
- [ ] Test `INTEGRATION_MODE=real` in local/dev/test/CI fails closed before any network call.
- [ ] Test missing `SLACK_WEBHOOK_URL` fails closed before any network call.
- [ ] Test invalid webhook URL fails closed and redacts the provided value.
- [ ] Test staging-allowed Slack real mode uses a mocked outbound call only.
- [ ] Test automated tests fail if an unmocked network call is attempted.
- [ ] Test Slack timeout returns timeout metadata and does not start retries.
- [ ] Test Slack 5xx maps to transient retry-eligible metadata within bounded limits.
- [ ] Test Slack 4xx or malformed payload maps to non-transient non-retryable metadata.
- [ ] Test open or invalid circuit breaker state blocks Slack before network.
- [ ] Test half-open behavior is bounded and explicit if supported by current controls.
- [ ] Test Slack adapter result redacts webhook URL, headers, tokens, and raw unsafe params.
- [ ] Test `steps_log` stores safe Slack metadata only.
- [ ] Test audit/log details contain safe operational metadata only.
- [ ] Test integration status shows Slack readiness booleans and never the webhook.
- [ ] Test firewall adapter remains simulation-only.
- [ ] Test email adapter remains simulation-only.
- [ ] Test webhook adapter remains simulation-only.
- [ ] Test no PagerDuty behavior is added.
- [ ] Test no `blocked_ips` mutation occurs.
- [ ] Test no subprocess calls occur.
- [ ] Test no queue, scheduler, daemon, ingest, detection, or correlation behavior changes.

## Manual staging test plan
- [ ] Configure staging environment marker.
- [ ] Set `INTEGRATION_MODE=real`.
- [ ] Configure `SLACK_WEBHOOK_URL` through environment or secret manager only.
- [ ] Verify integration status reports Slack real-mode readiness without showing the webhook.
- [ ] Ensure Slack circuit breaker is `closed`.
- [ ] Run a controlled notification-only `notify_slack` playbook execution.
- [ ] Confirm exactly one Slack message arrives in the staging channel.
- [ ] Confirm execution `steps_log` and audit/log output contain no webhook URL or secrets.
- [ ] Simulate Slack failure or timeout and confirm fail-closed behavior.
- [ ] Confirm rollback to simulation by unsetting real-mode config.

## Verification commands
When implementation is approved, run focused and regression tests such as:

```bash
python3 -m py_compile integrations/*.py routes/*.py engines/*.py core/*.py
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py -v
python3 -m pytest tests/test_playbook_metrics_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If new Slack-specific test files are added, include them in the focused integration adapter test command.

## Stop and rollback conditions
- [ ] Stop if implementation requires real network calls in automated tests.
- [ ] Stop if implementation can enable Slack real mode outside staging.
- [ ] Stop if webhook URL or secrets can appear in logs, UI, audit records, status APIs, or test output.
- [ ] Stop if real mode becomes global for non-Slack adapters.
- [ ] Stop if retry behavior can send unbounded duplicate Slack messages.
- [ ] Stop if circuit breaker open/unknown state can still call Slack.
- [ ] Stop if implementation requires daemon, scheduler, queue redesign, Redis/Celery migration, or background replay.
- [ ] Stop if implementation changes ingest, detection, or correlation.
- [ ] Roll back by setting `INTEGRATION_MODE=simulation`, unsetting `SLACK_WEBHOOK_URL`, and confirming Slack returns to simulation/fail-closed status.
