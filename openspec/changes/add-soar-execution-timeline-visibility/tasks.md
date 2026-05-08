# Tasks: SOAR Execution Timeline Visibility (Phase 2.5G)

Read each file before editing it.
Run `pytest tests/ -x -q` after each step that modifies Python files.
Run `cd frontend && npm run build` after each step that modifies JS files.
Run `cd frontend && npm test -- --watchAll=false` after Step 4 and after Step 6.

**Stop conditions:**
- If any existing queue, approval, or route test fails after a step, revert that step
  before proceeding.
- Do not commit until all steps pass the full suite.

Only these files are modified in this change:
- `core/approval_store.py`
- `routes/admin_routes.py`
- `frontend/src/components/SoarQueuePanel.js`
- `tests/test_approval_store.py`
- `tests/test_soar_worker_admin_run_control.py`
- `frontend/src/components/SoarQueuePanel.test.js`

---

## Step 0: Pre-flight — read existing tests before any edits

Before writing any code, read the following in full:
- `tests/test_soar_worker_admin_run_control.py` — identify any test that asserts the exact
  set of keys returned by `GET /admin/soar/queue/<id>`, or checks `latest_approval`'s exact
  key count. These tests must be updated in Step 1c before running the suite.
- `tests/test_approval_store.py` — confirm whether `create_approval_request` is used as a
  fixture helper. If it is, a 'created' event will exist in the DB after setup — account for
  this in the "empty list" test.
- `frontend/src/components/SoarQueuePanel.test.js` — identify all detail fixtures
  (`queueDetailFixture`, `awaitingApprovalDetailFixture`, etc.) that lack `approval_events`.
  These need `approval_events: []` added in Step 4.

---

## Step 1: Update `core/approval_store.py`

Read `core/approval_store.py` in full before editing. Locate `EVENT_COLUMNS`,
`_event_row_to_dict`, and `get_approval_request`.

- [ ] Add `list_approval_events` after `get_approval_request`:

  ```python
  def list_approval_events(conn, approval_request_id: int) -> list[dict[str, Any]]:
      with conn.cursor() as cur:
          cur.execute(
              f"""
              SELECT {EVENT_COLUMNS}
              FROM approval_request_events
              WHERE approval_request_id = %s
              ORDER BY created_at ASC, id ASC
              """,
              (approval_request_id,),
          )
          return [_event_row_to_dict(row) for row in cur.fetchall()]
  ```

- [ ] Run `pytest tests/ -x -q` — all existing tests pass.

---

## Step 2: Update `routes/admin_routes.py`

Read `routes/admin_routes.py` in full before editing. Locate the import block,
`_serialize_approval_summary`, and `get_queue_item_detail`.

### 2a. Add import

- [ ] Add `list_approval_events` to the existing `from core.approval_store import ...` line.
  Do not duplicate if already present.

### 2b. Extend `_serialize_approval_summary`

- [ ] Add `"created_at": approval["created_at"]` to the returned dict:

  ```python
  def _serialize_approval_summary(approval):
      if approval is None:
          return None
      return {
          "id": approval["id"],
          "status": approval["status"],
          "risk_level": approval["risk_level"],
          "created_at": approval["created_at"],
          "expires_at": approval["expires_at"],
          "decided_at": approval["decided_at"],
      }
  ```

### 2c. Update `get_queue_item_detail`

- [ ] After `item["latest_approval"] = _serialize_approval_summary(approval)`, add:

  ```python
  item["approval_events"] = (
      list_approval_events(conn, approval["id"]) if approval is not None else []
  )
  ```

- [ ] If any existing test asserts an exact key set on the queue detail response or an exact
  key count on `latest_approval`, update those assertions now to include `approval_events`
  and `created_at` respectively.

- [ ] Run `pytest tests/ -x -q` — all existing tests pass.

---

## Step 3: Test Python changes

### 3a. Tests in `test_approval_store.py`

Read `tests/test_approval_store.py` in full before editing. Import `list_approval_events`.

