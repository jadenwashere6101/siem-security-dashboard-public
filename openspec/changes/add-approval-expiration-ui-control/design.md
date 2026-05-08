# Design: Approval Expiration UI Control (Phase 2.5E)

---

## Current state (context only)

`ApprovalsPanel.js` imports three functions from `approvalService.js`:

```javascript
import {
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "../services/approvalService";
```

The panel has a `controlsStyle` div in the card header that renders:
- Status filter select
- Risk filter select
- Refresh button (`refreshButtonStyle`: blue `#93c5fd` tones)

Below the header, `panelContentStyle` renders the list or loading state. The detail panel
(`detailPanelStyle`) appears below the list when `selectedApprovalId` is set.

The decision controls (`decisionControlStyle`) render inside the detail panel, gated to
`canDecideSelected`. They use:
- `approveButtonStyle` (green)
- `denyButtonStyle` (red)
- `inlineErrorStyle` (red `#fca5a5`) for `decisionError`

The `isSuperAdmin` flag is already computed from `userRole`:
```javascript
const isSuperAdmin = userRole === "super_admin";
```

The backend endpoint added in Phase 2.5D returns:
```json
{
  "expired_approvals": 3,
  "skipped_queue_rows": 3,
  "expired_approval_ids": [1, 2, 3],
  "skipped_queue_ids": [101, 102, 103]
}
```

---

## Changes to `frontend/src/services/approvalService.js`

### Add `expireOverdueApprovals`

Add after `submitApprovalDecision`:

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

Update the named import block at the top of `ApprovalsPanel.js` to include
`expireOverdueApprovals`.

---

## Changes to `frontend/src/components/ApprovalsPanel.js`

### 1. Import `expireOverdueApprovals`

```javascript
import {
  expireOverdueApprovals,
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "../services/approvalService";
```

### 2. Add state

Add alongside the existing `useState` declarations:

```javascript
const [isExpiring, setIsExpiring] = useState(false);
const [expireResult, setExpireResult] = useState(null);
const [expireError, setExpireError] = useState("");
```

- `isExpiring`: boolean; `true` while the POST is in-flight.
- `expireResult`: the parsed response object on success, or `null`.
- `expireError`: error message string on failure, or `""`.

### 3. Add `handleExpireOverdue` handler

Add after `handleCloseDetail`:

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

Add `isExpiring` to the `useCallback` dependency array. The guard `if (!isSuperAdmin ||
isExpiring) return;` prevents double-submission and protects against analyst invocation if
the button were somehow rendered outside its gate.

### 4. Clear feedback on list load

In `loadApprovalList`, add two clears before the `await listApprovals(...)` call:

```javascript
setExpireResult(null);
setExpireError("");
```

This ensures that after a manual Refresh (or the quiet refresh triggered by `handleExpireOverdue`
itself), stale feedback does not persist.

The clears go inside the `try` block, after `setError("")`:

```javascript
const loadApprovalList = useCallback(async ({ quiet = false } = {}) => {
  try {
    if (quiet) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    setExpireResult(null);   // clear previous expire feedback
    setExpireError("");      // clear previous expire error

    const data = await listApprovals({ status: statusFilter });
    setApprovals(Array.isArray(data?.approvals) ? data.approvals : []);
  } catch (err) {
    ...
  }
}, [statusFilter]);
```

### 5. Add "Expire overdue" button to `controlsStyle`

After the Refresh button, inside `<div style={controlsStyle}>`, add:

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

Disabled while `isExpiring`, `loading`, or `refreshing` to prevent triggering cleanup
during an active list fetch.

### 6. Add inline feedback below `controlsStyle` (inside card header or just below it)

After the closing `</div>` of `controlsStyle` and before the closing `</div>` of the card
header `<div style={cardHeaderStyle}>`, add:

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

Both blocks only render when `isSuperAdmin`, matching the button gate.

The result message uses the exact field names from the backend response
(`expired_approvals`, `skipped_queue_rows`) with `?? 0` fallbacks. The `=== 1` ternary
handles singular vs plural ("approval" vs "approvals", "row" vs "rows").

### 7. Add style constants

Add alongside existing style constants:

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

Color notes:
- `expireButtonStyle`: orange-amber (`#fb923c`) — matches the `awaiting_approval` badge tone,
  signals operational action without implying danger.
