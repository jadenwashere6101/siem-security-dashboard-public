# Proposal: SOAR Playbook Execution Visibility Polish

## Problem

Playbook executions can now move beyond inert pending records: the manual simulation-only
executor writes `steps_log` entries with `simulated: true` and transitions executions through
`pending`, `running`, `success`, and `failed`. The existing Playbooks panel shows execution
rows and raw details, but it does not yet present simulated step progress, status transitions,
or execution context in an analyst-friendly timeline.

Operators need clearer visibility into what the simulation executor did without adding any
execution controls or changing executor behavior.

## Goal

Improve read-only visibility into simulated playbook executions by surfacing:

- execution status and status meaning
- linked `playbook_id`, `alert_id`, and `incident_id`
- created/started/completed timestamps
- `last_completed_step`
- readable `steps_log` timeline entries
- per-step `simulated` and `executed` flags
- failure messages and error codes

The UI should make it clear that the displayed actions are simulation results only.

## Scope

- Improve execution detail rendering in `PlaybooksPanel`.
- Add clearer summaries for `pending`, `running`, `success`, `failed`, and `abandoned`.
- Render `steps_log` as a readable timeline-style section.
- Show execution context fields and timestamps in compact key/value layout.
- Keep raw JSON available only if useful as secondary detail.
- Add focused frontend tests for rendering timeline/status/context states.
- Add backend response polish only if the current execution detail API lacks required fields.

## Out of Scope

- No implementation code as part of this proposal.
- No schema changes.
- No executor behavior changes.
- No daemon/systemd worker.
- No real integrations.
- No queue enqueueing.
- No approvals.
- No firewall/blocklist mutation.
- No ingest, detection, or correlation changes.
- No run, retry, cancel, replay, approve, or execute controls.
- No automatic refresh/polling loop unless already consistent with the panel.

## Success Criteria

- Execution details show status, context IDs, timestamps, and `last_completed_step`.
- `steps_log` entries render as readable timeline rows/cards.
- Each timeline step shows action, status, simulation mode, simulated/executed flags, message,
  and error details when present.
- Pending/running executions without steps show a useful empty state.
- Failed simulated steps are easy to identify.
- No mutation controls are added.
- No executor or backend behavior changes are required unless response shape is missing a
  field already stored in `playbook_executions`.
- Existing Playbooks definition management, SOAR queue, approval, incident, and executor
  tests remain unchanged.
