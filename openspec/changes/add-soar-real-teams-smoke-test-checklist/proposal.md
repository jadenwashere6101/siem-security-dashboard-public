# Proposal: SOAR Real Teams Smoke-Test Checklist

## Problem
Teams real-mode readiness now has guardrails, but the first real Teams message must not be sent casually from local development, automated tests, production, or an ambiguous staging environment. A manual staging-only smoke-test checklist is needed before any operator uses `INTEGRATION_MODE=real` with a real Teams webhook.

The checklist should make the first Teams send deliberate, approved, reversible, and evidence-backed while keeping Slack independent and keeping all non-Teams integrations simulation-only.

## Goal
Design a safe manual staging-only Teams smoke-test checklist before any real Teams message is sent.

## Scope
- Define the exact environment variables required:
  - `INTEGRATION_MODE=real`
  - `SOAR_ENV=staging`
  - `SOAR_REAL_TEAMS_ENABLED=true`
  - `TEAMS_WEBHOOK_URL`
- Define staging-only validation before any real send is attempted.
- Define preflight checks.
- Define Teams circuit-breaker verification.
- Define simulation rollback verification.
- Define one controlled manual Teams test path.
- Define expected safe evidence to capture.
- Define pass/fail criteria.
- Define timeout and outage expectations.
- Define duplicate-message prevention guidance.
- Define Teams webhook secrecy rules.
- Define rollback procedure and post-test cleanup.
- Define the no-network automated test guarantee.

## Out of scope
- No implementation code in this change.
- No real Teams message sent by this change.
- No real Slack message sent or Slack behavior changed.
- No real firewall execution.
- No real email execution.
- No real generic webhook execution.
- No PagerDuty integration.
- No frontend changes.
- No schema changes.
- No executor or queue changes.
- No ingest, detection, or correlation changes.
- No secrets in repo docs, examples, tests, prompts, tickets, logs, or evidence.

## Success criteria
- Operators have a clear staging-only checklist for the first Teams smoke test.
- The checklist requires explicit manual operator approval before the single real Teams test.
- The Teams webhook URL is never printed, logged, committed, stored, included in docs, copied into examples, or pasted into prompts.
- The checklist verifies default simulation before enabling real Teams.
- The checklist verifies Teams readiness via safe booleans only.
- The checklist verifies Teams circuit breaker state before any send.
- The checklist defines exactly one controlled test execution and immediate rollback.
- The checklist defines objective pass/fail criteria, timeout/outage handling, evidence capture, rollback, and post-test cleanup.
- Slack readiness remains independent and unchanged.
- Firewall, email, generic webhook, PagerDuty, blocklist, and remediation integrations remain simulation-only.
- Automated tests remain no-network.

## Why now
Real Teams is the second guarded notification-only integration candidate after Slack readiness. It crosses a network boundary and can leak sensitive context if operated carelessly. A staging checklist should exist before the first manual send so operators do not improvise with production secrets, local environments, duplicate executions, or unbounded retries.