- `expireResultStyle`: green (`#7ee787`) — matches `approvedBadgeStyle` color; indicates
  success.
- `expireErrorStyle`: red (`#fca5a5`) — matches `inlineErrorStyle` and `errorStateStyle`
  color; consistent with all other error surfaces in the panel.

---

## Changes to `frontend/src/services/approvalService.test.js`

Add one new test block for `expireOverdueApprovals`. Match the existing `submitApprovalDecision`
test pattern: set up `global.fetch`, call the function, assert fetch args and return value.

### Test: calls correct endpoint with correct method and headers

```javascript
it("calls POST /admin/soar/approvals/expire-pending with correct options", async () => {
  global.fetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      expired_approvals: 2,
      skipped_queue_rows: 1,
      expired_approval_ids: [4, 5],
      skipped_queue_ids: [201],
    }),
  });

  const result = await expireOverdueApprovals();

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toContain("/admin/soar/approvals/expire-pending");
  expect(options.method).toBe("POST");
  expect(options.credentials).toBe("include");
  expect(options.headers["Content-Type"]).toBe("application/json");
  expect(result.expired_approvals).toBe(2);
  expect(result.skipped_queue_rows).toBe(1);
});
```

### Test: throws on non-OK response

```javascript
it("throws with backend error message on non-OK response", async () => {
  global.fetch.mockResolvedValue({
    ok: false,
    json: async () => ({ error: "Forbidden" }),
  });

  await expect(expireOverdueApprovals()).rejects.toThrow("Forbidden");
});
```

### Test: throws with fallback message when no error field

```javascript
it("throws with fallback message when response has no error field", async () => {
  global.fetch.mockResolvedValue({
    ok: false,
    json: async () => ({}),
  });

  await expect(expireOverdueApprovals()).rejects.toThrow(
    "Unable to expire overdue approvals"
  );
});
```

---

## Changes to `frontend/src/components/ApprovalsPanel.test.js`

Add `expireOverdueApprovals` to the existing `jest.mock` block. The mock block currently mocks
three functions; add the fourth:

```javascript
jest.mock("../services/approvalService", () => ({
  listApprovals: jest.fn(),
  getApproval: jest.fn(),
  submitApprovalDecision: jest.fn(),
  expireOverdueApprovals: jest.fn(),   // add this line
}));
```

Add import at the top of the test file:

```javascript
import { expireOverdueApprovals, ... } from "../services/approvalService";
```

(Or confirm that the existing destructured import already includes it after adding to the
mock block — match whatever pattern the existing test file uses for the other functions.)

### New tests

**Test: "Expire overdue" button not rendered for analyst**

```javascript
it('does not render Expire overdue button for analyst', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  renderPanel({ userRole: "analyst" });
  await screen.findByText("No approval requests found.");
  expect(screen.queryByRole("button", { name: /expire overdue/i })).toBeNull();
});
```

**Test: "Expire overdue" button rendered for super_admin**

```javascript
it('renders Expire overdue button for super_admin', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  renderPanel({ userRole: "super_admin" });
  await screen.findByText("No approval requests found.");
  expect(screen.getByRole("button", { name: /expire overdue/i })).toBeInTheDocument();
});
```

**Test: button shows "Expiring..." while in-flight and re-enables on completion**

```javascript
it('shows Expiring... while in-flight and re-enables after', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  const { resolve, promise } = deferred();
  expireOverdueApprovals.mockReturnValue(promise);

  renderPanel({ userRole: "super_admin" });
  await screen.findByRole("button", { name: /expire overdue/i });

  await userEvent.click(screen.getByRole("button", { name: /expire overdue/i }));

  expect(screen.getByRole("button", { name: /expiring\.\.\./i })).toBeDisabled();

  resolve({
    expired_approvals: 0,
    skipped_queue_rows: 0,
    expired_approval_ids: [],
    skipped_queue_ids: [],
  });

  await screen.findByRole("button", { name: /expire overdue/i });
  expect(screen.getByRole("button", { name: /expire overdue/i })).not.toBeDisabled();
});
```

**Test: success shows inline result and calls loadApprovalList**

