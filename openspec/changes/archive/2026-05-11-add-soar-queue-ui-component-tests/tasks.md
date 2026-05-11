# Tasks: SOAR Queue UI Component Tests

Implement later as test-only frontend coverage.

---

## Completion Checklist

- [x] Task 1 — Inspect component and current test setup
- [x] Task 2 — Add component test file and mocks
- [x] Task 3 — Cover initial queue states
- [x] Task 4 — Cover nullable alert rendering
- [x] Task 5 — Cover detail flow
- [x] Task 6 — Cover simulation run control
- [x] Task 7 — Assert mutation controls are absent

---

## Task 1 — Inspect component and current test setup

Inspect:

- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/services/soarQueueService.js`
- `frontend/src/App.test.js`
- `frontend/src/services/soarQueueService.test.js`
- `frontend/package.json`

Confirm:

- component prop requirements
- current user-visible loading/error/empty text
- row detail trigger label
- run simulation button label
- existing Jest/React Testing Library conventions

---

## Task 2 — Add component test file and mocks

Create:

```text
frontend/src/components/SoarQueuePanel.test.js
```

Mock:

- `loadSoarQueueStatus`
- `loadRecentSoarQueueItems`
- `loadSoarQueueItem`
- `runSoarWorkerOnce`

Add a small `renderPanel()` helper that supplies required style props.

---

## Task 3 — Cover initial queue states

Add tests for:

- loading state while initial requests are pending
- error state when initial load rejects
- empty queue state when recent items are empty
- status counts rendering
- recent queue rows rendering

Use realistic but small status/recent fixtures.

---

## Task 4 — Cover nullable alert rendering

Add a test where a recent queue row has:

```javascript
alert_id: null
```

Assert the UI renders `"Deleted alert"` or the implementation-approved `"N/A"`
fallback.

---

## Task 5 — Cover detail flow

Add tests for:

- clicking/viewing a row calls `loadSoarQueueItem(queueId)`
- detail loading state
- detail success state
- detail error state
- `idempotency_key` appears after detail load
- `idempotency_key` is absent from the list before detail load

Keep the detail view read-only in assertions.

---

## Task 6 — Cover simulation run control

Add tests for:

- clicking `Run simulation batch` calls `runSoarWorkerOnce`
- request uses the current batch size
- button is disabled while run promise is pending
- successful run summary renders
- queue status/recent fetches are called again after success

Do not test backend worker behavior in frontend component tests.

---

## Task 7 — Assert mutation controls are absent

Add negative assertions for buttons or controls named:

- Retry
- Replay
- Cancel

Also confirm there is no real-mode toggle if there is a stable way to query it.

Do not make brittle assertions against unrelated prose.

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

If shared service mocks or helpers change, also run:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/services/soarQueueService.test.js
```

---

## Explicit Non-Tasks

Do not:

- change production behavior
- change backend endpoints
- change schema
- touch ingest/detection/correlation
- add real execution behavior
- rewrite the frontend test framework
- add end-to-end/browser automation
- commit anything
