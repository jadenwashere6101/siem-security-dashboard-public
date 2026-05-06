# Tasks: Improve SOAR Queue UI Filtering and Page Size

Implement later as a frontend-only usability improvement.

---

## Task 1 — Inspect current queue filter behavior

Inspect:

- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/services/soarQueueService.js`
- `frontend/src/components/SoarQueuePanel.test.js`
- `frontend/src/services/soarQueueService.test.js`

Confirm:

- current status filter state and options
- current default recent limit
- whether `loadRecentSoarQueueItems({ limit, status })` already passes query
  params correctly
- how selected detail state behaves on list refresh

---

## Task 2 — Add or normalize status filter options

Ensure the status filter supports exactly:

- all
- pending
- running
- success
- failed
- skipped

Requirements:

- default to `all`
- invalid values are not selectable
- selecting a status refreshes recent queue rows
- status counts remain unfiltered

---

## Task 3 — Add limit/page-size selector

Add a compact selector for:

- 10
- 25
- 50
- 100

Requirements:

- default to current behavior, preferably 50
- pass selected limit to `loadRecentSoarQueueItems`
- refresh recent rows when changed
- preserve manual refresh behavior
- preserve worker-run refresh behavior

---

## Task 4 — Preserve selected detail safely

Confirm or implement behavior:

- selected detail remains visible when filter changes
- selected detail remains visible when limit changes
- close action still clears selected detail
- selecting another row replaces detail
- no detail mutation controls are introduced

Do not automatically refetch detail on every filter/limit change unless the
current implementation has a simple and safe path.

---

## Task 5 — Improve empty filtered state if needed

When the filtered recent list is empty, render a normal empty state.

Acceptable copy:

```text
No queued SOAR actions found for this filter.
```

or the current generic empty copy if it remains clear.

Do not hide status counts when filtered rows are empty.

---

## Task 6 — Update component tests

Add or adjust `SoarQueuePanel` component tests for:

- default load includes default limit
- status filter change calls recent loader with selected status
- `all` filter behavior matches service convention
- limit change calls recent loader with selected limit
- manual refresh preserves selected filter/limit
- successful worker run refresh preserves selected filter/limit
- empty filtered results render cleanly
- selected detail remains visible after filter/limit changes
- no `idempotency_key` in list view
- no retry/replay/cancel controls

Use mocked frontend services only.

---

## Verification

Run:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/SoarQueuePanel.test.js
```

Run:

```bash
cd frontend
npm run build
```

If service behavior changes, also run:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/services/soarQueueService.test.js
```

---

## Explicit Non-Tasks

Do not:

- add retry/replay/cancel controls
- change worker execution behavior
- add backend mutation endpoints
- add real firewall controls
- touch ingest/detection/correlation
- change schema
- change backend endpoints unless absolutely required
- commit anything
