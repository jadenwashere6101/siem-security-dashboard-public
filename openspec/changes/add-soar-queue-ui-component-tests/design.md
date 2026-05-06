# Design: SOAR Queue UI Component Tests

---

## 1. Test File

Add a focused component test file:

```text
frontend/src/components/SoarQueuePanel.test.js
```

Use the existing frontend test stack:

- Jest
- React Testing Library
- `@testing-library/jest-dom`

Do not introduce new test libraries or configuration unless the existing setup
cannot render the component at all.

---

## 2. Service Mocking

Mock the SOAR queue service module:

```javascript
jest.mock("../services/soarQueueService", () => ({
  loadSoarQueueStatus: jest.fn(),
  loadRecentSoarQueueItems: jest.fn(),
  loadSoarQueueItem: jest.fn(),
  runSoarWorkerOnce: jest.fn(),
}));
```

Tests should import the mocked functions and control each async state by
resolving or rejecting promises.

This keeps tests frontend-only and avoids real API calls.

---

## 3. Render Helper

Create a small render helper that passes the style props required by
`SoarQueuePanel`.

Example shape:

```javascript
const renderPanel = () =>
  render(
    <SoarQueuePanel
      cardStyle={{}}
      cardHeaderStyle={{}}
      cardTitleStyle={{}}
      cardSubtitleStyle={{}}
      filterLabelStyle={{}}
      selectStyle={{}}
    />
  );
```

If the component accepts additional props by implementation time, keep the helper
minimal and aligned with the actual prop contract.

---

## 4. Baseline Data Fixtures

Use explicit fixtures for readability:

```javascript
const statusResponse = {
  counts: {
    pending: 2,
    running: 1,
    success: 3,
    failed: 1,
    skipped: 4,
  },
  total: 11,
};
```

Recent row fixture:

```javascript
{
  id: 101,
  alert_id: null,
  alert_reference: null,
  action: "block_ip",
  status: "pending",
  source_ip: "8.8.8.8",
  retry_count: 1,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-06T12:00:00Z",
  updated_at: "2026-05-06T12:01:00Z"
}
```

Detail fixture should include:

```javascript
idempotency_key: "queue-idempotency-key-101"
```

The list fixture should intentionally include no `idempotency_key` field so the
list-view assertion remains meaningful.

---

## 5. State Coverage

### Loading state

Make the status/recent promises stay pending and assert:

```text
Loading SOAR queue...
```

### Error state

Reject either status or recent load and assert a safe error message.

### Empty state

Resolve status counts and `items: []`, then assert:

```text
No queued SOAR actions found.
```

### Counts and rows

Resolve status and recent rows, then assert:

- status labels render
- count values render
- queue row action/status/source IP render
- retry text renders as `retry_count / max_retries`

Use role/text queries where practical.

---

## 6. Nullable Alert Coverage

For a recent item with:

```javascript
alert_id: null
```

Assert the UI displays:

```text
Deleted alert
```

or the actual project-approved fallback if implementation uses `"N/A"`.

This test guards the nullable `response_actions_log.alert_id` and queue alert
reference handling expectations that appear throughout the SOAR UI.

---

## 7. Detail Flow Coverage

Use the row `View` affordance or equivalent detail trigger.

Tests should cover:

- clicking `View` calls `loadSoarQueueItem(101)`
- detail loading state appears while the promise is pending
- detail success renders queue id, alert reference, action, status, source IP,
  retries, timestamps, and `idempotency_key`
- detail error renders a concise error if the detail request rejects

For `idempotency_key`:

- before clicking `View`, assert it is not present
- after detail success, assert it is present

This proves list view does not expose `idempotency_key` while detail can.

---

## 8. Run Simulation Coverage

Mock `runSoarWorkerOnce` with a pending promise and assert:

- clicking `Run simulation batch` calls the service with the current batch size
- button becomes disabled while the promise is pending
- button text or loading state reflects in-flight execution

Then resolve the promise and assert:

- summary values render
- `loadSoarQueueStatus` is called again
- `loadRecentSoarQueueItems` is called again

Do not assert backend mutation details. The component only owns the UI call,
disabled state, summary rendering, and refresh orchestration.

---

## 9. Mutation Safety Assertions

Because this is a read-heavy operational panel, include negative assertions where
stable:

- no `Retry` button
- no `Replay` button
- no `Cancel` button
- no real-mode toggle

Avoid overly brittle text assertions if unrelated page copy may include those
words in documentation. Prefer querying buttons by accessible name.

---

## 10. Test Robustness

Guidelines:

- reset mocks in `beforeEach`
- use `findBy*` for async success states
- use `waitFor` for call-count refresh assertions
- avoid snapshots for this component
- avoid testing inline style details except disabled state where relevant
- keep fixtures small and local to the test file

If current component markup lacks accessible labels needed for reliable tests,
implementation may add tiny accessibility attributes or button labels, but must
not change behavior.

---

## 11. Verification

Run the focused frontend test:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/SoarQueuePanel.test.js
```

Run the build:

```bash
cd frontend
npm run build
```

Optionally run the existing SOAR service test:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/services/soarQueueService.test.js
```
