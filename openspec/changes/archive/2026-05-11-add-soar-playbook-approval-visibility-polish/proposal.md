# Proposal: SOAR Playbook Approval Visibility Polish

## Problem

SOAR playbook executions can now pause at `require_approval`, create linked approval
requests, resume after approval, and safely stop after denial or expiration. The
PlaybooksPanel already shows execution details and a `steps_log` timeline, but approval gate
states can still be hard to scan because they appear as generic step entries.

Analysts need a clear read-only view that distinguishes:

- waiting for approval
- approval granted and simulation resumed
- approval denied and later steps skipped
- approval expired and later steps skipped

This visibility should not add new decision controls or imply real execution exists.

## Goal

Improve frontend visibility for approval-gated simulated playbook executions so analysts can
quickly understand current state and approval outcomes from the PlaybooksPanel execution
detail view.

The UI should clearly show:

- `awaiting_approval` execution status
- approval gate step state
- linked approval context when available
- resumed simulation after approval
- denied/expired stop behavior
- skipped later steps after denial/expiration
- simulation-only `simulated=true` and `executed=false` semantics

## Scope

- Improve PlaybooksPanel execution timeline labels for:
  - `approval_requested`
  - `approval_approved`
  - `approval_resumed`
  - `approval_denied`
  - `approval_expired`
  - `skipped_after_approval_gate`
  - aborted/failed approval gate states
- Show a prominent message for awaiting approval:
  - “Approval-gated simulation paused; no later steps will run until approval.”
- Show linked approval context from `steps_log` fields when available, such as
  `approval_request_id`, `approval_status`, `risk_level`, and gate messages.
- Add focused frontend tests for read-only rendering.
- Add backend read API polish only if the existing execution detail response lacks required
  stored fields.

## Out of Scope

- No implementation code as part of this proposal.
- No real execution.
- No approval/deny controls inside PlaybooksPanel.
- No playbook run, retry, resume, or cancel controls.
- No executor behavior changes.
- No approval decision behavior changes.
- No schema changes unless absolutely required and additive.
- No daemon, systemd service, scheduler, or worker changes.
- No ingest, detection, or correlation changes.
- No SOAR queue changes.
- No Slack, email, PagerDuty, webhook, firewall, or blocklist integration.
- No firewall/blocklist mutation.

## Success Criteria

- Analysts can identify approval-gated executions in `awaiting_approval` state.
- Approval requested, approved, resumed, denied, expired, and skipped states render with
  clear labels and explanatory copy.
- Linked approval IDs/status/risk are visible when present in existing API data.
- The UI clearly communicates simulation-only behavior and does not imply real remediation.
- No mutation controls are introduced.
- Existing PlaybooksPanel definition management behavior remains unchanged.
- Existing approval UI/routes, executor behavior, SOAR queue, ingest, detection, and
  correlation behavior remain unchanged.