- [ ] **Test: returns events ordered by `created_at ASC`**
  - Use `create_approval_request` (or direct insert) to create an approval and its
    associated 'created' event.
  - Insert a second event (e.g., 'denied') via `deny_request` or direct insert.
  - Call `list_approval_events(conn, approval_id)`.
  - Returns 2 items. `result[0]["event_type"] == "created"`.
    `result[1]["event_type"] == "denied"`.

- [ ] **Test: returns all fields from EVENT_COLUMNS**
  - Create an approval (creates a 'created' event).
  - Call `list_approval_events(conn, approval_id)`.
  - Result item has: `id`, `approval_request_id`, `event_type`, `actor_user_id`,
    `previous_status`, `new_status`, `comment`, `created_at`.

- [ ] **Test: filters by `approval_request_id`**
  - Create two separate approval requests, each with their own 'created' event.
  - Call `list_approval_events(conn, approval_id_1)`.
  - Returns items where all have `approval_request_id == approval_id_1`.

- [ ] **Test: returns empty list for unknown `approval_request_id`**
  - Call `list_approval_events(conn, 999999)` (no such approval).
  - Returns `[]`.

### 3b. Tests in `test_soar_worker_admin_run_control.py`

Read the file before editing. Find the queue item detail test section (tests for
`GET /admin/soar/queue/<id>`). Add the following tests after the Phase 2.5F tests.

- [ ] **Test: `approval_events` is empty list when no approval exists**
  - Insert queue row with no linked approval.
  - `GET /admin/soar/queue/<id>`.
  - `data["approval_events"] == []`.

- [ ] **Test: `approval_events` populated when approval exists**
  - Insert `awaiting_approval` queue row + call `create_approval_request` to create approval
    (which also creates a 'created' event).
  - `GET /admin/soar/queue/<id>`.
  - `len(data["approval_events"]) == 1`.
  - `data["approval_events"][0]["event_type"] == "created"`.
  - `data["approval_events"][0]["new_status"] == "pending"`.

- [ ] **Test: `approval_events` includes all lifecycle events**
  - Insert queue row + approval that is subsequently denied (creating 'created' + 'denied'
    events).
  - `GET /admin/soar/queue/<id>`.
  - `len(data["approval_events"]) == 2`.
  - Events ordered: `result[0]["event_type"] == "created"`,
    `result[1]["event_type"] == "denied"`.

- [ ] **Test: `latest_approval.created_at` is present**
  - Insert queue row + pending approval.
  - `GET /admin/soar/queue/<id>`.
  - `"created_at"` in `data["latest_approval"]`.
  - `data["latest_approval"]["created_at"]` is a non-empty string.

- [ ] Run `pytest tests/ -x -q` — all tests pass.

---

## Step 4: Update `SoarQueuePanel.js`

Read `frontend/src/components/SoarQueuePanel.js` in full before editing. Locate:
- The `formatQueueTimestamp` utility function (add `buildTimeline` and `getTimelineDotColor`
  after it, outside the component)
- The `selectedQueueItem ? ( <> ... </> )` Fragment added in Phase 2.5F (add the timeline
  section after the `approvalContextSectionStyle` block)
- The style constants block (add new timeline style constants here)

### 4a. Add `buildTimeline`

- [ ] Add after `formatQueueTimestamp`, outside the component:

  ```javascript
  function buildTimeline(queueItem) {
    const events = [];

    events.push({
      time: queueItem.created_at,
      type: "queued",
      label: "Action queued",
      detail: null,
    });

    const approvalTypeMap = {
      created:  { label: "Approval requested", type: "approval_created" },
      approved: { label: "Approval approved",  type: "approval_approved" },
      denied:   { label: "Approval denied",    type: "approval_denied" },
      expired:  { label: "Approval expired",   type: "approval_expired" },
    };

    for (const evt of (queueItem.approval_events || [])) {
      const mapped = approvalTypeMap[evt.event_type];
      if (mapped) {
        events.push({
          time: evt.created_at,
          type: mapped.type,
          label: mapped.label,
          detail: evt.comment || null,
        });
      }
    }

    if (queueItem.status === "success") {
      events.push({
        time: queueItem.updated_at,
        type: "success",
        label: "Action executed",
        detail: null,
      });
    } else if (queueItem.status === "failed") {
      events.push({
        time: queueItem.updated_at,
        type: "failed",
        label: "Action failed",
        detail: queueItem.last_error || null,
      });
    } else if (queueItem.status === "skipped") {
      events.push({
        time: queueItem.updated_at,
        type: "skipped",
        label: "Action skipped",
        detail: queueItem.last_error || null,
      });
    }

    return events;
  }
  ```

