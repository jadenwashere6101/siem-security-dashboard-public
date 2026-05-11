# Proposal: SOAR Playbook Trigger Execution Records

## Problem

SOAR playbook definitions can be created, managed, read, and matched against alerts, but
matching is still not wired into committed alert handling. Operators can define enabled
playbooks, yet no inert execution record is created to show which playbooks would be
scheduled for a committed alert.

There is still no playbook executor. The next safe step is to create pending
`playbook_executions` records after alert commit, without executing steps or enqueueing SOAR
actions.

## Goal

Plan a safe post-commit orchestration path that:

- receives committed alert IDs
- matches each alert against enabled playbook definitions
- creates one inert `playbook_executions` row per matched playbook/alert pair
- stores rows with `status='pending'`
- deduplicates repeated scheduling for the same playbook and alert

This change is visibility and scheduling metadata only. It must not execute playbook steps,
enqueue response actions, create approvals, or call integrations.

## Scope

- New post-commit playbook orchestration design, preferably in a dedicated orchestrator
  module instead of embedding logic directly inside ingest routes.
- Store helper design for idempotent pending execution creation.
- Idempotency/deduplication for one execution record per `(playbook_id, alert_id)` pair.
- Minimal post-commit wiring after alert rows are committed and visible.
- Tests proving matched playbooks create pending execution records.
- Tests proving duplicate calls do not create duplicate execution rows.
- Tests proving no SOAR queue rows, response action logs, approvals, or integration calls are
  created.
- Regression tests around existing ingest, detection, and correlation behavior.

## Out of Scope

- No implementation code as part of this proposal.
- No playbook step executor.
- No worker consumption of `playbook_executions`.
- No queue enqueueing.
- No Slack, email, firewall, or other integration work.
- No real execution.
- No frontend changes.
- No schema changes unless implementation proves a tiny additive idempotency constraint or
  index is required.
- No detection or correlation engine refactors.
- No broad ingest refactor.
- No changes to SOAR queue, approvals, incidents, protected targets, or dry-run adapter
  behavior.

## Success Criteria

- Playbook matching happens only after alert commit.
- Matched enabled playbooks create `playbook_executions` rows with `status='pending'`.
- Each `(playbook_id, alert_id)` pair is scheduled at most once.
- Disabled playbooks do not create execution records.
- Unknown or missing alert IDs are skipped safely.
- Orchestration failures are logged and do not fail already-committed ingest responses.
- No playbook steps execute.
- No SOAR queue rows are created by playbook scheduling.
- No approvals are created.
- No integrations or adapters are called.
- Existing ingest, detection, correlation, SOAR queue, incident, approval, protected-target,
  and dry-run adapter behavior remains unchanged.
