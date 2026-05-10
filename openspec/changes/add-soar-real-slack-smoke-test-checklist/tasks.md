# Tasks: SOAR Real Slack Smoke-Test Checklist

## Checklist Preparation
- [ ] Confirm staging environment identity before any real-mode configuration is enabled.
- [ ] Confirm the Slack destination is a staging/test Slack channel only.
- [ ] Confirm an operator and approver are assigned.
- [ ] Confirm default integration status reports simulation mode.
- [ ] Confirm Slack status exposes safe booleans only and does not expose the webhook URL.
- [ ] Confirm firewall, email, webhook, and PagerDuty remain simulation-only.
- [ ] Confirm automated tests are no-network and do not require real Slack secrets.
- [ ] Confirm Slack circuit breaker state is `closed`.
- [ ] Confirm no scheduler, daemon, background replay, or autonomous retry path will be used.

## Required Environment Variables
- [ ] Set `INTEGRATION_MODE=real` in staging only.
- [ ] Set `SOAR_ENV=staging` in staging only.
- [ ] Set `SOAR_REAL_SLACK_ENABLED=true` in staging only.
- [ ] Set `SLACK_WEBHOOK_URL` through approved runtime secret/env configuration only.
- [ ] Confirm `SLACK_WEBHOOK_URL` is not printed, logged, committed, stored in DB, pasted into prompts, or copied into tickets.

## Controlled Manual Test
- [ ] Select or create a staging-only test execution path with only `notify_slack`.
- [ ] Use a short non-sensitive message such as `SOAR staging Slack smoke test`.
- [ ] Confirm the playbook has no firewall, email, webhook, PagerDuty, approval bypass, or remediation steps.
- [ ] Confirm no active duplicate execution exists for the same test case.
- [ ] Verify integration status after env configuration:
  - [ ] `configured_mode=real`
  - [ ] Slack `slack_configured=true`
  - [ ] Slack `real_mode_allowed=true`
  - [ ] Slack `real_mode_ready=true`
  - [ ] no webhook URL value present
  - [ ] non-Slack adapters simulation-only
- [ ] Run exactly one manual executor invocation or approved manual path.
- [ ] Confirm exactly one Slack message arrives in the staging destination.
- [ ] Stop immediately if more than one message is sent.

## Evidence Capture
- [ ] Record test date/time.
- [ ] Record operator and approver names.
- [ ] Record staging environment identifier.
- [ ] Record deployed revision/version.
- [ ] Capture safe integration status booleans.
- [ ] Capture Slack circuit breaker state before and after.
- [ ] Capture playbook id and execution id.
- [ ] Capture sanitized `steps_log` metadata with no secrets.
- [ ] Record confirmation that exactly one Slack message arrived.
- [ ] Record rollback verification.

## Pass/Fail Review
- [ ] Pass only if the test ran in staging and sent exactly one intended Slack message.
- [ ] Pass only if no webhook URL appeared in logs, UI, status, audit, evidence, prompts, or commits.
- [ ] Pass only if firewall, email, webhook, and PagerDuty stayed simulation-only.
- [ ] Pass only if no blocked IP, subprocess, queue redesign, scheduler, daemon, or autonomous retry behavior occurred.
- [ ] Fail if environment identity was ambiguous.
- [ ] Fail if any secret was exposed.
- [ ] Fail if rollback could not be verified.

## Rollback
- [ ] Set `INTEGRATION_MODE=simulation` or unset it.
- [ ] Remove or unset `SLACK_WEBHOOK_URL` if not needed after the smoke test.
- [ ] Set `SOAR_REAL_SLACK_ENABLED=false` or unset it.
- [ ] Restart/reload only if required by runtime env handling.
- [ ] Verify integration status reports simulation.
- [ ] Verify Slack `real_mode_ready=false`.
- [ ] Verify non-Slack adapters remain simulation-only.
- [ ] If behavior was unexpected, force-open Slack circuit breaker if available.

## Automated Test Boundary
- [ ] Do not run automated tests with a real Slack webhook configured.
- [ ] Keep outbound Slack HTTP mocked or blocked in tests.
- [ ] Ensure tests fail on unmocked network calls.
- [ ] Ensure tests assert webhook redaction.

## Stop Conditions
- [ ] Stop if implementation code changes are required.
- [ ] Stop if smoke test would run outside staging.
- [ ] Stop if a webhook value must be printed, logged, committed, stored, or pasted into a prompt.
- [ ] Stop if any non-Slack integration would become real.
- [ ] Stop if executor, queue, schema, frontend, ingest, detection, or correlation changes are needed.
- [ ] Stop if approval for the one controlled Slack test is missing.