### 4b. Add `getTimelineDotColor`

- [ ] Add after `buildTimeline`:

  ```javascript
  function getTimelineDotColor(type) {
    if (type === "queued") return "#93c5fd";
    if (type === "approval_created") return "#fb923c";
    if (type === "approval_approved" || type === "success") return "#7ee787";
    if (type === "approval_denied" || type === "failed") return "#fca5a5";
    if (type === "approval_expired" || type === "skipped") return "#8b949e";
    return "#8b949e";
  }
  ```

### 4c. Add timeline JSX

- [ ] Inside the `selectedQueueItem ? ( <> ... </> )` Fragment, after the
  `{selectedQueueItem.latest_approval ? ... : null}` block, add:

  ```javascript
  <div style={timelineSectionStyle}>
    <div style={timelineHeaderStyle}>Execution Timeline</div>
    <ul style={timelineListStyle}>
      {buildTimeline(selectedQueueItem).map((evt, idx) => (
        <li key={idx} style={timelineItemStyle}>
          <span
            style={{
              ...timelineDotStyle,
              backgroundColor: getTimelineDotColor(evt.type),
            }}
          />
          <div style={timelineContentStyle}>
            <div style={timelineLabelStyle}>{evt.label}</div>
            {evt.detail ? (
              <div style={timelineDetailStyle}>{evt.detail}</div>
            ) : null}
          </div>
          <div style={timelineTimeStyle}>
            {formatQueueTimestamp(evt.time)}
          </div>
        </li>
      ))}
    </ul>
  </div>
  ```

### 4d. Add style constants

- [ ] Add alongside the existing style constants:

  ```javascript
  const timelineSectionStyle = {
    marginTop: "14px",
    paddingTop: "14px",
    borderTop: "1px solid #30363d",
  };

  const timelineHeaderStyle = {
    marginBottom: "10px",
    color: "#8b949e",
    fontSize: "12px",
    fontWeight: "700",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  };

  const timelineListStyle = {
    listStyle: "none",
    margin: 0,
    padding: 0,
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  };

  const timelineItemStyle = {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
  };

  const timelineDotStyle = {
    flexShrink: 0,
    marginTop: "4px",
    width: "8px",
    height: "8px",
    borderRadius: "50%",
  };

  const timelineContentStyle = {
    flex: 1,
    minWidth: 0,
  };

  const timelineLabelStyle = {
    fontSize: "13px",
    fontWeight: "600",
    color: "#e6edf3",
  };

  const timelineDetailStyle = {
    marginTop: "2px",
    fontSize: "12px",
    color: "#8b949e",
    overflowWrap: "break-word",
  };

  const timelineTimeStyle = {
    flexShrink: 0,
    fontSize: "12px",
    color: "#8b949e",
    whiteSpace: "nowrap",
  };
  ```

- [ ] Run `cd frontend && npm run build` — passes with no errors.

---

## Step 5: Update `SoarQueuePanel.test.js`

Read `frontend/src/components/SoarQueuePanel.test.js` in full before editing.

- [ ] Update all existing detail fixtures that lack `approval_events` to add
  `approval_events: []`. Also update `latest_approval` objects in those fixtures to include
  `created_at` where relevant. Confirm no existing test breaks after these fixture updates
  by running the test suite.

