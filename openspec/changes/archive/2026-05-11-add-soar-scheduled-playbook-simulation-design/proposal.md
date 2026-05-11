# Proposal: SOAR Scheduled Playbook Simulation Design

## Problem
SOAR playbooks currently execute only after committed alert-triggered scheduling records are created or through explicit manual simulation runner paths. The roadmap includes scheduled playbooks, but the current system intentionally has no daemon, scheduler, APScheduler, Celery, Redis, systemd worker, or autonomous remediation path.

Scheduled playbooks need a design before implementation because schedules can amplify operational risk: duplicate runs after restart, missed-run replay storms, overlapping executions, approval bottlenecks, circuit breaker interactions, and retry storms. These risks must be addressed while the system is still simulation-only and fail-closed.

## Goal
Design safe simulation-only scheduled playbook execution architecture.

## Scope
- Design scheduled playbook definitions.
- Define schedule metadata.
- Define enabled/disabled schedule behavior.
- Define last-run and next-run visibility.
- Define safe missed-run handling.
- Define schedule execution history linkage.
- Define manual pause/resume behavior.
- Define bounded execution concurrency.
- Define interactions with approval-gated playbooks, `permanently_failed` executions, circuit breakers, retry metadata, and stale execution detection.
- Define safe scheduler startup and restart behavior.
- Define read-only metrics visibility.
- Define audit logging expectations.

## Out of scope
- No implementation code in this change.
- No daemon implementation.
- No APScheduler, Celery, Redis, RQ, cron, or systemd worker implementation.
- No background autonomous retries.
- No real integrations.
- No enabling `INTEGRATION_MODE=real`.
- No firewall or blocklist mutation.
- No `blocked_ips` mutation.
- No queue redesign.
- No execution implementation.
- No frontend implementation yet.
- No hidden autonomous remediation.

## Success criteria
- Scheduled playbook behavior is specified as simulation-only, fail-closed, and operator-visible.
- Schedule metadata is explicit enough to support safe future implementation.
- Startup/restart behavior avoids hidden execution and replay storms.
- Missed-run handling is bounded and auditable.
- Overlapping runs are prevented by design.
- Approval, circuit breaker, retry, stale execution, and `permanently_failed` interactions are clear.
- Metrics and audit expectations are defined without adding execution behavior.

## Why design first
Scheduling introduces time-based automation. Even in simulation mode, unclear scheduling semantics can create duplicate executions, stale work, or noisy approval queues. Designing the scheduling contract first keeps any future implementation bounded, visible, and safe before a scheduler process or real integrations are introduced.
