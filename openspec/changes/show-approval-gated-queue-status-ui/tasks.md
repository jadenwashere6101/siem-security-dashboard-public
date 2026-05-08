# Tasks: Show Approval-Gated Queue Status in SOAR Queue UI

Read `SoarQueuePanel.js` and `SoarQueuePanel.test.js` before making any changes.
Verify build after every step: `cd frontend && npm run build`.
Run tests after Step 2: `cd frontend && npm test -- --watchAll=false`.

Only two files are modified in this change:
- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/components/SoarQueuePanel.test.js`

---

## Step 1: Update `SoarQueuePanel.js`

### 1a. Add `awaiting_approval` to `QUEUE_STATUSES`

- [ ] Locate the `QUEUE_STATUSES` constant at the top of the file.
- [ ] Change from:
  ```javascript
  const QUEUE_STATUSES = ["pending", "running", "success", "failed", "skipped"];
  ```
  To:
  ```javascript
  const QUEUE_STATUSES = ["pending", "running", "awaiting_approval", "success", "failed", "skipped"];
  ```
- [ ] Confirm `QUEUE_STATUS_FILTERS` is derived from `QUEUE_STATUSES` via spread — no
  separate change needed there.

### 1b. Add `awaitingApprovalBadgeStyle` constant

- [ ] Add alongside the existing badge style constants (after `skippedBadgeStyle`):
  ```javascript
  const awaitingApprovalBadgeStyle = {
    color: "#fb923c",
    backgroundColor: "rgba(251, 146, 60, 0.12)",
    border: "1px solid rgba(251, 146, 60, 0.3)",
  };
  ```

### 1c. Update `getStatusBadgeStyle`

- [ ] Add the `awaiting_approval` case between `running` and `success`:
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

### 1d. Add approval-waiting note in detail panel JSX

- [ ] Locate the `selectedQueueItem` branch inside the detail panel render block.
- [ ] After the last `<DetailField>` entry (the `Idempotency Key` field) and inside the
  `<div style={detailGridStyle}>` wrapper, add:
  ```javascript
  {selectedQueueItem.status === "awaiting_approval" ? (
    <div style={approvalWaitingNoteStyle}>
      This action is paused and waiting for approval before it can execute. To review
      and decide, open the Approvals panel.
    </div>
  ) : null}
  ```

### 1e. Add `approvalWaitingNoteStyle` constant

- [ ] Add alongside the existing style constants (near `detailGridStyle` or at the end of the
  style block):
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

- [ ] Run build — passes with no errors.

---

## Step 2: Update `SoarQueuePanel.test.js`

Read the full test file before editing. Confirm whether any existing test asserts on the
exact number of status count tiles — if so, update that assertion to expect six tiles.

### 2a. Update `statusFixture`

- [ ] Add `awaiting_approval: 1` to the `counts` object and update `total` to `12`:
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

### 2b. Add `awaitingApprovalRowFixture` and `awaitingApprovalDetailFixture`

- [ ] Add after `queueDetailFixture`:
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

### 2c. Add new tests inside the `SoarQueuePanel` describe block

- [ ] **Test: `awaiting_approval` count tile is shown**
  - `loadSoarQueueStatus` resolves with `statusFixture`.
  - `loadRecentSoarQueueItems` resolves with `{ items: [] }`.
  - `await waitFor(() => { ... })`: assert `screen.getAllByText("Awaiting Approval")` has at
    least one element (count tile label). Assert the count `1` is visible.

- [ ] **Test: `awaiting_approval` option exists in status filter dropdown**
  - Same setup as above.
  - After `waitFor`: `screen.getByRole("option", { name: "Awaiting Approval" })` is in the
    document.

- [ ] **Test: `awaiting_approval` badge renders in queue list**
  - `loadSoarQueueStatus` resolves with `statusFixture`.
  - `loadRecentSoarQueueItems` resolves with `{ items: [awaitingApprovalRowFixture] }`.
  - After `waitFor`: `screen.getAllByText("Awaiting Approval")` is non-empty (badge in row).

- [ ] **Test: empty state for `awaiting_approval` filter**
  - `loadSoarQueueStatus` resolves with `statusFixture`.
  - `loadRecentSoarQueueItems` resolves with `{ items: [] }`.
  - Wait for initial render. Use `userEvent.selectOptions` (or `fireEvent.change`) to change
    the Status filter select to `"awaiting_approval"`.
  - `loadRecentSoarQueueItems` now returns `{ items: [] }` (mock the new call).
  - After `waitFor`: `"No queued SOAR actions found for this filter."` is in the document.

- [ ] **Test: approval-waiting note visible in detail for awaiting_approval item**
  - `loadSoarQueueStatus` resolves with `statusFixture`.
  - `loadRecentSoarQueueItems` resolves with `{ items: [awaitingApprovalRowFixture] }`.
  - `loadSoarQueueItem` resolves with `awaitingApprovalDetailFixture`.
  - After initial load, click the View button for item 202.
  - `await waitFor`: `screen.getByText(/This action is paused and waiting for approval/)` is
    in the document.

- [ ] **Test: approval-waiting note absent for non-awaiting item**
  - `loadSoarQueueStatus` resolves with `statusFixture`.
  - `loadRecentSoarQueueItems` resolves with `{ items: [queueRowFixture] }`.
  - `loadSoarQueueItem` resolves with `queueDetailFixture` (status `"pending"`).
  - After detail loads: `screen.queryByText(/This action is paused and waiting for approval/)`
    is null.

- [ ] Run `npm test -- --watchAll=false` — all tests green, including existing ones.

---

## Step 3: Final audit

- [ ] Confirm only these files were modified:
  - `frontend/src/components/SoarQueuePanel.js`
  - `frontend/src/components/SoarQueuePanel.test.js`
- [ ] Confirm `SoarQueuePanel.js` does not import from `approvalService.js` or call any
  approval endpoint.
- [ ] Confirm the detail note has no event handlers, no anchor tags, and no navigation calls.
- [ ] Confirm `soarQueueService.js` was not modified.
- [ ] Confirm `ApprovalsPanel.js` was not modified.
- [ ] Run full build and test suite — clean.
