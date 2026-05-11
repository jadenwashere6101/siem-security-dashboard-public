# Design: SOAR Execution Timeline Visibility (Phase 2.5G)

---

## Current state (context only)

### Data available per queue detail response (after Phase 2.5F)

```json
{
  "id": 42,
  "action": "block_ip",
  "source_ip": "10.0.0.1",
  "status": "skipped",
  "last_error": "approval denied",
  "created_at": "2026-05-08T09:00:00Z",
  "updated_at": "2026-05-08T09:30:05Z",
  ...,
  "latest_approval": {
    "id": 7,
    "status": "denied",
    "risk_level": "high",
    "expires_at": "2026-05-08T10:00:00Z",
    "decided_at": "2026-05-08T09:30:00Z"
  }
}
```

`approval_events` is not yet in the response. `latest_approval.created_at` is not yet
included.

### `approval_request_events` table

```sql
CREATE TABLE IF NOT EXISTS approval_request_events (
    id SERIAL PRIMARY KEY,
    approval_request_id INTEGER NOT NULL
        REFERENCES approval_requests(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('created', 'approved', 'denied', 'expired')),
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Indexed on `approval_request_id` and `created_at`. Already serialized by
`_event_row_to_dict` in `approval_store.py`. Fetched inside `get_approval_request` but not
exposed in any queue endpoint.

### `get_approval_request` (approval_store.py)

Already fetches events for a given approval in one function call (approval + events
together). No standalone `list_approval_events` function currently exists as an exported
function.

---

## Change 1: `core/approval_store.py`

### Add `list_approval_events`

Add after `get_approval_request`:

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

This is the same query embedded in `get_approval_request`, extracted as a standalone
export. Returns `[]` when no events exist (new approval with no event rows).

Each returned dict has: `id`, `approval_request_id`, `event_type`, `actor_user_id`,
`previous_status`, `new_status`, `comment`, `created_at` (ISO string).

---

## Change 2: `routes/admin_routes.py`

### 2a. Update import

Add `list_approval_events` to the `from core.approval_store import ...` line.

### 2b. Extend `_serialize_approval_summary`

Current (5 fields):
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

Change to (6 fields — add `created_at`):
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

`created_at` is needed by the frontend to place "Approval requested" correctly on the
timeline. The Phase 2.5F tests that check `latest_approval` fields will not break — they
assert specific keys are absent (sensitive fields), not that only 5 keys exist.

### 2c. Update `get_queue_item_detail`

Current (after Phase 2.5F):
```python
item = _serialize_queue_item_for_detail(queue_row)
approval = get_latest_approval_for_queue_action(
    conn, queue_id=queue_id, action=queue_row["action"]
)
item["latest_approval"] = _serialize_approval_summary(approval)
return jsonify(item), 200
```

Change to:
```python
item = _serialize_queue_item_for_detail(queue_row)
approval = get_latest_approval_for_queue_action(
    conn, queue_id=queue_id, action=queue_row["action"]
)
item["latest_approval"] = _serialize_approval_summary(approval)
item["approval_events"] = (
    list_approval_events(conn, approval["id"]) if approval is not None else []
)
return jsonify(item), 200
```

`approval_events` is always an array — empty `[]` when no linked approval exists, populated
when one does. The `if approval is not None` guard prevents calling `list_approval_events`
with a `None` id.

---

## Change 3: `frontend/src/components/SoarQueuePanel.js`

### 3a. Add `buildTimeline` helper function

Add below the `formatQueueTimestamp` function (outside the component):

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

`buildTimeline` is a pure function — no React, no state, no hooks. Events are appended in
chronological order: queue creation → approval events (already sorted by backend) →
terminal queue event (which always occurs after approval events). No sort is needed.

The `approvalTypeMap` guard (`if (mapped)`) silently skips any future event_type values not
yet in the map, making it forward-compatible.

### 3b. Add `getTimelineDotColor` helper function

Add below `buildTimeline`:

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

Color assignments:
- `queued`: blue `#93c5fd` — matches `runningBadgeStyle` color family; neutral queue event
- `approval_created`: amber `#fb923c` — matches `awaitingApprovalBadgeStyle`; signals a
  gate was opened
- `approval_approved` / `success`: green `#7ee787` — matches `approvedBadgeStyle`
- `approval_denied` / `failed`: red `#fca5a5` — matches `deniedBadgeStyle`
- `approval_expired` / `skipped`: gray `#8b949e` — matches `expiredBadgeStyle`

### 3c. Add timeline section JSX

Inside the `selectedQueueItem ? ( <> ... </> )` Fragment (added in Phase 2.5F), after the
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

`buildTimeline` always returns at least one event ("Action queued"), so the `<ul>` is
never empty. No empty-state handling is needed.

