# Design: Show Approval-Gated Queue Status in SOAR Queue UI

---

## Current state (context only)

`SoarQueuePanel.js` drives all queue status rendering from a single constant at the top of
the file:

```javascript
const QUEUE_STATUSES = ["pending", "running", "success", "failed", "skipped"];
const QUEUE_STATUS_FILTERS = ["all", ...QUEUE_STATUSES];
```

`QUEUE_STATUSES` is used in three places:
1. Building `QUEUE_STATUS_FILTERS` for the dropdown.
2. The status counts grid (`countsGridStyle` section).
3. The fallback total calculation when `statusSummary?.total` is absent.

`getStatusBadgeStyle(status)` maps five status strings to five badge style objects and falls
through to `neutralBadgeStyle` for anything unrecognized.

The backend (`GET /admin/soar/queue/status`) already includes `awaiting_approval` in the
`counts` dict and the `total`. The `GET /admin/soar/queue/recent` endpoint already accepts
`awaiting_approval` as a valid `status` filter param. The queue row serializer already
returns `status: "awaiting_approval"` for items in that state. No backend changes are needed.

The `formatQueueLabel` utility:
```javascript
const formatQueueLabel = (value) =>
  String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
```
Already converts `"awaiting_approval"` → `"Awaiting Approval"` correctly. No change needed.

---

## Changes to `frontend/src/components/SoarQueuePanel.js`

### 1. Update `QUEUE_STATUSES` constant

Current:
```javascript
const QUEUE_STATUSES = ["pending", "running", "success", "failed", "skipped"];
```

Change to:
```javascript
const QUEUE_STATUSES = ["pending", "running", "awaiting_approval", "success", "failed", "skipped"];
```

**Effect:** The `awaiting_approval` tile appears in the status counts grid. The filter
dropdown gains the `"Awaiting Approval"` option. The fallback total sum includes these rows.

The ordering places `awaiting_approval` between `running` and `success` — reflecting the
lifecycle order: a running action that requires approval transitions to `awaiting_approval`
before it can reach `success` or `skipped`.

### 2. Add badge style for `awaiting_approval`

Add a new style constant alongside the existing badge style objects:

```javascript
const awaitingApprovalBadgeStyle = {
  color: "#fb923c",
  backgroundColor: "rgba(251, 146, 60, 0.12)",
  border: "1px solid rgba(251, 146, 60, 0.3)",
};
```

Orange-amber tone. Distinct from:
- pending (yellow `#f5d487`)
- running (blue `#93c5fd`)
- success (green `#7ee787`)
- failed (red `#fca5a5`)
- skipped (gray `#c9d1d9`)

Update `getStatusBadgeStyle`:

```javascript
const getStatusBadgeStyle = (status) => {
  if (status === "pending") return pendingBadgeStyle;
  if (status === "running") return runningBadgeStyle;
  if (status === "awaiting_approval") return awaitingApprovalBadgeStyle;
  if (status === "success") return successBadgeStyle;
  if (status === "failed") return failedBadgeStyle;
  if (status === "skipped") return skippedBadgeStyle;
  return neutralBadgeStyle;
};
```

### 3. Add approval-waiting note in the detail view

The detail panel renders fields for the selected queue item. Add a conditional block inside
the detail render, directly after the existing `DetailField` entries and before the closing
tag of `detailGridStyle`:

```javascript
{selectedQueueItem.status === "awaiting_approval" ? (
  <div style={approvalWaitingNoteStyle}>
    This action is paused and waiting for approval before it can execute. To review and
    decide, open the Approvals panel.
  </div>
) : null}
```

Add the corresponding style constant:

```javascript
const approvalWaitingNoteStyle = {
  gridColumn: "1 / -1",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(251, 146, 60, 0.3)",
  backgroundColor: "rgba(251, 146, 60, 0.08)",
  color: "#fb923c",
  fontSize: "13px",
  lineHeight: "1.5",
};
```

`gridColumn: "1 / -1"` ensures the note spans all columns in the `detailGridStyle` grid
(`gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))"`) instead of occupying just
one cell.

The note does not link to a specific approval record because the queue detail serializer
does not return `approval_request_id`. The note is informational text only. No anchor tag,
no programmatic navigation — the admin reads the note and navigates manually.

---

## Resulting UI behavior

### Status counts grid

Before (5 tiles): Pending | Running | Success | Failed | Skipped | Total

After (6 tiles): Pending | Running | Awaiting Approval | Success | Failed | Skipped | Total

The grid uses `repeat(auto-fit, minmax(130px, 1fr))`, which handles the extra tile without
layout changes.

### Status filter dropdown

Before: All | Pending | Running | Success | Failed | Skipped

After: All | Pending | Running | Awaiting Approval | Success | Failed | Skipped

### Queue list rows

A `block_ip` row in `awaiting_approval` state now renders with an orange-amber badge labeled
"Awaiting Approval". Previously it rendered with the neutral gray fallback badge.

### Empty state for awaiting_approval filter

When filter is set to `"awaiting_approval"` and no rows exist, the existing empty state
logic handles it correctly:

```javascript
{statusFilter === "all"
  ? "No queued SOAR actions found."
  : "No queued SOAR actions found for this filter."}
```

No change needed here — the filter value is not `"all"`, so the filtered message displays.

### Detail view for an awaiting_approval item

Existing fields are unchanged. The orange-amber note block appears below them, spanning full
width of the detail grid. It reads: "This action is paused and waiting for approval before
it can execute. To review and decide, open the Approvals panel."

