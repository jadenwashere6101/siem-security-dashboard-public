# Design: SOAR Real Teams Smoke-Test Checklist

## Safety posture
The smoke test is manual, staging-only, and limited to one controlled Teams notification. It must not be run from local development, automated tests, CI, production, or any environment where the Teams destination is unclear.

The checklist is documentation only. It does not add code, send a message, create a playbook, modify schema, alter executor behavior, change queues, or touch ingest/detection/correlation.

## Required environment variables
The staging runtime must have exactly these Teams real-mode controls:

```text
INTEGRATION_MODE=real
SOAR_ENV=staging
SOAR_REAL_TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=<set in runtime secret/env only>
```

Rules:
- `TEAMS_WEBHOOK_URL` must be injected through the staging runtime environment or approved secret manager only.
- The webhook URL must never be printed, logged, committed, stored in the database, included in docs, copied into examples, pasted into prompts, or copied into tickets.
- Operators may record `TEAMS_WEBHOOK_URL configured: yes/no`, never the value.
- If any required env var is missing, ambiguous, or configured outside staging, stop and keep simulation mode.
- `SLACK_WEBHOOK_URL` and `SOAR_REAL_SLACK_ENABLED` must not satisfy Teams readiness.

## Staging-only validation
Before any Teams real-mode test, operators must positively identify staging:

1. Confirm host, deployment target, database, app URL, and deployed revision are staging.
2. Confirm the Teams destination is a staging/test Teams channel or equivalent non-production destination.
3. Confirm no production Teams channel, production workflow, or production alert route is attached to the webhook.
4. Confirm the operator and approver understand that exactly one Teams message is authorized.
5. Stop if environment identity, destination ownership, or approval status is ambiguous.

## Preflight checks
Before enabling or using real Teams:

1. Confirm default simulation behavior.
   - With `INTEGRATION_MODE=simulation` or unset, verify integration status reports simulation.
   - Confirm Teams adapter status does not expose a webhook URL.
   - Confirm Slack remains independent.
   - Confirm firewall, email, generic webhook, and PagerDuty are not real-enabled.

2. Confirm automated tests remain no-network.
   - Use only mocked outbound Teams tests.
   - Do not run tests with a real `TEAMS_WEBHOOK_URL` in the test environment.
   - Confirm tests patch or block the outbound HTTP path.

3. Confirm circuit breaker state.
   - Teams circuit breaker must be `closed`.
   - If state is `open`, `half_open`, invalid, unknown, or ambiguous after restart, stop and resolve explicitly before any send.
   - Do not use half-open as the first real Teams smoke-test state.

4. Confirm playbook/test input safety.
   - The controlled test must use only a low-risk Teams notification action.
   - No `block_ip`, firewall, email, Slack, generic webhook, PagerDuty, queue replay, scheduler, daemon, autonomous retry, or remediation behavior is allowed.
   - Payload content must be short and non-sensitive.

5. Confirm duplicate-message prevention.
   - Confirm no active duplicate execution exists for the same test case.
   - Confirm only one operator will run the test.
   - Confirm only one terminal/session/path will invoke the executor.
   - Confirm retry loops, daemons, schedulers, and repeated manual invocations are not active.

6. Confirm approval.
   - A super_admin/operator must explicitly approve the one controlled test.
   - Record who approved, when, and the staging target, without recording secrets.

## Controlled manual test path
The smoke test should use one controlled staging execution path:

1. Prepare a test-only playbook or known safe existing playbook that contains only a Teams notification step.
2. Ensure the message text is non-sensitive, for example: `SOAR staging Teams smoke test`.
3. Confirm no additional steps exist in the playbook.
4. Confirm no active duplicate execution exists for the same test case.
5. Enable the required staging env vars in the staging runtime.
6. Restart or reload only if the runtime requires it to pick up env vars.
7. Call the read-only integration status endpoint and confirm:
   - `configured_mode` is `real`.
   - Teams `teams_configured` is `true` or equivalent safe configured flag is true.
   - Teams `real_mode_allowed` is `true`.
   - Teams `real_mode_ready` is `true`.
   - Teams `teams_real_enabled` is `true` where exposed.
   - no webhook value, host path, request header, token, or raw provider metadata appears.
   - Slack readiness remains independent and unchanged.
   - non-Teams adapters remain simulation-only.
8. Run exactly one manual executor invocation or approved manual path for the controlled execution.
9. Confirm exactly one Teams message arrived in the staging Teams destination.
10. Capture evidence listed below.
11. Roll back immediately to simulation mode.
12. Perform post-test cleanup.

Do not use a daemon, scheduler, retry loop, background replay, run-now loop, queue redesign, or repeated manual invocations for the smoke test.

## Evidence to capture
Capture only safe evidence:
- Date/time of test.
- Operator and approver names.
- Staging environment identifier.
- Git revision or deployed version.
- Integration status excerpt showing safe booleans only.
- Teams circuit breaker state before and after.
- Playbook id and execution id.
- Sanitized `steps_log` excerpt showing Teams result metadata without secrets.
- Confirmation that exactly one Teams message appeared.
- Timeout/outage observations if the send did not complete.
- Rollback confirmation showing simulation mode restored.
- Post-test cleanup confirmation.

Do not capture:
- `TEAMS_WEBHOOK_URL`.
- `SLACK_WEBHOOK_URL`.
- request headers.
- Teams webhook response bodies if they contain request metadata.
- raw params containing secrets.
- production Teams channel identifiers if considered sensitive.
- screenshots or logs that reveal webhook URL fragments.

