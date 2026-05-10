# Tasks: SOAR Playbook Metrics Frontend

Implement later in small read-only visibility steps. Do not implement as part of this
spec-only change.

## Step 1: Confirm Existing API Shape

Before writing any frontend code, verify the backend endpoint is working as expected.

- [ ] Inspect `routes/metrics_routes.py` or call `GET /metrics/playbooks` directly.
- [ ] Confirm response includes `total_executions` as an integer.
- [ ] Confirm `by_status` includes all six keys: `pending`, `running`,
      `awaiting_approval`, `success`, `failed`, `abandoned`.
- [ ] Confirm `by_playbook_id` is an array; confirm each entry includes `playbook_id`,
      `total`, and `by_status`.
- [ ] Confirm `recent` includes `window_hours`, `success`, `failed`, and `time_basis`.
- [ ] Confirm `approval_gated` includes `awaiting_approval` and `with_linked_approval`.
- [ ] Confirm unauthenticated requests return existing unauthorized response shape.
- [ ] Confirm analyst and super-admin tokens return HTTP 200.

If any required field is missing, stop and open a new spec to address the backend gap.
Do not add backend changes as part of this change.

## Step 2: Add Service Helper

File:

```text
frontend/src/services/metricsService.js
```

- [ ] Export `getPlaybookMetrics()` using the same fetch wrapper and auth header
      pattern as `playbookService.js`, `approvalService.js`, `soarQueueService.js`,
      and `integrationService.js`.
- [ ] Call `GET /metrics/playbooks`.
- [ ] Return parsed JSON on success.
- [ ] Throw on non-OK status.
- [ ] Do not add polling, retry, or background refresh.
- [ ] Do not call any other endpoint.

## Step 3: Add Service Tests

File:

```text
frontend/src/services/metricsService.test.js
```

- [ ] Test `getPlaybookMetrics()` calls `GET /metrics/playbooks`.
- [ ] Test `getPlaybookMetrics()` returns parsed JSON on a mocked success response.
- [ ] Test `getPlaybookMetrics()` throws on a mocked non-OK response.

Verification:

```bash
npm test -- --watchAll=false frontend/src/services/metricsService.test.js
```

## Step 4: Add PlaybookMetricsPanel Component

File:

```text
frontend/src/components/PlaybookMetricsPanel.js
```

- [ ] Call `getPlaybookMetrics()` on mount via `useEffect`.
- [ ] Render a loading state while the request is in flight.
- [ ] Render a user-friendly error message on API failure.
- [ ] Render an empty state when `total_executions` is `0` and all status counts
      are `0`.
- [ ] Include a persistent simulation-only notice (never conditionally hidden).

### Summary section

- [ ] Render `total_executions` labeled "Total Executions".

### Status breakdown section

- [ ] Render all six known statuses from `by_status`, including those with count `0`.
- [ ] Render an "Other / Unknown" row if `unknown_statuses` is present and non-empty.
- [ ] Do not render the "Other / Unknown" row if `unknown_statuses` is absent or empty.

### Recent activity section

- [ ] Render recent 24-hour success count labeled to indicate the window.
- [ ] Render recent 24-hour failed count labeled to indicate the window.
- [ ] Label the section with the `window_hours` value, not a hardcoded string.

### Approval-gated section

- [ ] Render `approval_gated.awaiting_approval` labeled "Currently awaiting approval".
- [ ] Render `approval_gated.with_linked_approval` labeled "Ever had a linked approval".

### Per-playbook breakdown section

- [ ] Render one row or card per entry in `by_playbook_id` in received order.
- [ ] Each entry shows playbook ID, total, and the six known status counts.
- [ ] If `other_status_count` is present and greater than `0`, render it labeled "Other".
- [ ] If `other_status_count` is absent or `0`, render nothing for that label.
- [ ] Render "No playbook-level data available." when `by_playbook_id` is empty or
      missing without hiding summary, status breakdown, or recent sections.

### Safety

