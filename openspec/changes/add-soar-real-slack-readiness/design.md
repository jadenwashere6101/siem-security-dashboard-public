# Design: SOAR Real Slack Readiness

## Design boundary
Real integration readiness is limited to Slack notification delivery. Every other adapter remains simulation-only, including firewall, email, webhook, and any future PagerDuty adapter.

The first real Slack path should reuse the existing adapter-backed playbook execution boundary. It must not change playbook orchestration, executor claiming, queue behavior, approval gates, ingest, detection, correlation, scheduled playbook metadata, or incident timeline behavior.

## Configuration model
Default behavior remains simulation.

Recommended environment controls:
- `INTEGRATION_MODE=simulation` remains the default and forces every adapter, including Slack, to simulate.
- `INTEGRATION_MODE=real` may be accepted only for Slack readiness and only when all staging guardrails pass.
- `SOAR_ENV=staging` or an equivalent existing environment marker must be required before Slack can use real mode.
- `SLACK_WEBHOOK_URL` must be present only in the runtime environment and must never be stored in the database.
- Optional `SLACK_TIMEOUT_SECONDS` may bound outbound request time, with a conservative default such as `3`.
- Optional `SLACK_CHANNEL_LABEL` may be a display label only; the webhook URL controls the real destination and must not be shown.

Fail closed when:
- `INTEGRATION_MODE` is missing, invalid, or not explicitly real.
- The environment is local, development, test, CI, or unknown.
- `SLACK_WEBHOOK_URL` is missing, empty, malformed, or points to an unsupported scheme.
- Slack circuit breaker state is `open`, invalid, unknown, or ambiguous after restart.
- Timeout configuration is invalid.

## Slack-only real mode
Real mode must be evaluated per adapter. Even if `INTEGRATION_MODE=real` is present, only Slack may become real-ready. Firewall, email, webhook, and PagerDuty must continue returning simulation-only metadata.

Status metadata should distinguish:
- `mode`: current effective adapter mode, such as `simulation` or `real`.
- `real_mode_configured`: whether all Slack real-mode configuration is present.
- `real_mode_allowed`: whether guardrails allow real Slack delivery in this environment.
- `real_mode_status`: safe human-readable readiness state.
- `webhook_configured`: boolean only, never the URL.

## Automated test network guarantees
Automated tests must never send Slack traffic.

Required guarantees:
- Test and CI environment forces Slack into simulation or fail-closed mode even if a webhook-like env var is present.
- Real Slack delivery tests must mock the outbound HTTP function or session.
- Tests should patch low-level network clients so any unmocked outbound call fails the test.
- No test should require real Slack secrets.
- No snapshot, log assertion, or failure output may contain webhook URL values.

Suggested tests:
- `INTEGRATION_MODE=simulation` never calls network.
- `INTEGRATION_MODE=real` in test/dev fails closed before network.
- Missing webhook fails closed before network.
- Staging guardrails plus mocked webhook call produce a Slack success result.
- Mocked timeout produces timeout metadata and no retry loop.
- Mocked Slack HTTP 4xx is non-transient and not retry eligible.
- Mocked Slack HTTP 5xx or timeout is transient, retry eligible only within existing bounded limits, and updates circuit breaker metadata.

## Timeout behavior
Real Slack sends must use a bounded timeout. Timeout failures should return structured adapter metadata:
- `success: false`
- `simulated: false`
- `executed: false` when the request is not known to have completed
- `failure_classification: timeout`
- `retry_eligible: true`
- `timeout_seconds`
- `elapsed_ms` when safely available

Timeouts must not create background retries, daemon behavior, queued replay, or hidden recovery.

## Circuit breaker interaction
Slack real mode must check circuit breaker state before any outbound call.

Behavior:
- `closed`: Slack may attempt the mocked or real staging send if all other guardrails pass.
- `open`: fail closed before network and return `failure_classification: circuit_open`.
- `half_open`: allow at most one explicit/manual probe path if current circuit breaker controls support it; otherwise fail closed until operator action.
- Unknown or invalid state: fail closed.

Slack failures should update breaker metadata using existing circuit breaker semantics:
- transient failures such as timeout or Slack 5xx may increment consecutive failures.
- non-transient failures such as malformed payload or missing webhook should fail closed and should not loop.
- breaker-open results must be visible in adapter output, execution `steps_log`, and integration status where already exposed.