`key={idx}` is used instead of `key={evt.time}` because two events could theoretically
share a timestamp. The timeline is append-only from this component's perspective — no
reordering or filtering — so index keys are safe here.

### 3d. Add style constants

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

`timelineContentStyle` uses `flex: 1; min-width: 0` to allow long detail text to wrap
rather than overflow. `timelineTimeStyle` uses `flex-shrink: 0; white-space: nowrap` so the
timestamp never wraps and always right-aligns in the row.

### Timeline examples

**Pending, non-gated action (no approval):**
```
● Action queued      09:00:00
```

**Awaiting approval:**
```
● Action queued        09:00:00
● Approval requested   09:01:00
```

**Skipped after denial:**
```
● Action queued        09:00:00
● Approval requested   09:01:00
● Approval denied      09:30:00    Too broad a block
● Action skipped       09:30:05    approval denied
```

**Skipped after expiration:**
```
● Action queued        09:00:00
● Approval requested   09:01:00
● Approval expired     10:01:00
● Action skipped       10:01:05    approval expired
```

---

## Changes to `tests/test_approval_store.py`

Read the file before editing. Match fixture and DB patterns of existing approval store tests.
Import `list_approval_events`.

- **Test: returns empty list when no events**
  - Insert an approval request.
  - Call `list_approval_events(conn, approval_id)`.
  - Returns `[]`.
  - *(Note: `create_approval_request` itself creates a 'created' event — insert a raw
    approval row directly if you need zero events, or call the function and expect 1 event.)*

- **Test: returns events ordered by `created_at ASC`**
  - Insert approval + let `create_approval_request` write the 'created' event.
  - Insert an 'approved' event after.
  - Call `list_approval_events(conn, approval_id)`.
  - Returns 2 items. `result[0]["event_type"] == "created"`.
    `result[1]["event_type"] == "approved"`.

- **Test: returns all fields from `EVENT_COLUMNS`**
  - Insert approval, create one event.
  - Call `list_approval_events`.
  - Result item has: `id`, `approval_request_id`, `event_type`, `actor_user_id`,
    `previous_status`, `new_status`, `comment`, `created_at`.

- **Test: filters by `approval_request_id`**
  - Insert two approval requests, each with one event.
  - Call `list_approval_events(conn, approval_id_1)`.
  - Returns only 1 item with `approval_request_id == approval_id_1`.

---

## Changes to `tests/test_soar_worker_admin_run_control.py`

Read the file before editing. Find the queue item detail test section. Add tests after the
Phase 2.5F tests for `latest_approval`.

- **Test: `approval_events` is empty list when no approval exists**
  - Insert queue row with no linked approval.
  - `GET /admin/soar/queue/<id>`.
  - `data["approval_events"] == []`.

- **Test: `approval_events` populated when approval exists**
  - Insert `awaiting_approval` queue row + pending approval (which creates a 'created' event
    via `create_approval_request`).
  - `GET /admin/soar/queue/<id>`.
  - `len(data["approval_events"]) == 1`.
  - `data["approval_events"][0]["event_type"] == "created"`.
  - `data["approval_events"][0]["new_status"] == "pending"`.

- **Test: `approval_events` includes all events for approval lifecycle**
  - Insert queue row + approval that is then denied.
  - `GET /admin/soar/queue/<id>`.
  - `len(data["approval_events"]) == 2` (created + denied).
  - Events are ordered: first `created`, then `denied`.

- **Test: `latest_approval.created_at` is present**
  - Insert queue row + pending approval.
  - `GET /admin/soar/queue/<id>`.
  - `"created_at"` in `data["latest_approval"]`.
  - Value is an ISO-format string.

---

## Changes to `frontend/src/components/SoarQueuePanel.test.js`

Read the file before editing. Update fixture(s) that model queue detail responses to include
`approval_events: []` (or a populated array) so they match the new response shape.

Add fixtures:

```javascript
const queueDetailWithEventsFixture = {
  ...queueDetailWithApprovalFixture,  // from Phase 2.5F
  latest_approval: {
    id: 7,
    status: "denied",
    risk_level: "high",
    created_at: "2026-05-08T09:01:00Z",    // extended in 2.5G
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

const queueDetailNoApprovalFixture = {
  ...queueDetailWithoutApprovalFixture,  // from Phase 2.5F
  approval_events: [],
};
```

Also update any existing fixtures (`queueDetailFixture`, `awaitingApprovalDetailFixture`,
`queueDetailWithApprovalFixture`, `queueDetailWithoutApprovalFixture`) to include
`approval_events: []` if they do not already, so existing tests remain consistent with the
new response shape.

### New tests