```javascript
it('shows inline result and refreshes list on success', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  expireOverdueApprovals.mockResolvedValue({
    expired_approvals: 3,
    skipped_queue_rows: 2,
    expired_approval_ids: [1, 2, 3],
    skipped_queue_ids: [101, 102],
  });

  renderPanel({ userRole: "super_admin" });
  await screen.findByRole("button", { name: /expire overdue/i });
  await userEvent.click(screen.getByRole("button", { name: /expire overdue/i }));

  await screen.findByText(/expired 3 approvals/i);
  expect(screen.getByText(/2 queue rows skipped/i)).toBeInTheDocument();
  // listApprovals called once on mount, once on quiet refresh after success
  expect(listApprovals).toHaveBeenCalledTimes(2);
});
```

**Test: error shows inline error, list is not refreshed**

```javascript
it('shows inline error on failure and does not refresh list', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  expireOverdueApprovals.mockRejectedValue(new Error("Unable to expire overdue approvals"));

  renderPanel({ userRole: "super_admin" });
  await screen.findByRole("button", { name: /expire overdue/i });
  await userEvent.click(screen.getByRole("button", { name: /expire overdue/i }));

  await screen.findByText(/Unable to expire overdue approvals/i);
  // listApprovals called once on mount only — no quiet refresh on failure
  expect(listApprovals).toHaveBeenCalledTimes(1);
});
```

**Test: feedback cleared on next list load (Refresh click)**

```javascript
it('clears expire result when Refresh is clicked', async () => {
  listApprovals.mockResolvedValue({ approvals: [] });
  expireOverdueApprovals.mockResolvedValue({
    expired_approvals: 1,
    skipped_queue_rows: 0,
    expired_approval_ids: [7],
    skipped_queue_ids: [],
  });

  renderPanel({ userRole: "super_admin" });
  await screen.findByRole("button", { name: /expire overdue/i });
  await userEvent.click(screen.getByRole("button", { name: /expire overdue/i }));

  await screen.findByText(/expired 1 approval/i);

  await userEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

  await waitFor(() => {
    expect(screen.queryByText(/expired 1 approval/i)).toBeNull();
  });
});
```

---

## Files changed

- `frontend/src/services/approvalService.js` — one new exported function
  (`expireOverdueApprovals`).
- `frontend/src/components/ApprovalsPanel.js` — import, three state vars, one handler,
  one `loadApprovalList` mutation (two state clears), one button, two feedback blocks,
  three style constants.
- `frontend/src/services/approvalService.test.js` — three new tests for
  `expireOverdueApprovals`.
- `frontend/src/components/ApprovalsPanel.test.js` — mock block update + six new tests.

No other files are created or modified.

---

## Safety boundaries

- `ApprovalsPanel.js` does not call the endpoint directly. All fetch logic is in the service.
- The button gate (`isSuperAdmin`) is evaluated at render time. The handler also checks
  `isSuperAdmin` defensively.
- The "Expire overdue" button does not touch `selectedApprovalId`, `decisionReason`,
  `submittingDecision`, or any other per-approval decision state.
- `loadApprovalList({ quiet: true })` after success uses the existing quiet-refresh path —
  `setRefreshing(true)` rather than `setLoading(true)`, consistent with the Refresh button.
- No new API endpoint is added. No backend file is modified.

---

## Risks

**1. Feedback clears immediately on quiet refresh triggered by success.**
`handleExpireOverdue` calls `loadApprovalList({ quiet: true })` after success. Because
`loadApprovalList` clears `expireResult` and `expireError` at the top of its try block, the
success message will disappear as soon as the refresh completes. This is the intended
behavior — the message confirms the action, and the refreshed list is the authoritative state.
The message is visible from success until the refresh resolves, which is typically < 500ms on
localhost. This is acceptable for an operational sweep control used by super_admins.

**2. Plural/singular edge case.**
The message "Expired N approval(s), N queue row(s) skipped" uses `=== 1` ternary for each
count. Edge cases: `expired_approvals: 0` renders "0 approvals" (correct). `expired_approvals:
1` renders "1 approval" (correct). The `?? 0` fallback handles an absent field.

**3. Button disabled during `loading` and `refreshing`.**
The button is disabled while the initial list fetch (`loading`) or a quiet refresh
(`refreshing`) is in progress. This prevents a race where the sweep runs concurrently with a
list fetch. The initial render always starts with `loading: true`, so the button is not
clickable until the first list load completes.