## Retry eligibility metadata
Slack adapter results should include retry metadata without starting retries:
- `retry_eligible`
- `failure_classification`
- `retry_after_seconds` when Slack returns a safe rate-limit hint
- `max_adapter_attempts`
- `circuit_state`

Retry eligibility must be advisory only. Existing playbook reliability limits, approval gates, permanently failed state, manual controls, and circuit breaker state remain authoritative. The stricter bound wins.

## Safe payload formatting
Slack payloads must be allowlisted and bounded.

Allowed content:
- playbook id
- execution id
- alert id or incident id when present
- severity/status summary
- adapter action name
- safe timestamp
- short human-readable summary
- safe links only if the application already has trusted internal URL construction

Forbidden content:
- webhook URL or any secret-like value
- raw playbook step params
- raw adapter params
- raw event payloads
- credentials, tokens, headers, cookies, authorization values
- unbounded exception strings or provider responses
- protected target details beyond already-safe display fields

Payloads should have a maximum length and should degrade to a concise safe fallback when fields are missing or too large.

## Secret redaction
Redaction must apply to:
- application logs
- audit log details
- `steps_log`
- integration status APIs
- test failure output
- frontend-visible status fields

Rules:
- Never log or store `SLACK_WEBHOOK_URL`.
- Never include request headers.
- Never include raw Slack response bodies if they may echo request metadata.
- If config metadata is needed, expose booleans such as `webhook_configured: true`.
- Redaction should happen before constructing adapter results, not only at route serialization.

## Audit and logging expectations
Audit/logging should record operationally useful metadata without secrets:
- adapter: `slack`
- action: `send_message`
- effective mode
- playbook execution id
- playbook id
- alert id or incident id when present
- success/failure
- failure classification
- circuit breaker state
- timeout metadata
- redacted config state such as webhook configured/missing

Do not add audit records that imply remediation occurred. Slack delivery is notification-only.

## Manual staging test plan
Manual staging validation should require:
- staging environment marker set.
- `INTEGRATION_MODE=real`.
- `SLACK_WEBHOOK_URL` configured through environment or secret manager, not database.
- Slack circuit breaker in `closed` state.
- a low-risk test playbook using only `notify_slack`.
- operator confirmation that the playbook is safe and notification-only.

Manual test steps:
- Verify integration status reports Slack real-mode readiness without revealing the webhook.
- Trigger or create a controlled test execution.
- Run the existing manual executor once, if that remains the execution path.
- Confirm one Slack message appears in the staging channel.
- Confirm `steps_log`, audit output, and adapter metadata omit secrets.
- Confirm duplicate retry behavior is bounded and visible.
- Force Slack failure with a mocked or disabled webhook in staging and verify fail-closed behavior.

## Rollback plan
Rollback must be immediate and operationally simple:
- Set `INTEGRATION_MODE=simulation`.
- Remove or unset `SLACK_WEBHOOK_URL`.
- Force-open the Slack circuit breaker if manual controls are available.
- Redeploy or restart only if runtime config requires it.
- Verify integration status reports Slack simulation/fail-closed mode.
- Verify playbook executions with `notify_slack` return simulated adapter output.

Rollback must not require schema changes, data migration, queue redesign, daemon changes, or frontend changes.

## Safety boundaries
- Default remains simulation.
- Real Slack is explicitly configured and staging-controlled only.
- Tests must never hit the network.
- Missing webhook fails closed.
- Payloads must not include secrets or raw unsafe params.
- Firewall remains simulation-only.
- No real email, webhook, PagerDuty, or firewall execution.
- No daemon or scheduler.
- No automatic autonomous retries.
- No background replay engine.
- No Redis/Celery migration.
- No ingest, detection, or correlation changes.
- No storing secrets in the database.

## Risks and stop conditions
- Stop if implementation cannot prevent real Slack sends in local/dev/test/CI.
- Stop if webhook URLs can appear in logs, UI, status APIs, audit records, or test output.
- Stop if real mode becomes global instead of Slack-only.
- Stop if Slack retry behavior can send unbounded duplicate messages.
- Stop if circuit breaker open/unknown state can still call Slack.
- Stop if timeout handling requires daemon, scheduler, queue redesign, or background retry behavior.
- Stop if implementation requires backend schema changes for secrets.
- Stop if firewall, email, webhook, PagerDuty, ingest, detection, or correlation behavior must change.
