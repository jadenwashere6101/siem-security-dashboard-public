# Design: Link Approvals and Queue Visibility (Phase 2.5F)

---

## Current state (context only)

### Backend

`GET /admin/soar/queue/<id>` calls `get_queue_action(conn, queue_id)` and serializes with
`_serialize_queue_item_for_detail`. Returns: id, alert_id, alert_reference, source_ip,
action, status, retry_count, max_retries, last_error, created_at, updated_at,
idempotency_key. No approval data.

`get_latest_approval_for_queue_action(conn, *, queue_id, action)` exists in
`core/approval_store.py`. It executes:
```sql
SELECT {REQUEST_COLUMNS} FROM approval_requests
WHERE queue_id = %s AND action = %s
ORDER BY created_at DESC, id DESC LIMIT 1
```
Returns a full approval dict (14 fields) or `None`.

### SoarQueuePanel.js

Detail panel: `selectedQueueItem ?` ternary returns a single `<div style={detailGridStyle}>`.
Inside: ten `DetailField` components + one conditional `approvalWaitingNoteStyle` div when
`status === "awaiting_approval"`. No approval data is available to render.

### ApprovalsPanel.js

Approval detail grid renders `<DetailField label="Queue ID" value={selectedApproval.queue_id ?? "N/A"} mono />`.
The label is "Queue ID" — minimal context, no note about what queue item it refers to or
where to view it.

---

## Change 1: `routes/admin_routes.py`

### 1a. Add import

Add to the existing `from core.approval_store import ...` import line:

```python
from core.approval_store import (
    ...,                          # existing imports
    get_latest_approval_for_queue_action,
)
```

If `get_latest_approval_for_queue_action` is already imported, do not duplicate it.

### 1b. Add `_serialize_approval_summary` helper

Add near the other `_serialize_*` helpers:

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

