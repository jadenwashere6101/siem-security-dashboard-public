# Tasks: Link Approvals and Queue Visibility (Phase 2.5F)

Read each file before editing it.
Run `pytest tests/ -x -q` after each step that modifies Python files.
Run `cd frontend && npm run build` after each step that modifies JS files.
Run `cd frontend && npm test -- --watchAll=false` after Step 5 and after Step 7.

**Stop conditions:**
- If any existing queue, approval, or route test fails after a step, revert that step
  before proceeding.
- Do not commit until all steps pass the full suite.

Only these files are modified in this change:
- `routes/admin_routes.py`
- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/components/ApprovalsPanel.js`
- `tests/test_soar_worker_admin_run_control.py`
- `frontend/src/components/SoarQueuePanel.test.js`
- `frontend/src/components/ApprovalsPanel.test.js`

---

## Step 0: Pre-flight — verify index coverage

Before writing any code, confirm the `approval_requests` table has an index suitable for
the `WHERE queue_id = %s AND action = %s ORDER BY created_at DESC` query that
`get_latest_approval_for_queue_action` executes.

- [x] Read `schema.sql`. Search for index definitions on `approval_requests`.
- [x] Confirm a composite index covering `(queue_id, action)` or `(queue_id, action,
  created_at DESC)` exists. A partial or covering index is also acceptable.
- [x] If no suitable index exists, add one to `schema.sql`:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_approval_requests_queue_action
      ON approval_requests (queue_id, action, created_at DESC, id DESC);
  ```
- [x] Run `pytest tests/ -x -q` — passes (schema-only change, no code touched).

---

## Step 1: Update `routes/admin_routes.py`

Read `routes/admin_routes.py` in full before editing. Note the existing import block
and the location of the other `_serialize_*` helper functions.

### 1a. Add import

- [x] Add `get_latest_approval_for_queue_action` to the existing `from core.approval_store
  import ...` line. Do not duplicate if already present.

### 1b. Add `_serialize_approval_summary`

- [x] Add after the existing `_serialize_queue_item_for_detail` function:

  ```python
  def _serialize_approval_summary(approval):
      if approval is None:
          return None
      return {
          "id": approval["id"],
          "status": approval["status"],
          "risk_level": approval["risk_level"],
          "expires_at": approval["expires_at"],
          "decided_at": approval["decided_at"],
      }
  ```

### 1c. Update `get_queue_item_detail`

- [x] After `item = _serialize_queue_item_for_detail(queue_row)`, add:

  ```python
  approval = get_latest_approval_for_queue_action(
      conn, queue_id=queue_id, action=queue_row["action"]
  )
  item["latest_approval"] = _serialize_approval_summary(approval)
  ```

  The call goes before `return jsonify(item), 200`, inside the existing `try` block,
  while `conn` is still open.

- [x] Run `pytest tests/ -x -q` — all existing tests pass.

  **Important:** Before running, read `tests/test_soar_worker_admin_run_control.py` to
  check whether any existing queue detail test asserts `data.keys()` or an exact key set.
  If so, update those assertions to include `"latest_approval"` before running.

---

## Step 2: Test `latest_approval` in `test_soar_worker_admin_run_control.py`

Read `tests/test_soar_worker_admin_run_control.py` in full before editing. Match the
fixture and DB setup patterns of the existing queue item detail tests.

- [x] **Test: `latest_approval` is null when no approval exists**
  - Insert a `block_ip` queue row with no linked approval record.
  - `GET /admin/soar/queue/<id>`.
  - Response 200. `data["latest_approval"] is None`.

- [x] **Test: `latest_approval` populated when approval exists**
  - Insert a `block_ip` `awaiting_approval` queue row.
  - Insert a `pending` approval linked to it.
  - `GET /admin/soar/queue/<id>`.
  - Response 200. `data["latest_approval"]["id"] == approval_id`.
  - `data["latest_approval"]["status"] == "pending"`.
  - `"risk_level"` in `data["latest_approval"]`.
  - `"expires_at"` in `data["latest_approval"]`.
  - `"decided_at"` in `data["latest_approval"]`.

- [x] **Test: `latest_approval` reflects most recent approval when multiple exist**
  - Insert queue row + two approvals for it (first `expired`, second `pending`).
  - `GET /admin/soar/queue/<id>`.
  - `data["latest_approval"]["id"] == second_approval_id`.
  - `data["latest_approval"]["status"] == "pending"`.

- [x] **Test: `latest_approval` does not include sensitive fields**
  - Insert queue row + approval.
  - `GET /admin/soar/queue/<id>`.
  - `"requested_by"` not in `data["latest_approval"]`.
  - `"approved_by"` not in `data["latest_approval"]`.
  - `"decided_by"` not in `data["latest_approval"]`.
  - `"request_reason"` not in `data["latest_approval"]`.
  - `"decision_comment"` not in `data["latest_approval"]`.