- [ ] Do not render run, retry, cancel, abandon, approve, deny, or any mutation controls.
- [ ] Access all response fields defensively (guard against null/undefined at every level).

## Step 5: Add Component Tests

File:

```text
frontend/src/components/PlaybookMetricsPanel.test.js
```

- [ ] Test loading state renders while request is in flight.
- [ ] Test error state renders on mocked API failure.
- [ ] Test empty state renders when `total_executions` is `0` and all counts are `0`.
- [ ] Test `total_executions` is visible in the populated state.
- [ ] Test all six known `by_status` keys are rendered, including those at `0`.
- [ ] Test recent 24-hour success and failure counts are visible with window labeled.
- [ ] Test `approval_gated.awaiting_approval` is visible.
- [ ] Test `approval_gated.with_linked_approval` is visible.
- [ ] Test per-playbook entry renders `playbook_id` and `total`.
- [ ] Test simulation-only notice is always visible in the populated state.
- [ ] Test no run, retry, cancel, approve, or mutation controls are rendered.
- [ ] Test component does not crash when `by_playbook_id` is missing or null.
- [ ] Test component does not crash when `recent` is missing or null.
- [ ] Test component does not crash when `approval_gated` is missing or null.
- [ ] Test `other_status_count` present renders an "Other" label on the per-playbook entry.
- [ ] Test absent `other_status_count` renders no such label.
- [ ] Test `unknown_statuses` present in response renders "Other / Unknown" row.
- [ ] Test absent `unknown_statuses` renders no such row.

Verification:

```bash
npm test -- --watchAll=false frontend/src/components/PlaybookMetricsPanel.test.js
```

## Step 6: Register Panel in App.js

File:

```text
frontend/src/App.js
```

- [ ] Add `import PlaybookMetricsPanel from './components/PlaybookMetricsPanel'`.
- [ ] Add the panel entry to the panel list following the same pattern used by
      `PlaybooksPanel`, `SoarQueuePanel`, `ApprovalsPanel`, `IncidentsPanel`, and
      `IntegrationStatusPanel`.
- [ ] Do not restructure layout, routing, or any other panel.
- [ ] Do not remove or reorder existing panels.

## Step 7: Run Nearby Regression Tests

Run the full suite of related panel tests to confirm no regressions:

```bash
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
npm test -- --watchAll=false frontend/src/components/SoarQueuePanel.test.js
npm test -- --watchAll=false frontend/src/components/ApprovalsPanel.test.js
npm test -- --watchAll=false frontend/src/components/IncidentsPanel.test.js
npm test -- --watchAll=false frontend/src/components/IntegrationStatusPanel.test.js
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
npm test -- --watchAll=false frontend/src/services/approvalService.test.js
npm test -- --watchAll=false frontend/src/services/soarQueueService.test.js
npm test -- --watchAll=false frontend/src/services/integrationService.test.js
```

Run build:

```bash
npm run build
```

## Step 8: Run Backend Non-Regression Tests

Confirm no backend files changed and existing backend tests pass:

```bash
git status --short
python3 -m py_compile routes/metrics_routes.py
python3 -m pytest tests/test_playbook_routes.py tests/test_playbook_step_executor.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_integration_routes.py tests/test_integration_adapters.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```

Expected: no backend files in `git status --short`. All backend tests pass.

## Stop and Rollback Conditions

- [ ] Stop if the service helper requires backend changes to work.
- [ ] Stop if `App.js` integration requires layout or routing restructuring.
- [ ] Stop if any mutation control is introduced anywhere in the panel.
- [ ] Stop if the simulation-only notice cannot be made persistently visible.
- [ ] Stop if `PlaybookMetricsPanel` calls any endpoint other than
      `GET /metrics/playbooks`.
- [ ] Stop if backend files appear in `git status --short` after implementation.
- [ ] Roll back `PlaybookMetricsPanel` if its component tests fail.
- [ ] Roll back `App.js` change if nearby panel regression tests fail.
- [ ] Roll back service helper if service tests fail.
