# Proposal: Show Approval-Gated Queue Status in SOAR Queue UI

## Problem

`block_ip` actions are now approval-gated. When the worker processes a `block_ip` queue row
and no approval exists yet, it creates an approval request and moves the queue row to
`awaiting_approval` — the worker will not execute the action until the linked approval is
decided. This status already exists in the database, and the backend already returns it in
status counts and accepts it as a filter value.

But `SoarQueuePanel.js` does not know about this status. The `QUEUE_STATUSES` constant
contains only `["pending", "running", "success", "failed", "skipped"]`. Consequences:

- The status counts grid does not display an `awaiting_approval` count tile. The count is
  present in the API response but silently ignored.
- The status filter dropdown does not include `awaiting_approval`. Super admins cannot filter
  the recent queue list to show only these items.
- Queue rows in `awaiting_approval` state render with the neutral fallback badge style —
  visually indistinct from an unknown or unrecognized status.
- The total count shown in the panel is computed from `QUEUE_STATUSES` when the API total is
  absent; this fallback sum also omits `awaiting_approval` rows.
- The detail view for a selected `awaiting_approval` item provides no explanation — an admin
  sees status "awaiting approval" with no context about what that means or where to act.

The result: a super admin viewing the SOAR queue while a `block_ip` action is waiting for
approval gets an incomplete picture. The action appears to have vanished from the queue or
stalled with no explanation.

## This change

Update `SoarQueuePanel.js` and its tests to correctly handle `awaiting_approval` as a first-
class queue status. All changes are UI-only — the backend already supports this status fully.

## In scope

- Add `"awaiting_approval"` to the `QUEUE_STATUSES` constant so the status counts grid shows
  the count, the filter dropdown includes the option, and the fallback total is accurate.
- Add a distinct badge style for `awaiting_approval` — visually different from pending,
  running, and skipped.
- Add a contextual note in the detail panel when the selected item has
  `status === "awaiting_approval"`, directing the admin to the Approvals panel to act.
- Update `SoarQueuePanel.test.js` to cover the new badge, the filtered empty state, and the
  detail note.

## Out of scope

- No backend changes. The backend already returns `awaiting_approval` in counts, accepts it
  as a filter, and serializes it in queue rows.
- No approve/deny controls inside the queue panel. Approval decisions belong to ApprovalsPanel.
- No linking from the queue detail to a specific approval record. The queue detail serializer
  does not return `approval_request_id` — adding that field is a backend change outside this
  scope.
- No queue mutation controls of any kind.
- No worker changes.
- No changes to ApprovalsPanel.
- No playbook, ingest, detection, or correlation changes.
- No new service functions. `soarQueueService.js` already passes the status filter string
  through to the backend — passing `"awaiting_approval"` works without modification.

## Role access

No change. `SoarQueuePanel` is already gated to `isSuperAdmin` in `App.js`. This change
does not alter that gate or introduce new role checks.

## Success criteria

- Frontend build passes with no new errors.
- The status counts grid shows an `awaiting_approval` tile with the correct count from the
  API response.
- The status filter dropdown includes `awaiting_approval` as a selectable option.
- Selecting the `awaiting_approval` filter and receiving an empty result renders the filtered
  empty state: "No queued SOAR actions found for this filter."
- Queue rows with `status: "awaiting_approval"` display a distinctive badge — not the neutral
  fallback style.
- In the detail view for an `awaiting_approval` item, a note is visible explaining that the
  action is waiting for approval and directing the admin to the Approvals panel.
- No note appears in the detail view for items with any other status.
- `SoarQueuePanel.test.js` includes tests for: the `awaiting_approval` badge, the filtered
  empty state, and the approval-waiting detail note.
- All existing `SoarQueuePanel.test.js` tests continue to pass.
- No changes to `soarQueueService.js`, ApprovalsPanel.js, or any backend file.
