# Proposal: SOAR Queue Visibility UI

## Problem

Admins can now inspect SOAR queue health through read-only backend endpoints, but
there is no frontend surface for that information. Without UI visibility, admins
still need API tools or direct database access to understand whether actions are
pending, running, failing, skipped, or completing successfully.

The first UI should be read-only. It should expose queue health and recent queue
items without adding retry, replay, cancel, or worker execution controls.

## Goal

Add a frontend admin UI for SOAR queue visibility using the existing read-only
backend endpoints:

- `GET /admin/soar/queue/status`
- `GET /admin/soar/queue/recent`
- `GET /admin/soar/queue/<id>`

The UI should show:

- queue counts by status
- recent queue items
- action
- status
- `source_ip`
- `alert_id` or `"Deleted alert"` / `"N/A"`
- `retry_count / max_retries`
- `created_at / updated_at`

## Scope

In scope:

- frontend service methods for queue status, recent items, and optional detail
- read-only admin panel/page/component
- loading state
- error state
- empty state
- safe nullable `alert_id` rendering
- tests where the current frontend test setup supports them
- frontend build verification

Out of scope:

- no retry/replay buttons
- no worker execution button
- no real firewall execution UI
- no playbooks/incidents UI
- no schema changes
- no backend endpoint changes unless absolutely required by implementation
- no ingest/detection/correlation changes

## Safety Requirements

- UI must be read-only.
- UI must not call mutation endpoints.
- UI must not expose `idempotency_key` in list view.
- Detail view may show `idempotency_key` only if the backend detail endpoint
  already exposes it and only inside the admin-only UI.
- Nullable `alert_id` must render as `"Deleted alert"` or `"N/A"` without
  crashing.
- Missing queue detail must show a normal error/empty state, not a broken page.

## Success Criteria

- Admin users can see queue status counts and recent queue items.
- The panel handles loading, error, and empty states.
- Queue item rows with `alert_id: null` render safely.
- No execute/retry/cancel controls are introduced.
- Existing admin frontend behavior remains unchanged.
- `npm run build` passes.

