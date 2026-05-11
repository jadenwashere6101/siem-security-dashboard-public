# Proposal: SOAR Playbook Approval Gates

## Problem

The simulation-only playbook executor can consume `pending` `playbook_executions`, simulate
definition steps, write `steps_log`, and finish with `success` or `failed`. That is safe for
low-risk simulated steps, but it does not yet model approval-gated remediation.

Operators need playbooks to pause at explicit approval gates before later high-risk simulated
steps. The system already has approval requests, approval APIs, and approval UI, but those
approvals are not linked to playbook executions or step indexes.

## Goal

Plan approval-gated playbook execution for simulation-only playbooks so the executor can:

- recognize a `require_approval` step
- create or reuse an approval request for the playbook execution and step index
- pause the playbook execution before later steps run
- resume manually only after approval
- safely stop on denial or expiration
- record approval lifecycle events in `steps_log`

This change must not introduce real execution, autonomous remediation, queue enqueueing, or
external integrations.

## Scope

- Define a `require_approval` playbook step type.
- Extend simulation-only executor behavior for approval pause/resume.
- Add the smallest approval-to-playbook-execution link if existing schema cannot represent it.
- Add execution status handling for `awaiting_approval`.
- Add store helpers for creating/reusing playbook step approval requests and resuming after
  decision.
- Add manual/script-based resume behavior only.
- Add backend tests proving pending approvals pause execution and block later steps.
- Add API/frontend test requirements only if existing approval visibility needs a small
  additive field to show playbook context.

## Out of Scope

- No implementation code as part of this proposal.
- No real firewall execution.
- No Slack, email, PagerDuty, webhook, or external integration calls.
- No daemon, systemd service, scheduler, or background playbook worker.
- No frontend redesign.
- No broad approval UI rewrite.
- No ingest, detection, or correlation changes.
- No SOAR queue behavior changes.
- No response action enqueueing.
- No firewall/blocklist mutation.
- No autonomous remediation.

## Success Criteria

- A simulation playbook can pause at `require_approval` with status `awaiting_approval`.
- No later playbook steps run while approval is pending.
- Approved requests allow manual resume from the next safe step.
- Denied or expired requests mark the execution safely stopped/failed and do not run later
  high-risk steps.
- `steps_log` records approval requested, approved, denied, expired, resumed, and skipped
  outcomes clearly.
- Approval requests can be traced to the playbook execution and step index.
- No SOAR queue rows are created or modified by playbook approval gates.
- Existing approval, queue, incident, protected-target, dry-run adapter, ingest, detection,
  correlation, and frontend behavior remains unchanged except for explicitly approved
  additive visibility.