Five fields only. Excluded: `queue_id` (redundant — same as the queue item's id), `action`
(redundant — same as queue item's action), `incident_id`, `request_reason`,
`decision_comment`, `requested_by`, `approved_by`, `decided_by`. The five included fields
are sufficient to understand the approval's state from the queue detail view. An admin who
needs more can look up the approval in the Approvals panel using the returned `id`.

### 1c. Update `get_queue_item_detail`

Current:
```python
def get_queue_item_detail(queue_id):
    conn = None
    try:
        conn = get_db_connection()
        queue_row = get_queue_action(conn, queue_id)
        if queue_row is None:
            return jsonify({"error": "Queue item not found"}), 404
        item = _serialize_queue_item_for_detail(queue_row)
        return jsonify(item), 200
    ...
```

Change to:
```python
def get_queue_item_detail(queue_id):
    conn = None
    try:
        conn = get_db_connection()
        queue_row = get_queue_action(conn, queue_id)
        if queue_row is None:
            return jsonify({"error": "Queue item not found"}), 404
        item = _serialize_queue_item_for_detail(queue_row)
        approval = get_latest_approval_for_queue_action(
            conn, queue_id=queue_id, action=queue_row["action"]
        )
        item["latest_approval"] = _serialize_approval_summary(approval)
        return jsonify(item), 200
    ...
```

`get_latest_approval_for_queue_action` uses a shared read-only connection with no transaction
side effects. The call is made while the connection is still open, before `conn.close()`.

`latest_approval` is `null` in the JSON response for queue items with no approval record
(all non-`block_ip` actions, or `block_ip` items created before approval tracking existed).

---

## Change 2: `frontend/src/components/SoarQueuePanel.js`

### 2a. Fragment restructure of `selectedQueueItem ?` branch

The current ternary returns a single `<div style={detailGridStyle}>`. The approval context
section must be a sibling of that div, which requires a React Fragment:

Current:
```javascript
} : selectedQueueItem ? (
  <div style={detailGridStyle}>
    ...existing fields...
  </div>
) : (
  <p style={emptyTextStyle}>Select a queue item to view details.</p>
)}
```

Change to:
```javascript
} : selectedQueueItem ? (
  <>
    <div style={detailGridStyle}>
      ...existing fields unchanged...
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

The existing content of `detailGridStyle` (all ten `DetailField` components + the
`approvalWaitingNoteStyle` note) is unchanged.

### 2b. Add style constants

Add alongside existing style constants:

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

`approvalContextSectionStyle`: adds visual separation from the queue fields above via
`borderTop` + `marginTop`. No background color — keeps the section visually part of the
same detail panel.

`approvalContextHeaderStyle`: matches the `tableMetaLabelStyle` pattern used elsewhere
(all-caps, muted gray, small font) to signal a section header.

`approvalContextGridStyle`: independent grid for the approval fields. `minmax(160px, 1fr)`
matches the spacing of `detailGridStyle` (`minmax(180px, 1fr)`) but slightly narrower since
these fields have shorter labels.

### Verification: no approve/deny controls

The approval context section contains only `DetailField` components (read-only display)
and style divs. No `<button>`, no `onClick` handlers on approval fields, no import from
`approvalService.js`, no call to `submitApprovalDecision`. `SoarQueuePanel.js` does not
gain any import from the approval service.

---

## Change 3: `frontend/src/components/ApprovalsPanel.js`

### 3a. Rename "Queue ID" label

Current (line ~292):
```javascript
<DetailField label="Queue ID" value={selectedApproval.queue_id ?? "N/A"} mono />
```

Change to:
```javascript
<DetailField label="Linked Queue Item" value={selectedApproval.queue_id ?? "N/A"} mono />
```

### 3b. Add queue link note inside `detailGridStyle`

After the existing `DetailField` block (after "Decision Comment") and before the closing
`</div>` of `detailGridStyle`, add:

```javascript
{selectedApproval.queue_id !== null && selectedApproval.queue_id !== undefined ? (
  <div style={queueLinkNoteStyle}>
    This approval is linked to Queue Item #{selectedApproval.queue_id}. Open the SOAR
    Queue panel to view its current execution status.
  </div>
) : null}
```

The note uses `gridColumn: "1 / -1"` via `queueLinkNoteStyle` to span all columns of
`detailGridStyle` (`gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))"`).

### 3c. Add style constant

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

Muted gray — informational, not a warning. Matches the muted tone of `tableMetaLabelStyle`
and `emptyTextStyle`. Distinct from `approvalWaitingNoteStyle` in SoarQueuePanel (which uses
orange-amber for an action-required signal) because this note is purely informational context.

### Verification: `approval_routes.py` not touched

`ApprovalsPanel.js` does not call any queue API endpoint. The queue link note is computed
entirely from `selectedApproval.queue_id`, which is already present in the approval detail
response. No new fetch, no new import, no change to `approvalService.js`.

---

## Changes to `tests/test_soar_worker_admin_run_control.py`

Read the existing test file before editing. Find the tests for `GET /admin/soar/queue/<id>`.
Add the following tests in that section.

### Test: `latest_approval` is null for queue item with no linked approval

```python
def test_queue_item_detail_latest_approval_null_when_no_approval(
    client, super_admin_session, postgres_db
):
    conn = postgres_db
    # Insert a queue row for a non-approval-gated action or one with no approval record
    queue_id = insert_queue_row(conn, action="block_ip", status="pending")
    conn.commit()
    resp = client.get(f"/admin/soar/queue/{queue_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["latest_approval"] is None
```

### Test: `latest_approval` populated when approval exists

```python
def test_queue_item_detail_latest_approval_present(
    client, super_admin_session, postgres_db
):
    conn = postgres_db
    queue_id = insert_queue_row(conn, action="block_ip", status="awaiting_approval")
    approval_id = insert_approval_request(
        conn, queue_id=queue_id, action="block_ip", status="pending"
    )
    conn.commit()
    resp = client.get(f"/admin/soar/queue/{queue_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["latest_approval"] is not None
    assert data["latest_approval"]["id"] == approval_id
    assert data["latest_approval"]["status"] == "pending"
    assert "risk_level" in data["latest_approval"]
    assert "expires_at" in data["latest_approval"]
    assert "decided_at" in data["latest_approval"]
```

