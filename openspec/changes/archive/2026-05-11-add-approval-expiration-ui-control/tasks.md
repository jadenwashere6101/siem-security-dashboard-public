# Tasks: Approval Expiration UI Control (Phase 2.5E)

Read each file before editing it.
Verify build after every step: `cd frontend && npm run build`.
Run tests after Step 3: `cd frontend && npm test -- --watchAll=false`.

Only these files are modified in this change:
- `frontend/src/services/approvalService.js`
- `frontend/src/components/ApprovalsPanel.js`
- `frontend/src/services/approvalService.test.js`
- `frontend/src/components/ApprovalsPanel.test.js`

---

## Step 1: Add `expireOverdueApprovals` to `approvalService.js`

Read `frontend/src/services/approvalService.js` in full before editing. Confirm the
`buildSiemPath`, `parseJsonResponse`, and `getApiErrorMessage` helpers are already imported.

- [x] Add after `submitApprovalDecision`:

  ```javascript
  export const expireOverdueApprovals = async () => {
    const res = await fetch(buildSiemPath("/admin/soar/approvals/expire-pending"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await parseJsonResponse(res, {});
    if (!res.ok) {
      throw new Error(
        getApiErrorMessage(data, "Unable to expire overdue approvals", ["error"])
      );
    }
    return data;
  };
  ```

- [x] Run `cd frontend && npm run build` — passes with no errors.

---

## Step 2: Update `ApprovalsPanel.js`

Read `frontend/src/components/ApprovalsPanel.js` in full before editing.

### 2a. Update import

- [x] Add `expireOverdueApprovals` to the named import from `../services/approvalService`:

  ```javascript
  import {
    expireOverdueApprovals,
    getApproval,
    listApprovals,
    submitApprovalDecision,
  } from "../services/approvalService";
  ```

### 2b. Add state vars

- [x] Add after the `submittingDecision` state line:

  ```javascript
  const [isExpiring, setIsExpiring] = useState(false);
  const [expireResult, setExpireResult] = useState(null);
  const [expireError, setExpireError] = useState("");
  ```

### 2c. Add state clears to `loadApprovalList`

- [x] Inside the `try` block of `loadApprovalList`, after `setError("")`, add:

  ```javascript
  setExpireResult(null);
  setExpireError("");
  ```

### 2d. Add `handleExpireOverdue`

- [x] Add after `handleCloseDetail`:

  ```javascript
  const handleExpireOverdue = useCallback(async () => {
    if (!isSuperAdmin || isExpiring) return;
    try {
      setIsExpiring(true);
      setExpireError("");
      setExpireResult(null);
      const result = await expireOverdueApprovals();
      setExpireResult(result);
      await loadApprovalList({ quiet: true });
    } catch (err) {
      setExpireError(err.message || "Unable to expire overdue approvals.");
    } finally {
      setIsExpiring(false);
    }
  }, [isSuperAdmin, isExpiring, loadApprovalList]);
  ```

### 2e. Add "Expire overdue" button to controls

- [x] Inside `<div style={controlsStyle}>`, after the Refresh button:

  ```javascript
  {isSuperAdmin ? (
    <button
      type="button"
      onClick={handleExpireOverdue}
      disabled={isExpiring || loading || refreshing}
      style={{
        ...expireButtonStyle,
        opacity: isExpiring || loading || refreshing ? 0.65 : 1,
        cursor: isExpiring || loading || refreshing ? "default" : "pointer",
      }}
    >
      {isExpiring ? "Expiring..." : "Expire overdue"}
    </button>
  ) : null}
  ```

### 2f. Add feedback blocks below controls

- [x] After the closing `</div>` of `controlsStyle`, still inside the card header `<div>`,
  add:

  ```javascript
  {isSuperAdmin && expireResult !== null ? (
    <div style={expireResultStyle}>
      Expired {expireResult.expired_approvals ?? 0} approval
      {expireResult.expired_approvals === 1 ? "" : "s"},{" "}
      {expireResult.skipped_queue_rows ?? 0} queue row
      {expireResult.skipped_queue_rows === 1 ? "" : "s"} skipped.
    </div>
  ) : null}
  {isSuperAdmin && expireError ? (
    <div style={expireErrorStyle}>{expireError}</div>
  ) : null}
  ```

### 2g. Add style constants

- [x] Add alongside existing style constants:

  ```javascript
  const expireButtonStyle = {
    minHeight: "40px",
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid rgba(251, 146, 60, 0.35)",
    backgroundColor: "rgba(251, 146, 60, 0.10)",
    color: "#fb923c",
    fontSize: "13px",
    fontWeight: "700",
  };

  const expireResultStyle = {
    marginTop: "8px",
    padding: "8px 12px",
    borderRadius: "8px",
    border: "1px solid rgba(126, 231, 135, 0.28)",
    backgroundColor: "rgba(63, 185, 80, 0.08)",
    color: "#7ee787",
    fontSize: "13px",
    fontWeight: "600",
  };

  const expireErrorStyle = {
    marginTop: "8px",
    padding: "8px 12px",
    borderRadius: "8px",
    border: "1px solid rgba(239, 68, 68, 0.28)",
    backgroundColor: "rgba(239, 68, 68, 0.08)",
    color: "#fca5a5",
    fontSize: "13px",
    fontWeight: "600",
  };
  ```

- [x] Run `cd frontend && npm run build` — passes with no errors.

---

## Step 3: Test `expireOverdueApprovals` in `approvalService.test.js`

