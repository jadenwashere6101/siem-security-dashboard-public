# Proposal: SOAR Real Slack Smoke-Test Checklist

## Problem
Slack real-mode readiness now has guardrails, but the first real Slack message must not be sent casually from local development, automated tests, or an ambiguous staging environment. A manual staging-only smoke-test checklist is needed before any operator uses `INTEGRATION_MODE=real` with a real Slack webhook.

The checklist should make the first send deliberate, approved, reversible, and evidence-backed while keeping all other integrations simulation-only.

## Goal
Design a safe manual staging-only Slack smoke-test checklist before any real Slack message is sent.

## Scope
- Define the exact environment variables required:
  - `INTEGRATION_MODE=real`
  - `SOAR_ENV=staging`
  - `SOAR_REAL_SLACK_ENABLED=true`
  - `SLACK_WEBHOOK_URL`
- Define preflight checks before any real send is attempted.
- Define one controlled manual test path.
- Define rollback to simulation mode.
- Define evidence to capture.
- Define pass/fail criteria.
- Define the no-network automated test guarantee.

## Out of scope
- No implementation code in this change.
- No real Slack message sent by this change.
- No real firewall execution.
- No real email execution.
- No real webhook execution.
- No PagerDuty integration.
- No frontend changes.
- No schema changes.
- No executor or queue changes.
- No ingest, detection, or correlation changes.

## Success criteria
- Operators have a clear staging-only checklist for the first Slack smoke test.
- The checklist requires explicit approval before the single real Slack test.
- The webhook URL is never printed, logged, committed, stored, or pasted into prompts.
- The checklist verifies default simulation before enabling real Slack.
- The checklist verifies Slack readiness via safe booleans only.
- The checklist defines exactly one controlled test execution and immediate rollback.
- The checklist defines objective pass/fail criteria and evidence.
- Automated tests remain no-network.

## Why now
Real Slack is the first possible real integration path. It is notification-only, but it still crosses a network boundary and can leak sensitive context if operated carelessly. A staging checklist should exist before the first manual send so operators do not improvise with production secrets, local environments, or unbounded playbook executions.
