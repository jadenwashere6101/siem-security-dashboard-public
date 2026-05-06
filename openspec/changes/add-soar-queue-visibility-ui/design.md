# Design: SOAR Queue Visibility UI

---

## 1. UI Placement

Add a read-only admin-facing panel for SOAR queue visibility.

Recommended placement:

```text
frontend/src/components/SoarQueuePanel.js
frontend/src/services/soarQueueService.js
```

Integrate into the existing admin/navigation shell in `frontend/src/App.js` using
the current section/panel pattern. Do not create a landing page or marketing
screen. The first screen should be the operational queue view.

If the current navigation has an admin/operations area, place it there. If not,
add a restrained admin section entry such as `"SOAR Queue"` visible only to admin
users according to the existing frontend role gating pattern.

---

## 2. Service Methods

Create a focused service module:

```text
frontend/src/services/soarQueueService.js
```

Functions:

```javascript
export const loadSoarQueueStatus = async () => { ... };
export const loadRecentSoarQueueItems = async ({ limit = 50, status } = {}) => { ... };
export const loadSoarQueueItem = async (queueId) => { ... };
```

Endpoints:

- `GET /admin/soar/queue/status`
- `GET /admin/soar/queue/recent?limit=50&status=pending`
- `GET /admin/soar/queue/<id>`

Use existing helpers:

- `buildSiemPath`
- `fetch(..., { credentials: "include" })`
- `parseJsonResponse` / `getApiErrorMessage` where consistent with nearby
  services/components

The service should not transform away nullable values. If backend returns
`alert_id: null`, the UI should receive `null`.

---

## 3. Panel Layout

The panel should be dense and operational, matching the existing admin dashboard
style.

Sections:

1. Status count strip
2. Filter/refresh controls
3. Recent queue table
4. Optional detail drawer/panel for a selected queue item

### Status count strip

Show counts for:

- pending
- running
- success
- failed
- skipped

Each count should be labeled and color-coded consistently with severity/status
patterns already used in the app. Avoid alarm-heavy styling unless count is
actually failed.

### Recent queue table

Columns:

- Queue ID
- Action
- Status
- Source IP
- Alert
- Retries
- Last Error
- Created
- Updated

Render retry count as:

```text
retry_count / max_retries
```

Truncate long `last_error` values with title/tooltip or expandable detail.

### Optional detail view

Clicking a row may load `GET /admin/soar/queue/<id>` and show a read-only detail
panel.

Allowed fields:

- queue ID
- action
- status
- source IP
- alert reference
- retries
- last error
- created/updated timestamps
- `idempotency_key` only if already returned by backend detail endpoint

No action buttons.

---

## 4. Nullable Alert Handling

Queue rows can have `alert_id: null`.

Rendering rules:

- if `alert_reference.label` exists, display it
- else if `alert_id` is a number, display `Alert <id>`
- else display `Deleted alert` or `N/A`

Suggested helper:

```javascript
const formatQueueAlertReference = (item) => {
  if (item?.alert_reference?.label) return item.alert_reference.label;
  if (item?.alert_id !== null && item?.alert_id !== undefined) return `Alert ${item.alert_id}`;
  return "Deleted alert";
};
```

Do not build a link to an alert detail page when `alert_id` is null.

---

## 5. Read-Only Safety

The UI must not include:

- retry button
- replay button
- cancel button
- delete button
- force worker run button
- real firewall execution control
- adapter enable/disable control

The frontend should only call `GET` endpoints from `soarQueueService.js`.

Tests or code review should grep for non-GET calls in the service.

---

## 6. Loading, Error, and Empty States

Loading:

- show existing loading pattern/spinner/text used by admin panels
- keep layout stable while fetching

Error:

- show a concise error state
- preserve existing data if refresh fails after a successful load
- do not expose raw stack traces

Empty:

- if recent queue items array is empty, display a neutral empty state such as
  `"No queued SOAR actions found"`

Unauthorized:

- backend will return `401`/`403`
- frontend should use existing auth/session behavior where possible
- panel should show a normal unable-to-load message if directly reached without
  access

---

## 7. Refresh Behavior

Initial implementation should use manual refresh or existing page-load fetch.

Optional:

- refresh button that re-fetches status and recent items
- conservative polling only if the existing app has a matching pattern

Do not add aggressive polling. Queue visibility is operational context, not a
real-time worker control panel.

---

## 8. Filtering

Status filter is useful but must remain read-only.

Allowed filters:

- all
- pending
- running
- success
- failed
- skipped

Changing filter calls:

```text
GET /admin/soar/queue/recent?status=<status>
```

Invalid statuses should not be sent by UI controls.

---

## 9. Testing Strategy

### Service tests

If the project has frontend service tests, add coverage for:

- `loadSoarQueueStatus()` calls `/admin/soar/queue/status`
- `loadRecentSoarQueueItems()` includes limit/status query params
- `loadSoarQueueItem(id)` calls `/admin/soar/queue/<id>`
- all service calls use `credentials: "include"`
- service does not issue non-GET requests

If the project does not currently have service tests, do not introduce a large
test framework just for this change; rely on build and focused component tests if
available.

### Component tests

If React component tests are already configured, cover:

- loading state
- error state
- empty state
- counts render
- recent queue rows render
- `alert_id: null` renders `"Deleted alert"` or `"N/A"`
- retry count renders as `retry_count / max_retries`
- no execute/retry/cancel buttons are present
- `idempotency_key` is not visible in list view

### Build verification

Run:

```bash
cd frontend && npm run build
```

---

## 10. Backend Contract Assumptions

The UI assumes backend responses follow the SOAR queue visibility API spec:

Status:

```json
{
  "counts": {
    "pending": 0,
    "running": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0
  },
  "total": 0,
  "generated_at": "..."
}
```

Recent:

```json
{
  "items": [],
  "limit": 50,
  "status": null
}
```

Item:

```json
{
  "id": 123,
  "alert_id": null,
  "alert_reference": {
    "status": "deleted_or_missing",
    "label": "Deleted alert"
  },
  "source_ip": "203.0.113.10",
  "action": "block_ip",
  "status": "pending",
  "retry_count": 0,
  "max_retries": 3,
  "last_error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

If backend detail endpoint is not implemented yet, defer detail UI rather than
changing backend during this UI phase.

---

## 11. Stop Conditions

Stop and re-plan if implementation requires:

- backend endpoint changes beyond small response-shape compatibility fixes
- queue mutation endpoints
- worker execution controls
- frontend role/auth redesign
- playbook/incident UI
- real firewall adapter UI
- schema changes

