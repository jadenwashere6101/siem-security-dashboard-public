# Proposal: SOAR Real Notification Delivery Tracking

## Problem
Slack and Teams now have real-readiness guardrails, but outbound delivery visibility is still centered on adapter output inside playbook `steps_log` and limited audit/log metadata. That is enough for simulation visibility, but it is not enough before production-style real notifications.

Operators need immutable delivery attempt history that can answer what notification was attempted, which provider was targeted, whether it was simulation or real mode, which playbook/step/incident/approval caused it, whether it timed out or failed, whether it might be a duplicate, and how circuit breaker/retry metadata affected the attempt. This history must remain safe to expose without leaking webhooks, tokens, headers, provider request bodies, or raw unsafe payloads.

## Goal
Design immutable outbound notification delivery tracking for simulation and future real Slack/Teams notifications before any production-style real notification operation.

## Scope
- Define immutable delivery attempt records.
- Label simulation vs real delivery attempts.
- Define outbound correlation identifiers.
- Record delivery timestamps and duration metadata.
- Record timeout and failure metadata.
- Record dedupe and idempotency metadata.
- Link delivery attempts to playbook executions, step indexes, incidents, alerts, and approvals.
- Define operator-visible delivery history.
- Define safe retention expectations.
- Define safe audit linkage.
- Define visibility-oriented metrics.
- Define circuit-breaker interaction.
- Define retry visibility metadata without creating retries.
- Define partial delivery failure handling.
- Suggest future schema direction.
- Suggest read APIs.
- Suggest UI visibility areas.
- Recommend future archive boundaries.

## Out of scope
- No implementation code in this change.
- No schema changes yet.
- No actual delivery persistence implementation.
- No autonomous retries.
- No daemon, scheduler, cron, APScheduler, Celery, Redis, RQ, or background replay behavior.
- No queue redesign.
- No replay engine.
- No real firewall execution.
- No PagerDuty implementation.
- No email implementation.
- No generic webhook implementation.
- No frontend implementation.
- No external delivery guarantees.
- No ingest, detection, or correlation changes.
- No commits or archiving.
- No secrets in repo docs, examples, tests, logs, prompts, or future delivery records.

## Success criteria
- A future implementation can persist immutable notification delivery attempts for simulation and real Slack/Teams sends.
- Delivery records make duplicate sends detectable through idempotency and correlation metadata.
- Delivery records distinguish execution success from provider delivery success, failure, timeout, and ambiguous outcomes.
- Delivery history can be queried by provider, mode, status, incident, approval, playbook execution, and time window.
- Operators can inspect delivery history without seeing webhooks, tokens, request headers, raw provider responses, or raw unsafe payloads.
- Circuit breaker state, retry eligibility, timeout metadata, and provider outage classifications are visible without creating autonomous retries.
- Failed and ambiguous delivery attempts remain visible and immutable.
- Default behavior remains simulation, and real mode remains staging-controlled.

## Why now
Slack and Teams are notification-only and guarded, but the first real delivery path still crosses an external network boundary. Before real notifications become routine, the system needs a durable delivery ledger that avoids relying on transient logs or mutable step output. Designing the ledger before implementation reduces the risk of duplicate real notifications, unclear retry history, leaked provider metadata, and delivery/execution mismatches.
