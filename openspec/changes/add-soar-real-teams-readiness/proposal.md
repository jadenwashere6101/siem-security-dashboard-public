# Proposal: SOAR Real Teams Readiness

## Problem
Slack is the first guarded real notification candidate, but many environments use Microsoft Teams as the operational notification surface. Teams can be a second safe real integration candidate only if it follows the same fail-closed pattern as Slack and does not weaken Slack, firewall, email, generic webhook, PagerDuty, queue, executor, or ingest safety boundaries.

Before any Teams real-mode implementation, the project needs a clear readiness design for environment configuration, staging controls, no-network tests, timeout behavior, circuit breaker interaction, retry metadata, payload safety, secret redaction, audit expectations, manual staging validation, and rollback.

## Goal
Design Microsoft Teams as a second safe real notification integration candidate, following the same guardrail pattern as Slack.

## Scope
- Define Teams webhook readiness requirements.
- Define `TEAMS_WEBHOOK_URL` environment variable requirements.
- Define Teams-only real-mode guardrails.
- Define staging-only controls.
- Require no-network pytest guarantees.
- Define timeout behavior.
- Define circuit breaker interaction.
- Define retry eligibility metadata.
- Define safe Teams payload formatting.
- Define secret redaction rules.
- Define audit/logging expectations.
- Define a manual staging test plan.
- Define rollback to simulation mode.
- Analyze Slack/Teams configuration separation so Slack behavior does not regress.

## Out of scope
- No implementation code in this change.
- No real Teams message sent.
- No real Slack changes.
- No real firewall execution.
- No real email execution.
- No real generic-webhook execution.
- No PagerDuty integration.
- No frontend changes.
- No schema changes.
- No executor or queue changes.
- No ingest, detection, or correlation changes.
- No storing secrets in the database.
- No real network calls in automated tests.

## Success criteria
- Teams remains simulation-only unless explicitly configured for staging real mode.
- Missing or invalid `TEAMS_WEBHOOK_URL` fails closed.
- Teams webhook URL is never logged, returned, committed, stored, or exposed in tests.
- Teams real mode is independent from Slack real mode.
- Slack readiness and Slack guarded behavior do not regress.
- Firewall, email, generic webhook, PagerDuty, and all remediation integrations remain simulation-only.
- Automated tests can prove Teams no-network behavior using mocks and network-deny fixtures.
- Circuit breaker open/invalid state blocks Teams before network.
- Rollback to simulation is simple and verifiable.

## Why now
Teams is notification-only like Slack, so it is an appropriate second real integration candidate after Slack readiness. Designing it before implementation prevents copy/paste drift, Slack/Teams environment confusion, accidental real mode in local/dev/test, and webhook leakage.