## Pass criteria
The smoke test passes only if all are true:
- The test ran in staging.
- Manual operator approval was recorded before the send.
- All required env vars were set through approved runtime configuration.
- Integration status showed Teams ready using safe booleans only.
- No Teams webhook URL appeared in logs, UI, status output, audit output, evidence, docs, prompts, commits, or tickets.
- Only Teams was real-ready for this test.
- Slack readiness remained independent and unchanged.
- Firewall, email, generic webhook, and PagerDuty remained simulation-only.
- Exactly one Teams message arrived in the intended staging destination.
- The playbook execution recorded safe metadata.
- No queue replay, scheduler, daemon, autonomous retry, firewall mutation, blocklist mutation, Slack send, email send, generic webhook send, or PagerDuty action occurred.
- Rollback to simulation was completed and verified.
- Post-test cleanup was completed.

## Fail criteria
The smoke test fails and must stop if any are true:
- Environment identity is not clearly staging.
- Manual approval is missing or ambiguous.
- Any required env var is missing.
- The Teams webhook URL is exposed anywhere.
- Integration status reports non-Teams real mode.
- Slack is unintentionally real-ready or changed by the Teams setup.
- Teams circuit breaker is open, half-open, invalid, unknown, or ambiguous.
- More than one Teams message is sent.
- Any real firewall, Slack, email, generic webhook, PagerDuty, subprocess, blocked IP, queue redesign, scheduler, daemon, or autonomous retry behavior occurs.
- Automated tests require or use a real webhook.
- Rollback cannot be verified.

## Timeout and outage expectations
If Teams is slow, unavailable, rate-limited, or returns an error:

- Do not retry manually unless a separate approval explicitly authorizes a second controlled attempt.
- Treat timeout or Teams outage as a failed smoke test, not as a reason to loop.
- Confirm the adapter result classifies the failure safely without exposing secrets.
- Confirm circuit breaker state after the failure.
- Capture safe evidence of the failure classification, elapsed/timeout metadata when available, and breaker state.
- Roll back to simulation immediately.

Timeout/outage handling must not add background retries, daemon behavior, scheduler behavior, queue replay, or hidden recovery.

## Duplicate-message prevention guidance
Before the send:

- Use one controlled playbook execution id.
- Confirm no active duplicate execution exists for the same playbook/test case.
- Confirm no manual executor process is already running.
- Confirm no daemon, scheduler, or run loop exists for playbook execution.
- Confirm only one operator will invoke the manual path.

After the send:

- Stop after the first result, whether success or failure.
- Do not retry from browser refreshes, repeated CLI commands, or stale terminal sessions.
- If duplicate delivery occurs, mark the smoke test failed, record safe evidence, force-open the Teams circuit breaker if available, and roll back to simulation.

## Webhook secrecy rules
The Teams webhook URL must never appear in:

- repo files or OpenSpec docs.
- shell history, command output, screenshots, or examples.
- application logs.
- audit records.
- route responses.
- frontend UI.
- `steps_log`.
- test fixtures, snapshots, assertions, or failure output.
- prompts, tickets, chat, or post-test evidence.

Use only safe boolean statements such as `TEAMS_WEBHOOK_URL configured: yes`.

## Rollback to simulation
Rollback steps:

1. Set `INTEGRATION_MODE=simulation` or remove `INTEGRATION_MODE`.
2. Remove or unset `TEAMS_WEBHOOK_URL` from staging runtime if no longer needed.
3. Remove or set `SOAR_REAL_TEAMS_ENABLED=false`.
4. Restart or reload only if runtime env refresh requires it.
5. Verify integration status reports simulation mode.
6. Verify Teams `real_mode_ready` is false.
7. Verify Slack readiness and behavior did not regress.
8. Verify firewall, email, generic webhook, and PagerDuty remain simulation-only.
9. Record rollback evidence without secrets.

If unexpected Teams behavior occurs, force-open the Teams circuit breaker if available, then rollback to simulation.

## Post-test cleanup
After pass or fail:

- Confirm real Teams mode is disabled or removed from staging runtime unless a separately approved follow-up keeps it enabled.
- Confirm `TEAMS_WEBHOOK_URL` is removed from local shells and any temporary runtime configuration where it is no longer needed.
- Confirm no webhook value was written to shell history, logs, evidence, docs, commits, tickets, or prompts.
- Confirm no duplicate execution remains active for the test case.
- Confirm Teams circuit breaker state is recorded.
- Confirm test evidence contains only safe booleans and sanitized metadata.
- Confirm automated test and CI environments remain no-network.

## No-network automated test guarantee
Automated tests must not be part of the manual smoke test. They must remain no-network:

- No real `TEAMS_WEBHOOK_URL` in test or CI env.
- Outbound Teams HTTP paths must be mocked or blocked.
- Test assertions must prove webhook values are redacted.
- Tests must fail if an unmocked network call is attempted.
- Slack tests and Teams tests must not share real webhook configuration.

## Safety boundaries
- Staging only.
- One controlled Teams test only after manual operator approval.
- Default remains simulation.
- Teams webhook URL must never be printed, logged, committed, stored, included in docs, or pasted into prompts.
- Real mode must remain Teams-only and staging-only for this smoke test.
- Slack must remain independent and unchanged.
- Real firewall remains out of scope.
- No real email, generic webhook, or PagerDuty.
- No frontend changes.
- No schema changes.
- No executor, queue, scheduler, daemon, ingest, detection, or correlation changes.