- [ ] Add fixtures:

  ```javascript
  const queueDetailWithEventsFixture = {
    id: 42,
    alert_id: 10,
    alert_reference: { status: "linked", label: "Alert 10" },
    action: "block_ip",
    status: "skipped",
    source_ip: "10.0.0.1",
    retry_count: 0,
    max_retries: 3,
    last_error: "approval denied",
    created_at: "2026-05-08T09:00:00Z",
    updated_at: "2026-05-08T09:30:05Z",
    idempotency_key: "idem-key-42",
    latest_approval: {
      id: 7,
      status: "denied",
      risk_level: "high",
      created_at: "2026-05-08T09:01:00Z",
      expires_at: "2026-05-08T10:00:00Z",
      decided_at: "2026-05-08T09:30:00Z",
    },
    approval_events: [
      {
        id: 1,
        approval_request_id: 7,
        event_type: "created",
        actor_user_id: null,
        previous_status: null,
        new_status: "pending",
        comment: null,
        created_at: "2026-05-08T09:01:00Z",
      },
      {
        id: 2,
        approval_request_id: 7,
        event_type: "denied",
        actor_user_id: 3,
        previous_status: "pending",
        new_status: "denied",
        comment: "Too broad",
        created_at: "2026-05-08T09:30:00Z",
      },
    ],
  };

  const queueDetailNoEventsFixture = {
    id: 43,
    alert_id: 11,
    alert_reference: { status: "linked", label: "Alert 11" },
    action: "block_ip",
    status: "pending",
    source_ip: "10.0.0.2",
    retry_count: 0,
    max_retries: 3,
    last_error: null,
    created_at: "2026-05-08T08:00:00Z",
    updated_at: "2026-05-08T08:00:00Z",
    idempotency_key: "idem-key-43",
    latest_approval: null,
    approval_events: [],
  };
  ```

- [ ] **Test: "Execution Timeline" section always renders**
  - `loadSoarQueueItem` resolves with `queueDetailNoEventsFixture`.
  - Click View.
  - `await waitFor`: `screen.getByText("Execution Timeline")` is in the document.

- [ ] **Test: "Action queued" event always renders**
  - Same setup as above.
  - `screen.getByText("Action queued")` is in the document.

- [ ] **Test: approval events render in timeline**
  - `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture`.
  - Click View.
  - `await waitFor`:
    - `screen.getByText("Approval requested")` is in the document.
    - `screen.getByText("Approval denied")` is in the document.

- [ ] **Test: decision comment renders as detail text**
  - `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture` (has `comment: "Too broad"`).
  - Click View.
  - `await waitFor`: `screen.getByText("Too broad")` is in the document.

- [ ] **Test: terminal event renders for skipped item**
  - `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture` (status `"skipped"`,
    `last_error: "approval denied"`).
  - Click View.
  - `await waitFor`:
    - `screen.getByText("Action skipped")` is in the document.
    - `screen.getByText("approval denied")` is in the document.

- [ ] **Test: no approve/deny button in timeline section**
  - `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture`.
  - Click View.
  - `screen.queryByRole("button", { name: /approve/i })` is null.
  - `screen.queryByRole("button", { name: /deny/i })` is null.

- [ ] Run `cd frontend && npm test -- --watchAll=false` — all tests pass, including existing ones.

---

## Step 6: Final audit

- [ ] Confirm only these files were created or modified:
  - `core/approval_store.py`
  - `routes/admin_routes.py`
  - `frontend/src/components/SoarQueuePanel.js`
  - `tests/test_approval_store.py`
  - `tests/test_soar_worker_admin_run_control.py`
  - `frontend/src/components/SoarQueuePanel.test.js`
- [ ] Confirm `approval_routes.py` was NOT modified.
- [ ] Confirm `ApprovalsPanel.js` was NOT modified.
- [ ] Confirm `approvalService.js` was NOT modified.
- [ ] Confirm `soarQueueService.js` was NOT modified.
- [ ] Confirm `soar_action_worker.py` was NOT modified.
- [ ] Confirm no `<button>` for approve or deny appears in new JSX.
- [ ] Confirm `buildTimeline` and `getTimelineDotColor` are defined outside the React
  component (they are pure functions, not hooks or component methods).
- [ ] Confirm `list_approval_events` does not call `conn.commit()`.
- [ ] Confirm `item["approval_events"]` assignment is inside the try block of
  `get_queue_item_detail`, while `conn` is still open.
- [ ] Run full Python suite: `pytest tests/ -x -q` — clean.
- [ ] Run full frontend suite: `cd frontend && npm test -- --watchAll=false` — clean.
