# Proposal: Link Approvals and Queue Visibility (Phase 2.5F)

## Problem

The approval system and the SOAR queue are tightly coupled operationally — every
`block_ip` queue row has a linked `approval_requests` record — but the two UI panels are
visually disconnected. Navigating between them requires knowing the cross-reference ID by
memory.

**ApprovalsPanel detail view**: shows `queue_id` as a plain number labeled "Queue ID".
An analyst or super_admin looking at Approval #7 knows the queue item number, but cannot
see whether that queue row is still in `awaiting_approval`, has been `skipped` because the
approval expired, or has been promoted to `running`. They must manually navigate to the
Queue panel and search.

**SoarQueuePanel detail view**: shows `awaiting_approval` status and a note to "open the
Approvals panel." An admin looking at Queue Item #42 in `awaiting_approval` cannot see the
linked approval's ID, status, or expiry without navigating to the Approvals panel and
scanning for the matching row. There is no approval ID or status surfaced here at all —
the backend endpoint (`GET /admin/soar/queue/<id>`) does not return any approval data.

In both cases the cross-reference exists in the database but is invisible in the UI.

## This change

Phase 2.5F adds read-only cross-reference context in both directions — one backend addition
and two frontend improvements.

**1. Backend: Add `latest_approval` summary to `GET /admin/soar/queue/<id>`.**

The existing `get_latest_approval_for_queue_action(conn, queue_id, action)` function in
`core/approval_store.py` already fetches the most recent approval for a (queue_id, action)
pair. The queue detail route calls it, serializes a minimal summary (id, status, risk_level,
expires_at, decided_at), and includes it as `latest_approval` in the JSON response. Returns
`null` for queue items with no linked approval.

No approval route is modified. No mutation is added.

**2. SoarQueuePanel: Show approval context in the detail view.**

When `selectedQueueItem.latest_approval` is non-null, render an "Linked Approval" subsection
below the existing detail fields. Shows: Approval ID, Approval Status, Risk, Expires, Decided.
Read-only. No approve/deny controls. No navigation links.

**3. ApprovalsPanel: Improve queue cross-reference display.**

The approval detail already returns `queue_id`. Rename the "Queue ID" field label to "Linked
Queue Item" and add a conditional note when `queue_id` is non-null: "This approval is linked
to Queue Item #{N}. Open the SOAR Queue panel to view its current execution status." This is
a frontend-only improvement — `approval_routes.py` is not modified.

## In scope

- `routes/admin_routes.py` — import + `_serialize_approval_summary` helper +
  `get_queue_item_detail` update.
- `frontend/src/components/SoarQueuePanel.js` — linked approval subsection + styles.
- `frontend/src/components/ApprovalsPanel.js` — label rename + queue link note + style.
- `tests/test_soar_worker_admin_run_control.py` — tests for `latest_approval` in queue
  detail response.
- `frontend/src/components/SoarQueuePanel.test.js` — tests for approval context rendering.
- `frontend/src/components/ApprovalsPanel.test.js` — tests for queue link note.

## Out of scope

- No approve/deny controls in `SoarQueuePanel`.
- No queue mutation controls.
- No changes to `approval_routes.py` — approval read routes stay unchanged.
- No changes to `GET /approvals` or `GET /approvals/<id>`.
- No changes to the worker, playbook, or scheduler.
- No changes to `approvalService.js` or `soarQueueService.js`.
- No real execution.
- No ingest, detection, or correlation changes.

## Role access

- `GET /admin/soar/queue/<id>` is already `super_admin_required`. The `latest_approval`
  field appears in the same response — no new role gate needed.
- ApprovalsPanel is already `analyst_or_super_admin_required`. The queue link note renders
  for both roles when `queue_id` is present — it is informational text only.
- `SoarQueuePanel` is already accessible to the roles that can reach the queue panel. No
  role change needed.

## Success criteria

- `GET /admin/soar/queue/<id>` returns `latest_approval: null` when no approval exists for
  the (queue_id, action) pair.
- `GET /admin/soar/queue/<id>` returns `latest_approval: { id, status, risk_level,
  expires_at, decided_at }` when an approval exists.
- SoarQueuePanel detail view renders the "Linked Approval" subsection only when
  `latest_approval` is non-null.
- SoarQueuePanel detail view renders no "Linked Approval" subsection for queue items with
  no linked approval (pending, running, success, failed, skipped with no approval history).
- ApprovalsPanel renders queue link note only when `selectedApproval.queue_id` is non-null.
- ApprovalsPanel renders no queue link note when `queue_id` is null.
- No approve/deny control appears in `SoarQueuePanel`.
- All existing queue store, approval store, route, and worker tests pass unchanged.
