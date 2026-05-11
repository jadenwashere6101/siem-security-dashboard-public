# Proposal: SOAR Integration Adapter Status Frontend

## Problem

The backend `GET /integrations/status` endpoint already exists and returns adapter names,
supported actions, mode, simulated status, and real-mode disabled state. However, there is
no frontend panel or section where analysts or super-admins can inspect this information.
Verifying adapter visibility currently requires direct API inspection or code review.

## Goal

Add a read-only frontend panel that calls `GET /integrations/status` and displays the
simulation adapter registry state: which adapters are registered, which actions they support,
that the system is running in simulation mode, and that real mode is disabled.

The panel must make it visually clear that no real integrations are active.

## Scope

- Add a frontend service helper for `GET /integrations/status`.
- Add a read-only `IntegrationStatusPanel` component showing adapter names, supported
  actions, mode, simulated status, and real-mode disabled state.
- Add loading, error, and empty states.
- Add frontend tests covering read-only rendering, state transitions, and the labeling
  that simulation mode is active and real mode is disabled.

## Out of Scope

- No implementation code in this proposal.
- No backend changes.
- No schema changes.
- No real integrations.
- No mutation controls of any kind.
- No test-connection, run-adapter, or execute buttons.
- No executor behavior changes.
- No SOAR queue changes.
- No playbook execution changes.
- No ingest, detection, or correlation changes.

## Success Criteria

- Authenticated analyst and super-admin users can view integration adapter status in the
  frontend without leaving the dashboard.
- The panel clearly labels the system as running in simulation mode.
- The panel clearly states that real mode is disabled.
- Each adapter row shows its name and supported actions.
- The panel renders a useful empty state when no adapters are returned.
- The panel renders a user-friendly error state if the API call fails.
- No mutation controls, connect buttons, or test buttons are present anywhere in the panel.
- Existing Playbooks, SOAR Queue, Approvals, and Incidents panel tests remain unaffected.
- No backend, schema, executor, or queue files are modified.
