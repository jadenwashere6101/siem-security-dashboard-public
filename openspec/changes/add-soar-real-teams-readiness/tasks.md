# Tasks: SOAR Real Teams Readiness

## Implementation planning
- [ ] Inspect current integration adapter registry and simulation adapter result shape.
- [ ] Decide whether Teams should be a new adapter or an extension of the notification adapter model.
- [ ] Define Teams adapter action names without conflicting with Slack, email, or generic webhook actions.
- [ ] Define Teams-specific env vars: `TEAMS_WEBHOOK_URL`, `SOAR_REAL_TEAMS_ENABLED`, and optional `TEAMS_TIMEOUT_SECONDS`.
- [ ] Define Teams staging marker behavior using `SOAR_ENV=staging`.
- [ ] Define Teams webhook validation without exposing the value.
- [ ] Define safe Teams payload allowlist and length bounds.
- [ ] Define secret redaction for Teams webhook values and provider metadata.
- [ ] Define Teams transient/non-transient failure mapping.
- [ ] Define Teams retry eligibility metadata without automatic retries.
- [ ] Define Teams status/readiness fields without leaking secrets.
- [ ] Define tests proving Slack and Teams config cannot satisfy each other.
- [ ] Confirm firewall, email, generic webhook, PagerDuty, and remediation adapters remain simulation-only.

## Future implementation slice, if approved
- [ ] Add Teams simulation adapter or Teams notification adapter entry.
- [ ] Add Teams real-mode code behind explicit staging guardrails.
- [ ] Add registry/config guardrails so real mode is adapter-specific and Teams-only.
- [ ] Add fail-closed validation for missing or invalid `TEAMS_WEBHOOK_URL`.
- [ ] Add bounded timeout handling for Teams HTTP calls.
- [ ] Add safe Teams payload formatter.
- [ ] Add secret redaction for logs, adapter results, audit details, status output, and tests.
- [ ] Integrate Teams real-mode attempts with existing circuit breaker checks.
- [ ] Add Teams retry eligibility metadata to adapter results.
- [ ] Extend integration status to show Teams readiness without exposing secrets.
- [ ] Preserve existing playbook execution, approval gate, reliability, metrics, and timeline behavior.
- [ ] Confirm Slack behavior does not regress.
- [ ] Confirm firewall, email, generic webhook, and PagerDuty remain simulation-only.

## Required backend tests
- [ ] Test default configuration keeps Teams simulation-only.
- [ ] Test `INTEGRATION_MODE=real` in local/dev/test/CI fails closed before any network call.
- [ ] Test missing `TEAMS_WEBHOOK_URL` fails closed before any network call.
- [ ] Test invalid Teams webhook fails closed and redacts the provided value.
- [ ] Test staging-allowed Teams real mode uses a mocked outbound call only.
- [ ] Test automated tests fail if an unmocked network call is attempted.
- [ ] Test Teams timeout returns timeout metadata and does not start retries.
- [ ] Test Teams 5xx/429 maps to transient retry-eligible metadata within bounded limits.
- [ ] Test Teams 4xx or malformed payload maps to non-transient non-retryable metadata.
- [ ] Test open or invalid Teams circuit breaker blocks before network.
- [ ] Test half-open behavior is bounded and explicit if supported by current controls.
- [ ] Test Teams adapter result redacts webhook URL, headers, tokens, and raw unsafe params.
- [ ] Test `steps_log` stores safe Teams metadata only.
- [ ] Test audit/log details contain safe operational metadata only.
- [ ] Test integration status shows Teams readiness booleans and never the webhook.
- [ ] Test `SLACK_WEBHOOK_URL` does not enable Teams.
- [ ] Test `TEAMS_WEBHOOK_URL` does not enable Slack.
- [ ] Test `SOAR_REAL_SLACK_ENABLED` does not enable Teams.
- [ ] Test `SOAR_REAL_TEAMS_ENABLED` does not enable Slack.
- [ ] Test Slack readiness and Slack guarded behavior remain unchanged.
- [ ] Test firewall adapter remains simulation-only.
- [ ] Test email adapter remains simulation-only.
- [ ] Test generic webhook adapter remains simulation-only.
- [ ] Test no PagerDuty behavior is added.
- [ ] Test no `blocked_ips` mutation occurs.
- [ ] Test no subprocess calls occur.
- [ ] Test no queue, scheduler, daemon, ingest, detection, or correlation behavior changes.

## Manual staging test plan
- [ ] Configure staging environment marker.
- [ ] Set `INTEGRATION_MODE=real`.
- [ ] Set `SOAR_REAL_TEAMS_ENABLED=true`.
- [ ] Configure `TEAMS_WEBHOOK_URL` through environment or secret manager only.
- [ ] Verify integration status reports Teams real-mode readiness without showing the webhook.
- [ ] Verify Slack readiness/behavior is unchanged.
- [ ] Ensure Teams circuit breaker is `closed`.
- [ ] Run a controlled notification-only Teams playbook execution.
- [ ] Confirm exactly one Teams message arrives in the staging destination.
- [ ] Confirm execution `steps_log` and audit/log output contain no webhook URL or secrets.
- [ ] Simulate Teams failure or timeout and confirm fail-closed behavior.
- [ ] Confirm rollback to simulation by unsetting real-mode config.

## Verification commands
When implementation is approved, run focused and regression tests such as:

```bash
python3 -m py_compile integrations/base_integration.py integrations/integration_registry.py integrations/*.py
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py -v
python3 -m pytest tests/test_playbook_metrics_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
git status --short
```

If new Teams-specific test files are added, include them in the focused integration adapter test command.

## Stop and rollback conditions
- [ ] Stop if implementation requires real network calls in automated tests.
- [ ] Stop if Teams real mode can be enabled outside staging.
- [ ] Stop if Teams webhook URL or secrets can appear in logs, UI, audit records, status APIs, tests, or prompts.
- [ ] Stop if Slack and Teams env vars can enable the wrong provider.
- [ ] Stop if Slack behavior regresses.
- [ ] Stop if real mode becomes global for non-Teams adapters.
- [ ] Stop if retry behavior can send unbounded duplicate Teams messages.
- [ ] Stop if circuit breaker open/unknown state can still call Teams.
- [ ] Stop if implementation requires daemon, scheduler, queue redesign, Redis/Celery migration, or background replay.
- [ ] Stop if implementation changes ingest, detection, or correlation.
- [ ] Roll back by setting `INTEGRATION_MODE=simulation`, unsetting `TEAMS_WEBHOOK_URL`, disabling `SOAR_REAL_TEAMS_ENABLED`, and confirming Teams returns to simulation/fail-closed status.
