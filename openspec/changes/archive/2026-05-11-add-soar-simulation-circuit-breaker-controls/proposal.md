# Proposal: SOAR Simulation Circuit Breaker Controls

## Problem
Simulation-mode integration circuit breaker state and enforcement now provide a safe foundation for preventing repeated adapter-backed playbook execution against unhealthy simulated adapters. Operators can see breaker state, and adapter-backed playbook execution respects breaker behavior, but there are not yet explicit manual controls for an operator to reset, force-open, or prepare a half-open probe.

Without explicit controls, recovery behavior can drift toward hidden state changes or ad hoc database edits. That is risky even in simulation mode because these patterns will shape any later real-integration readiness work.

## Goal
Design explicit/manual operator controls for simulation-mode integration circuit breakers.

## Scope
- Add super-admin-only manual circuit breaker controls.
- Support manual reset to `closed`.
- Support manual force-open.
- Support manual enablement of a `half_open` probe.
- Require explicit operator action for all control paths.
- Define audit logging expectations for every breaker control action.
- Define UI visibility expectations for current breaker state and available controls.
- Safely handle stale, open, invalid, or restart-ambiguous breaker states.
- Preserve safe interaction with existing playbook execution states.
- Preserve immutable playbook execution history.

## Out of scope
- No implementation code in this change.
- No autonomous retries.
- No automatic replay.
- No daemon or scheduler behavior.
- No real outbound calls.
- No enabling `INTEGRATION_MODE=real`.
- No Redis, Celery, RQ, or queue backend migration.
- No queue redesign.
- No background healing.
- No hidden recovery behavior.
- No firewall or blocklist mutation.
- No `blocked_ips` mutation.
- No ingest, detection, or correlation changes.
- No Slack, webhook, email, firewall, PagerDuty, or external service execution.
- No subprocess execution.
- No external API dependencies.

## Success criteria
- Super-admins have explicit, auditable simulation-only controls for breaker reset, force-open, and half-open probe enablement.
- Analysts retain read-only visibility where existing integration status visibility allows it.
- Breaker controls never execute playbooks, retry executions, replay failures, call adapters, or contact external services by themselves.
- All controls fail closed when state is invalid, ambiguous, non-simulation, or unsafe.
- UI expectations make simulation-only status and control consequences clear.
- Existing playbook execution history remains immutable.
- Existing playbook execution states, including `awaiting_approval`, `failed`, `permanently_failed`, and `abandoned`, are not bypassed by breaker controls.

## Why manual controls now
Circuit breaker state is a reliability safeguard, but operators still need explicit control over recovery and containment. Force-open lets an operator stop adapter-backed simulated execution during investigation. Reset-to-closed lets an operator clear a known-good simulation adapter after review. Half-open enablement lets recovery probing remain deliberate and bounded.

These controls should be designed before real execution exists so recovery semantics are visible, auditable, and fail-closed before any external system can be affected.
