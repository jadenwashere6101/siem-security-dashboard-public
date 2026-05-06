# Design: SOAR Queue Item Detail UI

---

## 1. UI Placement

Extend the existing SOAR Queue panel:

```text
frontend/src/components/SoarQueuePanel.js
```

Do not add a separate route or page for the first version. The detail view should
live next to the recent queue table as an operational inspection surface.

Recommended layouts:

- inline detail panel below the table
- side-by-side detail panel on wide screens
- compact drawer-like panel if the current dashboard style already uses that
  pattern

Avoid modal-only behavior unless the app already uses modals for admin detail
views. A persistent panel keeps queue context visible while inspecting an item.

---

## 2. Service Integration

Use the existing service method if present:

```javascript
loadSoarQueueItem(queueId)
```

Expected request:

```text
GET /admin/soar/queue/<id>
```

Rules:

- use `credentials: "include"` through the service
- reuse existing JSON parsing and error helper conventions
- do not add POST/PATCH/DELETE service methods for this change
- do not alter the backend detail response shape

If the service method is missing during implementation, add only the read-only
GET helper needed for this endpoint.

---

## 3. Component State

Add focused detail state:

```javascript
const [selectedQueueId, setSelectedQueueId] = useState(null);
const [selectedQueueItem, setSelectedQueueItem] = useState(null);
const [detailLoading, setDetailLoading] = useState(false);
const [detailError, setDetailError] = useState("");
```

When selecting a row:

1. set `selectedQueueId`
2. clear prior detail error
3. set detail loading
4. call `loadSoarQueueItem(id)`
5. set `selectedQueueItem`
6. clear loading

If the selected row disappears after a queue refresh, keep the selected detail
visible until the user closes it or selects another item. Do not clear useful
detail context just because the recent list changed.

---

## 4. Row Interaction

Recent queue rows should expose a clear view affordance.

Acceptable options:

- make the row clickable and add hover/focus styling
- add a small `View` button in a final table column

Recommended first version:

- add a `View` button or text button per row

Rationale:

- more accessible than making an entire table row clickable
- clearer for keyboard users
- avoids accidental selection when admins are scanning table data

The `View` control must only fetch details. It must not mutate queue state.

---

## 5. Detail Fields

Render these fields:

- Queue ID
- Alert reference
- Action
- Status
- Source IP
- Retries
- Last error
- Created
- Updated
- Idempotency key

Format retries as:

```text
retry_count / max_retries
```

Format alert reference using the same logic as list rows:

- `alert_reference.label` if present
- `Alert <id>` if `alert_id` is present
- `"Deleted alert"` or `"N/A"` if `alert_id` is null/missing

For status, reuse the same badge style as the table where practical.

---

## 6. Long Text Handling

`last_error` and `idempotency_key` can be long.

Rules:

- list view must still not show `idempotency_key`
- detail view can show `idempotency_key`
- wrap long values in a monospace block or pre-wrapped field
- avoid horizontal overflow on mobile/narrow containers
- preserve enough text to support admin investigation

Suggested styling:

```javascript
{
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  fontFamily: "'Courier New', monospace"
}
```

Do not show raw stack traces as primary UI. If `last_error` contains multiline or
stack-like content, render it as wrapped text inside the detail field without
breaking the layout.

---

## 7. Loading, Error, Empty, and Close States

No selection:

```text
Select a queue item to view details.
```

Loading:

```text
Loading queue item details...
```

Error:

```text
Unable to load SOAR queue item.
```

Use the service error message if it is concise and safe. Do not render raw HTML
or stack traces.

Close behavior:

- provide a simple close/dismiss control for the detail panel
- closing clears selected item state
- closing does not refresh or mutate queue data

---

## 8. Refresh Interaction

Manual refresh and worker-run refresh should continue refreshing the queue status
counts and recent list.

Detail behavior during refresh:

- do not automatically refetch selected detail unless implementation can do so
  cleanly
- do not clear selected detail on list refresh failure
- if the selected item is refreshed explicitly by selecting it again, replace the
  detail with the newest response

A later enhancement can add a separate detail refresh button if needed. Do not
add it in this first version unless it is trivial and read-only.

---

## 9. Read-Only Safety

The detail view must not include:

- retry button
- replay button
- cancel button
- delete button
- run worker button scoped to the selected row
- real firewall execution control
- adapter controls
- playbook/incident actions

The only allowed detail action is view/select/close. The existing panel-level
manual simulation batch control can remain unchanged.

---

## 10. Testing Strategy

### Service tests

If existing service tests cover `soarQueueService`, add or extend coverage for:

- `loadSoarQueueItem(123)` calls `/admin/soar/queue/123`
- request uses `credentials: "include"`
- failed responses surface a safe error message

If this service method is already covered, no duplicate test is required.

### Component tests

If React component tests are already configured, cover:

- no-selection detail state renders
- clicking `View` fetches detail
- loading state renders
- detail fields render after success
- `alert_id: null` renders `"Deleted alert"` or `"N/A"`
- `idempotency_key` appears in detail
- `idempotency_key` does not appear in list rows
- error state renders after failed detail fetch
- no retry/replay/cancel controls are present

Do not introduce broad frontend test infrastructure solely for this change.

### Build verification

Run:

```bash
cd frontend
npm run build
```

If frontend tests are added, run the relevant test command too.