The note only renders when `selectedQueueItem.status === "awaiting_approval"`. For all other
statuses, it is null.

---

## Changes to `frontend/src/components/SoarQueuePanel.test.js`

The existing tests are not broken by this change. The following tests must be added.

### Fixture additions

The existing `statusFixture` should be updated to include `awaiting_approval` to match what
the backend actually returns:

```javascript
const statusFixture = {
  counts: {
    pending: 2,
    running: 1,
    awaiting_approval: 1,
    success: 3,
    failed: 1,
    skipped: 4,
  },
  total: 12,
};
```

Add an `awaitingApprovalRowFixture`:

```javascript
const awaitingApprovalRowFixture = {
  id: 202,
  alert_id: 55,
  alert_reference: { status: "linked", label: "Alert 55" },
  action: "block_ip",
  status: "awaiting_approval",
  source_ip: "203.0.113.5",
  retry_count: 0,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-08T10:00:00Z",
  updated_at: "2026-05-08T10:01:00Z",
};

const awaitingApprovalDetailFixture = {
  ...awaitingApprovalRowFixture,
  idempotency_key: "awaiting-idempotency-key-202",
};
```

### New tests

**`awaiting_approval` count tile is shown:**
- `loadSoarQueueStatus` resolves with `statusFixture` (which includes `awaiting_approval: 1`).
- `loadRecentSoarQueueItems` resolves with `{ items: [] }`.
- After `waitFor`: the text "Awaiting Approval" (from `formatQueueLabel`) is visible in the
  counts grid.
- The value `1` is visible as its count.

**`awaiting_approval` filter option exists in dropdown:**
- After panel renders and loads, the status filter `<select>` contains an option with value
  `"awaiting_approval"`.
- `screen.getByRole("option", { name: "Awaiting Approval" })` is in the document.

**`awaiting_approval` badge renders distinctly:**
- `loadSoarQueueStatus` resolves with a counts fixture.
- `loadRecentSoarQueueItems` resolves with `{ items: [awaitingApprovalRowFixture] }`.
- After `waitFor`: a badge labeled "Awaiting Approval" is visible in the table.
- The badge element does not have the neutral/gray fallback style. (Test can assert the text
  exists without testing exact inline style values — matching the text label is sufficient
  since the existing tests follow the same convention.)

**Empty state for `awaiting_approval` filter:**
- `loadSoarQueueStatus` resolves with fixture.
- `loadRecentSoarQueueItems` resolves with `{ items: [] }`.
- User changes the status filter select to `"awaiting_approval"`.
- After `waitFor`: `"No queued SOAR actions found for this filter."` is visible.

**Detail note visible for awaiting_approval item:**
- `loadSoarQueueStatus` resolves with fixture.
- `loadRecentSoarQueueItems` resolves with `{ items: [awaitingApprovalRowFixture] }`.
- `loadSoarQueueItem` resolves with `awaitingApprovalDetailFixture`.
- User clicks the View button for item 202.
- After `waitFor`: the text "This action is paused and waiting for approval" (or a unique
  substring of the note) is visible in the document.

**Detail note absent for non-awaiting item:**
- Same setup but using `queueDetailFixture` (status `"pending"`).
- After detail loads: the approval-waiting note text is NOT in the document.

---

## Files changed

- `frontend/src/components/SoarQueuePanel.js` — four targeted edits:
  1. `QUEUE_STATUSES` constant
  2. `awaitingApprovalBadgeStyle` constant (new)
  3. `getStatusBadgeStyle` function
  4. Detail panel JSX + `approvalWaitingNoteStyle` constant (new)
- `frontend/src/components/SoarQueuePanel.test.js` — fixture updates + six new tests

No other files are created or modified.

---

## Safety boundaries

- `SoarQueuePanel.js` does not call any approval endpoint, does not import from
  `approvalService.js`, and does not render any approve/deny control.
- The detail note is a static text block. It has no event handlers and no data dependencies
  beyond `selectedQueueItem.status`.
- `soarQueueService.js` is unchanged. Passing `"awaiting_approval"` as a filter value
  already works — the service passes the string through as-is.
- ApprovalsPanel.js is unchanged. The two panels remain entirely independent.

---

## Risks

**1. Grid layout with six tiles.**
The counts grid uses `repeat(auto-fit, minmax(130px, 1fr))`. At typical admin panel widths,
six tiles (plus Total = seven) should flow without wrapping to a second row. If the panel is
viewed at narrow width (e.g., below ~1100px), tiles may wrap. This is consistent with how the
existing five tiles already wrap at narrow widths — no regression, no fix needed.

**2. `awaiting_approval` rows may appear in "all" filter when the admin does not expect them.**
Before this change, these rows were in the database and returned by the backend but may have
been missed by admins. After this change they render with a visible badge. This is correct
behavior — not a risk, but worth noting during review.

**3. `statusFixture` in the existing tests only covers five statuses.**
Updating `statusFixture` to include `awaiting_approval` changes the fixture used by all
existing tests. Verify that existing tests do not assert on the exact set of count tiles
(e.g., asserting that exactly five tiles render). If any test does, update it to expect six.
Reading the existing test file before editing will confirm whether this applies.

**4. No approval_request_id in the detail view.**
The queue detail serializer (`_serialize_queue_item_for_detail` in `admin_routes.py`) does not
return an `approval_request_id`. The informational note cannot deep-link to the specific
approval. This is by design for this change — adding that field is a future backend change.
The note's directive ("open the Approvals panel") remains accurate and actionable without it.
