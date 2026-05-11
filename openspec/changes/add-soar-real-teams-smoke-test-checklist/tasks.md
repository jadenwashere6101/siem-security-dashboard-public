# Tasks: SOAR Real Teams Smoke-Test Checklist

## Checklist Preparation
- [ ] Confirm staging environment identity before any real-mode configuration is enabled.
- [ ] Confirm the Teams destination is a staging/test Teams channel only.
- [ ] Confirm an operator and approver are assigned.
- [ ] Confirm manual operator approval is recorded before any real Teams send.
- [ ] Confirm default integration status reports simulation mode.
- [ ] Confirm Teams status exposes safe booleans only and does not expose the webhook URL.
- [ ] Confirm Slack readiness and behavior remain independent and unchanged.
- [ ] Confirm firewall, email, generic webhook, and PagerDuty remain simulation-only.
- [ ] Confirm automated tests are no-network and do not require real Teams secrets.
- [ ] Confirm Teams circuit breaker state is `closed`.
- [ ] Confirm no scheduler, daemon, background replay, run loop, or autonomous retry path will be used.
- [ ] Confirm no active duplicate execution exists for the same test case.

## Required Environment Variables
- [ ] Set `INTEGRATION_MODE=real` in staging only.
- [ ] Set `SOAR_ENV=staging` in staging only.
- [ ] Set `SOAR_REAL_TEAMS_ENABLED=true` in staging only.
- [ ] Set `TEAMS_WEBHOOK_URL` through approved runtime secret/env configuration only.
- [ ] Confirm `TEAMS_WEBHOOK_URL` is not printed, logged, committed, stored in DB, included in docs, pasted into prompts, or copied into tickets.
- [ ] Confirm Slack env vars do not satisfy Teams readiness.
- [ ] Confirm Teams env vars do not alter Slack readiness.

## Controlled Manual Test
- [ ] Select or create a staging-only test execution path with only the Teams notification action.
- [ ] Use a short non-sensitive message such as `SOAR staging Teams smoke test`.
- [ ] Confirm the playbook has no firewall, Slack, email, generic webhook, PagerDuty, approval bypass, or remediation steps.
- [ ] Confirm no active duplicate execution exists for the same test case.
- [ ] Confirm only one operator, terminal/session, and manual path will invoke the executor.
- [ ] Verify integration status after env configuration:
  - [ ] `configured_mode=real`
  - [ ] Teams configured flag is true
  - [ ] Teams `real_mode_allowed=true`
  - [ ] Teams `real_mode_ready=true`
  - [ ] Teams `teams_real_enabled=true` where exposed
  - [ ] no webhook URL, URL fragment, request header, token, or raw provider metadata present
  - [ ] Slack readiness unchanged
  - [ ] non-Teams adapters simulation-only
- [ ] Run exactly one manual executor invocation or approved manual path.
- [ ] Confirm exactly one Teams message arrives in the staging destination.
- [ ] Stop immediately if more than one message is sent.
- [ ] Stop immediately if timeout/outage occurs, capture safe failure evidence, and roll back.

## Evidence Capture
- [ ] Record test date/time.
- [ ] Record operator and approver names.
- [ ] Record staging environment identifier.
- [ ] Record deployed revision/version.
- [ ] Capture safe integration status booleans.
- [ ] Capture Teams circuit breaker state before and after.
- [ ] Capture playbook id and execution id.
- [ ] Capture sanitized `steps_log` metadata with no secrets.
- [ ] Record confirmation that exactly one Teams message arrived.
- [ ] Record timeout/outage failure classification if applicable.
- [ ] Record rollback verification.
- [ ] Record post-test cleanup verification.

## Pass/Fail Review
- [ ] Pass only if the test ran in staging and sent exactly one intended Teams message.
- [ ] Pass only if manual operator approval was recorded before the send.
- [ ] Pass only if no Teams webhook URL appeared in logs, UI, status, audit, evidence, prompts, docs, tickets, or commits.
- [ ] Pass only if Slack readiness remained independent and unchanged.
- [ ] Pass only if firewall, email, generic webhook, and PagerDuty stayed simulation-only.
- [ ] Pass only if no blocked IP, subprocess, queue redesign, scheduler, daemon, background replay, or autonomous retry behavior occurred.
- [ ] Pass only if rollback and post-test cleanup were verified.
- [ ] Fail if environment identity was ambiguous.
- [ ] Fail if approval was missing.
- [ ] Fail if any secret was exposed.
- [ ] Fail if more than one Teams message was sent.
- [ ] Fail if rollback could not be verified.

## Timeout and Outage Handling
- [ ] Treat Teams timeout, rate limit, 5xx, unavailable destination, or ambiguous delivery as a failed smoke test.
- [ ] Do not retry manually unless a separate approval explicitly authorizes a second controlled attempt.
- [ ] Confirm failure metadata is safe and excludes webhook URL, headers, tokens, and raw provider response bodies.
- [ ] Confirm Teams circuit breaker state after the failure.
- [ ] Capture safe failure evidence.
- [ ] Roll back to simulation immediately.

## Rollback
- [ ] Set `INTEGRATION_MODE=simulation` or unset it.
- [ ] Remove or unset `TEAMS_WEBHOOK_URL` if not needed after the smoke test.
- [ ] Set `SOAR_REAL_TEAMS_ENABLED=false` or unset it.
- [ ] Restart/reload only if required by runtime env handling.
- [ ] Verify integration status reports simulation.
- [ ] Verify Teams `real_mode_ready=false`.
- [ ] Verify Slack readiness/behavior is unchanged.
- [ ] Verify non-Teams adapters remain simulation-only.
- [ ] If behavior was unexpected, force-open Teams circuit breaker if available.

## Post-Test Cleanup
- [ ] Confirm real Teams mode is disabled or explicitly approved to remain staged.
- [ ] Confirm `TEAMS_WEBHOOK_URL` is removed from temporary shells and temporary runtime config where no longer needed.
- [ ] Confirm no webhook value was written to shell history, logs, docs, evidence, commits, tickets, or prompts.
- [ ] Confirm no duplicate execution remains active for the test case.
- [ ] Confirm Teams circuit breaker state is recorded.
- [ ] Confirm evidence contains only safe booleans and sanitized metadata.
- [ ] Confirm automated test and CI environments remain no-network.

## Automated Test Boundary
- [ ] Do not run automated tests with a real Teams webhook configured.
- [ ] Keep outbound Teams HTTP mocked or blocked in tests.
- [ ] Ensure tests fail on unmocked network calls.
- [ ] Ensure tests assert webhook redaction.
- [ ] Ensure Slack and Teams tests do not share real webhook configuration.

## Stop Conditions
- [ ] Stop if implementation code changes are required.
- [ ] Stop if smoke test would run outside staging.
- [ ] Stop if manual operator approval for the one controlled Teams test is missing.
- [ ] Stop if a Teams webhook value must be printed, logged, committed, stored, documented, or pasted into a prompt.
- [ ] Stop if any non-Teams integration would become real.
- [ ] Stop if Slack readiness or behavior would change.
- [ ] Stop if executor, queue, schema, frontend, ingest, detection, or correlation changes are needed.
- [ ] Stop if a daemon, scheduler, retry loop, or duplicate manual invocation is needed.
