# Proposal: SOAR Worker Run UI Control

## Problem

Admins can inspect SOAR queue health from the frontend, and the backend now has a
safe admin-only endpoint to run one worker batch manually. There is still no UI
control for that endpoint, so admins must use API tooling when they want to drain
a small batch without running the CLI.

Because this control mutates queue rows by invoking normal worker processing, the
first UI must make the safety boundary obvious: manual run, simulation only, one
batch only.

## Goal

Add a safe frontend admin control that calls:

```text
POST /admin/soar/worker/run-once
```

The control should:

- live in the existing SOAR Queue panel
- clearly label the operation as simulation/manual
- allow a small batch size input or use the backend default
- prevent duplicate in-flight requests
- show the returned summary after a run
- refresh queue status and recent items after a successful run
- handle loading and error states safely

## Scope

In scope:

- frontend service method for run-once
- read/write UI control inside the admin-only SOAR queue surface
- optional batch size input with conservative constraints
- run result summary display
- queue refresh after success
- loading/disabled/error states
- frontend build verification
- component/service tests only if the existing setup supports them without broad
  test infrastructure work

Out of scope:

- no real mode toggle
- no real firewall execution
- no retry/replay individual item controls
- no daemon or scheduler controls
- no playbooks/incidents UI
- no backend changes unless absolutely required
- no schema changes
- no ingest/detection/correlation changes

## Safety Requirements

- UI must clearly say the run is manual and simulation-only.
- UI must not expose a real execution option.
- UI must send only one `POST` to `/admin/soar/worker/run-once` per click.
- Button must be disabled while the request is in flight.
- Errors must show concise user-safe messages, not raw stack traces.
- Control should appear only where the current admin SOAR Queue panel is already
  accessible.
- The UI must not add retry, replay, cancel, delete, or per-row execution
  controls.

## Success Criteria

- Admin users can manually run one simulation worker batch from the SOAR Queue
  panel.
- The UI shows processed/success/failed/skipped/requeued summary counts returned
  by the backend.
- Queue counts and recent queue rows refresh after a successful run.
- Double-clicks do not send duplicate requests while a run is active.
- No real adapter or firewall controls are added.
- Frontend build passes.
