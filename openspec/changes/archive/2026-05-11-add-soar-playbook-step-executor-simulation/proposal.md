# Proposal: SOAR Playbook Step Executor Simulation

## Problem

Playbook definitions and `playbook_executions` now exist, and post-commit orchestration can
create inert `pending` execution records when enabled playbooks match committed alerts. Those
records are visible through APIs and frontend UI, but nothing consumes them yet.

The next safe step is to prove playbook step semantics in simulation only. The system needs a
manual executor that reads pending playbook executions, loads the linked definition, records
simulated step outcomes, and transitions execution status without calling real integrations
or enqueueing SOAR queue actions.

## Goal

Plan a simulation-only playbook step executor that:

- reads pending `playbook_executions`
- loads each linked `playbook_definitions` row
- marks an execution `running`
- iterates definition steps
- records simulated step results in `steps_log`
- transitions the execution to `success` or `failed`
- avoids all real external execution

This is not a daemon or production worker. It should be safe to run manually in development
and test environments.

## Scope

- Simulation-only executor module/function.
- Store helpers for claiming/listing pending executions and updating `steps_log`,
  `last_completed_step`, and execution status.
- Manual/script-based execution path only.
- Simulated behavior for currently supported registry actions: `monitor`, `flag_high_priority`,
  and `block_ip`.
- Status transitions: `pending -> running -> success|failed`.
- Idempotency rules that avoid re-running successful completed executions.
- Tests proving steps are simulated and no real adapters/actions are called.

## Out of Scope

- No implementation code as part of this proposal.
- No real firewall execution.
- No Slack, email, PagerDuty, or webhook integration.
- No daemon, systemd service, scheduler, Celery, APScheduler, or background worker.
- No approval gates.
- No frontend changes.
- No schema changes unless absolutely necessary and additive.
- No ingest, detection, or correlation changes.
- No changes to existing SOAR response queue behavior.
- No retry/dead-letter system yet, except future-work notes.
- No enqueueing `response_actions_queue` rows.

## Success Criteria

- A manual simulation executor can process pending `playbook_executions`.
- Each processed execution records one `steps_log` entry per simulated step.
- Successful simulated executions end with `status='success'`.
- Failed simulated executions end with `status='failed'`.
- Already terminal executions are not re-run.
- No real adapters or integrations are called.
- No firewall/blocklist mutation occurs.
- No approvals are created.
- No `response_actions_queue` rows are created.
- Existing SOAR queue, approval, incident, protected-target, ingest, detection, correlation,
  and frontend behavior remains unchanged.
