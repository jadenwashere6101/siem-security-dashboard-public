# Proposal: SOAR Queue Item Detail UI

## Problem

The SOAR Queue panel shows queue health and recent queue rows, but admins cannot
inspect the full details for a specific queue item from the UI. The backend
already exposes a read-only detail endpoint, and the list view intentionally
keeps sensitive or noisy fields such as `idempotency_key` out of the table.

Admins need a focused detail view for investigation without adding mutation
controls or queue management actions.

## Goal

Add a read-only queue item detail view to the existing SOAR Queue UI using:

```text
GET /admin/soar/queue/<id>
```

The detail view should show:

- queue id
- alert reference
- action
- status
- `source_ip`
- `retry_count / max_retries`
- `last_error`
- `created_at / updated_at`
- `idempotency_key` only in detail view

## Scope

In scope:

- detail selection behavior in `SoarQueuePanel`
- clickable or viewable recent queue rows
- detail fetch using the existing `loadSoarQueueItem(queueId)` service method
  if present
- loading state for selected item detail
- error state for selected item detail
- safe formatting for nullable `alert_id`
- safe wrapping/truncation for long `last_error` and `idempotency_key`
- frontend build verification
- service/component tests only if current setup supports them without broad
  setup changes

Out of scope:

- no retry/replay/cancel buttons
- no worker execution from detail view
- no real firewall actions
- no backend changes unless absolutely required
- no schema changes
- no ingest/detection/correlation changes
- no playbooks/incidents UI

## Safety Requirements

- Detail view must be read-only.
- Nullable `alert_id` must render as `"Deleted alert"` or `"N/A"` safely.
- List view must continue to omit `idempotency_key`.
- Detail view may show `idempotency_key` because the endpoint is admin-only.
- Errors must render as concise UI messages, not raw stack traces or broken
  markup.
- No mutation controls may be added to the detail view.

## Success Criteria

- Admin users can select a recent queue item and view its read-only details.
- Detail data is fetched from `GET /admin/soar/queue/<id>`.
- Loading, error, and empty/no-selection states are handled.
- `alert_id: null` renders safely.
- `idempotency_key` appears only in the detail view, not in the list table.
- No backend, schema, ingest, detection, or correlation changes are introduced.
- Frontend build passes.