### Test: `latest_approval` reflects most recent approval when multiple exist

```python
def test_queue_item_detail_latest_approval_is_most_recent(
    client, super_admin_session, postgres_db
):
    conn = postgres_db
    queue_id = insert_queue_row(conn, action="block_ip", status="awaiting_approval")
    insert_approval_request(
        conn, queue_id=queue_id, action="block_ip", status="expired"
    )
    approval_id_2 = insert_approval_request(
        conn, queue_id=queue_id, action="block_ip", status="pending"
    )
    conn.commit()
    resp = client.get(f"/admin/soar/queue/{queue_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["latest_approval"]["id"] == approval_id_2
    assert data["latest_approval"]["status"] == "pending"
```

### Test: `latest_approval` does not include sensitive fields

```python
def test_queue_item_detail_latest_approval_excludes_sensitive_fields(
    client, super_admin_session, postgres_db
):
    conn = postgres_db
    queue_id = insert_queue_row(conn, action="block_ip", status="awaiting_approval")
    insert_approval_request(conn, queue_id=queue_id, action="block_ip", status="pending")
    conn.commit()
    resp = client.get(f"/admin/soar/queue/{queue_id}")
    data = resp.get_json()
    la = data["latest_approval"]
    assert "requested_by" not in la
    assert "approved_by" not in la
    assert "decided_by" not in la
    assert "request_reason" not in la
    assert "decision_comment" not in la
```

---

## Changes to `frontend/src/components/SoarQueuePanel.test.js`

Read the existing test file before editing. Match its fixture and mock patterns.

### Add fixture for queue item with approval

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

### New tests

**Test: "Linked Approval" section renders when `latest_approval` is non-null**

- `loadSoarQueueStatus` resolves with status fixture.
- `loadRecentSoarQueueItems` resolves with a row fixture containing `id: 42`.
- `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
- Click View for item 42.
- `await waitFor`: `screen.getByText("Linked Approval")` is in the document.
- `screen.getByText("#7")` is in the document (Approval ID field).
- `screen.getAllByText("Pending")` has at least one element (Approval Status badge).

**Test: "Linked Approval" section absent when `latest_approval` is null**

- Same setup but `loadSoarQueueItem` resolves with `queueDetailWithoutApprovalFixture`.
- After detail loads: `screen.queryByText("Linked Approval")` is null.

**Test: all five approval summary fields render**

- `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
- Click View. After load:
  - `screen.getByText("Approval ID")` (label) — or look for `"#7"` (value).
  - `screen.getByText("Approval Status")` — or look for label text.
  - `screen.getByText("Risk")` — or look for the value "High".
  - `screen.getByText("Expires")` in document.
  - `screen.getByText("Decided")` in document.

**Test: no approve/deny button in approval context section**

- `loadSoarQueueItem` resolves with `queueDetailWithApprovalFixture`.
- After detail loads:
  - `screen.queryByRole("button", { name: /approve/i })` is null.
  - `screen.queryByRole("button", { name: /deny/i })` is null.

---

## Changes to `frontend/src/components/ApprovalsPanel.test.js`

### New tests

**Test: queue link note renders when `queue_id` is non-null**

```javascript
it('renders queue link note when approval has a queue_id', async () => {
  listApprovals.mockResolvedValue({ approvals: [approvalRowFixture] });
  getApproval.mockResolvedValue({
    approval: { ...approvalDetailFixture, queue_id: 42 },
  });
  renderPanel();
  // click the approval row to open detail
  await screen.findByText(/* some approval row identifier */);
  // trigger detail load
  ...
  await waitFor(() => {
    expect(screen.getByText(/This approval is linked to Queue Item #42/i)).toBeInTheDocument();
  });
});
```

**Test: queue link note absent when `queue_id` is null**