**Test: "Execution Timeline" section always renders when detail loaded**
- `loadSoarQueueItem` resolves with `queueDetailNoApprovalFixture` (no approval, no events).
- Click View.
- `await waitFor`: `screen.getByText("Execution Timeline")` is in the document.

**Test: "Action queued" event always renders**
- `loadSoarQueueItem` resolves with `queueDetailNoApprovalFixture`.
- Click View.
- `await waitFor`: `screen.getByText("Action queued")` is in the document.

**Test: approval events render in timeline**
- `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture`.
- Click View.
- `await waitFor`:
  - `screen.getByText("Approval requested")` is in the document.
  - `screen.getByText("Approval denied")` is in the document.

**Test: decision comment renders as detail text**
- `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture` (has `comment: "Too broad"`).
- Click View.
- `await waitFor`: `screen.getByText("Too broad")` is in the document.

**Test: terminal event renders for skipped item**
- `loadSoarQueueItem` resolves with a fixture where `status: "skipped"` and
  `last_error: "approval denied"`.
- Click View.
- `await waitFor`:
  - `screen.getByText("Action skipped")` is in the document.
  - `screen.getByText("approval denied")` is in the document (as detail).

**Test: no approve/deny button in timeline section**
- `loadSoarQueueItem` resolves with `queueDetailWithEventsFixture`.
- Click View.
- `screen.queryByRole("button", { name: /approve/i })` is null.
- `screen.queryByRole("button", { name: /deny/i })` is null.

---

## Files changed

- `core/approval_store.py` — one new exported function (`list_approval_events`).
- `routes/admin_routes.py` — one import addition, `created_at` added to
  `_serialize_approval_summary`, two lines added to `get_queue_item_detail`.
- `frontend/src/components/SoarQueuePanel.js` — `buildTimeline` function,
  `getTimelineDotColor` function, timeline section JSX, eight style constants.
- `tests/test_approval_store.py` — four new tests for `list_approval_events`.
- `tests/test_soar_worker_admin_run_control.py` — four new tests for `approval_events`
  and `latest_approval.created_at`.
- `frontend/src/components/SoarQueuePanel.test.js` — fixture updates + six new tests.

No other files are created or modified.

---

## Safety boundaries

- `list_approval_events` is a SELECT-only function. No mutation.
- `get_queue_item_detail` gains one additional read call. The call is inside the existing
  try/except/finally — same connection lifecycle, same rollback and close coverage.
- `buildTimeline` and `getTimelineDotColor` are pure functions outside the component. No
  state, no hooks, no side effects.
- No approve/deny control appears in any new JSX.
- `SoarQueuePanel.js` does not import from `approvalService.js`.
- `approval_routes.py`, `ApprovalsPanel.js`, and `soarQueueService.js` are not modified.

---

## Risks

**1. `approval_events` field breaks existing queue detail response shape tests.**
Any test that asserts `list(data.keys())` or an exact key count on the queue detail response
will fail. Also, any test that checks the `latest_approval` dict for an exact key set will
fail when `created_at` is added. Identify and update these before Step 1. Read
`test_soar_worker_admin_run_control.py` in full before touching `admin_routes.py`.

**2. Existing SoarQueuePanel.test.js fixtures lack `approval_events`.**
`queueDetailFixture`, `awaitingApprovalDetailFixture`, and Phase 2.5F fixtures do not yet
include `approval_events`. When `buildTimeline` reads `queueItem.approval_events || []`,
the `|| []` fallback prevents crashes — but tests that assert the detail panel renders
correctly should use fixtures with the correct shape. Update all detail fixtures to add
`approval_events: []` before adding new tests.

**3. `queue.updated_at` is imprecise for multi-step journeys.**
For a queue item that went `pending → running → awaiting_approval → skipped`, `updated_at`
reflects the most recent change only. The timeline shows "Action skipped" at `updated_at`
which is the correct terminal timestamp. The intermediate `running` transition is invisible
since no queue transition history table exists. This is a known limitation documented in the
proposal — not a bug to fix in this phase.

**4. `create_approval_request` always creates a 'created' event.**
The test "returns empty list when no events" requires inserting a raw approval row without
calling `create_approval_request`. If the test helper used by other tests calls
`create_approval_request`, a 'created' event will exist. Read the test helper before writing
the empty-list test and adjust accordingly (insert raw row directly, or accept 1 event as
the minimum).

**5. The `approval_events` filter by `approval_request_id` only returns events for the
most recent approval.**
If a queue item had multiple approval cycles (denied, re-requested), only the most recent
approval's events are shown. This is consistent with `latest_approval` (also most recent).
For Phase 3, if multiple approval cycles per queue item become necessary, a different
architecture will be needed.
