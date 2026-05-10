# Design: SOAR Real Teams Readiness

## Design boundary
Real Teams readiness is limited to Microsoft Teams notification delivery. It must not introduce real firewall, email, generic webhook, PagerDuty, queue, executor, scheduler, daemon, ingest, detection, or correlation behavior.

Teams should follow the Slack guardrail pattern but remain separately configured. A Slack webhook must never satisfy Teams readiness, and a Teams webhook must never satisfy Slack readiness.

## Configuration model
Default behavior remains simulation.

Recommended Teams controls:
- `INTEGRATION_MODE=simulation` remains the default and forces Teams to simulate.
- `INTEGRATION_MODE=real` may be accepted for Teams only when all Teams staging guardrails pass.
- `SOAR_ENV=staging` or an equivalent existing environment marker must be required before Teams can use real mode.
- `SOAR_REAL_TEAMS_ENABLED=true` should be required as an explicit Teams allow flag.
- `TEAMS_WEBHOOK_URL` must be present only in runtime environment or approved secret management.
- Optional `TEAMS_TIMEOUT_SECONDS` may bound outbound request time, with a conservative default such as `3`.
- Optional `TEAMS_CHANNEL_LABEL` may be a safe display label only; it must not include or derive from the webhook URL.

Fail closed when:
- `INTEGRATION_MODE` is missing, invalid, or not explicitly `real`.
- `SOAR_ENV` is not staging.
- `SOAR_REAL_TEAMS_ENABLED` is missing or not true.
- `TEAMS_WEBHOOK_URL` is missing, empty, malformed, or appears to be a Slack/webhook/provider URL from the wrong integration.
- Timeout config is invalid.
- Teams circuit breaker state is `open`, invalid, unknown, or ambiguous after restart.

## Teams-only real mode
Real mode must be adapter-specific.

If `INTEGRATION_MODE=real` is present:
- Teams may become real-ready only when Teams-specific guardrails pass.
- Slack may become real-ready only when Slack-specific guardrails pass.
- Firewall, email, generic webhook, PagerDuty, and remediation adapters remain simulation-only.

Teams status metadata should expose safe booleans only:
- `teams_configured`
- `real_mode_allowed`
- `real_mode_ready`
- `webhook_configured`
- `real_mode_status`

The status API must never return `TEAMS_WEBHOOK_URL`, host path fragments, request headers, tokens, or raw provider errors.

## Avoiding Slack/Teams config confusion
Teams readiness must be isolated from Slack readiness:
- `SLACK_WEBHOOK_URL` must not enable Teams.
- `TEAMS_WEBHOOK_URL` must not enable Slack.
- `SOAR_REAL_SLACK_ENABLED` must not enable Teams.
- `SOAR_REAL_TEAMS_ENABLED` must not enable Slack.
- Readiness output should use adapter-qualified fields or nested adapter metadata to avoid ambiguous top-level interpretation.
- Tests should set both Slack and Teams env vars in conflicting combinations and prove the wrong provider remains disabled.

## Automated no-network guarantee
Automated tests must never send Teams traffic.

Required guarantees:
- Test and CI environments force Teams into simulation or fail-closed mode even if a webhook-like env var is present.
- Real Teams delivery tests must mock the outbound HTTP function/session.
- Tests should patch low-level HTTP/network clients so any unmocked outbound call fails.
- No test should require a real Teams secret.
- No test output, snapshot, log assertion, or route response may contain the Teams webhook value.

Suggested tests:
- Default config keeps Teams simulation-only.
- `INTEGRATION_MODE=real` in local/dev/test/CI fails closed before network.
- Missing `TEAMS_WEBHOOK_URL` fails closed before network.
- Invalid Teams webhook fails closed and redacts the provided value.
- Staging-allowed Teams real mode uses a mocked outbound call only.
- Mocked timeout returns timeout metadata and does not create retries.
- Mocked Teams 4xx maps to non-transient, non-retryable metadata.
- Mocked Teams 5xx or timeout maps to transient retry-eligible metadata within bounded limits.
- Open or invalid Teams circuit breaker blocks before network.
- Slack env vars cannot satisfy Teams readiness, and Teams env vars cannot satisfy Slack readiness.

## Timeout behavior
Real Teams sends must use bounded timeout behavior.

Timeout result metadata should include:
- `success: false`
- `simulated: false`
- `executed: false` when delivery is not confirmed
- `failure_classification: timeout`
- `retry_eligible: true`
- `timeout_seconds`
- `elapsed_ms` when safely available

Timeouts must not create background retries, daemon behavior, queue replay, autonomous execution, or hidden recovery.

## Circuit breaker interaction
Teams real mode must check the Teams circuit breaker before any outbound call.

Behavior:
- `closed`: Teams may attempt the mocked or real staging send only if all guardrails pass.
- `open`: fail closed before network with `failure_classification: circuit_open`.
- `half_open`: allow at most one explicit/manual probe path if existing controls support it; otherwise fail closed until operator action.
- invalid/unknown: fail closed.