- [x] Run `pytest tests/ -x -q` — all tests pass.

---

## Step 3: Update `SoarQueuePanel.js`

Read `frontend/src/components/SoarQueuePanel.js` in full before editing. Locate the
`selectedQueueItem ?` ternary inside the detail panel (the ternary that currently returns
either `<div style={detailGridStyle}>` or `<p style={emptyTextStyle}>...`).

### 3a. Fragment restructure

- [x] Wrap the `selectedQueueItem ?` branch in a Fragment and add the approval context
  section after `detailGridStyle`:

  ```javascript
  } : selectedQueueItem ? (
    <>
      <div style={detailGridStyle}>
        {/* all existing DetailField components unchanged */}
        {selectedQueueItem.status === "awaiting_approval" ? (
          <div style={approvalWaitingNoteStyle}>
            This action is paused and waiting for approval before it can execute. To review
            and decide, open the Approvals panel.
          </div>
        ) : null}
      </div>
      {selectedQueueItem.latest_approval ? (
        <div style={approvalContextSectionStyle}>
          <div style={approvalContextHeaderStyle}>Linked Approval</div>
          <div style={approvalContextGridStyle}>
            <DetailField
              label="Approval ID"
              value={`#${selectedQueueItem.latest_approval.id}`}
              mono
            />
            <DetailField
              label="Approval Status"
              value={formatQueueLabel(selectedQueueItem.latest_approval.status)}
            />
            <DetailField
              label="Risk"
              value={formatQueueLabel(selectedQueueItem.latest_approval.risk_level)}
            />
            <DetailField
              label="Expires"
              value={formatQueueTimestamp(selectedQueueItem.latest_approval.expires_at)}
            />
            <DetailField
              label="Decided"
              value={formatQueueTimestamp(selectedQueueItem.latest_approval.decided_at)}
            />
          </div>
        </div>
      ) : null}
    </>
  ) : (
    <p style={emptyTextStyle}>Select a queue item to view details.</p>
  )}
  ```

  The content inside `detailGridStyle` is not modified — only the outer structure changes.

### 3b. Add style constants

- [x] Add alongside the existing style constants:

  ```javascript
  const approvalContextSectionStyle = {
    marginTop: "14px",
    paddingTop: "14px",
    borderTop: "1px solid #30363d",
  };

  const approvalContextHeaderStyle = {
    marginBottom: "10px",
    color: "#8b949e",
    fontSize: "12px",
    fontWeight: "700",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  };

  const approvalContextGridStyle = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: "10px",
  };
  ```

- [x] Run `cd frontend && npm run build` — passes with no errors.

---

## Step 4: Test `SoarQueuePanel.js` in `SoarQueuePanel.test.js`

Read `frontend/src/components/SoarQueuePanel.test.js` in full before editing. Note the
existing fixture patterns and the `deferred()` helper.

- [x] Add fixtures:

  ```javascript
  const queueDetailWithApprovalFixture = {
    id: 42,
    alert_id: 10,
    alert_reference: { status: "linked", label: "Alert 10" },
    action: "block_ip",
    status: "awaiting_approval",
    source_ip: "10.0.0.1",
    retry_count: 0,
    max_retries: 3,
    last_error: null,
    created_at: "2026-05-08T09:00:00Z",
    updated_at: "2026-05-08T09:01:00Z",
    idempotency_key: "idem-key-42",
    latest_approval: {
      id: 7,
      status: "pending",
      risk_level: "high",
      expires_at: "2026-05-08T10:00:00Z",
      decided_at: null,
    },
  };

  const queueDetailWithoutApprovalFixture = {
    ...queueDetailWithApprovalFixture,
    status: "pending",
    latest_approval: null,
  };
  ```

  Also update any existing `queueDetailFixture` to include `latest_approval: null` if it
  does not already have that field, so existing tests remain consistent with the new
  response shape.

- [x] **Test: "Linked Approval" section renders when `latest_approval` is non-null**
  - `loadSoarQueueStatus` resolves with status fixture.
  - `loadRecentSoarQueueItems` resolves with a list containing a row with `id: 42`.
  - `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
  - Click View for item 42.
  - `await waitFor`: `screen.getByText("Linked Approval")` is in the document.
  - `screen.getByText("#7")` is in the document.

- [x] **Test: "Linked Approval" section absent when `latest_approval` is null**
  - Same setup but `loadSoarQueueItem` resolves with `queueDetailWithoutApprovalFixture`.
  - After detail loads: `screen.queryByText("Linked Approval")` is null.

- [x] **Test: approval summary fields render**
  - `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
  - Click View. After load:
  - `screen.getByText("Approval Status")` is in the document.
  - `screen.getByText("Risk")` is in the document.
  - `screen.getByText("Expires")` is in the document.
  - `screen.getByText("Decided")` is in the document.

- [x] **Test: no approve/deny button in detail view**
  - `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
  - Click View. After load:
  - `screen.queryByRole("button", { name: /approve/i })` is null.
  - `screen.queryByRole("button", { name: /deny/i })` is null.