Read `frontend/src/services/approvalService.test.js` in full before editing. Match the
mock/assertion pattern of the existing `submitApprovalDecision` tests. Import
`expireOverdueApprovals`.

- [x] **Test: calls correct endpoint with correct method and headers**
  - `global.fetch` resolves `ok: true` with `{ expired_approvals: 2, skipped_queue_rows: 1, ... }`.
  - Call `expireOverdueApprovals()`.
  - Assert: `fetch` called once. URL contains `"/admin/soar/approvals/expire-pending"`.
    `options.method === "POST"`. `options.credentials === "include"`.
    `options.headers["Content-Type"] === "application/json"`.
  - Assert: returned object has `expired_approvals: 2` and `skipped_queue_rows: 1`.

- [x] **Test: throws with backend error message on non-OK response**
  - `global.fetch` resolves `ok: false`, `json: async () => ({ error: "Forbidden" })`.
  - `await expect(expireOverdueApprovals()).rejects.toThrow("Forbidden")`.

- [x] **Test: throws with fallback message when response has no error field**
  - `global.fetch` resolves `ok: false`, `json: async () => ({})`.
  - `await expect(expireOverdueApprovals()).rejects.toThrow("Unable to expire overdue approvals")`.

- [x] Run `cd frontend && npm test -- --watchAll=false` — all tests pass.

---

## Step 4: Test `ApprovalsPanel.js` in `ApprovalsPanel.test.js`

Read `frontend/src/components/ApprovalsPanel.test.js` in full before editing. Note the
`renderPanel` helper, the `deferred()` utility, and the existing `jest.mock` block.

- [x] Add `expireOverdueApprovals: jest.fn()` to the `jest.mock` block for
  `"../services/approvalService"`.

- [x] Import `expireOverdueApprovals` alongside the other service imports in the test file.

- [x] In `beforeEach` (or wherever the other mocks are reset), add:
  `expireOverdueApprovals.mockReset()`.

- [x] **Test: "Expire overdue" button not rendered for analyst**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - `renderPanel({ userRole: "analyst" })`.
  - `await screen.findByText("No approval requests found.")`.
  - `expect(screen.queryByRole("button", { name: /expire overdue/i })).toBeNull()`.

- [x] **Test: "Expire overdue" button rendered for super_admin**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - `renderPanel({ userRole: "super_admin" })` (default, can omit the option).
  - `await screen.findByText("No approval requests found.")`.
  - `expect(screen.getByRole("button", { name: /expire overdue/i })).toBeInTheDocument()`.

- [x] **Test: button shows "Expiring..." while in-flight and re-enables on completion**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - Use `deferred()` to control `expireOverdueApprovals`.
  - After initial render, click the button.
  - Assert button text is "Expiring..." and is disabled.
  - Resolve the deferred with `{ expired_approvals: 0, skipped_queue_rows: 0, ... }`.
  - `await screen.findByRole("button", { name: /expire overdue/i })` — button label restored.
  - Assert button is not disabled.

- [x] **Test: success shows inline result and calls `listApprovals` a second time**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - `expireOverdueApprovals.mockResolvedValue({ expired_approvals: 3, skipped_queue_rows: 2, ... })`.
  - Click "Expire overdue".
  - `await screen.findByText(/expired 3 approvals/i)`.
  - `expect(screen.getByText(/2 queue rows skipped/i)).toBeInTheDocument()`.
  - `expect(listApprovals).toHaveBeenCalledTimes(2)` — once on mount, once on quiet refresh.

- [x] **Test: error shows inline error, `listApprovals` not called a second time**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - `expireOverdueApprovals.mockRejectedValue(new Error("Unable to expire overdue approvals"))`.
  - Click "Expire overdue".
  - `await screen.findByText(/Unable to expire overdue approvals/i)`.
  - `expect(listApprovals).toHaveBeenCalledTimes(1)`.

- [x] **Test: feedback cleared on next list load (Refresh click)**
  - `listApprovals.mockResolvedValue({ approvals: [] })`.
  - `expireOverdueApprovals.mockResolvedValue({ expired_approvals: 1, skipped_queue_rows: 0, ... })`.
  - Click "Expire overdue". Wait for result text to appear.
  - Click Refresh button.
  - `await waitFor(() => expect(screen.queryByText(/expired 1 approval/i)).toBeNull())`.

- [x] Run `cd frontend && npm test -- --watchAll=false` — all tests pass, including existing ones.

---

## Step 5: Final audit

- [x] Confirm only these files were created or modified:
  - `frontend/src/services/approvalService.js`
  - `frontend/src/components/ApprovalsPanel.js`
  - `frontend/src/services/approvalService.test.js`
  - `frontend/src/components/ApprovalsPanel.test.js`
- [x] Confirm `ApprovalsPanel.js` does not call `fetch` directly — all network calls go through
  `approvalService.js`.
- [x] Confirm the "Expire overdue" button is gated to `isSuperAdmin` in the JSX.
- [x] Confirm `handleExpireOverdue` checks `isSuperAdmin` defensively.
- [x] Confirm `expireOverdueApprovals` does not appear in any Python file.
- [x] Confirm no scheduler, cron, polling, or `setInterval` was introduced.
- [x] Confirm `soarQueueService.js` was not modified.
- [x] Confirm `SoarQueuePanel.js` was not modified.
- [x] Run full test suite: `cd frontend && npm test -- --watchAll=false` — clean.