Teams failures should update breaker metadata consistently with Slack and existing adapter semantics:
- transient failures such as timeout, 429, or Teams 5xx may increment consecutive failures.
- non-transient failures such as missing webhook, malformed payload, invalid config, or Teams 4xx should not loop.
- breaker state must be visible in adapter output, execution `steps_log`, and integration status where already exposed.

## Retry eligibility metadata
Teams adapter results should expose advisory retry metadata:
- `retry_eligible`
- `failure_classification`
- `retry_after_seconds` when safely available from a provider rate-limit hint
- `max_adapter_attempts`
- `circuit_state`

This metadata must not start retries. Existing bounded playbook reliability controls, manual retry controls, approval gates, permanently failed state, and circuit breaker state remain authoritative.

## Safe Teams payload formatting
Teams payloads must be allowlisted and bounded.

Allowed content:
- playbook id
- execution id
- alert id or incident id when present
- status/severity summary
- adapter action name
- safe timestamp
- short non-sensitive summary
- safe internal link only if existing trusted internal URL construction exists

Forbidden content:
- `TEAMS_WEBHOOK_URL`
- `SLACK_WEBHOOK_URL`
- request headers
- tokens, cookies, authorization values, credentials, or secrets
- raw playbook step params
- raw adapter params
- raw event payloads
- raw provider response bodies
- unbounded exception strings
- protected target details beyond already-safe display fields

Payload length must be bounded. Missing fields should degrade to a concise safe fallback.

## Secret redaction
Redaction must apply to:
- application logs
- audit details
- adapter results
- `steps_log`
- integration status APIs
- tests and test failure output
- any future frontend-visible status fields

Rules:
- Never log or store `TEAMS_WEBHOOK_URL`.
- Never include Teams request headers.
- Never include raw Teams response bodies when they may include request metadata.
- Expose booleans such as `teams_configured` and `webhook_configured`, never the URL.
- Redact before constructing results and before serializing route/status responses.

## Audit and logging expectations
Audit/logging should record safe metadata:
- adapter: `teams`
- action: Teams notification action name
- effective mode
- playbook execution id
- playbook id
- alert id or incident id when present
- success/failure
- failure classification
- circuit breaker state
- timeout metadata
- redacted config state such as webhook configured/missing

Do not log raw payloads, headers, webhook URLs, or provider response bodies. Do not imply remediation occurred; Teams is notification-only.

## Manual staging test plan
Manual validation should require:
- staging environment marker set.
- `INTEGRATION_MODE=real`.
- `SOAR_REAL_TEAMS_ENABLED=true`.
- `TEAMS_WEBHOOK_URL` configured through environment/secret manager only.
- Teams circuit breaker in `closed` state.
- one low-risk test playbook using only the Teams notification action.
- operator approval for a single controlled staging message.

Manual test steps:
- Verify integration status reports Teams real-mode readiness without revealing the webhook.
- Verify Slack status and behavior are unchanged.
- Trigger or create a controlled test execution.
- Run exactly one manual executor invocation, if that remains the execution path.
- Confirm one Teams message appears in the staging Teams destination.
- Confirm `steps_log`, audit/log output, and adapter metadata omit secrets.
- Confirm duplicate retry behavior is bounded and visible.
- Roll back to simulation immediately after the test.

## Rollback plan
Rollback must be simple:
- Set `INTEGRATION_MODE=simulation` or remove it.
- Remove or unset `TEAMS_WEBHOOK_URL`.
- Set `SOAR_REAL_TEAMS_ENABLED=false` or remove it.
- Force-open the Teams circuit breaker if unexpected behavior occurs and controls are available.
- Restart/reload only if runtime env refresh requires it.
- Verify integration status reports Teams simulation/fail-closed mode.
- Verify Slack readiness and behavior did not regress.
- Verify firewall, email, generic webhook, and PagerDuty remain simulation-only.

Rollback must not require schema changes, queue changes, data migration, daemon changes, scheduler changes, or frontend changes.

## Safety boundaries
- Default remains simulation.
- Real Teams only when explicitly configured.
- Missing Teams webhook fails closed.
- Teams webhook URL must never be logged or returned.
- Real mode is staging-controlled.
- Firewall remains simulation-only.
- Slack behavior must not regress.
- No real Slack changes.
- No real email, generic webhook, PagerDuty, firewall, blocklist, subprocess, queue, daemon, scheduler, ingest, detection, or correlation changes.

## Risks and stop conditions
- Stop if implementation would enable Teams real mode locally/dev/test/CI.
- Stop if `TEAMS_WEBHOOK_URL` can leak in logs, status, UI, audit, tests, or prompts.
- Stop if Slack and Teams environment variables can enable the wrong provider.
- Stop if retry behavior can send unbounded duplicate Teams messages.
- Stop if circuit breaker open/unknown state can still call Teams.
- Stop if timeout handling needs daemon, scheduler, queue redesign, or background replay.
- Stop if implementation requires schema changes for secrets.
- Stop if Slack behavior regresses.
- Stop if any non-notification integration must become real.