- [x] Run `cd frontend && npm test -- --watchAll=false` — all tests pass, including existing ones.

---

## Step 5: Update `ApprovalsPanel.js`

Read `frontend/src/components/ApprovalsPanel.js` in full before editing. Locate the
`detailGridStyle` section inside the `selectedApproval ?` branch.

### 5a. Rename "Queue ID" label

- [x] Change:
  ```javascript
  <DetailField label="Queue ID" value={selectedApproval.queue_id ?? "N/A"} mono />
  ```
  To:
  ```javascript
  <DetailField label="Linked Queue Item" value={selectedApproval.queue_id ?? "N/A"} mono />
  ```

### 5b. Add queue link note

- [x] After the last `<DetailField>` inside `detailGridStyle` (the "Decision Comment"
  field) and before the closing `</div>` of `detailGridStyle`, add:

  ```javascript
  {selectedApproval.queue_id !== null && selectedApproval.queue_id !== undefined ? (
    <div style={queueLinkNoteStyle}>
      This approval is linked to Queue Item #{selectedApproval.queue_id}. Open the SOAR
      Queue panel to view its current execution status.
    </div>
  ) : null}
  ```

### 5c. Add style constant

- [x] Add alongside the existing style constants:

  ```javascript
  const queueLinkNoteStyle = {
    gridColumn: "1 / -1",
    padding: "10px 12px",
    borderRadius: "8px",
    border: "1px solid rgba(139, 148, 158, 0.2)",
    backgroundColor: "rgba(139, 148, 158, 0.06)",
    color: "#8b949e",
    fontSize: "13px",
    lineHeight: "1.5",
  };
  ```

- [x] Run `cd frontend && npm run build` — passes with no errors.

---

## Step 6: Test `ApprovalsPanel.js` in `ApprovalsPanel.test.js`

Read `frontend/src/components/ApprovalsPanel.test.js` in full before editing. Find any
existing test that asserts `"Queue ID"` — update it to `"Linked Queue Item"`. Note the
pattern for opening the detail panel (clicking a row or using `selectedApprovalId`).

- [x] **Test: queue link note renders when `queue_id` is non-null**
  - `listApprovals.mockResolvedValue` with an approval row.
  - `getApproval.mockResolvedValue` with an approval detail having `queue_id: 42`.
  - Click the approval row to open detail. Wait for detail to load.
  - `await waitFor`: `screen.getByText(/This approval is linked to Queue Item #42/i)` is
    in the document.
  - `screen.getByText(/Open the SOAR Queue panel/i)` is in the document.

- [x] **Test: queue link note absent when `queue_id` is null**
  - `getApproval.mockResolvedValue` with approval detail having `queue_id: null`.
  - Open detail. Wait for load.
  - `screen.queryByText(/This approval is linked to Queue Item/i)` is null.

- [x] **Test: "Linked Queue Item" label renders, "Queue ID" label does not**
  - `getApproval.mockResolvedValue` with approval detail having `queue_id: 42`.
  - Open detail. Wait for load.
  - `screen.getByText("Linked Queue Item")` is in the document.
  - `screen.queryByText("Queue ID")` is null.

- [x] Run `cd frontend && npm test -- --watchAll=false` — all tests pass, including
  existing ones.

---

## Step 7: Final audit

- [x] Confirm only these files were created or modified:
  - `routes/admin_routes.py`
  - `frontend/src/components/SoarQueuePanel.js`
  - `frontend/src/components/ApprovalsPanel.js`
  - `tests/test_soar_worker_admin_run_control.py`
  - `frontend/src/components/SoarQueuePanel.test.js`
  - `frontend/src/components/ApprovalsPanel.test.js`
- [x] Confirm `approval_routes.py` was NOT modified.
- [x] Confirm `approvalService.js` was NOT modified.
- [x] Confirm `soarQueueService.js` was NOT modified.
- [x] Confirm `SoarQueuePanel.js` does not import from `approvalService.js`.
- [x] Confirm `ApprovalsPanel.js` does not import from `soarQueueService.js`.
- [x] Confirm no `<button>` for approve or deny appears in the new `SoarQueuePanel.js` JSX.
- [x] Confirm `_serialize_approval_summary` returns exactly 5 fields: id, status,
  risk_level, expires_at, decided_at.
- [x] Confirm `get_latest_approval_for_queue_action` call is inside the existing try/except
  block in `get_queue_item_detail`, while `conn` is still open.
- [x] Run full Python suite: `pytest tests/ -x -q` — clean.
- [x] Run full frontend suite: `cd frontend && npm test -- --watchAll=false` — clean.
