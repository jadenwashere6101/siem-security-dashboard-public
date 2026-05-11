# Proposal: SOAR Playbook Definition UI

## Problem

The frontend Playbooks panel currently provides read-only visibility into playbook
definitions and execution records. Backend definition-management APIs now exist, but
super admins still do not have a safe UI for creating, editing, or enabling/disabling
definitions.

Operators need a controlled frontend workflow for preparing playbook definitions before
execution exists. Analysts must remain read-only, and the UI must not imply that playbooks
can run.

## Goal

Add super-admin-only frontend controls for SOAR playbook definition management:

- create a playbook definition
- edit an existing playbook definition
- enable or disable an existing playbook definition

The controls should use the backend definition-management APIs only:

- `POST /playbooks`
- `PUT /playbooks/<id>`
- `PATCH /playbooks/<id>/enabled`

No playbook execution, queue enqueueing, retry, cancel, or run controls should be added.

## Scope

- Extend `frontend/src/services/playbookService.js` with definition-management API helpers.
- Extend `frontend/src/components/PlaybooksPanel.js` with super-admin-only management
  controls.
- Validate ID, name, trigger JSON, steps JSON, and enabled boolean before submitting.
- Keep analyst users read-only.
- Show safe success/error feedback after create, edit, and enable/disable operations.
- Refresh definition data after successful mutations.
- Add frontend tests for super-admin controls, analyst no-controls behavior, service calls,
  validation errors, and no execution controls.

## Out of Scope

- No implementation code as part of this proposal.
- No backend changes.
- No schema changes.
- No playbook executor.
- No run, retry, cancel, replay, or approve buttons.
- No creation of `playbook_executions`.
- No ingest route wiring.
- No correlation wiring.
- No detection or correlation changes.
- No SOAR queue changes.
- No Slack, email, firewall, or other integration work.
- No real execution mode.

## Success Criteria

- Super admins can see create/edit/enable-disable controls in the Playbooks panel.
- Analysts can still inspect playbooks but see no mutation controls.
- Service helpers call only `POST /playbooks`, `PUT /playbooks/<id>`, and
  `PATCH /playbooks/<id>/enabled` for definition management.
- The form validates malformed JSON and required fields before calling the API.
- Successful mutations refresh the definitions list and keep execution records untouched.
- The UI clearly labels management as definition configuration only.
- No UI element implies playbook execution exists.
- Existing SOAR queue, incident, approval, dashboard, and read-only playbook behavior remains
  unchanged.
