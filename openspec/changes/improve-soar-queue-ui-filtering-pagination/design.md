# Design: Improve SOAR Queue UI Filtering and Page Size

---

## 1. UI Placement

Extend the existing controls area in:

```text
frontend/src/components/SoarQueuePanel.js
```

The controls should remain compact and operational:

- Status selector
- Page size selector
- Manual simulation batch control
- Refresh button

The page-size selector should sit near the status filter because both affect the
recent queue list query.

---

## 2. Status Filter

Supported values:

```javascript
const QUEUE_STATUS_FILTERS = [
  "all",
  "pending",
  "running",
  "success",
  "failed",
  "skipped",
];
```

UI labels:

- All
- Pending
- Running
- Success
- Failed
- Skipped

Behavior:

- default to `all`
- changing the filter refreshes recent queue rows
- `all` should omit the `status` query param if the service already follows that
  convention
- invalid statuses should not be possible through the UI

The status count strip should continue showing all statuses, regardless of the
selected recent-list filter.

---

## 3. Limit / Page Size Selector

Supported values:

```javascript
const QUEUE_RECENT_LIMITS = [10, 25, 50, 100];
```

UI label:

```text
Rows
```

Behavior:

- default to the current project default, preferably `50` if already used
- changing the limit refreshes recent queue rows
- selected value is passed to `loadRecentSoarQueueItems({ limit, status })`
- backend remains responsible for final validation/clamping

This is limit-based page sizing, not full pagination. Do not add next/previous
page controls unless the backend grows cursor/offset support in a separate
change.

---

## 4. Data Loading Flow

Current queue visibility load likely fetches:

```javascript
Promise.all([
  loadSoarQueueStatus(),
  loadRecentSoarQueueItems({ limit: 50, status: statusFilter }),
]);
```

Update it to use state:

```javascript
loadRecentSoarQueueItems({
  limit: recentLimit,
  status: statusFilter,
});
```

Dependency rules:

- the load callback depends on `statusFilter` and `recentLimit`
- `useEffect` should reload when either changes
- manual refresh should preserve current filter and limit
- worker-run refresh should preserve current filter and limit

Avoid adding polling or background refresh loops.

---

## 5. Selected Detail Preservation

Changing filter or limit can cause the selected row to disappear from the recent
list. Detail handling should remain predictable.

Recommended behavior:

- keep the selected detail panel open when filter/limit changes
- do not clear selected detail just because the item is no longer visible
- if the selected item is still visible, optionally keep its row highlighted
- if the admin selects another row, replace the detail with the new selection
- close button still clears selected detail

Rationale:

Admins may filter the table while preserving context about an item they are
investigating.

Do not refetch detail automatically on every list filter change unless the
implementation already has a clean detail refresh path.

---

## 6. Empty Filtered Results

If the recent endpoint returns no items for the selected filter, show a neutral
empty state.

Suggested copy:

```text
No queued SOAR actions found for this filter.
```

If implementation prefers the existing generic empty state, that is acceptable
as long as it is not misleading and does not look like an error.

Counts should remain visible so admins can see whether there are queue items in
other statuses.

---

## 7. Service Behavior

The existing service method should already support:

```javascript
loadRecentSoarQueueItems({ limit, status })
```

Expected URL behavior:

- `limit=10`, `limit=25`, `limit=50`, or `limit=100`
- omit `status` for `all`
- include `status=<status>` for specific filters

No new backend endpoint should be needed.

If the service does not currently pass these params correctly, patch only the
frontend service method. Do not change backend contracts unless absolutely
required.

---

## 8. Read-Only Safety

This change must not add:

- retry button
- replay button
- cancel button
- delete button
- selected-row worker execution
- real firewall execution controls
- adapter controls
- schema changes
- backend mutation calls

The only endpoint affected by filter/limit changes should be:

```text
GET /admin/soar/queue/recent
```

Manual refresh may also call the existing status endpoint:

```text
GET /admin/soar/queue/status
```

The existing simulation run button may remain unchanged, but filtering work
should not alter its behavior.

---

## 9. Component Test Strategy

Update or add `SoarQueuePanel` component tests to cover:

- default load uses status `all` and default limit
- selecting `failed` calls `loadRecentSoarQueueItems` with `status: "failed"`
- selecting `all` omits or passes `all` according to current service/component
  convention
- selecting limit `10`, `25`, `50`, or `100` refreshes recent rows with that
  limit
- manual refresh preserves current filter and limit
- successful worker run refresh preserves current filter and limit
- empty filtered results render a safe empty state
- selected detail remains visible after filter/limit change
- no `idempotency_key` appears in list view
- no retry/replay/cancel controls appear

Use mocked service functions. Do not call real backend endpoints.

---

## 10. Verification

Run focused component tests:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/SoarQueuePanel.test.js
```

Run build:

```bash
cd frontend
npm run build
```

If the service test is adjusted, also run:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/services/soarQueueService.test.js
```
