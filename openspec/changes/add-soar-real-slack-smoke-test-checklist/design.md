# Design: SOAR Real Slack Smoke-Test Checklist

## Safety posture
The smoke test is manual, staging-only, and limited to one controlled Slack notification. It must not be run from local development, automated tests, CI, production, or any environment where the Slack destination is unclear.

The checklist is documentation only. It does not add code, send a message, create a playbook, modify schema, alter executor behavior, change queues, or touch ingest/detection/correlation.

## Required environment variables
The staging runtime must have exactly these Slack real-mode controls:

```text
INTEGRATION_MODE=real
SOAR_ENV=staging
SOAR_REAL_SLACK_ENABLED=true
SLACK_WEBHOOK_URL=<set in runtime secret/env only>
```

Rules:
- `SLACK_WEBHOOK_URL` must be injected through the staging runtime environment or approved secret manager only.
- The webhook URL must never be printed, logged, committed, stored in the database, pasted into prompts, pasted into tickets, or copied into test fixtures.
- Operators may record `SLACK_WEBHOOK_URL configured: yes/no`, never the value.
- If any required env var is missing or ambiguous, stop and keep simulation mode.

## Preflight checks
Before enabling or using real Slack:

1. Confirm this is staging.
   - Verify host, deployment target, database, and app URL are staging.
   - Verify no production Slack channel is attached to the webhook.

2. Confirm default simulation behavior.
   - With `INTEGRATION_MODE=simulation` or unset, verify integration status reports simulation.
   - Confirm Slack adapter status does not expose a webhook URL.
   - Confirm firewall, email, webhook, and PagerDuty are not real-enabled.

3. Confirm automated tests remain no-network.
   - Use only mocked outbound Slack tests.
   - Do not run tests with a real `SLACK_WEBHOOK_URL` in the test environment.
   - Confirm tests patch or block the outbound HTTP path.

4. Confirm circuit breaker state.
   - Slack circuit breaker must be `closed`.
   - If state is `open`, `half_open`, invalid, or ambiguous after restart, stop and resolve explicitly before any send.

5. Confirm playbook/test input safety.
   - The controlled test must use only a low-risk `notify_slack` action.
   - No `block_ip`, firewall, email, webhook, PagerDuty, queue replay, scheduler, or autonomous retry behavior is allowed.
   - Payload content must be short and non-sensitive.

6. Confirm approval.
   - A super_admin/operator must explicitly approve the one controlled test.
   - Record who approved, when, and the staging target, without recording secrets.

## Controlled manual test path
The smoke test should use one controlled staging execution path:

1. Prepare a test-only playbook or known safe existing playbook that contains only a Slack notification step.
2. Ensure the message text is non-sensitive, for example: `SOAR staging Slack smoke test`.
3. Confirm no additional steps exist in the playbook.
4. Confirm no active duplicate execution exists for the same test case.
5. Enable the required staging env vars in the staging runtime.
6. Restart or reload only if the runtime requires it to pick up env vars.
7. Call the read-only integration status endpoint and confirm:
   - `configured_mode` is `real`.
   - Slack `slack_configured` is `true`.
   - Slack `real_mode_allowed` is `true`.
   - Slack `real_mode_ready` is `true`.
   - No webhook value appears.
   - Non-Slack adapters remain simulation-only.
8. Run exactly one manual executor invocation or approved manual path for the controlled execution.
9. Confirm exactly one Slack message arrived in the staging Slack destination.
10. Capture evidence listed below.
11. Roll back immediately to simulation mode.

Do not use a daemon, scheduler, retry loop, background replay, run-now loop, queue redesign, or repeated manual invocations for the smoke test.

## Evidence to capture
Capture only safe evidence:
- Date/time of test.
- Operator and approver names.
- Staging environment identifier.
- Git revision or deployed version.
- Integration status excerpt showing safe booleans only.
- Slack circuit breaker state before and after.
- Playbook id and execution id.
- Sanitized `steps_log` excerpt showing Slack result metadata without secrets.
- Confirmation that exactly one Slack message appeared.
- Rollback confirmation showing simulation mode restored.

Do not capture:
- `SLACK_WEBHOOK_URL`.
- Request headers.
- Slack webhook response bodies if they contain request metadata.
- Raw params containing secrets.
- Production Slack channel identifiers if considered sensitive.

## Pass criteria
The smoke test passes only if all are true:
- The test ran in staging.
- All required env vars were set through approved runtime configuration.
- Integration status showed Slack ready using safe booleans only.
- No webhook URL appeared in logs, UI, status output, audit output, evidence, or prompts.
- Only Slack was real-ready.
- Firewall, email, webhook, and PagerDuty remained simulation-only.
- Exactly one Slack message arrived in the intended staging destination.
- The playbook execution recorded safe metadata.
- No queue replay, scheduler, daemon, autonomous retry, firewall mutation, or blocklist mutation occurred.
- Rollback to simulation was completed and verified.

## Fail criteria
The smoke test fails and must stop if any are true:
- Environment identity is not clearly staging.
- Any required env var is missing.
- The webhook URL is exposed anywhere.
- Integration status reports non-Slack real mode.
- Slack circuit breaker is open, invalid, or ambiguous.
- More than one Slack message is sent.
- Any real firewall, email, webhook, PagerDuty, subprocess, blocked IP, queue redesign, scheduler, daemon, or autonomous retry behavior occurs.
- Automated tests require or use a real webhook.
- Rollback cannot be verified.

## Rollback to simulation
Rollback steps:
1. Set `INTEGRATION_MODE=simulation` or remove `INTEGRATION_MODE`.
2. Remove or unset `SLACK_WEBHOOK_URL` from staging runtime if no longer needed.
3. Remove or set `SOAR_REAL_SLACK_ENABLED=false`.
4. Restart or reload only if runtime env refresh requires it.
5. Verify integration status reports simulation mode.
6. Verify Slack `real_mode_ready` is false.
7. Verify non-Slack adapters remain simulation-only.
8. Record rollback evidence without secrets.

If unexpected Slack behavior occurs, force-open the Slack circuit breaker if available, then rollback to simulation.

## No-network automated test guarantee
Automated tests must not be part of the manual smoke test. They must remain no-network:
- No real `SLACK_WEBHOOK_URL` in test or CI env.
- Outbound Slack HTTP paths must be mocked or blocked.
- Test assertions must prove webhook values are redacted.
- Tests must fail if an unmocked network call is attempted.

## Safety boundaries
- Staging only.
- One controlled Slack test only after approval.
- Default remains simulation.
- Webhook URL must never be printed, logged, committed, stored, or pasted into prompts.
- Real firewall remains out of scope.
- No real email, webhook, or PagerDuty.
- No frontend changes.
- No schema changes.
- No executor, queue, scheduler, daemon, ingest, detection, or correlation changes.
