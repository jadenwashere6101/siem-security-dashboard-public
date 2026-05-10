# Proposal: SOAR Real Slack Readiness

## Problem
SOAR integration adapters are currently simulation-only. That remains the correct default, but Slack is the lowest-risk first candidate for a tightly controlled real outbound integration because it is notification-only and does not mutate firewall, blocklist, incident, queue, ingest, detection, or correlation state.

Before any real Slack message can be sent, the project needs an explicit readiness design that keeps every other integration simulation-only, proves automated tests never hit the network, and defines fail-closed guardrails for local, development, test, and unconfigured environments.

## Goal
Design the first safe real integration path for Slack only while preserving simulation mode as the default for all integrations.

## Scope
- Define real Slack adapter readiness requirements.
- Define Slack webhook environment variable requirements.
- Define `INTEGRATION_MODE` behavior for Slack only.
- Require staging-only real mode guardrails.
- Require no-network pytest guarantees.
- Define timeout behavior for Slack outbound calls.
- Define interaction with existing integration circuit breakers.
- Define Slack retry eligibility metadata.
- Define safe payload formatting.
- Define secret redaction rules for logs, audit records, status APIs, test output, and UI surfaces.
- Define audit and logging expectations.
- Define a manual staging test plan.
- Define a rollback plan back to simulation mode.
- Allow one future implementation slice to combine Slack real-mode code, registry/config guardrails, mocked outbound tests, and status API readiness if the design remains safe.

## Out of scope
- No implementation code in this change.
- No real firewall execution.
- No real email execution.
- No real webhook execution.
- No PagerDuty integration.
- No frontend changes yet.
- No daemon or scheduler changes.
- No queue redesign.
- No ingest, detection, or correlation changes.
- No storing secrets in the database.
- No real network calls in automated tests.
- No enabling real mode for any adapter except Slack.

## Success criteria
- Slack remains simulation-only unless explicitly configured for staging real mode.
- Missing Slack webhook configuration fails closed with a safe, non-secret error.
- Local, development, and test environments cannot accidentally send Slack messages.
- Automated tests prove real Slack paths are disabled in test/dev and mock outbound calls without network access.
- Slack payloads use allowlisted, bounded fields and do not include secrets or raw unsafe params.
- Circuit breaker state blocks Slack real-mode sends when open or ambiguous.
- Timeout and retry metadata are visible without creating autonomous retry behavior.
- Firewall, email, webhook, PagerDuty, and all other integrations remain simulation-only.

## Why now
The project already has simulation adapters, adapter-backed playbook execution, circuit breaker metadata and enforcement, reliability metadata, playbook metrics, scheduled metadata visibility, and operator-visible integration status. Slack readiness is the next reasonable design step because it can introduce a single notification-only real path without enabling remediation or autonomous execution.

This design should exist before implementation so real outbound execution cannot arrive through ad hoc config checks, unmocked tests, leaked webhook URLs, or implicit behavior changes.
