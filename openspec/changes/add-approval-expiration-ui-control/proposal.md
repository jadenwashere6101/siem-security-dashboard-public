# Proposal: Approval Expiration UI Control (Phase 2.5E)

## Problem

Phase 2.5D added `POST /admin/soar/approvals/expire-pending` — a `super_admin`-only endpoint
that expires all overdue pending approvals and sweeps linked `awaiting_approval` queue rows to
`skipped` in one atomic operation. The endpoint works. It is not reachable from the UI.

The gap: a super_admin who wants to clean up stale approvals must invoke the endpoint via curl
or a shell script. There is no in-panel button. The Approvals panel already lists expired
approvals and supports the `expired` filter, but there is no way to trigger the expiration
sweep from within the panel itself.

Two visible consequences before this change:

1. An approval's `expires_at` has passed. The panel shows `pending`. The super_admin knows
   it is overdue. To materialize the transition they must leave the UI and call the endpoint
   manually, then return and refresh.

2. A queue row is stuck in `awaiting_approval`. Its linked approval expired but the panel
   still shows both as unresolved. The super_admin cannot trigger cleanup from here.

The underlying state machine is correct. The admin endpoint is correct. The only missing
piece is a button that calls it.

## This change

Phase 2.5E adds a super-admin-only "Expire overdue" button to `ApprovalsPanel.js`. The button
calls `expireOverdueApprovals()` (a new function in `approvalService.js`), shows inline
feedback (count summary on success, inline error on failure), and refreshes the approval list
on success. Analyst users see no change — the button is gated to `isSuperAdmin`.

Separate from the per-row Approve/Deny controls, this is an operational sweep control. It has
no per-row targeting: one click expires every overdue approval and sweeps every linked queue
row that has a terminal approval.

## In scope

- `frontend/src/services/approvalService.js` — new `expireOverdueApprovals()` function.
- `frontend/src/components/ApprovalsPanel.js` — button + state + handler.
- `frontend/src/services/approvalService.test.js` — test for `expireOverdueApprovals`.
- `frontend/src/components/ApprovalsPanel.test.js` — tests for button visibility,
  loading state, success feedback, list refresh, and error display.

## Out of scope

- No backend changes. `POST /admin/soar/approvals/expire-pending` is already implemented.
- No changes to `GET /approvals` or `GET /approvals/<id>`.
- No changes to per-row Approve/Deny controls.
- No scheduler, cron, polling, or auto-trigger.
- No changes to `SoarQueuePanel.js` — the queue panel is a separate component.
- No changes to `soarQueueService.js`.
- No Python file changes.

## Role access

- Analyst: button is not rendered. No change to analyst view.
- Super_admin: button is rendered in the panel header controls area, alongside Refresh.

## Success criteria

- `expireOverdueApprovals()` POSTs to `/admin/soar/approvals/expire-pending` with
  `credentials: "include"` and `Content-Type: application/json`. Returns parsed response.
  Throws with backend error message on non-OK response.
- Button labeled "Expire overdue" only renders when `isSuperAdmin`.
- Button is disabled while the request is in-flight (`isExpiring === true`). Label changes
  to "Expiring..." while in-flight.
- On success: inline summary appears — "Expired N approvals, N queue rows skipped" — and the
  approval list refreshes via `loadApprovalList({ quiet: true })`.
- On failure: inline error message appears. List is not refreshed.
- After the next list load (triggered by success or by the Refresh button), the inline
  summary and error are cleared.
- All existing approval panel tests pass unchanged.
- `approvalService.js` does not call `conn.commit()` (it is a frontend file; stated to confirm
  no accidental copy of backend patterns).