```javascript
it('does not render queue link note when queue_id is null', async () => {
  listApprovals.mockResolvedValue({ approvals: [approvalRowFixture] });
  getApproval.mockResolvedValue({
    approval: { ...approvalDetailFixture, queue_id: null },
  });
  renderPanel();
  // open detail
  ...
  await waitFor(() => {
    expect(screen.queryByText(/This approval is linked to Queue Item/i)).toBeNull();
  });
});
```

**Test: "Linked Queue Item" label renders in detail (replaces "Queue ID")**

```javascript
it('renders "Linked Queue Item" label in approval detail', async () => {
  listApprovals.mockResolvedValue({ approvals: [approvalRowFixture] });
  getApproval.mockResolvedValue({ approval: { ...approvalDetailFixture, queue_id: 42 } });
  renderPanel();
  // open detail
  ...
  await waitFor(() => {
    expect(screen.getByText("Linked Queue Item")).toBeInTheDocument();
    expect(screen.queryByText("Queue ID")).toBeNull();
  });
});
```

---

## Files changed

- `routes/admin_routes.py` — one import, one new helper function, one route update.
- `frontend/src/components/SoarQueuePanel.js` — Fragment restructure + approval context
  subsection JSX + three style constants.
- `frontend/src/components/ApprovalsPanel.js` — one label rename + one conditional note
  block + one style constant.
- `tests/test_soar_worker_admin_run_control.py` — four new tests for `latest_approval`.
- `frontend/src/components/SoarQueuePanel.test.js` — two fixtures + four new tests.
- `frontend/src/components/ApprovalsPanel.test.js` — three new tests.

No other files are created or modified.

---

## Safety boundaries

- `SoarQueuePanel.js` does not import from `approvalService.js` and does not call any
  approval mutation endpoint.
- `ApprovalsPanel.js` does not call any queue endpoint and does not import from
  `soarQueueService.js`.
- The `_serialize_approval_summary` helper cannot mutate state — it is a pure dict
  projection from an already-fetched approval record.
- `get_latest_approval_for_queue_action` is read-only (SELECT only). The call is inside
  the existing try/except/finally of `get_queue_item_detail`, so the existing rollback
  and connection-close logic covers it.
- `approval_routes.py` is not touched. The approval detail endpoint remains unchanged.

---

## Risks

**1. `get_latest_approval_for_queue_action` adds a second DB query to `GET /admin/soar/queue/<id>`.**
This is a single indexed lookup (`WHERE queue_id = %s AND action = %s ORDER BY created_at DESC
LIMIT 1`). The `approval_requests` table already has an index on `(status, expires_at)`.
Whether there is an index on `(queue_id, action, created_at)` is unconfirmed — verify during
Step 0. If no suitable index exists, add one. For a read-only admin detail view, even a
seq scan on a small table is acceptable, but an index is better.

**2. `latest_approval` field breaks existing queue detail test assertions.**
Any test that asserts on the exact set of keys in the queue detail response will fail when
`latest_approval` is added. Identify these tests before implementing and update them to
expect the new field. Read `test_soar_worker_admin_run_control.py` in full before Step 2.

**3. Fragment restructure in SoarQueuePanel.js.**
Changing from `<div style={detailGridStyle}>` to `<>...<div>...</div>...</>` affects the
JSX structure. Existing tests that query by content inside the detail panel are unaffected
(they find elements regardless of wrapper). The `approvalWaitingNoteStyle` block remains
inside `detailGridStyle` and is not moved.

**4. "Linked Queue Item" label rename in ApprovalsPanel.js.**
Any test that asserts `screen.getByText("Queue ID")` will fail. Read the test file before
editing to identify and update these assertions.

**5. null vs undefined for `queue_id`.**
The approval detail serializer returns `None` → `null` in JSON. JavaScript `null !== undefined`.
The note condition checks both: `queue_id !== null && queue_id !== undefined`. This is
consistent with the `?? "N/A"` fallback already used on the `DetailField`.
