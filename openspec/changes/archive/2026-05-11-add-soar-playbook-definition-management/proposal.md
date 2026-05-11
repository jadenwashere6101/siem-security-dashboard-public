# Proposal: SOAR Playbook Definition Management

## Problem

SOAR playbook definitions can be inspected through read-only APIs and frontend visibility,
but operators still cannot safely create or maintain definitions through the backend API.
Direct database edits are risky because step action names, trigger shape, and enabled state
can drift away from the validation rules used by the playbook foundation.

There is still no executor and no ingest/correlation wiring. Definition management must
therefore configure future policy only; it must not run anything or create execution records.

## Goal

Add controlled backend APIs for managing SOAR playbook definitions without enabling
execution:

- create a playbook definition
- update an existing playbook definition
- enable or disable a playbook definition
- continue supporting inspection through the existing read APIs

All mutation must validate playbook steps through `engines/playbook_registry.py` and use
existing `core/playbook_store.py` patterns.

## Scope

- Backend API endpoints for playbook definition create/update/enable-disable.
- Super-admin-only mutation behavior.
- Analyst read-only access remains unchanged.
- Store helper additions for definition update and enabled-state changes.
- Validation for ID, name, trigger config, steps, enabled value, and supported step actions.
- Tests for successful admin mutations.
- Tests proving analysts/viewers/unauthenticated users cannot mutate.
- Tests proving mutations do not create executions, enqueue actions, or execute steps.

## Out of Scope

- No implementation code as part of this proposal.
- No frontend changes.
- No schema changes unless implementation proves a tiny additive column is required.
- No playbook executor.
- No step execution.
- No ingest route wiring.
- No correlation wiring.
- No queue enqueueing.
- No Slack, email, firewall, or other integration work.
- No real execution mode.
- No changes to SOAR queue, approvals, incidents, protected targets, or dry-run adapter
  behavior.

## Success Criteria

- Only `super_admin` users can create, update, enable, or disable playbook definitions.
- Analysts can keep using existing read-only playbook endpoints but receive `403` for
  mutation attempts.
- Viewers and unauthenticated callers cannot mutate definitions.
- Create and update requests validate steps with `validate_playbook_steps`.
- Invalid payloads return safe `400` responses without partial writes.
- Duplicate definition IDs return a safe conflict response.
- Updating or enabling a definition does not create `playbook_executions`.
- Updating or enabling a definition does not enqueue SOAR actions.
- Updating or enabling a definition does not call trigger matching, executor, detection,
  correlation, ingest, queue worker, approvals, incidents, or integrations.
- Existing read APIs and frontend visibility behavior remain unchanged.
