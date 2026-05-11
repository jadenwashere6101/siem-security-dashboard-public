# Proposal: SOAR Playbook Frontend Visibility

## Problem

SOAR playbook definitions and execution records can now be read through backend APIs, but
there is no frontend surface for analysts to inspect them. Operators still need direct API
or database access to understand which playbooks are configured and what execution records
exist.

This limits visibility during the safe foundation phase, especially because no executor or
ingest wiring exists yet. Analysts need a read-only dashboard view before any controls or
automation are added.

## Goal

Add frontend read-only visibility for SOAR playbook definitions and playbook executions
using the existing backend read APIs:

- `GET /playbooks`
- `GET /playbooks/<id>`
- `GET /playbook-executions`
- `GET /playbook-executions/<id>`

The UI should let analysts inspect definitions and execution records without creating,
editing, running, retrying, cancelling, approving, or enqueueing anything.

## Scope

- Frontend API service functions for playbook definition and execution read endpoints.
- A modular read-only Playbooks panel/page/component.
- Simple tables or compact cards for definitions and execution records.
- Optional detail view for selected definition or execution records.
- Loading, refreshing, error, and empty states.
- Filters that map to existing read API query params where useful.
- Tests for rendering, API calls, read-only behavior, and error/empty states.
- Navigation/tab entry only if consistent with the current dashboard pattern.

## Out of Scope

- No implementation code as part of this proposal.
- No backend changes.
- No schema changes.
- No playbook create/update/delete UI.
- No executor controls.
- No run, retry, cancel, replay, or approve buttons.
- No ingest route wiring.
- No detection or correlation changes.
- No SOAR queue changes.
- No Slack, email, firewall, or other integration work.
- No real execution mode.

## Success Criteria

- Authorized analysts can open a frontend playbook visibility view.
- The view loads playbook definitions from `GET /playbooks`.
- The view loads execution records from `GET /playbook-executions`.
- Definitions and executions render with stable, readable fields.
- Loading, error, refresh, and empty states are handled.
- Optional detail views use only `GET /playbooks/<id>` and
  `GET /playbook-executions/<id>`.
- No frontend code calls POST, PUT, PATCH, or DELETE for playbooks.
- No UI element implies execution, retry, cancellation, approval, creation, editing, or
  deletion.
- Existing SOAR queue, incident, approval, dashboard, and auth behavior is unchanged.
