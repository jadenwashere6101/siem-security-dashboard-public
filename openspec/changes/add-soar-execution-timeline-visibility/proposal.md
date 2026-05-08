# Proposal: SOAR Execution Timeline Visibility (Phase 2.5G)

## Problem

The SOAR Queue detail view shows a queue item's current state and its most recent linked
approval (Phase 2.5F). It does not show the sequence of events that led to that state.

An operator looking at a `skipped` queue item sees: status `skipped`, `last_error: approval
denied`. They cannot see when the action was originally queued, when the approval was
requested, who denied it, or when the skip was materialized. To reconstruct that sequence
they must navigate to the Approvals panel, find the approval by queue_id, and read the event
history there.

For an `awaiting_approval` item: the operator can see the approval is pending, but has no
sense of how long it has been waiting or when it will expire from looking at the queue panel
alone.

All of the data to answer these questions already exists:
- `response_actions_queue.created_at` — when the action entered the queue
- `approval_request_events` — every approval state transition with timestamps and comments
- `response_actions_queue.updated_at` + `status` — when the queue row last changed (reliable
  as a terminal event timestamp since terminal transitions happen once and don't overwrite)

No additional database tables or columns are needed.

## This change

Phase 2.5G adds a read-only "Execution Timeline" section to the `SoarQueuePanel` detail
view. The timeline assembles a chronological event sequence from three sources already in
the queue detail response:

1. `queue.created_at` — always first: "Action queued."
2. `approval_events` — each approval state transition in order: requested → approved/denied/
   expired. Includes decision comments where present.
3. `queue.updated_at` + `queue.status` — terminal event (skipped/failed/success), only
   emitted when the queue row is in a terminal state.

Two targeted backend additions make `approval_events` available in the queue detail
response:

1. **New `list_approval_events(conn, approval_request_id)`** in `core/approval_store.py`.
   Fetches `approval_request_events` rows for a given approval, ordered `created_at ASC`.
   This mirrors what `get_approval_request` already does internally.

2. **`GET /admin/soar/queue/<id>` extended**: after fetching the linked approval
   (already added in Phase 2.5F), call `list_approval_events` and include the result as
   `approval_events: [...]` in the response. Also add `created_at` to
   `_serialize_approval_summary` (non-breaking — just one more field).

No schema changes. No new tables. No new indexes.

## In scope

- `core/approval_store.py` — new `list_approval_events` function.
- `routes/admin_routes.py` — import `list_approval_events`, add `created_at` to
  `_serialize_approval_summary`, add `approval_events` to `get_queue_item_detail` response.
- `frontend/src/components/SoarQueuePanel.js` — timeline section + `buildTimeline` helper
  function + `getTimelineDotColor` helper + style constants.
- `tests/test_approval_store.py` — tests for `list_approval_events`.
- `tests/test_soar_worker_admin_run_control.py` — tests for `approval_events` field and
  `latest_approval.created_at` in queue detail response.
- `frontend/src/components/SoarQueuePanel.test.js` — timeline rendering tests.

## Out of scope

- `response_actions_log` — keyed by `alert_id`, not `queue_id`. No reliable per-queue-item
  attribution until real adapters are built in Phase 3. Not included.
- No approve/deny controls in queue panel.
- No worker behavior changes.
- No scheduler or daemon.
- No changes to `ApprovalsPanel.js` — it already has its own event history table.
- No changes to `approval_routes.py`, `soarQueueService.js`, or `approvalService.js`.
- No new database tables, columns, or indexes.

## Role access

`GET /admin/soar/queue/<id>` is already `super_admin_required`. The `approval_events` field
appears in the same response — no new role gate needed.

## Success criteria

- `GET /admin/soar/queue/<id>` returns `approval_events: []` when no linked approval exists.
- `GET /admin/soar/queue/<id>` returns `approval_events` with the correct events — ordered
  `created_at ASC` — when a linked approval exists.
- `latest_approval.created_at` is present in the response (non-breaking addition to existing
  summary).
- The SoarQueuePanel detail view always renders an "Execution Timeline" section for a loaded
  queue item.
- Timeline always includes at least one event: "Action queued" at `queue.created_at`.
- Approval events render in timeline order with correct labels and comments.
- Terminal events ("Action skipped", "Action failed", "Action executed") render only when
  `queue.status` is in `{skipped, failed, success}`.
- No approve/deny button appears in the timeline or anywhere in the queue detail view.
- All existing queue, approval, and route tests pass unchanged.
